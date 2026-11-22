"""Stick control: /api/control/rc, /api/ws/rc and the dead-man watchdog."""
import asyncio

import pytest
import pytest_asyncio

from app.config import settings
from app.services.drone_manager import DroneManager, DroneNotFlyingError


@pytest_asyncio.fixture
async def flying_dm():
    dm = DroneManager()
    await dm.connect()
    await dm.takeoff()
    calls: list[tuple] = []
    real = dm.tello.send_rc_control

    def spy(*a):
        calls.append(a)
        real(*a)

    dm.tello.send_rc_control = spy
    dm.rc_calls = calls  # type: ignore[attr-defined]
    yield dm
    await dm.shutdown()


@pytest.mark.asyncio
async def test_rc_requires_flying():
    dm = DroneManager()
    await dm.connect()
    with pytest.raises(DroneNotFlyingError):
        await dm.send_rc(0, 50, 0, 0)
    await dm.shutdown()


@pytest.mark.asyncio
async def test_rc_sends_and_applies_speed_cap(flying_dm, monkeypatch):
    monkeypatch.setattr(settings, "rc_speed_limit_pct", 50)
    assert await flying_dm.send_rc(100, -100, 40, 0) is True
    assert flying_dm.rc_calls[-1] == (50, -50, 20, 0)
    assert flying_dm.rc_moving


@pytest.mark.asyncio
async def test_rc_dropped_while_a_command_runs(flying_dm):
    async with flying_dm._lock:
        assert await flying_dm.send_rc(0, 50, 0, 0) is False
    assert flying_dm.rc_calls == []


@pytest.mark.asyncio
async def test_watchdog_hovers_when_input_stops(flying_dm, monkeypatch):
    monkeypatch.setattr(settings, "rc_timeout_s", 0.15)
    await flying_dm.send_rc(0, 60, 0, 0)
    await asyncio.sleep(0.5)
    assert flying_dm.rc_calls[-1] == (0, 0, 0, 0)
    assert not flying_dm.rc_moving


@pytest.mark.asyncio
async def test_steady_input_keeps_flying(flying_dm, monkeypatch):
    monkeypatch.setattr(settings, "rc_timeout_s", 0.15)
    for _ in range(6):
        await flying_dm.send_rc(0, 60, 0, 0)
        await asyncio.sleep(0.05)
    assert flying_dm.rc_calls[-1] == (0, 60, 0, 0)
    assert flying_dm.rc_moving


@pytest.mark.asyncio
async def test_discrete_move_zeroes_sticks_first(flying_dm):
    from app.models.commands import MoveDirection

    await flying_dm.send_rc(0, 60, 0, 0)
    await flying_dm.move(MoveDirection.up, 20)
    assert flying_dm.rc_calls[-1] == (0, 0, 0, 0)
    assert not flying_dm.rc_moving


@pytest.mark.asyncio
async def test_land_clears_stick_state(flying_dm):
    await flying_dm.send_rc(30, 0, 0, 0)
    await flying_dm.land()
    assert not flying_dm.rc_moving


def test_http_rc_rejected_on_ground(test_client):
    test_client.post("/api/control/connect")
    r = test_client.post("/api/control/rc", json={"lr": 0, "fb": 40, "ud": 0, "yaw": 0})
    assert r.status_code == 409
    assert r.json()["detail"] == "Take off first"


def test_http_rc_validates_range(test_client):
    r = test_client.post("/api/control/rc", json={"lr": 150})
    assert r.status_code == 422


def test_http_rc_ok_when_flying(test_client):
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    r = test_client.post("/api/control/rc", json={"lr": 0, "fb": 40, "ud": 0, "yaw": 0})
    assert r.status_code == 200, r.text
    test_client.post("/api/control/land")


def test_ws_rc_reports_status_changes_and_zeroes_on_close(test_client):
    dm = test_client.app.state.drone_manager
    test_client.post("/api/control/connect")
    with test_client.websocket_connect("/api/ws/rc") as ws:
        ws.send_json({"lr": 0, "fb": 40, "ud": 0, "yaw": 0})
        assert ws.receive_json() == {"type": "rc_status", "ok": False, "error": "Take off first"}
        test_client.post("/api/control/takeoff")
        ws.send_json({"lr": 0, "fb": 40, "ud": 0, "yaw": 0})
        assert ws.receive_json() == {"type": "rc_status", "ok": True, "error": None}
        ws.send_json({"lr": 0, "fb": 45, "ud": 0, "yaw": 0})  # same answer: no message
        ws.send_json({"lr": 999})
        assert ws.receive_json()["error"] == "Bad stick message"
        ws.send_json({"lr": 0, "fb": 45, "ud": 0, "yaw": 0})
        assert ws.receive_json()["ok"] is True
        assert dm.rc_moving
    # socket closed -> sticks zeroed
    for _ in range(50):
        if not dm.rc_moving:
            break
        import time
        time.sleep(0.01)
    assert not dm.rc_moving
    test_client.post("/api/control/land")


def test_ws_rc_refused_during_sequence(seq_client):
    import time

    from app.config import settings as s

    seq_client.post("/api/control/connect")
    old = s.mock_command_delay_s
    s.mock_command_delay_s = 0.3
    try:
        r = seq_client.post("/api/sequences/run", json={"sequence": {
            "name": "slow", "steps": [{"type": "wait", "seconds": 1.0}]}})
        assert r.status_code == 200, r.text
        time.sleep(0.4)  # auto takeoff done, now hovering
        with seq_client.websocket_connect("/api/ws/rc") as ws:
            ws.send_json({"lr": 0, "fb": 40, "ud": 0, "yaw": 0})
            assert ws.receive_json()["error"] == "A sequence is running"
        seq_client.post("/api/sequences/abort")
    finally:
        s.mock_command_delay_s = old
        for _ in range(100):
            if seq_client.get("/api/sequences/run/status").json()["status"] != "running":
                break
            time.sleep(0.05)
