from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from app.config import settings
from app.services.detector import Detection, Detector, VisionUnavailableError
from app.services.drone_manager import DroneManager
from app.services.tracking import HOVER, TrackingGains, compute_rc, pick_target

logger = logging.getLogger(__name__)

#: A frame that has not changed for this long means the video link has stalled.
STALE_FRAME_S = 1.0


class VisionService:
    """Runs object detection on the video stream and, optionally, follows a target.

    Detection is off until switched on, so an idle backend uses no GPU. The
    detector is built on first use because loading the model is slow.

    Tracking drives the drone through ``DroneManager.send_rc`` and stops the
    moment a pilot takes over (see ``DroneManager.add_override_callback``).
    With no target, or a stalled video stream, it hovers.
    """

    def __init__(
        self,
        drone_manager: DroneManager,
        detector_factory: Callable[[], Detector],
    ) -> None:
        self._dm = drone_manager
        self._detector_factory = detector_factory
        self._detector: Detector | None = None
        self._subscribers: set[Callable] = set()
        self._task: asyncio.Task | None = None
        self._detecting = False
        self._tracking = False
        self._target_label = "person"
        self._last_frame: Any = None
        self._last_frame_at = 0.0
        self._dm.add_override_callback(self._on_pilot_override)

    # -- State --

    def state(self) -> dict[str, Any]:
        return {
            "available": True,
            "detecting": self._detecting,
            "tracking": self._tracking,
            "target": self._target_label,
            "hz": settings.vision_hz,
        }

    def subscribe(self, callback: Callable) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: Callable) -> None:
        self._subscribers.discard(callback)

    # -- Control --

    async def set_detecting(self, enabled: bool) -> None:
        if enabled and self._detector is None:
            # Model load (and first-run weight download) blocks for seconds.
            self._detector = await asyncio.to_thread(self._detector_factory)
        if not enabled:
            await self.set_tracking(False)
        self._detecting = enabled
        if enabled and self._task is None:
            self._task = asyncio.create_task(self._loop())
        await self._broadcast([], None, stale=False)

    async def set_tracking(self, enabled: bool, target: str | None = None) -> None:
        if not enabled:
            if self._tracking:
                self._tracking = False
                await self._dm.stop_rc()
                logger.info("Tracking stopped")
            return
        if not self._dm.is_flying:
            raise VisionUnavailableError("Drone is not flying")
        if target:
            self._target_label = target
        await self.set_detecting(True)
        self._tracking = True
        logger.info("Tracking started: %s", self._target_label)

    def _on_pilot_override(self, reason: str) -> None:
        """A human (or land/emergency) took control: let go at once, send nothing more."""
        if self._tracking:
            self._tracking = False
            logger.info("Tracking cancelled by %s", reason)

    async def stop(self) -> None:
        self._detecting = False
        self._tracking = False
        self._dm.remove_override_callback(self._on_pilot_override)
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # -- Loop --

    async def _loop(self) -> None:
        interval = 1.0 / settings.vision_hz
        while True:
            started = time.monotonic()
            if self._detecting:
                try:
                    await self._step()
                except Exception as e:
                    logger.warning("Vision step failed: %s", e)
                    if self._tracking:
                        self._tracking = False
                        await self._safe_hover()
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))

    async def _step(self) -> None:
        frame = self._dm.get_frame() if self._dm.is_streaming else None
        now = time.monotonic()
        if frame is not None and frame is not self._last_frame:
            self._last_frame, self._last_frame_at = frame, now
        stale = frame is None or now - self._last_frame_at > STALE_FRAME_S

        detections: list[Detection] = []
        if not stale:
            detections = await asyncio.to_thread(self._detector.detect, frame)

        target = pick_target(detections, self._target_label) if self._tracking else None

        if self._tracking:
            if not self._dm.is_flying:
                self._tracking = False
            else:
                command = compute_rc(target, self._gains()) if not stale else HOVER
                # Re-check: a pilot may have taken over while detection was running.
                if self._tracking:
                    await self._dm.send_rc(*command, source="tracker")

        await self._broadcast(detections, target, stale, frame)

    @staticmethod
    def _gains() -> TrackingGains:
        return TrackingGains(
            yaw=settings.vision_track_gain_yaw,
            ud=settings.vision_track_gain_ud,
            fb=settings.vision_track_gain_fb,
            target_height=settings.vision_track_target_height,
            max_speed=settings.vision_track_max_speed,
        )

    async def _safe_hover(self) -> None:
        try:
            await self._dm.stop_rc()
        except Exception as e:
            logger.error("Could not zero sticks after vision failure: %s", e)

    async def _broadcast(
        self,
        detections: list[Detection],
        target: Detection | None,
        stale: bool,
        frame: Any = None,
    ) -> None:
        # Frame size lets a client letterbox/crop its overlay the same way as the video.
        height, width = frame.shape[:2] if frame is not None else (None, None)
        message = {
            "type": "detections",
            "data": {
                "detections": [d.to_dict() for d in detections],
                "target": target.to_dict() if target else None,
                "detecting": self._detecting,
                "tracking": self._tracking,
                "stale": stale,
                "frame_width": width,
                "frame_height": height,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        dead: list[Callable] = []
        for cb in self._subscribers:
            try:
                await cb(message)
            except Exception:
                dead.append(cb)
        for cb in dead:
            self._subscribers.discard(cb)
