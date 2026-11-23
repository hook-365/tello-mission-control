import asyncio

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.detector import Detection, VisionUnavailableError
from app.services.drone_manager import DroneManager
from app.services.tracking import HOVER, TrackingGains, compute_rc, pick_target
from app.services.vision_service import VisionService


def box(label="person", cx=0.5, cy=0.5, w=0.2, h=0.5, confidence=0.9) -> Detection:
    return Detection(label=label, confidence=confidence, x=cx - w / 2, y=cy - h / 2, w=w, h=h)


class FakeDetector:
    def __init__(self, detections=None):
        self.detections = detections or []
        self.calls = 0
        self.error: Exception | None = None

    def detect(self, frame):
        self.calls += 1
        if self.error:
            raise self.error
        return list(self.detections)


# -- Tracking maths --

GAINS = TrackingGains()


def test_no_target_means_hover():
    assert compute_rc(None, GAINS) == HOVER


def test_centred_target_at_wanted_size_means_hover():
    assert compute_rc(box(cx=0.5, cy=0.5, h=GAINS.target_height), GAINS) == HOVER


def test_small_errors_fall_in_the_deadband():
    assert compute_rc(box(cx=0.52, cy=0.49, h=GAINS.target_height * 0.97), GAINS) == HOVER


def test_target_to_the_right_turns_clockwise():
    lr, fb, ud, yaw = compute_rc(box(cx=0.8, h=GAINS.target_height), GAINS)
    assert yaw > 0 and (lr, fb, ud) == (0, 0, 0)


def test_target_to_the_left_turns_counter_clockwise():
    assert compute_rc(box(cx=0.2, h=GAINS.target_height), GAINS)[3] < 0


def test_target_high_in_frame_climbs():
    assert compute_rc(box(cy=0.2, h=0.3), GAINS)[2] > 0


def test_target_low_in_frame_descends():
    assert compute_rc(box(cy=0.8, h=0.3), GAINS)[2] < 0


def test_far_target_approaches_and_near_target_backs_off():
    assert compute_rc(box(h=0.2), GAINS)[1] > 0
    assert compute_rc(box(h=0.9), GAINS)[1] < 0


def test_never_strafes():
    assert compute_rc(box(cx=0.05, cy=0.9, h=0.1), GAINS)[0] == 0


def test_every_channel_is_capped():
    gains = TrackingGains(yaw=500, ud=500, fb=500, max_speed=25)
    command = compute_rc(box(cx=1.0, cy=0.0, w=0.02, h=0.02), gains)
    assert max(abs(v) for v in command) == 25


def test_pick_target_takes_the_largest_matching_box():
    near, far = box(w=0.4, h=0.8), box(w=0.1, h=0.2)
    assert pick_target([far, box(label="dog", w=0.9, h=0.9), near], "person") is near
    assert pick_target([box(label="dog")], "person") is None
    assert pick_target([], "person") is None


# -- VisionService --


@pytest.fixture
def fast_vision(monkeypatch):
    monkeypatch.setattr(settings, "vision_hz", 50.0)


@pytest_asyncio.fixture
async def rig(fast_vision):
    dm = DroneManager()
    await dm.connect()
    await dm.takeoff()
    await dm.stream_on()
    detector = FakeDetector()
    factory_calls = []

    def factory():
        factory_calls.append(1)
        return detector

    service = VisionService(dm, factory)
    messages = []

    async def capture(message):
        messages.append(message)

    service.subscribe(capture)
    yield dm, service, detector, messages, factory_calls
    await service.stop()
    await dm.shutdown()


async def settle(seconds=0.12):
    await asyncio.sleep(seconds)


@pytest.mark.asyncio
async def test_detector_loads_only_when_first_switched_on(rig):
    dm, service, detector, messages, factory_calls = rig
    assert factory_calls == [] and service.state()["detecting"] is False
    await service.set_detecting(True)
    await service.set_detecting(False)
    await service.set_detecting(True)
    assert factory_calls == [1]


@pytest.mark.asyncio
async def test_broadcasts_detections(rig):
    dm, service, detector, messages, _ = rig
    detector.detections = [box(label="dog", cx=0.3)]
    await service.set_detecting(True)
    await settle()

    last = messages[-1]
    assert last["type"] == "detections"
    assert last["data"]["detecting"] is True and last["data"]["tracking"] is False
    assert last["data"]["stale"] is False
    assert (last["data"]["frame_width"], last["data"]["frame_height"]) == (960, 720)
    [d] = last["data"]["detections"]
    assert d["label"] == "dog" and set(d) == {"label", "confidence", "x", "y", "w", "h"}
    assert "timestamp" in last


@pytest.mark.asyncio
async def test_detection_alone_never_moves_the_drone(rig):
    dm, service, detector, _, _ = rig
    detector.detections = [box(cx=0.9)]
    await service.set_detecting(True)
    await settle()
    assert dm.tello.rc_commands == []


@pytest.mark.asyncio
async def test_switching_off_stops_running_the_detector(rig):
    dm, service, detector, _, _ = rig
    await service.set_detecting(True)
    await settle()
    await service.set_detecting(False)
    calls = detector.calls
    await settle()
    assert detector.calls == calls


@pytest.mark.asyncio
async def test_tracking_steers_towards_the_target(rig):
    dm, service, detector, messages, _ = rig
    detector.detections = [box(cx=0.85, h=GAINS.target_height)]
    await service.set_tracking(True)
    await settle()

    lr, fb, ud, yaw = dm.tello.rc_commands[-1]
    assert yaw > 0 and lr == 0
    assert messages[-1]["data"]["tracking"] is True
    assert messages[-1]["data"]["target"]["label"] == "person"


@pytest.mark.asyncio
async def test_tracking_hovers_when_the_target_is_lost(rig):
    dm, service, detector, _, _ = rig
    detector.detections = [box(cx=0.85)]
    await service.set_tracking(True)
    await settle()
    detector.detections = []
    await settle()
    assert dm.tello.rc_commands[-1] == HOVER
    assert service.state()["tracking"] is True  # still armed, will re-acquire


@pytest.mark.asyncio
async def test_tracking_hovers_when_video_stalls(rig, monkeypatch):
    dm, service, detector, messages, _ = rig
    detector.detections = [box(cx=0.85)]
    frozen = dm.get_frame()
    monkeypatch.setattr(dm, "get_frame", lambda: frozen)  # same frame object forever
    monkeypatch.setattr("app.services.vision_service.STALE_FRAME_S", 0.05)
    await service.set_tracking(True)
    await settle(0.25)

    assert dm.tello.rc_commands[-1] == HOVER
    assert messages[-1]["data"]["stale"] is True
    assert messages[-1]["data"]["detections"] == []


@pytest.mark.asyncio
async def test_tracking_requires_flight(rig):
    dm, service, _, _, _ = rig
    await dm.land()
    with pytest.raises(VisionUnavailableError):
        await service.set_tracking(True)
    assert service.state()["tracking"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("pilot_action", ["stick", "move", "rotate", "flip", "land", "emergency"])
async def test_pilot_input_cancels_tracking_and_tracker_stays_silent(rig, pilot_action):
    from app.models.commands import FlipDirection, MoveDirection, RotateDirection

    dm, service, detector, _, _ = rig
    detector.detections = [box(cx=0.85)]
    await service.set_tracking(True)
    await settle()

    await {
        "stick": lambda: dm.send_rc(0, 40, 0, 0),
        "move": lambda: dm.move(MoveDirection.forward, 50),
        "rotate": lambda: dm.rotate(RotateDirection.cw, 90),
        "flip": lambda: dm.flip(FlipDirection.left),
        "land": lambda: dm.land(),
        "emergency": lambda: dm.emergency(),
    }[pilot_action]()

    assert service.state()["tracking"] is False
    sent = len(dm.tello.rc_commands)
    await settle()
    assert len(dm.tello.rc_commands) == sent  # tracker sent nothing after the override
    if pilot_action == "stick":
        assert dm.tello.rc_commands[-1] == (0, 40, 0, 0)


@pytest.mark.asyncio
async def test_centred_gamepad_does_not_cancel_tracking(rig):
    """A released stick sends one zero frame; that is not a pilot taking over."""
    dm, service, detector, _, _ = rig
    detector.detections = [box(cx=0.85)]
    await service.set_tracking(True)
    await dm.send_rc(0, 0, 0, 0)
    assert service.state()["tracking"] is True


@pytest.mark.asyncio
async def test_stopping_tracking_zeroes_the_sticks(rig):
    dm, service, detector, _, _ = rig
    detector.detections = [box(cx=0.85)]
    await service.set_tracking(True)
    await settle()
    await service.set_tracking(False)
    assert dm.tello.rc_commands[-1] == HOVER
    assert service.state() == {**service.state(), "tracking": False, "detecting": True}


@pytest.mark.asyncio
async def test_detector_failure_stops_tracking_and_hovers(rig):
    dm, service, detector, _, _ = rig
    detector.detections = [box(cx=0.85)]
    await service.set_tracking(True)
    await settle()
    detector.error = RuntimeError("CUDA out of memory")
    await settle()
    assert service.state()["tracking"] is False
    assert dm.tello.rc_commands[-1] == HOVER


@pytest.mark.asyncio
async def test_tracker_stick_changes_stay_out_of_the_command_log(rig):
    dm, service, detector, _, _ = rig
    entries = []

    async def capture(entry):
        entries.append(entry["data"]["command"])

    dm.add_command_log_callback(capture)
    detector.detections = [box(cx=0.85)]
    await service.set_tracking(True)
    await settle()
    detector.detections = []
    await settle()
    assert "rc_start" not in entries and "rc_stop" not in entries


# -- HTTP --


@pytest.fixture
def vision_client(test_client: TestClient, fast_vision):
    detector = FakeDetector([box(cx=0.85)])
    service = VisionService(test_client.app.state.drone_manager, lambda: detector)
    test_client.app.state.vision_service = service
    yield test_client
    test_client.app.state.vision_service = None


def test_vision_is_off_by_default(test_client: TestClient):
    assert test_client.get("/api/vision").json() == {
        "available": False, "detecting": False, "tracking": False,
    }
    assert test_client.post("/api/vision/detect", json={"enabled": True}).status_code == 503
    assert test_client.post("/api/vision/track", json={"enabled": True}).status_code == 503


def test_enabled_without_ultralytics_stays_off_and_app_still_starts(monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", True)
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    with TestClient(app) as client:
        assert client.get("/api/vision").json()["available"] is False
        assert client.post("/api/control/connect").status_code == 200


def test_detect_and_track_endpoints(vision_client: TestClient):
    state = vision_client.post("/api/vision/detect", json={"enabled": True}).json()
    assert state["available"] is True and state["detecting"] is True

    # Tracking needs the drone in the air.
    vision_client.post("/api/control/connect")
    assert vision_client.post("/api/vision/track", json={"enabled": True}).status_code == 409

    vision_client.post("/api/control/takeoff")
    state = vision_client.post("/api/vision/track", json={"enabled": True, "target": "person"}).json()
    assert state["tracking"] is True and state["target"] == "person"

    vision_client.post("/api/control/land")
    assert vision_client.get("/api/vision").json()["tracking"] is False


def test_detector_load_failure_returns_503(test_client: TestClient):
    def broken():
        raise FileNotFoundError("no such model: nope.pt")

    test_client.app.state.vision_service = VisionService(
        test_client.app.state.drone_manager, broken
    )
    resp = test_client.post("/api/vision/detect", json={"enabled": True})
    assert resp.status_code == 503
    assert "nope.pt" in resp.json()["detail"]
    test_client.app.state.vision_service = None


def test_detections_arrive_on_the_telemetry_websocket(vision_client: TestClient):
    vision_client.post("/api/control/connect")
    vision_client.post("/api/video/stream/start")
    with vision_client.websocket_connect("/api/ws/telemetry") as ws:
        vision_client.post("/api/vision/detect", json={"enabled": True})
        for _ in range(50):
            message = ws.receive_json()
            if message["type"] == "detections" and message["data"]["detections"]:
                break
        else:
            pytest.fail("no detections message received")
    assert message["data"]["detections"][0]["label"] == "person"
