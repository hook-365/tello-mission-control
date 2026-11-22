"""Photos and video clips from the drone camera, saved on the host.

Files land in ``settings.media_dir`` (``data/media`` by default, volume-mounted
in Docker) as ``photo-YYYYmmdd-HHMMSS-mmm.jpg`` and ``clip-YYYYmmdd-HHMMSS.mp4``.

Clips are H.264 MP4 encoded with PyAV (already installed: djitellopy uses it to
decode the drone's video), so they play in any browser. If the H.264 encoder is
missing we fall back to OpenCV's MPEG-4 writer, which saves fine but may need a
desktop player such as VLC.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^(photo|clip)-[0-9]{8}-[0-9]{6}(-[0-9]{3})?(-[0-9]+)?\.(jpg|mp4)$")


class MediaError(Exception):
    pass


class MediaNotFoundError(MediaError):
    pass


def _stamp(ms: bool = False) -> str:
    now = datetime.now()
    s = now.strftime("%Y%m%d-%H%M%S")
    return f"{s}-{now.microsecond // 1000:03d}" if ms else s


@dataclass
class MediaItem:
    name: str
    kind: Literal["photo", "clip"]
    size_bytes: int
    created_at: datetime
    duration_s: float | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat(),
            "duration_s": self.duration_s,
            "url": f"/api/media/files/{self.name}",
        }


_durations: dict[tuple[str, float], float | None] = {}


def clip_duration(path: Path) -> float | None:
    """Clip length in seconds, read from the file (cached per name + mtime)."""
    key = (path.name, path.stat().st_mtime)
    if key not in _durations:
        try:
            import av  # noqa: PLC0415

            with av.open(str(path)) as c:
                _durations[key] = round(c.duration / 1_000_000, 1) if c.duration else None
        except Exception:  # noqa: BLE001
            _durations[key] = None
    return _durations[key]


def frame_to_bgr(frame: np.ndarray, is_rgb: bool) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR) if is_rgb else frame


def is_real_frame(frame: Any) -> bool:
    """djitellopy starts with a black 300x400 placeholder until video decodes."""
    return isinstance(frame, np.ndarray) and frame.ndim == 3 and frame.size > 0 and bool(frame.any())


class _ClipWriter:
    """Writes RGB frames to an MP4 with wall-clock timestamps (frame drops keep real timing)."""

    def __init__(self, path: Path, width: int, height: int, fps: int) -> None:
        self.path = path
        self.width, self.height = width - width % 2, height - height % 2  # H.264 needs even sizes
        self._av = None
        self._cv = None
        try:
            import av  # noqa: PLC0415

            self._av = av.open(str(path), "w", format="mp4")
            stream = self._av.add_stream("libx264", rate=fps)
            stream.width, stream.height = self.width, self.height
            stream.pix_fmt = "yuv420p"
            stream.options = {"preset": "veryfast", "crf": "23"}
            from fractions import Fraction  # noqa: PLC0415

            stream.codec_context.time_base = Fraction(1, 1000)
            self._stream = stream
        except Exception as e:  # noqa: BLE001
            logger.warning("H.264 encoder unavailable (%s); falling back to MPEG-4", e)
            if self._av is not None:
                try:
                    self._av.close()
                except Exception:  # noqa: BLE001
                    pass
            self._av = None
            self._cv = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (self.width, self.height))
            if not self._cv.isOpened():
                raise MediaError("No video encoder available")

    def write(self, rgb: np.ndarray, t_ms: int) -> None:
        if rgb.shape[1] != self.width or rgb.shape[0] != self.height:
            rgb = cv2.resize(rgb, (self.width, self.height))
        if self._av is not None:
            import av  # noqa: PLC0415

            frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
            frame.pts = t_ms
            for packet in self._stream.encode(frame):
                self._av.mux(packet)
        else:
            self._cv.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

    def close(self) -> None:
        if self._av is not None:
            for packet in self._stream.encode():
                self._av.mux(packet)
            self._av.close()
        elif self._cv is not None:
            self._cv.release()


class _Recording:
    def __init__(self, path: Path, get_frame: Callable[[], Any], is_rgb: Callable[[], bool]) -> None:
        self.final_path = path
        self.part_path = path.with_name(path.name + ".part")
        self._get_frame = get_frame
        self._is_rgb = is_rgb
        self._stop = threading.Event()
        self.started = time.monotonic()
        self.started_at = datetime.now(timezone.utc)
        self.frames = 0
        self.error: str | None = None
        self._thread = threading.Thread(target=self._loop, name="clip-recorder", daemon=True)
        self._thread.start()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def _loop(self) -> None:
        fps = max(5, min(60, settings.record_fps))
        interval = 1.0 / fps
        writer: _ClipWriter | None = None
        try:
            next_t = time.monotonic()
            while not self._stop.is_set():
                if self.elapsed > settings.record_max_s:
                    logger.info("Recording hit the %ss limit, stopping", settings.record_max_s)
                    break
                frame = self._get_frame()
                if is_real_frame(frame):
                    rgb = frame if self._is_rgb() else cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    if writer is None:
                        writer = _ClipWriter(self.part_path, rgb.shape[1], rgb.shape[0], fps)
                    writer.write(rgb, int(self.elapsed * 1000))
                    self.frames += 1
                next_t += interval
                time.sleep(max(0.0, next_t - time.monotonic()))
        except Exception as e:  # noqa: BLE001
            logger.exception("Recording failed")
            self.error = str(e)
        finally:
            if writer is not None:
                try:
                    writer.close()
                except Exception as e:  # noqa: BLE001
                    self.error = self.error or str(e)

    @property
    def finished(self) -> bool:
        return not self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)


class MediaService:
    def __init__(self, drone_manager, directory: str | Path | None = None) -> None:
        self._dm = drone_manager
        self._dir = Path(directory or settings.media_dir)
        self._rec: _Recording | None = None
        self._lock = asyncio.Lock()

    @property
    def directory(self) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        return self._dir

    # -- files --

    def path_for(self, name: str) -> Path:
        if not _NAME_RE.match(name):
            raise MediaNotFoundError(name)
        p = self.directory / name
        if not p.is_file():
            raise MediaNotFoundError(name)
        return p

    def _item(self, p: Path) -> MediaItem:
        st = p.stat()
        kind = "photo" if p.suffix == ".jpg" else "clip"
        return MediaItem(
            name=p.name,
            kind=kind,
            size_bytes=st.st_size,
            created_at=datetime.fromtimestamp(st.st_mtime, timezone.utc),
            duration_s=clip_duration(p) if kind == "clip" else None,
        )

    def list(self) -> list[MediaItem]:
        items = [self._item(p) for p in self.directory.iterdir() if p.is_file() and _NAME_RE.match(p.name)]
        return sorted(items, key=lambda i: i.created_at, reverse=True)

    def delete(self, name: str) -> None:
        self.path_for(name).unlink()

    def _unique(self, stem: str, ext: str) -> Path:
        p = self.directory / f"{stem}.{ext}"
        n = 2
        while p.exists() or p.with_name(p.name + ".part").exists():
            p = self.directory / f"{stem}-{n}.{ext}"
            n += 1
        return p

    # -- camera --

    async def ensure_camera(self, timeout: float | None = None) -> None:
        """Turn the video stream on if needed and wait for the first real frame."""
        dm = self._dm
        if not dm.is_connected:
            raise MediaError("Drone is not connected")
        if not dm.is_streaming:
            await dm.stream_on()
        deadline = time.monotonic() + (settings.camera_start_timeout_s if timeout is None else timeout)
        while not is_real_frame(dm.get_frame()):
            if time.monotonic() > deadline:
                raise MediaError("Camera didn't send a picture in time")
            await asyncio.sleep(0.1)

    async def take_photo(self) -> MediaItem:
        await self.ensure_camera()
        frame = self._dm.get_frame()
        bgr = frame_to_bgr(frame, self._dm.frame_is_rgb)
        ok, jpeg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            raise MediaError("Couldn't encode the photo")
        path = self._unique(f"photo-{_stamp(ms=True)}", "jpg")
        await asyncio.to_thread(path.write_bytes, jpeg.tobytes())
        item = self._item(path)
        await self._event("photo", item)
        await self._dm.log_command("photo", {"name": item.name})
        return item

    @property
    def is_recording(self) -> bool:
        return self._rec is not None and not self._rec.finished

    def recording_status(self) -> dict:
        rec = self._rec if self.is_recording else None
        return {
            "recording": rec is not None,
            "name": rec.final_path.name if rec else None,
            "elapsed_s": round(rec.elapsed, 1) if rec else 0.0,
            "started_at": rec.started_at.isoformat() if rec else None,
        }

    async def start_recording(self) -> dict:
        async with self._lock:
            if self.is_recording:
                return self.recording_status()
            if self._rec is not None:  # finished on its own (time limit): tidy up first
                await self._finalize()
            await self.ensure_camera()
            path = self._unique(f"clip-{_stamp()}", "mp4")
            self._rec = _Recording(path, self._dm.get_frame, lambda: self._dm.frame_is_rgb)
            status = self.recording_status()
            await self._dm.broadcast_event({"type": "media", "data": {"event": "recording_started", **status}})
            await self._dm.log_command("record_start", {"name": path.name})
            return status

    async def stop_recording(self) -> MediaItem | None:
        async with self._lock:
            if self._rec is None:
                return None
            return await self._finalize()

    async def _finalize(self) -> MediaItem | None:
        rec, self._rec = self._rec, None
        await asyncio.to_thread(rec.stop)
        duration = round(rec.elapsed, 1)
        if rec.frames == 0 or not rec.part_path.exists():
            rec.part_path.unlink(missing_ok=True)
            await self._dm.broadcast_event({"type": "media", "data": {"event": "recording_stopped", "item": None}})
            await self._dm.log_command("record_stop", {}, error=rec.error or "No video frames were recorded")
            return None
        rec.part_path.rename(rec.final_path)
        item = self._item(rec.final_path)
        item.duration_s = item.duration_s or duration
        await self._event("recording_stopped", item)
        await self._dm.log_command("record_stop", {"name": item.name, "seconds": duration})
        return item

    async def shutdown(self) -> None:
        if self._rec is not None:
            await self.stop_recording()

    async def _event(self, event: str, item: MediaItem) -> None:
        await self._dm.broadcast_event({"type": "media", "data": {"event": event, "item": item.to_dict()}})
