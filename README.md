# Tello Mission Control

Fly a DJI Tello from a web browser: live video, keyboard or game-controller flying, saved flight routines, photos and clips, and a log of every flight. It runs entirely on your own computer.

```
Browser  ←→  this app (on your computer)  ←→  Tello over its own Wi-Fi
```

<img width="800" alt="Tello Web Controller Interface" src="https://github.com/user-attachments/assets/9ba9d593-b2ef-4b7d-b769-9882847af1cb">

> **Status:** everything here has been tested against a built-in pretend drone, and nothing has been flown on a real Tello yet. Treat first real flights as a test: open space, short hops, a finger on **Land**.

## 1. Get it running (no drone needed)

Do this on your normal Wi-Fi. The drone's Wi-Fi has no internet, so nothing can be downloaded once you have joined it.

```bash
git clone https://github.com/hook-365/tello-mission-control.git
cd tello-mission-control
```

Then pick one:

| | You need | Run | Open |
|---|---|---|---|
| **A. Script** (macOS, Linux) | Python 3.12 or 3.13, Node.js 20+ | `./start.sh` | http://localhost:8000 |
| **B. Docker** (any OS) | Docker | `cp .env.template .env` then `docker compose up --build` | http://localhost:3000 |
| **C. By hand** (Windows, or if you prefer) | Python 3.12 or 3.13, Node.js 20+ | [the commands below](#running-by-hand) | http://localhost:8000 |

Click **Connect**. You are now flying the pretend drone: it answers every command, shows a placeholder video picture and reports fake battery and height. Try the controls, build a sequence, plug in a controller.

## 2. Fly the real drone

1. In `.env`, set `TELLO_USE_MOCK_DRONE=false`.
2. Charge the battery. Sequences need 30% or more, flips 50%.
3. Turn the Tello on and join its Wi-Fi (`TELLO-XXXXXX`) from the computer running the app.
4. Start the app the same way as before, open it and click **Connect**.

Things worth knowing:

- **Use option A or C for the real drone if you can.** The drone sends video and telemetry back over UDP, and Docker can get in the way of that, especially on macOS and Windows. Docker on Linux should work; if **Connect** times out, switch to A or C.
- **Windows or macOS firewall prompt:** allow Python to accept incoming connections, or the video and telemetry never arrive.
- **Tello "TT" / RoboMaster TT:** with the expansion module attached, the Wi-Fi name may be `RMTT-XXXXXX` and the module's switch has to be in direct-connect mode (not router mode). This is from DJI's documentation, not something tested here.
- **No internet while flying.** That is fine for the app. If you want both at once, see [docs/networking.md](docs/networking.md).

## Controls

**Keyboard** (click the page first)

| Key | Action |
|---|---|
| `T` / `L` | Take off / land |
| `W` `A` `S` `D` | Forward, left, back, right |
| `Space` / `Shift` | Up / down |
| `Q` / `E` | Spin left / right |
| `Esc` | **Emergency stop: motors cut, the drone drops** |

Keys start in **Tap** mode: one hop per press. Switch to **Hold to fly** in the Flight Controls panel to fly smoothly while a key is held.

**Game controller** (Xbox, PlayStation, most USB or Bluetooth pads). Press any button once so the browser notices it.

| Control | Action |
|---|---|
| **Hold LB or RB** | Required to fly. Let go and the drone stops and hovers. |
| Left stick | Up/down and spin |
| Right stick | Forward/back and sideways |
| LB or RB + Start | Take off |
| Back | Land |
| Click both sticks together | **Emergency stop: the drone drops** |

Set **Stick speed** to 50% or lower indoors.

## What else it does

- **Sequences:** build a routine from steps (move, spin, flip, hover, photo, record, orbit, glide), save it and play it with one tap. Five are built in.
- **Photos and clips:** saved to `./data/media/` and shown in the Gallery.
- **Warnings:** amber and red banners for low battery and weak Wi-Fi signal.
- **Flight log:** every session is recorded and can be played back from the clock icon.
- **Object detection and person following:** optional and a large download. See [docs/vision.md](docs/vision.md).
- **Fly it with Claude:** an MCP server exposes the drone as tools. See [mcp_server/README.md](mcp_server/README.md).

Details for all of these are in [docs/flying.md](docs/flying.md).

## Safety

- Clear space around and above the drone, and keep it in sight.
- **Land** is the normal way down. **Emergency stop** cuts the motors mid-air.
- The drone hovers by itself if stick input stops for half a second (controller unplugged, browser closed, Wi-Fi hiccup).
- A Tello lands on its own after about 15 seconds without any command.
- Closing the app or disconnecting while airborne lands the drone first.
- There is no password on the app. Anyone on the same network who can reach the computer can fly the drone.

## If something goes wrong

| Problem | Try |
|---|---|
| **Connect** times out | Check the computer is on the drone's Wi-Fi and `TELLO_USE_MOCK_DRONE=false`. With Docker, switch to option A or C. |
| Connected but no video | Allow Python through the firewall. A VPN can also block it. |
| Controller not detected | Press a button on it with the page in focus. Chrome and Edge have the best support. |
| A sequence won't start | Battery under 30% (50% with flips) or a red signal warning. The message says which. |
| Orbit or Glide drifts the wrong way sideways | Set `TELLO_GO_Y_IS_LEFT=false` in `.env`. |
| Used Docker first, now `start.sh` can't save photos or the flight log | Docker created `./data` as root. Run `sudo chown -R $USER data`. |
| Port already in use | Change `TELLO_API_PORT` (and `TELLO_FRONTEND_PORT` for Docker) in `.env`. |

## Running by hand

What `start.sh` does, as separate commands. On Windows use PowerShell (not tested on Windows yet).

```bash
cp .env.template .env                                  # Windows: copy .env.template .env

cd frontend && npm ci && npm run build && cd ..        # builds the web UI once

python3 -m venv backend/.venv                          # Windows: py -3.12 -m venv backend\.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
                                                       # Windows: backend\.venv\Scripts\python -m pip install -r backend\requirements.txt

backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --env-file .env
                                                       # Windows: backend\.venv\Scripts\python -m uvicorn ...same arguments
```

Run the last command from the repo root so photos, sequences and the flight log land in `./data`, the same folder Docker uses.

## More documentation

| | |
|---|---|
| [docs/flying.md](docs/flying.md) | Sequencer, camera moves, controller, warnings, flight log |
| [docs/configuration.md](docs/configuration.md) | Every setting in `.env` |
| [docs/api.md](docs/api.md) | REST and WebSocket API, with `curl` examples |
| [docs/vision.md](docs/vision.md) | Object detection and person following |
| [docs/networking.md](docs/networking.md) | Keeping internet while on the drone's Wi-Fi |
| [mcp_server/README.md](mcp_server/README.md) | Flying it from Claude |
| [docs/roadmap.md](docs/roadmap.md) | What is done and what could come next |
| [CLAUDE.md](CLAUDE.md) | Code layout and design rules, for anyone changing the code |

## Developing

```bash
cd backend && source .venv/bin/activate && python -m pytest     # backend tests, pretend drone only
cd frontend && npx vitest run                                    # frontend tests
cd frontend && npm run dev                                       # UI with hot reload on :5173, expects the backend on :8000
```

## Credits

Based on [thakorneyp11/tello-mission-control](https://github.com/thakorneyp11/tello-mission-control) ([demo video](https://youtube.com/shorts/Ex-KBuxlEQw)). This copy keeps that project's history, so its fixes can be merged in with `git fetch upstream && git merge upstream/main`.
