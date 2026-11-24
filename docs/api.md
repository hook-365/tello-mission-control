# API reference

The backend listens on port 8000. Everything the web UI does goes through these endpoints, so anything can drive the drone: `curl`, a script, or the [MCP server](../mcp_server/README.md).

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/control/connect` | Connect to drone |
| POST | `/api/control/disconnect` | Disconnect (auto-lands if flying) |
| POST | `/api/control/takeoff` | Take off |
| POST | `/api/control/land` | Land |
| POST | `/api/control/emergency` | Emergency motor kill |
| POST | `/api/control/move` | Move (body: `{direction, distance_cm}`) |
| POST | `/api/control/rotate` | Rotate (body: `{direction, angle_deg}`) |
| GET | `/api/video/stream` | MJPEG video stream |
| POST | `/api/video/stream/start` | Start video stream |
| POST | `/api/video/stream/stop` | Stop video stream |
| POST | `/api/video/snapshot` | Capture single JPEG frame (download only, not saved) |
| GET | `/api/media` | Saved photos and clips, newest first, plus recording status |
| POST | `/api/media/photo` | Save a photo to the gallery (starts the camera if needed) |
| POST | `/api/media/record/start` · `/stop` | Start / stop and save a clip |
| GET | `/api/media/record/status` | `{recording, name, elapsed_s, started_at}` |
| GET / DELETE | `/api/media/files/{name}` | Download or delete a photo or clip |
| POST | `/api/control/flip` | Flip (body: `{direction}` forward/back/left/right) |
| POST | `/api/control/rc` | One stick update (body: `{lr, fb, ud, yaw}`, each -100..100); must be flying |
| WS | `/api/ws/rc` | Stream stick updates as `{lr, fb, ud, yaw}` JSON; replies `{"type":"rc_status"}` when accepted/refused changes. Hovers if updates stop for 0.5 s or the socket closes |
| GET | `/api/status` | `{connected, flying, streaming, battery, wifi_snr}` |
| GET | `/api/telemetry` | Latest telemetry snapshot (same fields as the WebSocket frame) |
| GET | `/api/flights` | Recorded flights, newest first |
| GET | `/api/flights/{id}` | One flight with its full telemetry and command log |
| DELETE | `/api/flights/{id}` | Delete a recorded flight |
| GET | `/api/vision` | `{available, detecting, tracking, target, hz}` |
| POST | `/api/vision/detect` | Switch object detection on/off (body: `{enabled}`) |
| POST | `/api/vision/track` | Start/stop following a target (body: `{enabled, target}`) |
| GET | `/api/sequences` | List flight sequences (see [Sequences](#sequences)) |
| WS | `/api/ws/telemetry` | Telemetry push (~4Hz), command logs, sequence progress `media` events (photo saved, recording started/stopped, deleted) and detections (when vision is on) |

### Allowed Values

| Parameter | Values |
|-----------|--------|
| Move direction | `forward`, `back`, `left`, `right`, `up`, `down` |
| Move distance | 20–500 cm |
| Rotate direction | `cw`, `ccw` |
| Rotate angle | 1–360° |

## Sequences

| Method | Endpoint | What it does |
|---|---|---|
| GET | `/api/sequences` | List built-in and saved sequences |
| POST | `/api/sequences` | Save a new sequence |
| GET / PUT / DELETE | `/api/sequences/{id}` | Read, update, delete (built-ins are read-only) |
| POST | `/api/sequences/{id}/run` | Run a saved sequence |
| POST | `/api/sequences/run` | Run `{"sequence_id": ...}` or an unsaved `{"sequence": {...}}` |
| POST | `/api/sequences/abort` | Abort and land |
| GET | `/api/sequences/run/status` | Current run status |

Progress streams over the existing WebSocket as `{"type": "sequence_progress", "data": {...}}` messages. Step types: `takeoff`, `land`, `move` (`direction`, `distance_cm`), `rotate` (`direction` cw/ccw, `angle_deg`), `flip` (`direction` forward/back/left/right), `wait` (`seconds`), `photo`, `record` (`action` start/stop), `orbit` (`direction` left/right, `radius_cm` 50-300, `degrees` 30-360, `speed_cm_s` 10-60), `glide` (`forward_cm`, `right_cm`, `up_cm` each -500..500 with one over 20, `speed_cm_s` 10-100).

## Examples

```bash
# Connect
curl -X POST http://localhost:8000/api/control/connect

# Check status
curl http://localhost:8000/api/status

# Takeoff
curl -X POST http://localhost:8000/api/control/takeoff

# Move forward 100cm
curl -X POST http://localhost:8000/api/control/move \
  -H 'Content-Type: application/json' \
  -d '{"direction":"forward","distance_cm":100}'

# Rotate 90° clockwise
curl -X POST http://localhost:8000/api/control/rotate \
  -H 'Content-Type: application/json' \
  -d '{"direction":"cw","angle_deg":90}'

# Land
curl -X POST http://localhost:8000/api/control/land

# Emergency stop (kills motors instantly)
curl -X POST http://localhost:8000/api/control/emergency

# Disconnect
curl -X POST http://localhost:8000/api/control/disconnect
```

### Video Stream

Open in browser or use in an `<img>` tag:

```
http://localhost:8000/api/video/stream
```

### Telemetry (WebSocket)

```bash
wscat -c ws://localhost:8000/api/ws/telemetry
```

Server pushes telemetry frames at ~4 Hz:

```json
{
  "type": "telemetry",
  "data": {
    "battery": 85,
    "height": 120,
    "flight_time": 42,
    "temperature": { "high": 65, "low": 60 },
    "attitude": { "pitch": 2, "roll": -1, "yaw": 180 },
    "speed": { "x": 0, "y": 10, "z": 0 },
    "barometer": 150.5,
    "tof_distance": 120,
    "wifi_snr": 72,
    "battery_level": "ok",
    "signal_level": "ok"
  },
  "timestamp": "2026-03-17T10:30:00.123Z"
}
```

Command log events are also pushed over the same connection:

```json
{
  "type": "command_log",
  "data": {
    "command": "move",
    "params": { "direction": "forward", "distance_cm": 100 },
    "result": "ok",
    "timestamp": "2026-03-17T10:30:01.456Z"
  }
}
```
