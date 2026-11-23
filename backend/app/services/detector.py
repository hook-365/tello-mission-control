from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from app.config import settings

logger = logging.getLogger(__name__)


class VisionUnavailableError(Exception):
    """Vision was requested but cannot run (feature off or dependency missing)."""


@dataclass(frozen=True)
class Detection:
    """One detected object. Box is normalised to the frame: 0..1, origin top-left."""

    label: str
    confidence: float
    x: float  # left edge
    y: float  # top edge
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return self.w * self.h

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Detector(Protocol):
    def detect(self, frame: Any) -> list[Detection]:
        """Find objects in one RGB frame (H x W x 3 uint8). Blocking."""
        ...


class YoloDetector:
    """Ultralytics YOLO. Imported lazily so the default install stays small."""

    def __init__(self, model: str, confidence: float, device: str | None = None) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise VisionUnavailableError(
                "Vision needs the optional dependencies: "
                "pip install -r requirements-vision.txt"
            ) from e
        self._model = YOLO(model)  # downloads the weights on first use
        self._confidence = confidence
        self._device = device or None
        logger.info("YOLO detector ready: %s (device=%s)", model, device or "auto")

    def detect(self, frame: Any) -> list[Detection]:
        # djitellopy decodes frames as RGB; Ultralytics expects BGR for numpy input.
        bgr = frame[..., ::-1]
        result = self._model.predict(
            bgr, conf=self._confidence, device=self._device, verbose=False
        )[0]
        names = result.names
        detections = []
        for (x1, y1, x2, y2), conf, cls in zip(
            result.boxes.xyxyn.tolist(), result.boxes.conf.tolist(), result.boxes.cls.tolist()
        ):
            detections.append(
                Detection(
                    label=str(names[int(cls)]),
                    confidence=round(float(conf), 3),
                    x=round(x1, 4),
                    y=round(y1, 4),
                    w=round(x2 - x1, 4),
                    h=round(y2 - y1, 4),
                )
            )
        return detections


def load_default_detector() -> Detector:
    return YoloDetector(
        settings.vision_model, settings.vision_confidence, settings.vision_device
    )
