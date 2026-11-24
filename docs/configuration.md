# Configuration

Settings are environment variables starting with `TELLO_`. Put them in `.env` in the repo root (copy `.env.template`). Docker and `./start.sh` both read that file; if you start `uvicorn` by hand, pass `--env-file .env`.

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

Settings for object detection and following are in [vision.md](vision.md).
