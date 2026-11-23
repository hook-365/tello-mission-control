import sqlite3
import time
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.telemetry import TelemetryData, TelemetryFrame
from app.services.flight_recorder import FlightRecorder


def _frame(height: int = 0) -> TelemetryFrame:
    return TelemetryFrame(
        data=TelemetryData(
            battery=80, height=height, flight_time=1,
            temperature={"high": 60.0, "low": 55.0},
            attitude={"pitch": 0, "roll": 0, "yaw": 0},
            speed={"x": 0, "y": 0, "z": 0},
            barometer=0.0, tof_distance=height,
        ),
        timestamp=datetime.now(timezone.utc),
    )


def _cmd(command: str, **params) -> dict:
    return {
        "type": "command_log",
        "data": {
            "command": command, "params": params, "result": "ok", "error": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@pytest_asyncio.fixture
async def recorder(tmp_path):
    rec = FlightRecorder(tmp_path / "nested" / "flights.db")
    await rec.start()
    yield rec
    await rec.stop()


# -- FlightRecorder --


@pytest.mark.asyncio
async def test_creates_missing_directory(recorder, tmp_path):
    assert (tmp_path / "nested" / "flights.db").exists()
    assert await recorder.list_sessions() == []


@pytest.mark.asyncio
async def test_session_spans_connect_to_disconnect(recorder):
    await recorder.on_command(_cmd("connect"))
    await recorder.on_telemetry(_frame(0))
    await recorder.on_command(_cmd("takeoff"))
    await recorder.on_telemetry(_frame(50))
    await recorder.on_command(_cmd("move", direction="forward", distance_cm=100))
    await recorder.on_command(_cmd("disconnect"))

    [summary] = await recorder.list_sessions()
    assert summary["telemetry_frames"] == 2
    assert summary["commands"] == 4
    assert summary["ended_at"] is not None
    assert summary["active"] is False

    detail = await recorder.get_session(summary["id"])
    assert [c["command"] for c in detail["command_log"]] == ["connect", "takeoff", "move", "disconnect"]
    assert detail["command_log"][2]["params"] == {"direction": "forward", "distance_cm": 100}
    assert [t["data"]["height"] for t in detail["telemetry"]] == [0, 50]


@pytest.mark.asyncio
async def test_each_connection_is_its_own_session(recorder):
    for _ in range(2):
        await recorder.on_command(_cmd("connect"))
        await recorder.on_telemetry(_frame())
        await recorder.on_command(_cmd("disconnect"))
    sessions = await recorder.list_sessions()
    assert len(sessions) == 2
    assert sessions[0]["id"] > sessions[1]["id"]  # newest first


@pytest.mark.asyncio
async def test_open_session_is_flagged_active(recorder):
    await recorder.on_command(_cmd("connect"))
    [summary] = await recorder.list_sessions()
    assert summary["active"] is True
    assert summary["ended_at"] is None
    assert recorder.active_session_id == summary["id"]


@pytest.mark.asyncio
async def test_telemetry_without_connect_opens_a_session(recorder):
    await recorder.on_telemetry(_frame())
    assert len(await recorder.list_sessions()) == 1


@pytest.mark.asyncio
async def test_stray_disconnect_creates_nothing(recorder):
    await recorder.on_command(_cmd("disconnect"))
    assert await recorder.list_sessions() == []


@pytest.mark.asyncio
async def test_stop_closes_the_open_session(tmp_path):
    path = tmp_path / "flights.db"
    rec = FlightRecorder(path)
    await rec.start()
    await rec.on_command(_cmd("connect"))
    await rec.stop()

    rows = sqlite3.connect(path).execute("SELECT ended_at FROM sessions").fetchall()
    assert rows[0][0] is not None


@pytest.mark.asyncio
async def test_start_closes_sessions_orphaned_by_a_crash(tmp_path):
    path = tmp_path / "flights.db"
    rec = FlightRecorder(path)
    await rec.start()
    await rec.on_command(_cmd("connect"))
    frame = _frame()
    await rec.on_telemetry(frame)
    rec._db.close()  # simulate a crash: session never ended
    rec._db = None

    rec2 = FlightRecorder(path)
    await rec2.start()
    try:
        [summary] = await rec2.list_sessions()
        assert summary["ended_at"] == frame.timestamp.isoformat()
        assert summary["active"] is False
    finally:
        await rec2.stop()


@pytest.mark.asyncio
async def test_failed_write_does_not_raise(recorder):
    """Broadcasters drop subscribers that raise, which would end recording."""
    await recorder.on_command(_cmd("connect"))
    real_db = recorder._db
    recorder._db = sqlite3.connect(":memory:")  # no tables: every write fails
    await recorder.on_telemetry(_frame())
    await recorder.on_command(_cmd("takeoff"))
    recorder._db = real_db

    await recorder.on_telemetry(_frame())  # recording carries on afterwards
    [summary] = await recorder.list_sessions()
    assert summary["telemetry_frames"] == 1


@pytest.mark.asyncio
async def test_delete_removes_session_and_rows(recorder):
    await recorder.on_command(_cmd("connect"))
    await recorder.on_telemetry(_frame())
    await recorder.on_command(_cmd("disconnect"))
    [summary] = await recorder.list_sessions()

    assert await recorder.delete_session(summary["id"]) is True
    assert await recorder.delete_session(summary["id"]) is False
    assert await recorder.list_sessions() == []
    assert recorder._db.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0] == 0
    assert recorder._db.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 0


# -- HTTP --


def _wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_flight_is_recorded_end_to_end(test_client: TestClient):
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    test_client.post("/api/control/move", json={"direction": "up", "distance_cm": 50})

    # Telemetry polls at 4 Hz in the background.
    assert _wait_for(lambda: test_client.get("/api/flights").json()[0]["telemetry_frames"] >= 2)
    [active] = test_client.get("/api/flights").json()
    assert active["active"] is True
    assert test_client.delete(f"/api/flights/{active['id']}").status_code == 409

    test_client.post("/api/control/land")
    test_client.post("/api/control/disconnect")

    [summary] = test_client.get("/api/flights").json()
    assert summary["active"] is False

    detail = test_client.get(f"/api/flights/{summary['id']}").json()
    assert [c["command"] for c in detail["command_log"]] == [
        "connect", "takeoff", "move", "land", "disconnect",
    ]
    assert max(t["data"]["height"] for t in detail["telemetry"]) == 100

    assert test_client.delete(f"/api/flights/{summary['id']}").status_code == 200
    assert test_client.get("/api/flights").json() == []


def test_unknown_flight_returns_404(test_client: TestClient):
    assert test_client.get("/api/flights/999").status_code == 404
    assert test_client.delete("/api/flights/999").status_code == 404


def test_flights_return_503_when_logging_disabled(monkeypatch):
    monkeypatch.setattr(settings, "flight_log_enabled", False)
    with TestClient(app) as client:
        assert client.get("/api/flights").status_code == 503
        # Flying is unaffected.
        assert client.post("/api/control/connect").status_code == 200


def test_unwritable_log_path_does_not_stop_startup(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    monkeypatch.setattr(settings, "flight_log_path", str(blocker / "flights.db"))
    with TestClient(app) as client:
        assert client.get("/api/flights").status_code == 503
        assert client.post("/api/control/connect").status_code == 200


def test_telemetry_snapshot(test_client: TestClient):
    assert test_client.get("/api/telemetry").status_code == 409
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    data = test_client.get("/api/telemetry").json()
    assert data["battery"] == 85
    assert data["height"] == 50
    assert set(data["attitude"]) == {"pitch", "roll", "yaw"}
