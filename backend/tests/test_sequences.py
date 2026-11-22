"""Tests for the flight sequencer: models/validation, storage, API and runner."""

import asyncio
import json
import time

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import settings
from app.models.sequences import (
    FlipStep,
    MoveStep,
    RunState,
    SequenceIn,
    describe_step,
)
from app.services.drone_manager import DroneManager
from app.services.sequence_runner import PreflightError, SequenceAlreadyRunningError, SequenceRunner
from app.services.sequence_store import (
    BUILTIN_SEQUENCES,
    BuiltinSequenceError,
    SequenceNotFoundError,
    SequenceStore,
)

SIMPLE = {
    "name": "Hop",
    "steps": [
        {"type": "move", "direction": "up", "distance_cm": 50},
        {"type": "rotate", "direction": "cw", "angle_deg": 360},
    ],
}


# ---------------------------------------------------------------- models


def test_valid_sequence_parses():
    seq = SequenceIn(**SIMPLE)
    assert seq.auto_takeoff_land is True
    assert isinstance(seq.steps[0], MoveStep)
    assert seq.has_flips is False


def test_name_is_trimmed_and_blank_rejected():
    assert SequenceIn(**{**SIMPLE, "name": "  Hop  "}).name == "Hop"
    with pytest.raises(ValidationError):
        SequenceIn(**{**SIMPLE, "name": "   "})


@pytest.mark.parametrize(
    "step",
    [
        {"type": "move", "direction": "up", "distance_cm": 19},
        {"type": "move", "direction": "up", "distance_cm": 501},
        {"type": "move", "direction": "sideways", "distance_cm": 100},
        {"type": "rotate", "direction": "cw", "angle_deg": 0},
        {"type": "rotate", "direction": "cw", "angle_deg": 361},
        {"type": "flip", "direction": "l"},
        {"type": "wait", "seconds": 0.1},
        {"type": "wait", "seconds": 11},
        {"type": "barrel_roll"},
    ],
)
def test_step_parameter_ranges_rejected(step):
    with pytest.raises(ValidationError):
        SequenceIn(name="bad", steps=[step])


def test_empty_and_too_long_sequences_rejected():
    with pytest.raises(ValidationError):
        SequenceIn(name="empty", steps=[])
    with pytest.raises(ValidationError):
        SequenceIn(name="long", steps=[{"type": "wait", "seconds": 1}] * 51)


def test_flight_order_without_auto_takeoff():
    with pytest.raises(ValidationError, match="needs the drone in the air"):
        SequenceIn(name="x", auto_takeoff_land=False, steps=[{"type": "move", "direction": "up", "distance_cm": 50}])
    with pytest.raises(ValidationError, match="ends in the air"):
        SequenceIn(name="x", auto_takeoff_land=False, steps=[{"type": "takeoff"}])
    ok = SequenceIn(
        name="x",
        auto_takeoff_land=False,
        steps=[{"type": "takeoff"}, {"type": "flip", "direction": "left"}, {"type": "land"}],
    )
    assert ok.has_flips


def test_double_takeoff_and_land_on_ground_rejected():
    with pytest.raises(ValidationError, match="already in the air"):
        SequenceIn(name="x", steps=[{"type": "takeoff"}, {"type": "takeoff"}])
    with pytest.raises(ValidationError, match="already on the ground"):
        SequenceIn(name="x", steps=[{"type": "land"}, {"type": "land"}])


def test_describe_step():
    assert describe_step(FlipStep(direction="back")) == "Flip back"
    assert describe_step(MoveStep(direction="forward", distance_cm=100)) == "Forward 100 cm"


def test_builtins_are_valid():
    assert {"builtin-victory-lap", "builtin-square-dance", "builtin-elevator-spin"} <= set(BUILTIN_SEQUENCES)
    assert all(s.builtin for s in BUILTIN_SEQUENCES.values())


# ---------------------------------------------------------------- store


def test_store_crud_roundtrip(tmp_path):
    store = SequenceStore(tmp_path)
    created = store.create(SequenceIn(**SIMPLE))
    assert created.id.startswith("hop-")
    assert (tmp_path / f"{created.id}.json").exists()
    assert store.get(created.id).steps == created.steps

    updated = store.update(created.id, SequenceIn(**{**SIMPLE, "name": "Big hop"}))
    assert updated.name == "Big hop"
    assert updated.created_at == created.created_at

    names = [s.name for s in store.list()]
    assert "Big hop" in names and "Victory lap" in names

    store.delete(created.id)
    with pytest.raises(SequenceNotFoundError):
        store.get(created.id)


def test_store_builtins_read_only(tmp_path):
    store = SequenceStore(tmp_path)
    with pytest.raises(BuiltinSequenceError):
        store.update("builtin-victory-lap", SequenceIn(**SIMPLE))
    with pytest.raises(BuiltinSequenceError):
        store.delete("builtin-victory-lap")


def test_store_rejects_path_traversal(tmp_path):
    store = SequenceStore(tmp_path / "seqs")
    (tmp_path / "secret.json").write_text(json.dumps(SIMPLE))
    with pytest.raises(SequenceNotFoundError):
        store.get("../secret")


def test_store_skips_corrupt_files(tmp_path):
    store = SequenceStore(tmp_path)
    (tmp_path / "broken.json").write_text("{not json")
    (tmp_path / "invalid.json").write_text(json.dumps({"name": "x", "steps": []}))
    assert all(s.builtin for s in store.list())


# ---------------------------------------------------------------- runner (unit)


@pytest_asyncio.fixture
async def connected_dm():
    dm = DroneManager()
    await dm.connect()
    log: list[dict] = []

    async def capture(entry):
        log.append(entry)

    dm.add_command_log_callback(capture)
    dm.events = log  # type: ignore[attr-defined]
    yield dm
    await dm.shutdown()


def _commands(dm) -> list[str]:
    return [e["data"]["command"] for e in dm.events if e["type"] == "command_log"]


def _progress(dm) -> list[dict]:
    return [e["data"] for e in dm.events if e["type"] == "sequence_progress"]


@pytest.mark.asyncio
async def test_runner_completes_with_auto_bookends(connected_dm):
    runner = SequenceRunner(connected_dm)
    seq = SequenceIn(**{**SIMPLE, "steps": SIMPLE["steps"] + [{"type": "flip", "direction": "back"}]})
    started = await runner.start(seq, "hop")
    assert started.status == RunState.running
    assert started.total_steps == 5  # takeoff + 3 + land
    final = await runner.wait()
    assert final.status == RunState.completed
    assert _commands(connected_dm) == ["takeoff", "move", "rotate", "flip", "land"]
    assert not connected_dm.is_flying
    # progress points at the user's step index (None for the auto bookends)
    indexes = [p["step_index"] for p in _progress(connected_dm) if p["status"] == "running" and p["current_step"]]
    assert indexes[0] is None and 0 in indexes and 2 in indexes
    assert _progress(connected_dm)[-1]["status"] == "completed"


@pytest.mark.asyncio
async def test_runner_explicit_takeoff_land(connected_dm):
    runner = SequenceRunner(connected_dm)
    seq = SequenceIn(
        name="manual",
        auto_takeoff_land=False,
        steps=[{"type": "takeoff"}, {"type": "move", "direction": "left", "distance_cm": 30}, {"type": "land"}],
    )
    await runner.start(seq)
    assert (await runner.wait()).status == RunState.completed
    assert _commands(connected_dm) == ["takeoff", "move", "land"]


@pytest.mark.asyncio
async def test_runner_skips_takeoff_if_already_flying(connected_dm):
    await connected_dm.takeoff()
    runner = SequenceRunner(connected_dm)
    await runner.start(SequenceIn(**SIMPLE))
    await runner.wait()
    assert _commands(connected_dm) == ["takeoff", "move", "rotate", "land"]  # only the manual takeoff


@pytest.mark.asyncio
async def test_abort_during_hover_is_immediate_and_lands(connected_dm):
    runner = SequenceRunner(connected_dm)
    seq = SequenceIn(name="long hover", steps=[{"type": "wait", "seconds": 10}, {"type": "move", "direction": "up", "distance_cm": 50}])
    await runner.start(seq)
    await asyncio.sleep(0.1)
    t0 = time.monotonic()
    assert runner.abort("Aborted by user") is True
    final = await runner.wait()
    assert time.monotonic() - t0 < 2
    assert final.status == RunState.aborted
    assert "landed" in final.message
    assert "move" not in _commands(connected_dm)
    assert _commands(connected_dm)[-1] == "land"
    assert not connected_dm.is_flying


@pytest.mark.asyncio
async def test_abort_mid_move_finishes_step_then_lands(connected_dm, monkeypatch):
    monkeypatch.setattr(settings, "mock_command_delay_s", 0.2)
    runner = SequenceRunner(connected_dm)
    await runner.start(SequenceIn(name="square", steps=[{"type": "move", "direction": "forward", "distance_cm": 100}] * 5))
    await asyncio.sleep(0.3)  # takeoff done, first move in flight
    runner.abort()
    final = await runner.wait()
    assert final.status == RunState.aborted
    cmds = _commands(connected_dm)
    assert cmds[-1] == "land"
    assert cmds.count("move") < 5


@pytest.mark.asyncio
async def test_abort_when_idle_returns_false(connected_dm):
    assert SequenceRunner(connected_dm).abort() is False


@pytest.mark.asyncio
async def test_preflight_checks(connected_dm):
    runner = SequenceRunner(connected_dm)
    connected_dm.tello._battery = 25
    with pytest.raises(PreflightError, match="at least 30%"):
        await runner.start(SequenceIn(**SIMPLE))

    connected_dm.tello._battery = 45
    flips = SequenceIn(name="f", steps=[{"type": "flip", "direction": "left"}])
    with pytest.raises(PreflightError, match="flips need"):
        await runner.start(flips)
    await runner.start(SequenceIn(**SIMPLE))  # no flips: fine at 45%
    with pytest.raises(SequenceAlreadyRunningError):
        await runner.start(SequenceIn(**SIMPLE))
    await runner.wait()


@pytest.mark.asyncio
async def test_preflight_requires_connection():
    with pytest.raises(PreflightError, match="not connected"):
        await SequenceRunner(DroneManager()).start(SequenceIn(**SIMPLE))


@pytest.mark.asyncio
async def test_flip_skipped_when_battery_drops(connected_dm):
    runner = SequenceRunner(connected_dm)
    seq = SequenceIn(name="f", steps=[{"type": "wait", "seconds": 0.5}, {"type": "flip", "direction": "left"}])
    await runner.start(seq)
    await asyncio.sleep(0.1)
    connected_dm.tello._battery = 40
    final = await runner.wait()
    assert final.status == RunState.completed
    assert "flip" not in _commands(connected_dm)
    assert any("Skipped flip" in p["message"] for p in _progress(connected_dm))


@pytest.mark.asyncio
async def test_battery_critical_mid_run_lands(connected_dm):
    runner = SequenceRunner(connected_dm)
    seq = SequenceIn(name="f", steps=[{"type": "wait", "seconds": 0.5}, {"type": "move", "direction": "up", "distance_cm": 50}])
    await runner.start(seq)
    await asyncio.sleep(0.1)
    connected_dm.tello._battery = 10
    final = await runner.wait()
    assert final.status == RunState.aborted
    assert "Battery low" in final.message
    assert "move" not in _commands(connected_dm)
    assert not connected_dm.is_flying


@pytest.mark.asyncio
async def test_failed_step_lands_drone(connected_dm, monkeypatch):
    async def broken_rotate(*_args):
        raise RuntimeError("motor stall")

    monkeypatch.setattr(connected_dm, "rotate", broken_rotate)
    runner = SequenceRunner(connected_dm)
    await runner.start(SequenceIn(**SIMPLE))
    final = await runner.wait()
    assert final.status == RunState.failed
    assert "motor stall" in final.message
    assert _commands(connected_dm)[-1] == "land"
    assert not connected_dm.is_flying


# ---------------------------------------------------------------- API


def _wait_until_done(client: TestClient, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get("/api/sequences/run/status").json()
        if status["status"] != "running":
            return status
        time.sleep(0.05)
    raise AssertionError("sequence did not finish in time")


def test_api_list_includes_builtins(seq_client: TestClient):
    resp = seq_client.get("/api/sequences")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert {"Victory lap", "Square dance", "Elevator spin"} <= set(names)


def test_api_crud(seq_client: TestClient):
    resp = seq_client.post("/api/sequences", json=SIMPLE)
    assert resp.status_code == 201
    seq = resp.json()
    assert seq["builtin"] is False

    assert seq_client.get(f"/api/sequences/{seq['id']}").json()["name"] == "Hop"

    resp = seq_client.put(f"/api/sequences/{seq['id']}", json={**SIMPLE, "name": "Hop 2"})
    assert resp.status_code == 200 and resp.json()["name"] == "Hop 2"

    assert seq_client.delete(f"/api/sequences/{seq['id']}").status_code == 204
    assert seq_client.get(f"/api/sequences/{seq['id']}").status_code == 404
    assert seq_client.delete(f"/api/sequences/{seq['id']}").status_code == 404


def test_api_validation_errors(seq_client: TestClient):
    bad = {"name": "x", "steps": [{"type": "move", "direction": "up", "distance_cm": 900}]}
    assert seq_client.post("/api/sequences", json=bad).status_code == 422
    assert seq_client.put("/api/sequences/nope-123", json=SIMPLE).status_code == 404


def test_api_builtins_read_only(seq_client: TestClient):
    assert seq_client.put("/api/sequences/builtin-victory-lap", json=SIMPLE).status_code == 403
    assert seq_client.delete("/api/sequences/builtin-victory-lap").status_code == 403


def test_api_run_requires_connection(seq_client: TestClient):
    resp = seq_client.post("/api/sequences/builtin-square-dance/run")
    assert resp.status_code == 409
    assert "not connected" in json.dumps(resp.json())


def test_api_run_builtin_to_completion(seq_client: TestClient):
    seq_client.post("/api/control/connect")
    resp = seq_client.post("/api/sequences/builtin-square-dance/run")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
    final = _wait_until_done(seq_client)
    assert final["status"] == "completed"
    assert final["sequence_id"] == "builtin-square-dance"
    assert seq_client.get("/api/status").json()["flying"] is False


def test_api_run_unsaved_draft(seq_client: TestClient):
    seq_client.post("/api/control/connect")
    resp = seq_client.post("/api/sequences/run", json={"sequence": SIMPLE})
    assert resp.status_code == 200
    assert _wait_until_done(seq_client)["status"] == "completed"
    assert seq_client.post("/api/sequences/run", json={}).status_code == 422


def test_api_run_low_battery_blocked(seq_client: TestClient):
    seq_client.post("/api/control/connect")
    seq_client.app.state.drone_manager.tello._battery = 40
    resp = seq_client.post("/api/sequences/builtin-victory-lap/run")  # has a flip
    assert resp.status_code == 409
    assert "flips need" in json.dumps(resp.json())


def test_api_abort_lands_and_blocks_manual_commands(seq_client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "mock_command_delay_s", 0.15)
    seq_client.post("/api/control/connect")
    assert seq_client.post("/api/sequences/builtin-square-dance/run").status_code == 200
    time.sleep(0.4)

    # manual flying and a second run are refused while the sequence runs
    assert seq_client.post("/api/control/move", json={"direction": "up", "distance_cm": 50}).status_code == 409
    assert seq_client.post("/api/control/flip", json={"direction": "left"}).status_code == 409
    assert seq_client.post("/api/sequences/builtin-square-dance/run").status_code == 409

    resp = seq_client.post("/api/sequences/abort")
    assert resp.json()["ok"] is True
    final = _wait_until_done(seq_client)
    assert final["status"] == "aborted"
    assert seq_client.get("/api/status").json()["flying"] is False
    assert seq_client.post("/api/sequences/abort").json()["message"] == "No sequence running"


def test_api_land_button_aborts_sequence(seq_client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "mock_command_delay_s", 0.15)
    seq_client.post("/api/control/connect")
    seq_client.post("/api/sequences/builtin-elevator-spin/run")
    time.sleep(0.3)
    assert "Aborting" in seq_client.post("/api/control/land").json()["message"]
    final = _wait_until_done(seq_client)
    assert final["status"] == "aborted" and "Land pressed" in final["message"]


def test_api_manual_flip(seq_client: TestClient):
    seq_client.post("/api/control/connect")
    assert seq_client.post("/api/control/flip", json={"direction": "left"}).status_code == 409  # not flying
    seq_client.post("/api/control/takeoff")
    assert seq_client.post("/api/control/flip", json={"direction": "left"}).json()["ok"] is True
    assert seq_client.post("/api/control/flip", json={"direction": "l"}).status_code == 422


def test_websocket_streams_sequence_progress(seq_client: TestClient):
    seq_client.post("/api/control/connect")
    with seq_client.websocket_connect("/api/ws/telemetry") as ws:
        seq_client.post("/api/sequences/run", json={"sequence": SIMPLE})
        statuses = []
        for _ in range(60):
            msg = json.loads(ws.receive_text())
            if msg["type"] == "sequence_progress":
                statuses.append(msg["data"]["status"])
                if msg["data"]["status"] != "running":
                    break
        assert statuses[0] == "running"
        assert statuses[-1] == "completed"


def test_api_emergency_during_sequence_stops_without_landing_command(seq_client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "mock_command_delay_s", 0.15)
    seq_client.post("/api/control/connect")
    seq_client.post("/api/sequences/builtin-square-dance/run")
    time.sleep(0.3)
    assert seq_client.post("/api/control/emergency").json()["ok"] is True
    final = _wait_until_done(seq_client)
    assert final["status"] in ("aborted", "failed")
    assert "Emergency" in final["message"] or "not flying" in final["message"]
    assert seq_client.get("/api/status").json()["flying"] is False
