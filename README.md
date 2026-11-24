# Tello Web Controller

A locally-deployed web application for controlling a DJI Tello drone via browser. React frontend communicates with a FastAPI backend, which drives the drone through the `djitellopy` Python library.

```
Browser (React) ←HTTP/WS→ FastAPI + djitellopy ←UDP→ DJI Tello (192.168.10.1)
```

<img width="800" alt="Tello Web Controller Interface" src="https://github.com/user-attachments/assets/9ba9d593-b2ef-4b7d-b769-9882847af1cb">

Demo video: https://youtube.com/shorts/Ex-KBuxlEQw


## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose (optional)
- DJI Tello drone (or use mock mode for development)

## Quick Start

### 1. Environment Setup

```bash
cp .env.template .env
# Edit .env as needed (mock mode is enabled by default)
```

### 2. Docker (recommended)

```bash
docker compose up --build
```

This starts both services:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000

### 3. Native Development

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# With mock drone (no hardware needed)
TELLO_USE_MOCK_DRONE=true uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# With real drone (connect to Tello Wi-Fi first)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd frontend
npm ci
npm run dev    # http://localhost:5173
```

> **Real drone on Linux**: If you need direct UDP access to the drone (192.168.10.1), add `network_mode: host` to the backend service in `docker-compose.yml`. Note that `network_mode: host` does not work on macOS/Windows — run the backend natively instead.

## Flight Sequencer

Script a routine ("up 50, forward 100, spin 360, flip"), save it with a name like *Victory lap*, and play it with one tap.

### 1. One-time setup

The Tello's Wi-Fi has no internet, so build everything **while you're still on your home Wi-Fi**:

```bash
cp .env.template .env
docker compose build
```

Want a test run first? Leave `TELLO_USE_MOCK_DRONE=true` in `.env`, run `docker compose up`, open http://localhost:3000 and click **Connect**. You get a fake drone, so you can build and play sequences without the real one. When you're ready to fly for real, set `TELLO_USE_MOCK_DRONE=false`.

### 2. Connect to the Tello

1. Charge the battery. Sequences need **30%+**, flips need **50%+**.
2. Turn the Tello on and join its Wi-Fi (`TELLO-XXXXXX`) from your computer.
3. Run `docker compose up`, open http://localhost:3000 and click **Connect**.

**Second adapter note:** while you're on the Tello's Wi-Fi, your computer has no internet. That's fine for flying, since the app runs entirely on your machine. If you want internet at the same time, plug in Ethernet, or add a cheap USB Wi-Fi adapter and use it for the Tello while the built-in Wi-Fi stays on your home network. See [the networking section](#the-networking-problem-tello-wifi-vs-internet) for details.

**Linux + Docker:** if **Connect** times out, the drone's UDP replies probably aren't reaching the container. Run the backend natively instead (see Native Development above), or give the backend service `network_mode: host`.

### 3. Using the sequencer

1. Click **Sequences** in the bottom bar.
2. Pick a built-in (★ Victory lap, ★ Square dance, ★ Elevator spin, ★ Orbit shot, ★ Reveal) or **+ New sequence**.
3. Add steps with the buttons: **Move** (20-500 cm), **Spin** (1-360°), **Flip** (forward/back/left/right), **Hover** (0.5-10 s), plus the camera steps **Photo**, **Record**, **Orbit** and **Glide** (see [Camera Moves](#camera-moves)).
4. Reorder by dragging a row or using the ↑ ↓ arrows. The trash can deletes a step.
5. Name it and hit **Save new**. Saved sequences are plain JSON files in `./data/sequences/`, so they survive rebuilds.
6. Press **Play**. The step that's running lights up blue.

With **Auto take off / land** ticked (the default) the drone takes off by itself before step 1 and always lands at the end. Untick it to place Take off and Land steps yourself.

**Stopping:**

| Button | What happens |
|---|---|
| **Abort** (big orange) | Finishes the move in progress (a Tello can't stop mid-move), then lands. Hovers stop right away. Pressing **Land** during a sequence does the same. |
| **Emergency Stop** (or `Esc`) | Cuts the motors instantly. The drone **drops**. Only for real emergencies. |

**Safety checks built in:** a sequence won't start unless the drone is connected and has 30%+ battery (50%+ if it has flips). If the battery drops below 50% mid-run, flips are skipped; below 15%, it lands. Manual flying buttons are locked while a sequence runs. Hovers max out at 10 s because a Tello lands on its own after about 15 s without a command.

**Before you press Play:** fly somewhere with clear space around and above (the built-in descriptions say how much each needs), keep the drone in sight, and start with a short sequence.

### Sequencer API

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

## Camera Moves

Photos and video clips from the drone's camera are saved on the computer running the backend, in `./data/media/` (a Docker volume, so they survive rebuilds). Photos are JPEGs; clips are H.264 MP4s that play in any browser or phone.

- **Status bar:** the camera button takes a photo, the red dot starts a clip (it turns into a stop square with a **REC 0:12** timer), and the pictures button opens the **Gallery**. They work on the ground too: the camera switches itself on.
- **Gallery:** tap a thumbnail to view or play it, **Save** to download, **Delete** to remove it from the computer.
- **Sequence steps:**

| Step | What it does |
|---|---|
| **Photo** | Saves a photo. Works on the ground or in the air. |
| **Record** start / stop | Starts or stops a clip. Any clip a sequence started is stopped and saved when it ends, even if it's aborted or a step fails. |
| **Orbit** left/right | Circles whatever is *N* cm in front of the drone, turning to keep the camera on it. Flown as 30° hops plus turns (a Tello can't turn while flying a line), so it's a 12-sided circle rather than a perfect one. |
| **Glide** | One smooth straight line on several axes at once, e.g. back 200 and up 120. |

When a sequence has Photo or Record steps, the camera turns on before take-off and the run waits for the first picture (up to 8 s), so the clip doesn't start black.

**Built-ins:**
- **★ Orbit shot:** rises 40 cm, starts recording and circles the subject 1.5 m ahead. Needs about 4 x 4 m of clear space.
- **★ Reveal:** start close to the subject, facing it. Records while the drone slowly backs away 2 m and rises 1.2 m, then snaps a photo.

**Not yet checked on a real drone:** the sideways direction of Orbit and Glide follows djitellopy's docs (the Tello's `go` command counts left as positive). If a right orbit drifts left, set `TELLO_GO_Y_IS_LEFT=false`. Clips stop themselves after 5 minutes (`TELLO_RECORD_MAX_S`).

## Flying with a Game Controller

Any controller your browser recognises works (Xbox, PlayStation, 8BitDo and most USB/Bluetooth pads). Plug it in or pair it with the laptop, open the app and **press any button once**: browsers only reveal a controller after a button press. The Flight Controls panel then shows its name.

| Control | What it does |
|---|---|
| **Hold LB or RB** | Fly. This is the dead-man switch: let go and the drone stops and hovers. |
| Left stick | Up/down and spin |
| Right stick | Forward/back and sideways |
| **LB or RB + Start** (Menu) | Take off |
| Back (View) | Land |
| **Click both sticks in together** (L3 + R3) | Emergency motor stop. The drone **drops**. |

- **Stick speed** (slider, 20-100%) sets how fast full stick goes. Start at 50% indoors. The setting is remembered.
- Small stick movements are ignored (deadzone) and the response is gentle near centre, so drift won't move the drone.
- No controller? Switch the keyboard to **Hold to fly**: hold W/A/S/D, Space, Shift, Q, E to fly smoothly; let go to hover. **Tap** mode keeps the original one-hop-per-press keys.

**Safety built in:** sticks only work while the drone is flying and no sequence is running. The drone stops and hovers if you let go of the bumper, unplug the controller, switch tabs, or if the browser stops sending for half a second (Wi-Fi hiccup, crash). Pressing a move/spin/flip button or Land first stops any stick motion.

## Battery and Signal Warnings

The status bar shows the Wi-Fi signal next to the battery: the number is the drone's own signal-to-noise reading (higher is better, around 90 right beside it).

| | Amber banner | Red banner + beeping |
|---|---|---|
| Battery | 30% or less: "land soon" | 15% or less: "land now" |
| Wi-Fi signal | 40 or less: "stay closer" | 20 or less: "the drone may land itself" |

The beep repeats every 10 s while something is red; the speaker button on the banner mutes it. Sequences refuse to start on a red signal, and the sequencer shows the warnings above **Play**. The signal thresholds are starting points: if the banners fire too early or too late in your space, change `TELLO_WIFI_SNR_WEAK` / `TELLO_WIFI_SNR_CRITICAL`.

To try the warnings without a drone, start mock mode with a low battery or signal, e.g. `TELLO_MOCK_BATTERY_PCT=20 TELLO_MOCK_WIFI_SNR=30`.

## Flying with the API

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

## Flying with Claude (MCP)

`mcp_server/` exposes the drone as MCP tools — connect, takeoff, move, rotate, flip, land, telemetry, camera snapshot, gallery photos and clips, saved sequences and the flight log:

```bash
cd mcp_server && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
claude mcp add tello -- "$PWD/.venv/bin/python" "$PWD/server.py"
```

Setup, HTTP transport and the tool list are in [`mcp_server/README.md`](mcp_server/README.md).

## Staying in Sync with the Original Project

This copy is based on [thakorneyp11/tello-mission-control](https://github.com/thakorneyp11/tello-mission-control) and keeps its full history, so fixes from there can be pulled in later:

```bash
git remote add upstream https://github.com/thakorneyp11/tello-mission-control.git   # once
git fetch upstream
git merge upstream/main
```

The original project has no license file; check with its author before sharing this copy publicly.

## Running Tests

```bash
cd backend
source .venv/bin/activate
python -m pytest -v    # 208 tests, all use MockTello (no drone needed)

cd ../frontend && npx vitest run   # 125 frontend tests
```

## API Reference

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
| GET | `/api/sequences` | List flight sequences (see [Sequencer API](#sequencer-api)) |
| WS | `/api/ws/telemetry` | Telemetry push (~4Hz), command logs, sequence progress `media` events (photo saved, recording started/stopped, deleted) and detections (when vision is on) |

### Allowed Values

| Parameter | Values |
|-----------|--------|
| Move direction | `forward`, `back`, `left`, `right`, `up`, `down` |
| Move distance | 20–500 cm |
| Rotate direction | `cw`, `ccw` |
| Rotate angle | 1–360° |

### Flight Log & Replay

Every connection is recorded to a SQLite file: each telemetry frame (~4 Hz) and every command, grouped into one session from connect to disconnect. Open the clock icon in the status bar to list recorded flights, then pick one to scrub or play back its telemetry alongside the commands that were issued. Sequence runs appear in that list as a start and an outcome (with the reason if one was aborted or failed), and saved photos and clips link to the file.

The log lives at `TELLO_FLIGHT_LOG_PATH` (`data/flights.db`; with Docker, `./data` on the host). It grows by roughly 3 MB per hour connected and is never pruned automatically — delete flights from the UI or the API. If the file can't be opened the backend logs an error and carries on without recording.

### Object Detection & Person Tracking (optional)

Off by default, because it needs PyTorch (several GB). To enable it:

```bash
# Native
cd backend && pip install -r requirements.txt -r requirements-vision.txt
TELLO_VISION_ENABLED=true uvicorn app.main:app --host 0.0.0.0 --port 8000

# Docker
docker compose -f docker-compose.yml -f docker-compose.vision.yml up --build
```

Two buttons then appear in the status bar:

- **Detect** runs YOLO (`yolov8n` by default) on the video about 5 times a second and draws labelled boxes over the feed. The model loads the first time you switch it on, which takes a few seconds, and its weights (~6 MB) are downloaded on first use.
- **Follow** (only while flying) turns the drone to keep the nearest person centred, climbs or descends to match, and moves forward or back to hold them at a set size in frame. It never strafes.

Following is built to let go easily:

- Any pilot input cancels it at once: a stick, a move/rotate/flip, land, emergency or disconnect. So does any step of a flight sequence, and it will not start while a sequence is running.
- With no person in view it hovers and waits. If the video stalls for a second, or the detector errors, it hovers.
- Every channel is capped at `TELLO_VISION_TRACK_MAX_SPEED` (default 30 of 100).

> ⚠️ The tracking gains are **untuned defaults that have never been flown on a real drone** — they were only exercised against the mock. The drone still cannot see obstacles: it will follow a person into a wall. First flights should be in a large clear space with a low speed cap and a finger on Land.

| Variable | Default | Description |
|----------|---------|-------------|
| `TELLO_VISION_ENABLED` | `false` | Turn the feature on |
| `TELLO_VISION_MODEL` | `yolov8n.pt` | Ultralytics model name or path |
| `TELLO_VISION_CONFIDENCE` | `0.4` | Minimum detection confidence |
| `TELLO_VISION_DEVICE` | *(auto)* | `cpu`, `cuda:0`, … |
| `TELLO_VISION_HZ` | `5.0` | Detections per second |
| `TELLO_VISION_TRACK_MAX_SPEED` | `30` | Cap on every stick channel while following |
| `TELLO_VISION_TRACK_GAIN_YAW` / `_UD` / `_FB` | `60` / `40` / `40` | Stick velocity per unit of error |
| `TELLO_VISION_TRACK_TARGET_HEIGHT` | `0.5` | How much of the frame height the person should fill |

## Configuration

All environment variables are prefixed with `TELLO_`. See `.env.template` for the full list with defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `TELLO_USE_MOCK_DRONE` | `false` | Use fake drone for development |
| `TELLO_TELLO_HOST` | `192.168.10.1` | Drone IP address |
| `TELLO_API_PORT` | `8000` | Backend server port |
| `TELLO_FRONTEND_PORT` | `3000` | Frontend server port (Docker) |
| `TELLO_TELEMETRY_POLL_HZ` | `4.0` | Telemetry polling frequency |
| `TELLO_FLIGHT_LOG_ENABLED` | `true` | Record telemetry and commands for every connection |
| `TELLO_FLIGHT_LOG_PATH` | `data/flights.db` | SQLite file for the flight log |
| `TELLO_VIDEO_FPS` | `30` | Video stream frame rate |
| `TELLO_VIDEO_JPEG_QUALITY` | `70` | JPEG compression quality |
| `TELLO_CORS_ORIGINS` | `["http://localhost:3000","http://localhost:5173"]` | Allowed CORS origins |
| `TELLO_MOCK_COMMAND_DELAY_S` | `0.0` | Mock mode: seconds each fake command takes (the template uses 0.8 so sequences are watchable) |
| `TELLO_SEQUENCES_DIR` | `data/sequences` | Where saved sequences are stored |
| `TELLO_SEQUENCE_MIN_BATTERY_PCT` | `30` | Minimum battery to start a sequence |
| `TELLO_SEQUENCE_FLIP_MIN_BATTERY_PCT` | `50` | Minimum battery for flips |
| `TELLO_SEQUENCE_ABORT_BATTERY_PCT` | `15` | Land mid-sequence below this |
| `TELLO_BATTERY_LOW_PCT` | `30` | Amber battery banner at or below this |
| `TELLO_BATTERY_CRITICAL_PCT` | `15` | Red battery banner + beep at or below this |
| `TELLO_WIFI_SNR_WEAK` | `40` | Amber signal banner at or below this |
| `TELLO_WIFI_SNR_CRITICAL` | `20` | Red signal banner + beep; sequences won't start |
| `TELLO_WIFI_POLL_INTERVAL_S` | `3.0` | How often to ask the drone for its signal (skipped while a command runs) |
| `TELLO_RC_SPEED_LIMIT_PCT` | `100` | Hard cap on stick speed, on top of the in-app slider |
| `TELLO_RC_TIMEOUT_S` | `0.5` | Hover if stick updates stop for this long |
| `TELLO_MEDIA_DIR` | `data/media` | Where photos and clips are saved |
| `TELLO_RECORD_FPS` | `30` | Frame rate of saved clips |
| `TELLO_RECORD_MAX_S` | `300` | Clips stop and save themselves after this long |
| `TELLO_CAMERA_START_TIMEOUT_S` | `8.0` | How long to wait for the first picture when the camera starts |
| `TELLO_GO_Y_IS_LEFT` | `true` | Sideways sign for Orbit/Glide; set `false` if they drift the wrong way |
| `TELLO_MOCK_BATTERY_PCT` | `85` | Mock mode: starting battery |
| `TELLO_MOCK_WIFI_SNR` | `90` | Mock mode: Wi-Fi signal |

## Project Structure

```
├── backend/                        # FastAPI + djitellopy
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py                 # App entry point, lifespan, CORS
│   │   ├── config.py               # Settings via env vars
│   │   ├── routers/                # API endpoints
│   │   ├── services/               # DroneManager, TelemetryService
│   │   └── models/                 # Pydantic schemas
│   └── tests/                      # pytest (44 tests)
├── frontend/                       # React + Vite + TailwindCSS
│   ├── Dockerfile
│   ├── nginx.conf                  # Nginx reverse proxy config
│   └── src/
├── mcp_server/                     # MCP server (thin client of the backend API)
├── sample_drone_integration/       # djitellopy reference scripts
│   ├── droneeyes.py                # Video streaming example
│   ├── drone_control_simple.py     # Basic flight control example
│   └── drone_control_full.py       # Advanced flight choreography
├── docs/                           # PRD & Architecture docs
├── docker-compose.yml              # Both services orchestration
├── docker-compose.vision.yml       # Optional overlay: backend with object detection
├── .env.template                   # Environment variable template
└── .env                            # Local environment config (gitignored)
```

## Safety

- Always have clear space around the drone before takeoff
- Keep battery above 30%
- `/api/control/emergency` bypasses all locks — use if anything goes wrong
- Disconnecting while airborne auto-lands first
- Person tracking gives up control on any pilot input and hovers when it loses its target or the video

## Future Implementations

A roadmap of where this project could go, roughly ordered from most practical to most ambitious.

### Phase 1 — Platform Hardening

- ~~**MCP Server** — Expose drone commands as MCP tools so Claude (or any MCP client) can fly the drone through natural language~~ ✅ Done — see [`mcp_server/`](mcp_server/README.md)
- ~~**Flight Logging & Replay** — Persist every command + telemetry snapshot to SQLite/TimescaleDB, replay sessions in the UI as a timeline~~ ✅ Done (SQLite) — see [Flight Log & Replay](#flight-log--replay)
- ~~**Gamepad Support** — Map PS5/Xbox controllers via the Gamepad API to `send_rc_control()` for proper analog stick flying~~ ✅ Done — see [Flying with a Game Controller](#flying-with-a-game-controller)
- **WebRTC Video** — Replace MJPEG with WebRTC for lower latency, better compression, and future peer-to-peer streaming

### Phase 2 — Computer Vision

- ~~**Object Detection Overlay** — Run YOLOv8/v10 on the video stream (on the ground station GPU or via edge TPU) and draw bounding boxes on the HUD~~ ✅ Done (optional) — see [Object Detection & Person Tracking](#object-detection--person-tracking-optional)
- ~~**Face / Person Tracking** — Detect a target and auto-generate RC commands to keep them centered in frame — "follow me" mode~~ ✅ Done for people, untuned on real hardware
- **Optical Flow & SLAM** — Estimate drone position drift without GPS using visual odometry, display estimated position on a 2D minimap
- **QR / ArUco Marker Navigation** — Place markers as waypoints; drone reads them mid-flight to self-correct position

### Phase 3 — Autonomous Flight

- **Waypoint Mission Planner** — Draw a flight path on a 2D/3D grid UI, convert to a sequence of `go_xyz_speed()` commands
- **Geofencing & Safety Zones** — Define virtual boundaries the drone can't cross; auto-hover or return if breached
- **Auto-Landing on Low Battery** — Monitor battery in real-time, trigger autonomous return-and-land below a threshold
- **Obstacle Avoidance** — Fuse TOF sensor + video depth estimation to halt forward movement when obstacles detected

### Phase 4 — AI Agent Layer

- **Claude-Powered Mission Planning** — Describe a mission in natural language ("survey this room in a grid pattern"), agent generates and executes the command sequence
- **Voice Control** — Whisper STT → Claude intent parsing → MCP tool call → drone action, full voice-to-flight pipeline
- **Anomaly Narration** — AI watches the video stream and narrates what it sees, flags unusual objects or changes
- **Multi-Modal Reporting** — After a flight, AI auto-generates a summary report with captured images, telemetry charts, and observations

### Phase 5 — Multi-Drone & Swarm

- **Swarm Support** — Leverage `djitellopy.Swarm` with Tello EDUs, manage multiple drones from one UI with individual + synchronized controls
- **Formation Flying** — Define geometric formations (line, V-shape, grid) that maintain relative positions
- **Collaborative Mapping** — Multiple drones scan different zones simultaneously, stitch results into a combined map

### Phase 6 — Hardware & Integration

- **Raspberry Pi Ground Station Image** — Pre-built SD card image with Docker stack, auto-connects to Tello on boot, zero-config
- **Custom Companion Board** — ESP32 or Pi Pico as a relay for additional sensors (LIDAR, gas, thermal) mounted on the Tello
- **Home Assistant Integration** — Trigger drone patrols from HA automations (e.g. "fly a perimeter check when motion is detected at night")
- **3D Print Accessories** — Custom payload mounts, sensor brackets, and landing gear extensions

> The MCP server is the single highest-leverage next step — once drone control is exposed as tools, everything in Phases 4+ becomes dramatically easier to build because Claude can orchestrate it all.

## Challenges

### The Networking Problem: Tello WiFi vs. Internet

This is the fundamental challenge. The Tello drone creates its own WiFi access point (`TELLO-XXXXXX` at `192.168.10.1`), and when your machine connects to it, you lose internet access. This is a dealbreaker for production use — you can't reach MCP servers, cloud APIs, or anything else online.

There are a few ways to solve this, each with different trade-offs.

**Option 1: Dual Network Interfaces (simplest and most reliable)**

Use your machine's built-in WiFi to connect to the Tello, and plug in an Ethernet cable for internet. Most laptops and all desktops support this out of the box. Your OS routing table will send traffic to `192.168.10.x` over WiFi and everything else over Ethernet. This "just works" on Linux, macOS, and Windows without any special configuration — the OS prefers the wired interface for default gateway automatically.

**Option 2: USB WiFi Adapter (no Ethernet available)**

If you don't have Ethernet access, grab a cheap USB WiFi dongle. Connect the dongle to the Tello AP, and keep your built-in WiFi on your home/office network. You'd then configure the backend to bind specifically to the USB adapter's interface for Tello UDP traffic. This requires a small amount of OS-level network config but works well.

**Option 3: Dedicated Ground Station Device (best for production)**

Deploy a small dedicated device — a Raspberry Pi 4/5 or an Intel NUC mini PC — as your permanent "ground station." This device connects its WiFi to the Tello drone and its Ethernet to your local network (router). Your webapp runs on this device via Docker, and you access it from any browser on your regular network.

```
                        YOUR LOCAL NETWORK (with internet)
                        ┌──────────────────────────────────┐
                        │                                  │
  ┌──────────┐    WiFi  │   ┌──────────┐     Ethernet      │    ┌──────────┐
  │  Tello   │◄─────────┤   │  Ground  │◄─────────────────►├───►│  Router  │──► Internet
  │  Drone   │  AP mode  │   │  Station │    192.168.1.x    │    │          │
  │192.168.  │          │   │  (Pi/NUC)│                   │    └──────────┘
  │  10.1    │ UDP 8889 │   │          │                   │
  └──────────┘   8890   │   │ Docker:  │     :3000 (UI)    │    ┌──────────┐
               11111   │   │ backend  │◄────────────────────────│ Your     │
                        │   │ frontend │     :8000 (API)    │    │ Laptop/  │
                        │   └──────────┘                   │    │ Desktop  │
                        │                                  │    └──────────┘
                        └──────────────────────────────────┘
```

The beauty of this setup is that the ground station has two network paths simultaneously — WiFi to the drone, Ethernet to your LAN and internet. Your laptop just opens `http://groundstation.local:3000` in a browser. The backend on the ground station can reach both the Tello (via WiFi UDP) and the internet (via Ethernet) for MCP servers, AI APIs, etc.
