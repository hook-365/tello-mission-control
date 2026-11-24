"""MCP server for the Tello Web Controller.

A thin client of the backend's REST API: the backend stays the only process that
talks to the drone, so this server can run anywhere that can reach it over HTTP.

    python server.py                      # stdio (for `claude mcp add`)
    python server.py --http --port 8765   # streamable HTTP on 127.0.0.1:8765/mcp
"""

from __future__ import annotations

import argparse
import os
from typing import Annotated, Any, Literal

import httpx
from pydantic import Field
from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

DEFAULT_API_URL = "http://localhost:8000"

# A 500 cm move at the Tello's default speed takes several seconds, and the
# backend holds the request open until the drone acknowledges it.
REQUEST_TIMEOUT_S = 30.0

INSTRUCTIONS = """\
Fly a DJI Tello drone. Typical flow: connect -> takeoff -> move/rotate -> land.

The drone has no GPS and no obstacle sensing: it cannot see walls, people or
ceilings, and it drifts. Keep moves short, check get_telemetry (height, battery)
between steps, and land when battery drops below 20%. Every move blocks until the
drone finishes it. emergency_stop cuts the motors in mid-air: the drone falls, so
use it only to prevent harm. Use land for a normal stop.
"""


def _error_detail(resp: httpx.Response) -> str:
    """Pull a readable reason out of a FastAPI error body."""
    try:
        detail = resp.json().get("detail", resp.text)
    except (ValueError, AttributeError):
        return resp.text
    if isinstance(detail, list):  # request validation errors: one dict per bad field
        return "; ".join(
            ": ".join(filter(None, [".".join(str(p) for p in d.get("loc", [])[1:]), d.get("msg", "")]))
            for d in detail
        )
    if isinstance(detail, dict):  # sequence pre-flight refusal: a message plus the reasons
        problems = "; ".join(str(p) for p in detail.get("problems", []))
        message = str(detail.get("message", "")) or "Refused"
        return f"{message}: {problems}" if problems else message
    return str(detail)


def build_server(client: httpx.AsyncClient | None = None, api_url: str | None = None) -> MCPServer:
    """Create the MCP server. ``client`` is injectable for tests."""
    base_url = (api_url or os.environ.get("TELLO_API_URL") or DEFAULT_API_URL).rstrip("/")
    http = client or httpx.AsyncClient(base_url=base_url, timeout=REQUEST_TIMEOUT_S)
    server = MCPServer("tello", instructions=INSTRUCTIONS)

    async def request(method: str, path: str, json: dict[str, Any] | None = None) -> httpx.Response:
        try:
            resp = await http.request(method, path, json=json)
        except httpx.TimeoutException:
            raise ToolError(
                f"The drone backend did not answer within {REQUEST_TIMEOUT_S:.0f}s. "
                "The command may still be in progress: check get_status before retrying."
            )
        except httpx.HTTPError as e:
            raise ToolError(f"Cannot reach the drone backend at {base_url}: {e}")
        if resp.is_error:
            raise ToolError(f"{_error_detail(resp)} (HTTP {resp.status_code})")
        return resp

    async def call(method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        return (await request(method, path, json)).json()

    # -- Connection --

    @server.tool()
    async def connect() -> dict:
        """Connect to the drone. Required before anything else. Returns battery %."""
        return await call("POST", "/api/control/connect")

    @server.tool()
    async def disconnect() -> dict:
        """Disconnect from the drone. Lands it first if it is flying."""
        return await call("POST", "/api/control/disconnect")

    # -- Flight --

    @server.tool()
    async def takeoff() -> dict:
        """Take off and hover at roughly 50-80 cm. Needs clear space above and around."""
        return await call("POST", "/api/control/takeoff")

    @server.tool()
    async def land() -> dict:
        """Land straight down from the current position."""
        return await call("POST", "/api/control/land")

    @server.tool()
    async def emergency_stop() -> dict:
        """Cut the motors immediately. The drone FALLS from wherever it is.

        Only for preventing harm (about to hit someone, out of control).
        Use land for every normal stop.
        """
        return await call("POST", "/api/control/emergency")

    @server.tool()
    async def move(
        direction: Literal["forward", "back", "left", "right", "up", "down"],
        distance_cm: Annotated[int, Field(ge=20, le=500)],
    ) -> dict:
        """Fly a straight line relative to where the drone is facing, then hover.

        distance_cm must be 20-500. Blocks until the move finishes. The drone
        cannot detect obstacles, so only move into space known to be clear.
        """
        return await call(
            "POST", "/api/control/move", {"direction": direction, "distance_cm": distance_cm}
        )

    @server.tool()
    async def rotate(
        direction: Literal["cw", "ccw"], angle_deg: Annotated[int, Field(ge=1, le=360)]
    ) -> dict:
        """Turn in place: cw = clockwise seen from above, ccw = counter-clockwise.

        angle_deg must be 1-360.
        """
        return await call(
            "POST", "/api/control/rotate", {"direction": direction, "angle_deg": angle_deg}
        )

    @server.tool()
    async def flip(direction: Literal["forward", "back", "left", "right"]) -> dict:
        """Do a flip. Needs battery above 50% and about a metre of clear space all round."""
        return await call("POST", "/api/control/flip", {"direction": direction})

    # -- State --

    @server.tool()
    async def get_status() -> dict:
        """Whether the drone is connected, flying and streaming video, plus battery %."""
        return await call("GET", "/api/status")

    @server.tool()
    async def get_telemetry() -> dict:
        """Current sensor readings.

        height and tof_distance are cm above the surface below, speed is cm/s per
        axis, attitude is degrees, temperature is deg C, flight_time is seconds.
        """
        return await call("GET", "/api/telemetry")

    @server.tool()
    async def take_snapshot() -> Image:
        """Capture what the drone's forward camera sees right now, as a JPEG."""
        resp = await request("POST", "/api/video/snapshot")
        return Image(data=resp.content, format="jpeg")

    # -- Camera gallery --

    @server.tool()
    async def take_photo() -> dict:
        """Save a photo to the drone's gallery on the ground station.

        Unlike take_snapshot this keeps the file; it does not return the image.
        Works on the ground too (the camera switches itself on).
        """
        return await call("POST", "/api/media/photo")

    @server.tool()
    async def start_recording() -> dict:
        """Start recording a video clip to the gallery. Stops itself after 5 minutes."""
        return await call("POST", "/api/media/record/start")

    @server.tool()
    async def stop_recording() -> dict:
        """Stop the clip being recorded and save it. `item` is null if nothing was recording."""
        return await call("POST", "/api/media/record/stop")

    @server.tool()
    async def list_media() -> dict:
        """Photos and clips in the gallery, newest first, plus whether a clip is recording."""
        return await call("GET", "/api/media")

    # -- Flight sequences --

    @server.tool()
    async def list_sequences() -> list[dict]:
        """Saved flight sequences (pre-planned routines such as an orbit or a reveal shot).

        Returns id, name, description and step count for each; steps are left out.
        """
        sequences = await call("GET", "/api/sequences")
        return [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "description": s.get("description", ""),
                "steps": len(s.get("steps", [])),
            }
            for s in sequences
        ]

    @server.tool()
    async def run_sequence(sequence_id: str) -> dict:
        """Start a saved sequence by id and return at once; it keeps flying on its own.

        The drone takes off and lands by itself as the sequence needs. It is refused
        if a pre-flight check fails (low battery, weak signal) or one is already
        running. Other flight commands are refused until it ends: poll
        get_sequence_status, and use abort_sequence, land or emergency_stop to end it.
        """
        return await call("POST", f"/api/sequences/{sequence_id}/run")

    @server.tool()
    async def get_sequence_status() -> dict:
        """Progress of the current or last sequence run: status, step, and any message."""
        return await call("GET", "/api/sequences/run/status")

    @server.tool()
    async def abort_sequence() -> dict:
        """Stop the running sequence. The drone lands after its current step finishes."""
        return await call("POST", "/api/sequences/abort")

    # -- Flight log --

    @server.tool()
    async def list_flights() -> list[dict]:
        """Recorded flights, newest first: id, start/end time, frame and command counts."""
        return await call("GET", "/api/flights")

    @server.tool()
    async def get_flight_commands(flight_id: int) -> dict:
        """The commands issued during one recorded flight, oldest first.

        Telemetry is left out because a flight holds thousands of frames.
        """
        flight = await call("GET", f"/api/flights/{flight_id}")
        flight.pop("telemetry", None)
        return flight

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server for the Tello Web Controller")
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default: 8765)")
    parser.add_argument("--api-url", help=f"backend URL (default: $TELLO_API_URL or {DEFAULT_API_URL})")
    args = parser.parse_args()

    server = build_server(api_url=args.api_url)
    if args.http:
        server.run("streamable-http", host=args.host, port=args.port)
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
