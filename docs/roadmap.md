# Roadmap

A roadmap of where this project could go, roughly ordered from most practical to most ambitious.

### Phase 1 — Platform Hardening

- ~~**MCP Server** — Expose drone commands as MCP tools so Claude (or any MCP client) can fly the drone through natural language~~ ✅ Done — see [`mcp_server/`](../mcp_server/README.md)
- ~~**Flight Logging & Replay** — Persist every command + telemetry snapshot to SQLite/TimescaleDB, replay sessions in the UI as a timeline~~ ✅ Done (SQLite) — see [Flight Log & Replay](flying.md#flight-log-and-replay)
- ~~**Gamepad Support** — Map PS5/Xbox controllers via the Gamepad API to `send_rc_control()` for proper analog stick flying~~ ✅ Done — see [Flying with a Game Controller](../README.md#controls)
- **WebRTC Video** — Replace MJPEG with WebRTC for lower latency, better compression, and future peer-to-peer streaming

### Phase 2 — Computer Vision

- ~~**Object Detection Overlay** — Run YOLOv8/v10 on the video stream (on the ground station GPU or via edge TPU) and draw bounding boxes on the HUD~~ ✅ Done (optional) — see [Object Detection & Person Tracking](vision.md)
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
