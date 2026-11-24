# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Implementation Guidelines
Please review all relevant files with critical thinking, analyze with thinking process, plan todo with thinking process, implement with testing and verification. Create testcases to ensure requirements work as expected without interfering with other functionalities.

If you found that the task is really huge and using agent teammates is more efficient, please create an agent team with multiple teammates to implement this requirements in parallel. from review codebase, technical design, UX/UI designing, reviewing/discussing codes/designs with each other, until the development/process ends and perform testing & verification together. If there's still room of improvements or any agent found any issue/bug, please handle it too.

Please keep in mind that this implementation will not only be used for these existing customers. So it needs to be scalable, configurable, and easy to maintain. Please maintain code quality for this implementation too.

For Frontend implementation, use `frontend-design` plugin skill to ensure minimal, smooth, and seamless UX for new implementations.
Use `context-extractor` agent skill to extract context from huge documents or code scripts from this codebase when needed.
Use `code-simplifier` plugin skill to simplify code and improve readability.
Ask for context if needed.

## Project Overview

**Tello Web Controller** — a locally-deployed web app for controlling a DJI Tello drone via browser. Two-tier client-server architecture: React frontend communicates with FastAPI backend over HTTP (commands) and WebSocket (telemetry). The backend exclusively owns the UDP connection to the drone.

## Architecture

```
React App (localhost:3000) ←HTTP/WS→ FastAPI + djitellopy (localhost:8000) ←UDP→ Tello (192.168.10.1)
```

- **Frontend**: React 18 + Vite, TailwindCSS, Zustand for state, served via Nginx in Docker
- **Backend**: Python 3.12+, FastAPI, djitellopy (Tello SDK), OpenCV for video encoding
- **Deployment**: Docker Compose with two services (`frontend`, `backend`)

## Build & Run Commands

### Docker (recommended)
```bash
cp .env.template .env               # First time setup
docker compose up --build            # Build and start both services
docker compose up -d                 # Start detached
docker compose down                  # Stop all services
```

Services:
- **Frontend**: http://localhost:3000 (Nginx serving React + proxying API)
- **Backend**: http://localhost:8000 (FastAPI)

### Backend (standalone dev)
```bash
cd backend && source .venv/bin/activate
TELLO_USE_MOCK_DRONE=true uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (standalone dev)
```bash
cd frontend && npm ci && npm run dev     # Dev server on :5173
cd frontend && npm run build             # Production build
```

### Tests
```bash
cd backend && source .venv/bin/activate
python -m pytest -v                             # All backend tests
python -m pytest tests/test_drone_manager.py    # Unit tests only
python -m pytest tests/test_control.py          # API integration tests
python -m pytest tests/test_video.py            # Video streaming tests
python -m pytest tests/test_telemetry.py        # WebSocket tests

cd mcp_server && .venv/bin/python -m pytest tests   # MCP server tests (separate venv)

cd frontend && npx vitest                       # Frontend tests
cd frontend && npx vitest run                   # Frontend tests (CI mode)
```

## Project Structure

```
├── backend/                        # FastAPI + djitellopy
│   ├── Dockerfile                  # Python 3.12-slim + OpenCV deps
│   ├── app/
│   │   ├── main.py                 # FastAPI app, lifespan, CORS, router wiring
│   │   ├── config.py               # pydantic-settings with TELLO_ env prefix
│   │   ├── routers/
│   │   │   ├── control.py          # POST /api/control/* (connect, takeoff, land, move, rotate, flip, emergency)
│   │   │   ├── rc.py               # Stick control: POST /api/control/rc, WS /api/ws/rc
│   │   │   ├── video.py            # GET /api/video/stream (MJPEG), POST /api/video/snapshot
│   │   │   ├── media.py            # /api/media: saved photos and clips, recording
│   │   │   ├── telemetry.py        # WS /api/ws/telemetry (telemetry, command log, sequence/media/detection events)
│   │   │   ├── sequences.py        # /api/sequences: CRUD, run, abort, run status
│   │   │   ├── flights.py          # GET/DELETE /api/flights (recorded sessions)
│   │   │   ├── vision.py           # /api/vision (503 unless TELLO_VISION_ENABLED)
│   │   │   └── status.py           # GET /api/status, GET /api/telemetry
│   │   ├── services/
│   │   │   ├── drone_manager.py    # Singleton Tello wrapper + asyncio.Lock + MockTello
│   │   │   ├── telemetry_service.py # Background 4Hz polling + pub-sub broadcasting
│   │   │   ├── flight_alerts.py    # Battery / Wi-Fi alert levels from config thresholds
│   │   │   ├── sequence_store.py   # Saved sequences as JSON files (+ built-ins)
│   │   │   ├── sequence_runner.py  # Runs one sequence at a time: pre-flight checks, abort, progress events
│   │   │   ├── media.py            # Photos + H.264 clip recording to TELLO_MEDIA_DIR
│   │   │   ├── flight_recorder.py  # SQLite flight log; subscribes to telemetry + command log
│   │   │   ├── detector.py         # Detector protocol + lazy-imported YoloDetector (optional dep)
│   │   │   ├── tracking.py         # Pure follow-target controller (box -> stick velocities)
│   │   │   └── vision_service.py   # Detection loop, broadcast, tracking; yields to pilot override
│   │   └── models/
│   │       ├── commands.py         # Pydantic request/response schemas with validation
│   │       ├── sequences.py        # Sequence steps, run request and run status
│   │       └── telemetry.py        # Telemetry data models
│   └── tests/                      # pytest, all against MockTello
├── frontend/                       # React + Vite + TailwindCSS
│   ├── Dockerfile                  # Multi-stage: Node build → Nginx runtime
│   ├── nginx.conf                  # SPA fallback + API/WS/MJPEG reverse proxy
│   └── src/
├── mcp_server/                     # MCP server: thin REST client, own venv (mcp SDK v2 conflicts with backend pins)
├── sample_drone_integration/       # djitellopy reference scripts for developers
├── docs/                           # User guide, API and settings reference; original PRD/architecture
├── start.sh                        # Non-Docker launcher: venv, UI build, uvicorn serving API + UI on one port
├── docker-compose.yml              # Both services orchestration (./data holds sequences, media, flight log)
├── docker-compose.vision.yml       # Override: build the backend with the optional vision extra
├── .github/workflows/tests.yml     # CI: backend, frontend and MCP server tests
├── .env.template                   # Environment variable template
└── .env                            # Local environment config (gitignored)
```

## Key Design Constraints

- **Command serialization**: Tello SDK processes one command at a time. `DroneManager` uses `asyncio.Lock` to serialize all commands. Emergency bypasses the lock for instant response. Stick updates (`send_rc`) are dropped, not queued, while another command holds the lock, and a watchdog hovers the drone if they stop arriving (`TELLO_RC_TIMEOUT_S`).
- **One event fan-out**: `DroneManager.broadcast_event` carries command-log entries, sequence progress and media events to every subscriber (telemetry WebSocket, flight recorder). Subscribers must check `type` and must not raise.
- **Sequences own the drone while running**: manual flight commands return 409, Land aborts the run, and stick input and tracking are refused.
- **Pilot override**: anything that drives the drone automatically (currently person tracking) must register with `DroneManager.add_override_callback` and send sticks via `send_rc(..., source="<name>")`. Every pilot command (and so every sequence step) calls `_notify_override` before reaching the drone, and automation must stop sending the moment it fires. New pilot-facing commands on `DroneManager` need the same call.
- **Vision is optional**: `ultralytics` is never imported at module level. Tests use a fake `Detector`; the real model is not exercised by the test suite.
- **Mock mode**: Set `TELLO_USE_MOCK_DRONE=true` to run without a physical drone. MockTello generates placeholder video frames and simulates all telemetry.
- **Video via MJPEG over HTTP** (`multipart/x-mixed-replace`). Frontend renders with `<img src="/api/video/stream" />`.
- **Telemetry via WebSocket push** at ~4 Hz from a background polling task — not client-polled.
- **Two ways to serve the UI**: Docker uses Nginx (`:3000`, proxies `/api`); without Docker, `main.mount_frontend` serves `frontend/dist` from the backend (`:8000`). The UI only uses relative `/api` URLs, so both work.
- **Docker networking**: Uses standard bridge networking. Frontend Nginx proxies to backend via Docker DNS (`http://backend:8000`). For real drone on Linux, add `network_mode: host` to backend service.
- **No authentication** in v1 — the app runs on the Tello's isolated Wi-Fi network.
- **CORS**: Backend allows `http://localhost:3000` and `http://localhost:5173`.

## API Surface

`docs/api.md` is the full list; keep it current when adding endpoints. The README is the short getting-started page for pilots: reference material goes in `docs/`.

- Control: `POST /api/control/{connect,disconnect,takeoff,land,emergency,move,rotate,flip,rc}`, `WS /api/ws/rc`
- Video and media: `/api/video/stream` (MJPEG), `/api/video/snapshot`, `/api/media` (photos, clips, recording)
- State: `GET /api/status`, `GET /api/telemetry`, `WS /api/ws/telemetry`
- Sequences: `/api/sequences` (CRUD), `/run`, `/{id}/run`, `/abort`, `/run/status`
- Flight log: `GET /api/flights`, `GET/DELETE /api/flights/{id}`
- Vision (optional): `GET /api/vision`, `POST /api/vision/{detect,track}`
- MCP: `mcp_server/` wraps the above as tools; add a tool there when adding a pilot-facing endpoint

## Environment Variables

All prefixed with `TELLO_`. See `.env.template` for the full list with defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `TELLO_USE_MOCK_DRONE` | `false` | Use fake drone for development |
| `TELLO_TELLO_HOST` | `192.168.10.1` | Drone IP address |
| `TELLO_API_PORT` | `8000` | Backend server port |
| `TELLO_FRONTEND_PORT` | `3000` | Frontend server port (Docker) |
| `TELLO_TELEMETRY_POLL_HZ` | `4.0` | Telemetry polling frequency |
| `TELLO_VIDEO_FPS` | `30` | Video stream frame rate |
| `TELLO_VIDEO_JPEG_QUALITY` | `70` | JPEG compression quality (1-100) |
| `TELLO_CORS_ORIGINS` | `["http://localhost:3000","http://localhost:5173"]` | Allowed CORS origins |

## Reference Documents

- `docs/flying.md`, `docs/api.md`, `docs/configuration.md`, `docs/vision.md`, `docs/networking.md`, `docs/roadmap.md` — current user and reference docs
- `docs/requirement-*.md` — the original project's PRD, architecture and design notes (historical; they predate most features)
- `sample_drone_integration/` — reference scripts showing djitellopy usage patterns
