"""Tests for the MCP tools against a fake of the backend's REST API.

The real backend pins older FastAPI/pydantic versions than the MCP SDK needs, so
the two cannot share an environment; the fake below mirrors the status codes and
bodies the backend actually returns.
"""

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from server import build_server  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0fakejpeg\xff\xd9"


class FakeBackend:
    def __init__(self) -> None:
        self.connected = False
        self.flying = False
        self.requests: list[tuple[str, str, dict | None]] = []
        self.battery = 85
        self.recording = False
        self.sequence_running = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        self.requests.append((request.method, path, body))

        if path == "/api/control/connect":
            self.connected = True
            return httpx.Response(200, json={"ok": True, "status": "connected", "battery": 85})
        if path == "/api/status":
            return httpx.Response(200, json={
                "connected": self.connected, "flying": self.flying,
                "streaming": False, "battery": 85 if self.connected else 0,
            })
        if path == "/api/control/emergency":
            self.flying = False
            return httpx.Response(200, json={"ok": True, "message": "Emergency stop executed"})
        if path == "/api/flights":
            return httpx.Response(200, json=[{"id": 3, "commands": 2, "telemetry_frames": 40}])
        if path == "/api/flights/3":
            return httpx.Response(200, json={
                "id": 3, "telemetry": [{"timestamp": "t", "data": {}}] * 40,
                "command_log": [{"command": "connect"}, {"command": "takeoff"}],
            })
        if path.startswith("/api/flights/"):
            return httpx.Response(404, json={"detail": "Flight not found"})

        if path == "/api/sequences":
            return httpx.Response(200, json=[{
                "id": "orbit", "name": "Orbit", "description": "Circle a point",
                "builtin": True, "steps": [{"type": "takeoff"}, {"type": "orbit"}, {"type": "land"}],
            }])
        if path == "/api/sequences/run/status":
            return httpx.Response(200, json={
                "status": "running" if self.sequence_running else "idle",
                "sequence_name": "Orbit" if self.sequence_running else None,
                "current_step": 1 if self.sequence_running else 0, "total_steps": 3,
            })
        if path == "/api/sequences/abort":
            was, self.sequence_running = self.sequence_running, False
            return httpx.Response(200, json={
                "ok": True, "message": "Abort requested" if was else "No sequence running",
            })
        if path == "/api/sequences/orbit/run":
            if self.battery < 30:
                return httpx.Response(409, json={"detail": {
                    "message": "Pre-flight check failed",
                    "problems": ["Battery is at 20%, need at least 30%"],
                }})
            self.sequence_running = True
            return httpx.Response(200, json={"status": "running", "sequence_name": "Orbit"})
        if path.startswith("/api/sequences/") and path.endswith("/run"):
            return httpx.Response(404, json={"detail": "Sequence 'nope' not found"})
        if path == "/api/media":
            return httpx.Response(200, json={
                "items": [{"name": "photo-1.jpg", "kind": "photo"}],
                "recording": {"recording": self.recording},
            })
        if path == "/api/media/record/stop":
            was, self.recording = self.recording, False
            return httpx.Response(200, json={
                "item": {"name": "clip-1.mp4", "kind": "video"} if was else None,
            })

        if not self.connected:
            return httpx.Response(409, json={"detail": "Drone is not connected"})
        if path == "/api/media/photo":
            return httpx.Response(200, json={"name": "photo-1.jpg", "kind": "photo"})
        if path == "/api/media/record/start":
            self.recording = True
            return httpx.Response(200, json={"recording": True, "name": "clip-1.mp4"})
        if path == "/api/control/takeoff":
            self.flying = True
            return httpx.Response(200, json={"ok": True, "message": "Takeoff successful"})
        if path == "/api/control/land":
            self.flying = False
            return httpx.Response(200, json={"ok": True, "message": "Landing successful"})
        if path == "/api/control/disconnect":
            self.connected = self.flying = False
            return httpx.Response(200, json={"ok": True, "message": ""})
        if path == "/api/telemetry":
            return httpx.Response(200, json={"battery": 85, "height": 50 if self.flying else 0})
        if path == "/api/video/snapshot":
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        if path in ("/api/control/move", "/api/control/rotate", "/api/control/flip"):
            if not self.flying:
                return httpx.Response(409, json={"detail": "Drone is not flying"})
            if path.endswith("move") and not 20 <= body["distance_cm"] <= 500:
                return httpx.Response(422, json={"detail": [{"msg": "distance out of range"}]})
            return httpx.Response(200, json={"ok": True, "message": "done"})
        return httpx.Response(404, json={"detail": "Not Found"})


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def server(backend):
    client = httpx.AsyncClient(transport=httpx.MockTransport(backend), base_url="http://tello")
    return build_server(client=client)


async def call(server, name, **arguments):
    result = await server.call_tool(name, arguments)
    assert not result.is_error
    return result


async def call_json(server, name, **arguments):
    """Call a tool and decode its JSON text content (what an MCP client reads)."""
    result = await call(server, name, **arguments)
    decoded = [json.loads(block.text) for block in result.content]
    return decoded[0] if len(decoded) == 1 else decoded


@pytest.mark.asyncio
async def test_exposes_the_expected_tools(server):
    names = {t.name for t in await server.list_tools()}
    assert names == {
        "connect", "disconnect", "takeoff", "land", "emergency_stop", "move", "rotate",
        "flip", "get_status", "get_telemetry", "take_snapshot", "list_flights",
        "get_flight_commands", "take_photo", "start_recording", "stop_recording",
        "list_media", "list_sequences", "run_sequence", "get_sequence_status",
        "abort_sequence",
    }


@pytest.mark.asyncio
async def test_no_raw_stick_tool(server):
    """Continuous RC needs sub-second refresh, which a model's turn cannot give."""
    names = {t.name for t in await server.list_tools()}
    assert not any("rc" in n for n in names)


@pytest.mark.asyncio
async def test_move_schema_constrains_direction(server):
    move = next(t for t in await server.list_tools() if t.name == "move")
    assert set(move.input_schema["properties"]["direction"]["enum"]) == {
        "forward", "back", "left", "right", "up", "down",
    }


@pytest.mark.asyncio
async def test_full_flight(server, backend):
    assert (await call_json(server, "connect"))["battery"] == 85
    await call(server, "takeoff")
    await call(server, "move", direction="forward", distance_cm=100)
    await call(server, "rotate", direction="cw", angle_deg=90)
    await call(server, "flip", direction="left")
    assert (await call_json(server, "get_status"))["flying"] is True
    assert (await call_json(server, "get_telemetry"))["height"] == 50
    await call(server, "land")
    await call(server, "disconnect")

    assert backend.requests == [
        ("POST", "/api/control/connect", None),
        ("POST", "/api/control/takeoff", None),
        ("POST", "/api/control/move", {"direction": "forward", "distance_cm": 100}),
        ("POST", "/api/control/rotate", {"direction": "cw", "angle_deg": 90}),
        ("POST", "/api/control/flip", {"direction": "left"}),
        ("GET", "/api/status", None),
        ("GET", "/api/telemetry", None),
        ("POST", "/api/control/land", None),
        ("POST", "/api/control/disconnect", None),
    ]


@pytest.mark.asyncio
async def test_emergency_stop_works_without_connecting(server, backend):
    await call(server, "emergency_stop")
    assert backend.requests == [("POST", "/api/control/emergency", None)]


@pytest.mark.asyncio
async def test_backend_refusal_surfaces_its_reason(server):
    with pytest.raises(ToolError, match=r"Drone is not connected \(HTTP 409\)"):
        await server.call_tool("takeoff", {})


@pytest.mark.asyncio
async def test_backend_validation_errors_are_readable():
    def reject(request):
        return httpx.Response(422, json={"detail": [
            {"type": "greater_than_equal", "loc": ["body", "distance_cm"],
             "msg": "Input should be greater than or equal to 20"},
        ]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(reject), base_url="http://tello")
    server = build_server(client=client)
    with pytest.raises(ToolError, match=r"distance_cm: Input should be greater than or equal to 20 \(HTTP 422\)"):
        await server.call_tool("move", {"direction": "up", "distance_cm": 50})


@pytest.mark.asyncio
async def test_out_of_range_values_are_rejected_before_any_request(server, backend):
    for name, args in [
        ("move", {"direction": "up", "distance_cm": 5}),
        ("move", {"direction": "up", "distance_cm": 501}),
        ("rotate", {"direction": "cw", "angle_deg": 0}),
        ("rotate", {"direction": "cw", "angle_deg": 361}),
    ]:
        with pytest.raises(ToolError):
            await server.call_tool(name, args)
    assert backend.requests == []


@pytest.mark.asyncio
async def test_move_schema_advertises_the_distance_limits(server):
    move = next(t for t in await server.list_tools() if t.name == "move")
    distance = move.input_schema["properties"]["distance_cm"]
    assert (distance["minimum"], distance["maximum"]) == (20, 500)


@pytest.mark.asyncio
async def test_bad_direction_is_rejected_before_any_request(server, backend):
    with pytest.raises(ToolError):
        await server.call_tool("move", {"direction": "diagonal", "distance_cm": 50})
    assert backend.requests == []


@pytest.mark.asyncio
async def test_snapshot_returns_image_content(server):
    await call(server, "connect")
    result = await call(server, "take_snapshot")
    [image] = result.content
    assert image.type == "image"
    assert image.mime_type == "image/jpeg"
    import base64
    assert base64.b64decode(image.data) == JPEG


@pytest.mark.asyncio
async def test_flight_log_tools(server):
    flights = await call_json(server, "list_flights")
    assert flights["id"] == 3

    detail = await call_json(server, "get_flight_commands", flight_id=3)
    assert [c["command"] for c in detail["command_log"]] == ["connect", "takeoff"]
    assert "telemetry" not in detail

    with pytest.raises(ToolError, match="Flight not found"):
        await server.call_tool("get_flight_commands", {"flight_id": 99})


@pytest.mark.asyncio
async def test_unreachable_backend_names_the_url():
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url="http://tello")
    server = build_server(client=client, api_url="http://tello:8000")
    with pytest.raises(ToolError, match="Cannot reach the drone backend at http://tello:8000"):
        await server.call_tool("get_status", {})


@pytest.mark.asyncio
async def test_timeout_warns_the_command_may_still_be_running():
    def hang(request):
        raise httpx.ReadTimeout("timed out")

    client = httpx.AsyncClient(transport=httpx.MockTransport(hang), base_url="http://tello")
    server = build_server(client=client)
    with pytest.raises(ToolError, match="may still be in progress"):
        await server.call_tool("takeoff", {})


@pytest.mark.asyncio
async def test_camera_gallery_tools(server, backend):
    with pytest.raises(ToolError, match="Drone is not connected"):
        await server.call_tool("take_photo", {})

    await call(server, "connect")
    assert (await call_json(server, "take_photo"))["name"] == "photo-1.jpg"
    assert (await call_json(server, "start_recording"))["recording"] is True
    assert (await call_json(server, "list_media"))["recording"] == {"recording": True}
    assert (await call_json(server, "stop_recording"))["item"]["name"] == "clip-1.mp4"
    assert (await call_json(server, "stop_recording"))["item"] is None


@pytest.mark.asyncio
async def test_sequence_tools(server, backend):
    listed = await call_json(server, "list_sequences")
    assert listed == {"id": "orbit", "name": "Orbit", "description": "Circle a point", "steps": 3}

    assert (await call_json(server, "get_sequence_status"))["status"] == "idle"
    assert (await call_json(server, "run_sequence", sequence_id="orbit"))["status"] == "running"
    assert (await call_json(server, "get_sequence_status"))["sequence_name"] == "Orbit"
    assert "Abort requested" in (await call_json(server, "abort_sequence"))["message"]
    assert ("POST", "/api/sequences/orbit/run", None) in backend.requests


@pytest.mark.asyncio
async def test_sequence_preflight_refusal_lists_the_problems(server, backend):
    backend.battery = 20
    with pytest.raises(ToolError, match="Pre-flight check failed: Battery is at 20%"):
        await server.call_tool("run_sequence", {"sequence_id": "orbit"})


@pytest.mark.asyncio
async def test_unknown_sequence_is_reported(server):
    with pytest.raises(ToolError, match="not found"):
        await server.call_tool("run_sequence", {"sequence_id": "nope"})
