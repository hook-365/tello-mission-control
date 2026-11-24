# Object detection and person following (optional)

Off by default, because it needs PyTorch (several GB). To enable it:

```bash
# Without Docker: install the extra once, set TELLO_VISION_ENABLED=true in .env, then start as usual
./start.sh --mock        # first run creates backend/.venv; Ctrl+C once it is up
backend/.venv/bin/python -m pip install -r backend/requirements-vision.txt   # or: uv pip install --python backend/.venv/bin/python -r ...
./start.sh

# Docker
docker compose -f docker-compose.yml -f docker-compose.vision.yml up --build
```

**Switch Detect on once while you still have internet.** The model file is downloaded the first time, and the drone's Wi-Fi has no internet.

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
