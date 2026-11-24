# Tello MCP Server

Exposes the Tello Web Controller as [Model Context Protocol](https://modelcontextprotocol.io) tools, so Claude (or any MCP client) can fly the drone.

It is a thin client of the backend's REST API. The backend stays the only process that talks to the drone, so the two can run on different machines.

## Setup

Needs Python 3.10+ and the backend running (see the top-level README). Use a separate virtualenv from the backend: the MCP SDK requires newer versions of packages the backend pins.

```bash
cd mcp_server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Use with Claude Code

```bash
claude mcp add tello \
  --env TELLO_API_URL=http://localhost:8000 \
  -- /absolute/path/to/mcp_server/.venv/bin/python /absolute/path/to/mcp_server/server.py
```

Then ask for things like "connect to the drone, take off, turn to face the window and take a picture", or "run the orbit sequence and record it".

## Run over HTTP

```bash
python server.py --http --port 8765      # http://127.0.0.1:8765/mcp
```

It binds to `127.0.0.1` by default. There is **no authentication**: anyone who can reach the port can fly the drone, so only pass `--host 0.0.0.0` on a network you trust.

## Tools

| Tool | What it does |
|------|--------------|
| `connect` / `disconnect` | Open or close the link to the drone (disconnect lands first) |
| `takeoff` / `land` | Take off to a hover, or land in place |
| `emergency_stop` | Cut the motors mid-air — the drone falls |
| `move` | Fly `forward`/`back`/`left`/`right`/`up`/`down` by 20–500 cm |
| `rotate` | Turn `cw`/`ccw` by 1–360° |
| `flip` | Flip `forward`/`back`/`left`/`right` |
| `get_status` | Connected / flying / streaming, battery |
| `get_telemetry` | Height, speed, attitude, temperature, battery |
| `take_snapshot` | Current camera frame as a JPEG image |
| `take_photo` | Save a photo to the gallery (keeps the file, returns its name) |
| `start_recording` / `stop_recording` | Record a video clip to the gallery |
| `list_media` | Photos and clips in the gallery, and whether a clip is recording |
| `list_sequences` | Saved flight sequences: id, name, description, step count |
| `run_sequence` | Start a saved sequence; returns at once while it flies |
| `get_sequence_status` / `abort_sequence` | Follow a running sequence, or stop it (lands after the current step) |
| `list_flights` | Recorded flights from the flight log |
| `get_flight_commands` | Commands issued during one recorded flight |

Continuous stick control (`/api/control/rc`) is deliberately not exposed: it needs refreshing several times a second, which a model taking seconds per turn cannot do.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `TELLO_API_URL` / `--api-url` | `http://localhost:8000` | Where the backend is |
| `--http` | off | Serve streamable HTTP instead of stdio |
| `--host` / `--port` | `127.0.0.1` / `8765` | HTTP bind address |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

The tests run the tools against a fake of the backend API; they do not need the backend or a drone.
