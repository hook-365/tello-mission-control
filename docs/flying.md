# Flying guide

How each feature of the app behaves. Getting it running is covered in the [README](../README.md).

## Flight sequencer

Script a routine ("up 50, forward 100, spin 360, flip"), save it with a name like *Victory lap*, and play it with one tap.

1. Click **Sequences** in the bottom bar.
2. Pick a built-in (★ Victory lap, ★ Square dance, ★ Elevator spin, ★ Orbit shot, ★ Reveal) or **+ New sequence**.
3. Add steps with the buttons: **Move** (20-500 cm), **Spin** (1-360°), **Flip** (forward/back/left/right), **Hover** (0.5-10 s), plus the camera steps **Photo**, **Record**, **Orbit** and **Glide** (see [Camera, photos and clips](#camera-photos-and-clips)).
4. Reorder by dragging a row or using the ↑ ↓ arrows. The trash can deletes a step.
5. Name it and hit **Save new**. Saved sequences are plain JSON files in `./data/sequences/`.
6. Press **Play**. The step that's running lights up blue.

With **Auto take off / land** ticked (the default) the drone takes off by itself before step 1 and always lands at the end. Untick it to place Take off and Land steps yourself.

**Stopping:**

| Button | What happens |
|---|---|
| **Abort** (big orange) | Finishes the move in progress (a Tello can't stop mid-move), then lands. Hovers stop right away. Pressing **Land** during a sequence does the same. |
| **Emergency Stop** (or `Esc`) | Cuts the motors instantly. The drone **drops**. Only for real emergencies. |

**Safety checks built in:** a sequence won't start unless the drone is connected and has 30%+ battery (50%+ if it has flips). If the battery drops below 50% mid-run, flips are skipped; below 15%, it lands. Manual flying buttons are locked while a sequence runs. Hovers max out at 10 s because a Tello lands on its own after about 15 s without a command.

**Before you press Play:** fly somewhere with clear space around and above (the built-in descriptions say how much each needs), keep the drone in sight, and start with a short sequence.

## Camera, photos and clips

Photos and video clips from the drone's camera are saved on the computer running the backend, in `./data/media/`. Photos are JPEGs; clips are H.264 MP4s that play in any browser or phone.

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

## Game controller and keyboard

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

## Battery and signal warnings

The status bar shows the Wi-Fi signal next to the battery: the number is the drone's own signal-to-noise reading (higher is better, around 90 right beside it).

| | Amber banner | Red banner + beeping |
|---|---|---|
| Battery | 30% or less: "land soon" | 15% or less: "land now" |
| Wi-Fi signal | 40 or less: "stay closer" | 20 or less: "the drone may land itself" |

The beep repeats every 10 s while something is red; the speaker button on the banner mutes it. Sequences refuse to start on a red signal, and the sequencer shows the warnings above **Play**. The signal thresholds are starting points: if the banners fire too early or too late in your space, change `TELLO_WIFI_SNR_WEAK` / `TELLO_WIFI_SNR_CRITICAL`.

To try the warnings without a drone, start mock mode with a low battery or signal, e.g. `TELLO_MOCK_BATTERY_PCT=20 TELLO_MOCK_WIFI_SNR=30`.

## Flight log and replay

Every connection is recorded to a SQLite file: each telemetry frame (~4 Hz) and every command, grouped into one session from connect to disconnect. Open the clock icon in the status bar to list recorded flights, then pick one to scrub or play back its telemetry alongside the commands that were issued. Sequence runs appear in that list as a start and an outcome (with the reason if one was aborted or failed), and saved photos and clips link to the file.

The log lives at `TELLO_FLIGHT_LOG_PATH` (`data/flights.db`). It grows by roughly 3 MB per hour connected and is never pruned automatically — delete flights from the UI or the API. If the file can't be opened the backend logs an error and carries on without recording.
