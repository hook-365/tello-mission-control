import asyncio

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.config import settings
from app.models.commands import FlipDirection
from app.services.drone_manager import (
    DroneManager,
    DroneNotConnectedError,
    DroneNotFlyingError,
)


@pytest_asyncio.fixture
async def flying_dm():
    dm = DroneManager()
    await dm.connect()
    await dm.takeoff()
    yield dm
    await dm.shutdown()


@pytest.fixture
def short_rc_timeout(monkeypatch):
    monkeypatch.setattr(settings, "rc_timeout_ms", 80)


# -- DroneManager: RC --


@pytest.mark.asyncio
async def test_rc_requires_connection():
    dm = DroneManager()
    with pytest.raises(DroneNotConnectedError):
        await dm.send_rc(10, 0, 0, 0)


@pytest.mark.asyncio
async def test_rc_requires_flying():
    dm = DroneManager()
    await dm.connect()
    try:
        with pytest.raises(DroneNotFlyingError):
            await dm.send_rc(10, 0, 0, 0)
    finally:
        await dm.shutdown()


@pytest.mark.asyncio
async def test_rc_reaches_drone(flying_dm):
    await flying_dm.send_rc(10, -20, 30, -40)
    assert flying_dm.tello.rc_commands == [(10, -20, 30, -40)]
    assert flying_dm.rc_active is True


@pytest.mark.asyncio
async def test_rc_zero_frame_deactivates(flying_dm):
    await flying_dm.send_rc(50, 0, 0, 0)
    await flying_dm.send_rc(0, 0, 0, 0)
    assert flying_dm.rc_active is False


@pytest.mark.asyncio
async def test_rc_not_blocked_by_command_lock(flying_dm):
    """Stick input must get through while a blocking move holds the lock."""
    async with flying_dm._lock:
        await asyncio.wait_for(flying_dm.send_rc(0, 60, 0, 0), timeout=0.5)
    assert flying_dm.tello.rc_commands[-1] == (0, 60, 0, 0)


@pytest.mark.asyncio
async def test_rc_logs_transitions_not_every_frame(flying_dm):
    entries = []

    async def capture(entry):
        entries.append(entry["data"]["command"])

    flying_dm.add_command_log_callback(capture)
    for _ in range(5):
        await flying_dm.send_rc(0, 40, 0, 0)
    await flying_dm.send_rc(0, 0, 0, 0)
    assert entries == ["rc_start", "rc_stop"]


@pytest.mark.asyncio
async def test_watchdog_hovers_when_input_goes_stale(flying_dm, short_rc_timeout):
    entries = []

    async def capture(entry):
        entries.append(entry["data"]["command"])

    flying_dm.add_command_log_callback(capture)
    await flying_dm.send_rc(0, 70, 0, 0)
    await asyncio.sleep(0.3)

    assert flying_dm.tello.rc_commands[-1] == (0, 0, 0, 0)
    assert flying_dm.rc_active is False
    assert entries == ["rc_start", "rc_timeout"]


@pytest.mark.asyncio
async def test_watchdog_leaves_refreshed_input_alone(flying_dm, short_rc_timeout):
    for _ in range(8):
        await flying_dm.send_rc(0, 70, 0, 0)
        await asyncio.sleep(0.03)
    assert flying_dm.rc_active is True
    assert (0, 0, 0, 0) not in flying_dm.tello.rc_commands


@pytest.mark.asyncio
async def test_land_and_emergency_clear_rc(flying_dm):
    await flying_dm.send_rc(0, 70, 0, 0)
    await flying_dm.land()
    assert flying_dm.rc_active is False

    await flying_dm.takeoff()
    await flying_dm.send_rc(0, 70, 0, 0)
    await flying_dm.emergency()
    assert flying_dm.rc_active is False


@pytest.mark.asyncio
async def test_watchdog_runs_only_while_sticks_are_live(flying_dm, short_rc_timeout):
    assert flying_dm._rc_watchdog is None  # nothing idles after connect/takeoff

    await flying_dm.send_rc(0, 50, 0, 0)
    watchdog = flying_dm._rc_watchdog
    assert watchdog is not None and not watchdog.done()

    await flying_dm.send_rc(0, 0, 0, 0)
    await asyncio.sleep(0.1)
    assert watchdog.done()

    # Live input again gets a fresh watchdog, which still trips.
    await flying_dm.send_rc(0, 50, 0, 0)
    await asyncio.sleep(0.3)
    assert flying_dm.tello.rc_commands[-1] == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_disconnect_stops_watchdog(flying_dm):
    await flying_dm.send_rc(0, 50, 0, 0)
    await flying_dm.disconnect()
    assert flying_dm._rc_watchdog is None


# -- DroneManager: flip --


@pytest.mark.asyncio
async def test_flip_maps_direction_to_sdk_letter(flying_dm):
    for direction, letter in [
        (FlipDirection.forward, "f"),
        (FlipDirection.back, "b"),
        (FlipDirection.left, "l"),
        (FlipDirection.right, "r"),
    ]:
        await flying_dm.flip(direction)
        assert flying_dm.tello.flips[-1] == letter


@pytest.mark.asyncio
async def test_flip_requires_flying():
    dm = DroneManager()
    await dm.connect()
    try:
        with pytest.raises(DroneNotFlyingError):
            await dm.flip(FlipDirection.left)
    finally:
        await dm.shutdown()


# -- HTTP --


def _fly(client: TestClient) -> None:
    client.post("/api/control/connect")
    client.post("/api/control/takeoff")


def test_rc_endpoint(test_client: TestClient):
    _fly(test_client)
    resp = test_client.post("/api/control/rc", json={"lr": 0, "fb": 50, "ud": 0, "yaw": -25})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert test_client.app.state.drone_manager.tello.rc_commands[-1] == (0, 50, 0, -25)


def test_rc_endpoint_defaults_missing_channels_to_zero(test_client: TestClient):
    _fly(test_client)
    resp = test_client.post("/api/control/rc", json={"yaw": 30})
    assert resp.status_code == 200
    assert test_client.app.state.drone_manager.tello.rc_commands[-1] == (0, 0, 0, 30)


def test_rc_endpoint_rejects_out_of_range(test_client: TestClient):
    _fly(test_client)
    resp = test_client.post("/api/control/rc", json={"lr": 101, "fb": 0, "ud": 0, "yaw": 0})
    assert resp.status_code == 422


def test_rc_endpoint_requires_flying(test_client: TestClient):
    test_client.post("/api/control/connect")
    resp = test_client.post("/api/control/rc", json={"fb": 50})
    assert resp.status_code == 409


def test_flip_endpoint(test_client: TestClient):
    _fly(test_client)
    resp = test_client.post("/api/control/flip", json={"direction": "left"})
    assert resp.status_code == 200
    assert test_client.app.state.drone_manager.tello.flips == ["l"]


def test_flip_endpoint_validates_direction(test_client: TestClient):
    _fly(test_client)
    resp = test_client.post("/api/control/flip", json={"direction": "up"})
    assert resp.status_code == 422


def test_flip_endpoint_requires_flying(test_client: TestClient):
    test_client.post("/api/control/connect")
    resp = test_client.post("/api/control/flip", json={"direction": "left"})
    assert resp.status_code == 409


# -- Control WebSocket --


def test_control_ws_forwards_frames_and_zeroes_on_close(test_client: TestClient):
    _fly(test_client)
    dm = test_client.app.state.drone_manager
    with test_client.websocket_connect("/api/ws/control") as ws:
        ws.send_json({"lr": 0, "fb": 80, "ud": 0, "yaw": 0})
        # A rejected frame is answered, which also proves the first was processed.
        ws.send_json({"lr": 999})
        assert ws.receive_json() == {"ok": False, "error": "Invalid RC frame"}
        assert dm.tello.rc_commands[-1] == (0, 80, 0, 0)
        assert dm.rc_active is True

    test_client.get("/api/status")  # let the server finish its disconnect handler
    assert dm.tello.rc_commands[-1] == (0, 0, 0, 0)
    assert dm.rc_active is False


def test_control_ws_reports_not_flying(test_client: TestClient):
    test_client.post("/api/control/connect")
    with test_client.websocket_connect("/api/ws/control") as ws:
        ws.send_json({"fb": 50})
        assert ws.receive_json() == {"ok": False, "error": "Drone is not flying"}
