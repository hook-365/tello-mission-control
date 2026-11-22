from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from app.config import settings
from app.services.flight_alerts import battery_level, parse_snr, signal_level
from app.models.commands import FLIP_CODES, FlipDirection, MoveDirection, RotateDirection

logger = logging.getLogger(__name__)


class DroneNotConnectedError(Exception):
    pass


class DroneNotFlyingError(Exception):
    pass


class MockTello:
    """Fake Tello for development without a physical drone."""

    def __init__(self) -> None:
        self._connected = False
        self._flying = False
        self._battery = settings.mock_battery_pct
        self._wifi_snr = settings.mock_wifi_snr
        self._height = 0
        self._flight_time = 0
        self._yaw = 0
        self._pitch = 0
        self._roll = 0
        self._speed_x = 0
        self._speed_y = 0
        self._speed_z = 0
        self._barometer = 0.0
        self._temp_high = 65.0
        self._temp_low = 60.0

    @staticmethod
    def _simulate_flight_time() -> None:
        """Optionally pretend a command takes real time (blocking, like djitellopy)."""
        if settings.mock_command_delay_s > 0:
            time.sleep(settings.mock_command_delay_s)

    def _reset_flight_state(self) -> None:
        self._flying = False
        self._height = 0
        self._barometer = 0.0
        self._speed_x = 0
        self._speed_y = 0
        self._speed_z = 0

    def connect(self) -> None:
        self._connected = True
        logger.info("MockTello: connected")

    def end(self) -> None:
        self._connected = False
        self._flying = False
        self._height = 0
        self._barometer = 0.0
        logger.info("MockTello: disconnected")

    def takeoff(self) -> None:
        self._simulate_flight_time()
        self._flying = True
        self._height = 50
        self._barometer = 50.0
        logger.info("MockTello: takeoff")

    def land(self) -> None:
        self._simulate_flight_time()
        self._reset_flight_state()
        logger.info("MockTello: land")

    def emergency(self) -> None:
        self._reset_flight_state()
        logger.info("MockTello: emergency stop")

    def move_forward(self, x: int) -> None:
        self._simulate_flight_time()
        self._speed_y = x
        logger.info("MockTello: move_forward %dcm", x)

    def move_back(self, x: int) -> None:
        self._simulate_flight_time()
        self._speed_y = -x
        logger.info("MockTello: move_back %dcm", x)

    def move_left(self, x: int) -> None:
        self._simulate_flight_time()
        self._speed_x = -x
        logger.info("MockTello: move_left %dcm", x)

    def move_right(self, x: int) -> None:
        self._simulate_flight_time()
        self._speed_x = x
        logger.info("MockTello: move_right %dcm", x)

    def move_up(self, x: int) -> None:
        self._simulate_flight_time()
        self._height += x
        self._barometer = float(self._height)
        self._speed_z = x
        logger.info("MockTello: move_up %dcm", x)

    def move_down(self, x: int) -> None:
        self._simulate_flight_time()
        self._height = max(0, self._height - x)
        self._barometer = float(self._height)
        self._speed_z = -x
        logger.info("MockTello: move_down %dcm", x)

    def rotate_clockwise(self, x: int) -> None:
        self._simulate_flight_time()
        self._yaw = (self._yaw + x) % 360
        logger.info("MockTello: rotate_cw %ddeg", x)

    def rotate_counter_clockwise(self, x: int) -> None:
        self._simulate_flight_time()
        self._yaw = (self._yaw - x) % 360
        logger.info("MockTello: rotate_ccw %ddeg", x)

    def flip(self, direction: str) -> None:
        if direction not in ("l", "r", "f", "b"):
            raise ValueError(f"Invalid flip direction: {direction}")
        self._simulate_flight_time()
        logger.info("MockTello: flip %s", direction)

    # -- Telemetry getters (matching djitellopy.Tello API) --

    def get_battery(self) -> int:
        return self._battery

    def get_height(self) -> int:
        return self._height

    def get_flight_time(self) -> int:
        return self._flight_time

    def get_highest_temperature(self) -> float:
        return self._temp_high

    def get_lowest_temperature(self) -> float:
        return self._temp_low

    def get_pitch(self) -> int:
        return self._pitch

    def get_roll(self) -> int:
        return self._roll

    def get_yaw(self) -> int:
        return self._yaw

    def get_speed_x(self) -> int:
        return self._speed_x

    def get_speed_y(self) -> int:
        return self._speed_y

    def get_speed_z(self) -> int:
        return self._speed_z

    def get_barometer(self) -> float:
        return self._barometer

    def get_distance_tof(self) -> int:
        return self._height

    def send_rc_control(self, lr: int, fb: int, ud: int, yaw: int) -> None:
        # Fire-and-forget like the real SDK's "rc a b c d". Nudge the fake
        # telemetry so stick input is visible on the HUD.
        self._speed_x, self._speed_y, self._speed_z = fb, lr, ud
        if self._flying:
            self._height = max(20, min(1000, self._height + ud // 10))
            self._yaw = (self._yaw + yaw // 10) % 360

    def query_wifi_signal_noise_ratio(self) -> str:
        return str(self._wifi_snr)

    # -- Video --

    def streamon(self) -> None:
        logger.info("MockTello: stream on")

    def streamoff(self) -> None:
        logger.info("MockTello: stream off")

    def get_frame_read(self) -> "MockFrameRead":
        return MockFrameRead()


class MockFrameRead:
    """Fake frame reader that generates a placeholder test pattern."""

    @property
    def frame(self):
        import numpy as np

        # 960x720 dark frame with text overlay
        img = np.zeros((720, 960, 3), dtype=np.uint8)
        img[:] = (40, 40, 40)  # dark gray background

        try:
            import cv2

            cv2.putText(
                img, "MOCK DRONE", (280, 340),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3,
            )
            cv2.putText(
                img, "No drone connected", (310, 400),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 1,
            )
        except ImportError:
            pass

        return img


class DroneManager:
    """Singleton service owning the Tello connection.

    All commands are serialized through an asyncio.Lock.
    Blocking djitellopy calls are offloaded via asyncio.to_thread().
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tello: Any | None = None
        self._connected: bool = False
        self._flying: bool = False
        self._streaming: bool = False
        self._frame_read: Any | None = None
        self._command_log_callbacks: list[Callable] = []
        self._wifi_snr: int | None = None
        # Stick (rc) state
        self._rc_moving = False
        self._rc_last = 0.0
        self._rc_watchdog: asyncio.Task | None = None

    # -- Properties --

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_flying(self) -> bool:
        return self._flying

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    @property
    def wifi_snr(self) -> int | None:
        """Last Wi-Fi signal-to-noise reading, or None if unknown."""
        return self._wifi_snr

    @property
    def tello(self) -> Any | None:
        return self._tello

    # -- Command log broadcasting --

    def add_command_log_callback(self, callback: Callable) -> None:
        self._command_log_callbacks.append(callback)

    def remove_command_log_callback(self, callback: Callable) -> None:
        try:
            self._command_log_callbacks.remove(callback)
        except ValueError:
            pass

    async def _broadcast_command_log(
        self,
        command: str,
        params: dict,
        result: str,
        error: str | None = None,
    ) -> None:
        await self.broadcast_event({
            "type": "command_log",
            "data": {
                "command": command,
                "params": params,
                "result": result,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })

    async def broadcast_event(self, entry: dict) -> None:
        """Send any JSON-able event dict to every WebSocket subscriber."""
        dead: list[Callable] = []
        for cb in self._command_log_callbacks:
            try:
                await cb(entry)
            except Exception:
                dead.append(cb)
        for cb in dead:
            try:
                self._command_log_callbacks.remove(cb)
            except ValueError:
                pass

    # -- Core execute method --

    async def execute(self, fn: Callable, *args: Any) -> Any:
        """Execute a blocking djitellopy method with lock serialization."""
        async with self._lock:
            return await asyncio.to_thread(fn, *args)

    # -- Connection --

    async def connect(self) -> dict:
        if self._connected:
            battery = await self.get_battery()
            return {"ok": True, "status": "already_connected", "battery": battery}

        if settings.use_mock_drone:
            self._tello = MockTello()
        else:
            from djitellopy import Tello

            self._tello = Tello(host=settings.tello_host)
            self._tello.RETRY_COUNT = settings.tello_retry_count

        await self.execute(self._tello.connect)
        self._connected = True
        battery = await self.get_battery()
        await self.refresh_wifi_snr()
        await self._broadcast_command_log("connect", {}, "ok")
        return {"ok": True, "status": "connected", "battery": battery}

    async def disconnect(self) -> dict:
        if not self._connected:
            return {"ok": True, "status": "already_disconnected"}

        if self._streaming:
            try:
                await self.execute(self._tello.streamoff)
            except Exception as e:
                logger.warning("Failed to stop stream during disconnect: %s", e)
            self._streaming = False
            self._frame_read = None

        if self._flying:
            try:
                await self.execute(self._tello.land)
            except Exception as e:
                logger.warning("Failed to land during disconnect: %s", e)
            self._flying = False

        await self.execute(self._tello.end)
        self._connected = False
        self._tello = None
        self._wifi_snr = None
        self._rc_moving = False
        await self._broadcast_command_log("disconnect", {}, "ok")
        return {"ok": True, "status": "disconnected"}

    # -- Flight commands --

    async def takeoff(self) -> dict:
        self._require_connected()
        await self.execute(self._tello.takeoff)
        self._flying = True
        await self._broadcast_command_log("takeoff", {}, "ok")
        return {"ok": True, "message": "Takeoff successful"}

    async def land(self) -> dict:
        self._require_connected()
        self._rc_moving = False  # land overrides any stick input
        await self.execute(self._tello.land)
        self._flying = False
        await self._broadcast_command_log("land", {}, "ok")
        return {"ok": True, "message": "Landing successful"}

    async def emergency(self) -> dict:
        """Emergency stop — bypasses the lock for instant response."""
        self._rc_moving = False
        if self._tello:
            await asyncio.to_thread(self._tello.emergency)
            self._flying = False
        await self._broadcast_command_log("emergency", {}, "ok")
        return {"ok": True, "message": "Emergency stop executed"}

    # -- Movement --

    async def move(self, direction: MoveDirection, distance_cm: int) -> dict:
        self._require_connected()
        self._require_flying()
        await self.stop_rc()
        method_map = {
            MoveDirection.forward: self._tello.move_forward,
            MoveDirection.back: self._tello.move_back,
            MoveDirection.left: self._tello.move_left,
            MoveDirection.right: self._tello.move_right,
            MoveDirection.up: self._tello.move_up,
            MoveDirection.down: self._tello.move_down,
        }
        fn = method_map[direction]
        await self.execute(fn, distance_cm)
        await self._broadcast_command_log(
            "move", {"direction": direction.value, "distance_cm": distance_cm}, "ok"
        )
        return {"ok": True, "message": f"Moved {direction.value} {distance_cm}cm"}

    # -- Rotation --

    async def rotate(self, direction: RotateDirection, angle_deg: int) -> dict:
        self._require_connected()
        self._require_flying()
        await self.stop_rc()
        if direction == RotateDirection.cw:
            await self.execute(self._tello.rotate_clockwise, angle_deg)
        else:
            await self.execute(self._tello.rotate_counter_clockwise, angle_deg)
        await self._broadcast_command_log(
            "rotate", {"direction": direction.value, "angle_deg": angle_deg}, "ok"
        )
        return {"ok": True, "message": f"Rotated {direction.value} {angle_deg}°"}

    # -- Flips --

    async def flip(self, direction: FlipDirection) -> dict:
        self._require_connected()
        self._require_flying()
        await self.stop_rc()
        await self.execute(self._tello.flip, FLIP_CODES[direction])
        await self._broadcast_command_log("flip", {"direction": direction.value}, "ok")
        return {"ok": True, "message": f"Flipped {direction.value}"}

    # -- Video streaming --

    async def stream_on(self) -> dict:
        self._require_connected()
        if self._streaming:
            return {"ok": True, "message": "Stream already active"}
        await self.execute(self._tello.streamon)
        self._frame_read = await asyncio.to_thread(self._tello.get_frame_read)
        self._streaming = True
        await self._broadcast_command_log("stream_on", {}, "ok")
        return {"ok": True, "message": "Video stream started"}

    async def stream_off(self) -> dict:
        self._require_connected()
        if not self._streaming:
            return {"ok": True, "message": "Stream already stopped"}
        await self.execute(self._tello.streamoff)
        self._frame_read = None
        self._streaming = False
        await self._broadcast_command_log("stream_off", {}, "ok")
        return {"ok": True, "message": "Video stream stopped"}

    def get_frame(self):
        """Get the current frame as a numpy array. Non-blocking (reads cached frame)."""
        if not self._frame_read:
            return None
        return self._frame_read.frame

    # -- Stick control (rc) --

    @property
    def rc_moving(self) -> bool:
        return self._rc_moving

    async def send_rc(self, lr: int, fb: int, ud: int, yaw: int) -> bool:
        """Send one stick update. Returns False if skipped because a command is busy.

        "rc" is fire-and-forget on the Tello, so this is fast, but it still goes
        through the lock so it can never interleave with a move/flip/land.
        If a discrete command is running we drop this update rather than queue
        it: a stale stick position arriving late is worse than a missed one.
        """
        self._require_connected()
        self._require_flying()
        if self._lock.locked():
            return False
        cap = max(10, min(100, settings.rc_speed_limit_pct))
        vals = [max(-100, min(100, int(v))) * cap // 100 for v in (lr, fb, ud, yaw)]
        await self.execute(self._tello.send_rc_control, *vals)
        self._rc_last = time.monotonic()
        was_moving = self._rc_moving
        self._rc_moving = any(vals)
        if self._rc_moving and not was_moving:
            await self._broadcast_command_log("stick_control", {}, "ok")
        if self._rc_moving:
            self._ensure_rc_watchdog()
        return True

    async def stop_rc(self) -> None:
        """Zero the sticks (hover) if stick control left the drone moving."""
        if not self._rc_moving:
            return
        self._rc_moving = False
        if self._connected and self._flying and self._tello is not None:
            try:
                await self.execute(self._tello.send_rc_control, 0, 0, 0, 0)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to zero sticks: %s", e)

    def _ensure_rc_watchdog(self) -> None:
        if self._rc_watchdog is None or self._rc_watchdog.done():
            self._rc_watchdog = asyncio.create_task(self._rc_watchdog_loop())

    async def _rc_watchdog_loop(self) -> None:
        """Dead-man on the server side: if the browser stops sending (tab hidden,
        Wi-Fi hiccup, controller unplugged), stop the drone and hover."""
        while self._rc_moving:
            await asyncio.sleep(0.1)
            if self._rc_moving and time.monotonic() - self._rc_last > settings.rc_timeout_s:
                logger.info("Stick input timed out, hovering")
                await self.stop_rc()
                await self._broadcast_command_log(
                    "stick_timeout", {}, "ok", error=None
                )

    # -- Wi-Fi signal --

    async def refresh_wifi_snr(self) -> int | None:
        """Ask the drone for its Wi-Fi SNR ("wifi?").

        Unlike the telemetry getters this is a real command on the command
        socket, so it goes through the lock. If a flight command is in progress
        we skip this round and keep the last reading rather than queue behind it.
        """
        if not self._connected or not self._tello or self._lock.locked():
            return self._wifi_snr
        query = getattr(self._tello, "query_wifi_signal_noise_ratio", None)
        if query is None:
            return self._wifi_snr
        try:
            raw = await self.execute(query)
        except Exception as e:  # noqa: BLE001 - a flaky reading must never break telemetry
            logger.debug("Wi-Fi query failed: %s", e)
            return self._wifi_snr
        snr = parse_snr(raw)
        if snr is not None:
            self._wifi_snr = snr
        return self._wifi_snr

    # -- Telemetry (no lock needed — reads cached state) --

    async def get_battery(self) -> int:
        if not self._tello:
            return 0
        return await asyncio.to_thread(self._tello.get_battery)

    async def get_telemetry(self) -> dict:
        if not self._tello:
            return {
                "battery": 0, "height": 0, "flight_time": 0,
                "temperature": {"high": 0.0, "low": 0.0},
                "attitude": {"pitch": 0, "roll": 0, "yaw": 0},
                "speed": {"x": 0, "y": 0, "z": 0},
                "barometer": 0.0, "tof_distance": 0,
                "wifi_snr": None, "battery_level": "ok", "signal_level": "unknown",
            }
        t = self._tello

        def _read_all() -> dict:
            return {
                "battery": t.get_battery(),
                "height": t.get_height(),
                "flight_time": t.get_flight_time(),
                "temperature": {
                    "high": t.get_highest_temperature(),
                    "low": t.get_lowest_temperature(),
                },
                "attitude": {
                    "pitch": t.get_pitch(),
                    "roll": t.get_roll(),
                    "yaw": t.get_yaw(),
                },
                "speed": {
                    "x": t.get_speed_x(),
                    "y": t.get_speed_y(),
                    "z": t.get_speed_z(),
                },
                "barometer": t.get_barometer(),
                "tof_distance": t.get_distance_tof(),
            }

        data = await asyncio.to_thread(_read_all)
        data["wifi_snr"] = self._wifi_snr
        data["battery_level"] = battery_level(data["battery"])
        data["signal_level"] = signal_level(self._wifi_snr)
        return data

    # -- Guards --

    def _require_connected(self) -> None:
        if not self._connected:
            raise DroneNotConnectedError("Drone is not connected")

    def _require_flying(self) -> None:
        if not self._flying:
            raise DroneNotFlyingError("Drone is not flying (call takeoff first)")

    # -- Cleanup --

    async def shutdown(self) -> None:
        self._rc_moving = False
        if self._rc_watchdog is not None:
            self._rc_watchdog.cancel()
        if self._connected:
            try:
                await self.disconnect()
            except Exception as e:
                logger.error("Error during shutdown disconnect: %s", e)
