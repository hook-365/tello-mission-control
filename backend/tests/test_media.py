"""Photos, clips, the gallery API and the camera sequence steps (all in mock mode)."""

import asyncio
import time

import av
import cv2
import numpy as np
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import settings
from app.models.sequences import (
    GlideStep,
    OrbitStep,
    RunState,
    SequenceIn,
    describe_step,
    flight_order_errors,
)
from app.services.drone_manager import DroneManager
from app.services.media import MediaError, MediaNotFoundError, MediaService, frame_to_bgr, is_real_frame
from app.services.sequence_runner import SequenceRunner
from app.services.sequence_store import BUILTIN_SEQUENCES


@pytest_asyncio.fixture
async def dm():
    d = DroneManager()
    await d.connect()
    d.events = []  # type: ignore[attr-defined]

    async def capture(e):
        d.events.append(e)

    d.add_command_log_callback(capture)
    yield d
    await d.shutdown()


@pytest.fixture
def media(dm, tmp_path):
    return MediaService(dm, tmp_path)


def _commands(d):
    return [e["data"]["command"] for e in d.events if e["type"] == "command_log"]


# ------------------------------------------------------------- frames


def test_frame_helpers():
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    rgb[..., 0] = 200  # red
    assert frame_to_bgr(rgb, True)[0, 0, 2] == 200
    assert frame_to_bgr(rgb, False)[0, 0, 0] == 200
    assert not is_real_frame(None)
    assert not is_real_frame(np.zeros((300, 400, 3), dtype=np.uint8))  # djitellopy placeholder
    assert is_real_frame(rgb)


@pytest.mark.asyncio
async def test_mock_camera_moves_with_the_drone(dm):
    await dm.stream_on()
    before = dm.get_frame().copy()
    await dm.takeoff()
    await dm.rotate(__import__("app.models.commands", fromlist=["RotateDirection"]).RotateDirection.cw, 90)
    await asyncio.sleep(0.05)
    assert not np.array_equal(before, dm.get_frame())


# ------------------------------------------------------------- photos & clips


@pytest.mark.asyncio
async def test_photo_starts_camera_and_saves_jpeg_with_right_colours(dm, media, tmp_path):
    assert not dm.is_streaming
    item = await media.take_photo()
    assert dm.is_streaming
    assert item.kind == "photo" and item.name.endswith(".jpg")
    img = cv2.imread(str(tmp_path / item.name))  # BGR
    b, g, r = img[50, 20]
    assert b > r  # the mock sky is blue; a swapped image would be orange
    assert "photo" in _commands(dm)
    assert any(e["type"] == "media" and e["data"]["event"] == "photo" for e in dm.events)


@pytest.mark.asyncio
async def test_photo_needs_connection(tmp_path):
    with pytest.raises(MediaError):
        await MediaService(DroneManager(), tmp_path).take_photo()


@pytest.mark.asyncio
async def test_photo_times_out_without_picture(dm, media, monkeypatch):
    await dm.stream_on()
    monkeypatch.setattr(dm, "get_frame", lambda: np.zeros((300, 400, 3), dtype=np.uint8))
    with pytest.raises(MediaError, match="in time"):
        await media.ensure_camera(timeout=0.3)


@pytest.mark.asyncio
async def test_record_clip_is_playable_h264(dm, media, tmp_path):
    status = await media.start_recording()
    assert status["recording"] and media.is_recording
    assert (await media.start_recording())["name"] == status["name"]  # second start is a no-op
    await asyncio.sleep(1.0)
    item = await media.stop_recording()
    assert item is not None and item.kind == "clip" and item.duration_s >= 0.9
    assert not media.is_recording
    assert not list(tmp_path.glob("*.part"))
    with av.open(str(tmp_path / item.name)) as c:
        stream = c.streams.video[0]
        assert stream.codec_context.name == "h264"
        assert sum(1 for _ in c.decode(stream)) >= 15
    assert await media.stop_recording() is None
    assert _commands(dm)[-1] == "record_stop"


@pytest.mark.asyncio
async def test_recording_stops_itself_at_limit(dm, media, monkeypatch):
    monkeypatch.setattr(settings, "record_max_s", 0.5)
    await media.start_recording()
    await asyncio.sleep(1.0)
    assert not media.is_recording
    item = await media.stop_recording()  # tidies up and keeps the file
    assert item is not None and item.name in [i.name for i in media.list()]


@pytest.mark.asyncio
async def test_list_and_delete_and_unsafe_names(media, tmp_path):
    a = await media.take_photo()
    b = await media.take_photo()
    assert a.name != b.name
    (tmp_path / "notes.txt").write_text("hi")
    names = [i.name for i in media.list()]
    assert set(names) == {a.name, b.name}
    media.delete(a.name)
    assert [i.name for i in media.list()] == [b.name]
    for bad in ["../secret.jpg", "notes.txt", a.name, "photo-x.jpg"]:
        with pytest.raises(MediaNotFoundError):
            media.path_for(bad)


# ------------------------------------------------------------- step models


def test_orbit_segments_turn_toward_subject_and_are_flyable():
    hops = OrbitStep(direction="right", radius_cm=150, degrees=360).segments()
    assert len(hops) == 12
    assert sum(t for _, _, t in hops) == 360
    assert all(r > 0 and abs(r) > 20 for _, r, _ in hops)
    left = OrbitStep(direction="left", radius_cm=50, degrees=31).segments()
    assert len(left) == 1 and left[0][1] < -20 and left[0][2] == 31
    for r in (50, 75, 120, 300):
        for d in (30, 31, 45, 90, 179, 360):
            hops = OrbitStep(direction="right", radius_cm=r, degrees=d).segments()
            assert sum(t for *_, t in hops) == d
            assert all(max(abs(f), abs(s)) > 20 for f, s, _ in hops)


@pytest.mark.parametrize(
    "step",
    [
        {"type": "orbit", "direction": "up"},
        {"type": "orbit", "direction": "right", "radius_cm": 40},
        {"type": "orbit", "direction": "right", "degrees": 361},
        {"type": "glide", "forward_cm": 10, "up_cm": -20},
        {"type": "glide", "forward_cm": 600},
        {"type": "record", "action": "pause"},
    ],
)
def test_bad_camera_steps_rejected(step):
    with pytest.raises(ValidationError):
        SequenceIn(name="x", steps=[step])


def test_camera_step_rules():
    assert describe_step(GlideStep(forward_cm=-200, up_cm=120)) == "Glide back 200, up 120 cm"
    assert "Orbit right 360°" in describe_step(OrbitStep(direction="right"))
    photo_on_ground = [{"type": "photo"}, {"type": "takeoff"}, {"type": "land"}]
    assert SequenceIn(name="x", auto_takeoff_land=False, steps=photo_on_ground).needs_camera
    seq = SequenceIn(name="x", auto_takeoff_land=False, steps=[{"type": "takeoff"}, {"type": "land"}])
    assert not seq.needs_camera
    errors = flight_order_errors([GlideStep(up_cm=50)], auto_takeoff_land=False)
    assert errors and "needs the drone in the air" in errors[0]
    assert BUILTIN_SEQUENCES["builtin-orbit-shot"].needs_camera
    assert BUILTIN_SEQUENCES["builtin-reveal"].needs_camera


# ------------------------------------------------------------- runner


@pytest.mark.asyncio
async def test_runner_orbit_shot_records_a_clip(dm, media):
    runner = SequenceRunner(dm, media)
    seq = BUILTIN_SEQUENCES["builtin-orbit-shot"]
    await runner.start(seq)
    final = await runner.wait()
    assert final.status == RunState.completed, final.message
    cmds = _commands(dm)
    assert cmds[0] == "stream_on"  # camera starts itself before take-off
    assert cmds[1] == "takeoff"
    assert cmds.count("go") == 12 and cmds.count("rotate") == 12
    assert cmds[-1] == "land"
    assert [i.kind for i in media.list()] == ["clip"]
    assert dm.tello._yaw == 0  # a full orbit faces the same way again
    msgs = [e["data"]["message"] for e in dm.events if e["type"] == "sequence_progress"]
    assert any("(12/12)" in m for m in msgs)


@pytest.mark.asyncio
async def test_runner_reveal_glides_back_and_up(dm, media):
    runner = SequenceRunner(dm, media)
    await runner.start(BUILTIN_SEQUENCES["builtin-reveal"])
    final = await runner.wait()
    assert final.status == RunState.completed, final.message
    go = [e["data"]["params"] for e in dm.events if e["type"] == "command_log" and e["data"]["command"] == "go"]
    assert go == [{"forward_cm": -200, "right_cm": 0, "up_cm": 120, "speed_cm_s": 25}]
    assert dm.tello._pos_x == -200
    assert sorted(i.kind for i in media.list()) == ["clip", "photo"]


@pytest.mark.asyncio
async def test_right_means_right_on_the_tello(dm, monkeypatch):
    sent = []
    monkeypatch.setattr(dm.tello, "go_xyz_speed", lambda *a: sent.append(a))
    await dm.takeoff()
    await dm.go(0, 100, 0, 30)
    assert sent[-1] == (0, -100, 0, 30)  # Tello's y axis points left
    monkeypatch.setattr(settings, "go_y_is_left", False)
    await dm.go(0, 100, 0, 30)
    assert sent[-1] == (0, 100, 0, 30)


@pytest.mark.asyncio
async def test_abort_mid_orbit_saves_clip_and_lands(dm, media, monkeypatch):
    monkeypatch.setattr(settings, "mock_command_delay_s", 0.1)
    runner = SequenceRunner(dm, media)
    await runner.start(BUILTIN_SEQUENCES["builtin-orbit-shot"])
    deadline = time.monotonic() + 10
    while _commands(dm).count("go") < 2 and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    runner.abort()
    final = await runner.wait()
    assert final.status == RunState.aborted
    assert "clip saved" in final.message
    assert not dm.is_flying and not media.is_recording
    assert _commands(dm).count("go") < 12
    assert [i.kind for i in media.list()] == ["clip"]


@pytest.mark.asyncio
async def test_failed_step_still_saves_clip(dm, media, monkeypatch):
    def boom(*a):
        raise RuntimeError("motor stall")

    monkeypatch.setattr(dm.tello, "go_xyz_speed", boom)
    runner = SequenceRunner(dm, media)
    await runner.start(BUILTIN_SEQUENCES["builtin-reveal"])
    final = await runner.wait()
    assert final.status == RunState.failed
    assert "motor stall" in final.message and "clip saved" in final.message
    assert not media.is_recording


# ------------------------------------------------------------- API


def test_media_api(seq_client: TestClient):
    c = seq_client
    assert c.post("/api/media/photo").status_code == 409  # not connected
    c.post("/api/control/connect")
    photo = c.post("/api/media/photo").json()
    r = c.get(photo["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert c.post("/api/media/record/start").json()["recording"] is True
    assert c.get("/api/media/record/status").json()["recording"] is True
    time.sleep(0.5)
    clip = c.post("/api/media/record/stop").json()["item"]
    assert clip["kind"] == "clip"
    assert c.get(clip["url"]).headers["content-type"] == "video/mp4"
    listing = c.get("/api/media").json()
    assert {i["name"] for i in listing["items"]} >= {photo["name"], clip["name"]}
    listed_clip = next(i for i in listing["items"] if i["name"] == clip["name"])
    assert listed_clip["duration_s"] and listed_clip["duration_s"] > 0
    assert listing["recording"]["recording"] is False
    assert c.delete(f"/api/media/files/{photo['name']}").status_code == 200
    assert c.get(photo["url"]).status_code == 404
    assert c.get("/api/media/files/..%2Fconfig.py").status_code == 404


def test_snapshot_colours_fixed(seq_client: TestClient):
    seq_client.post("/api/control/connect")
    r = seq_client.post("/api/video/snapshot")
    img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
    b, g, r_ = img[50, 20]
    assert b > r_
