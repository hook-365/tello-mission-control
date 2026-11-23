"""Follow-a-target controller: turns one detection box into stick velocities.

Pure functions, no I/O, so the maths can be tested without a drone or a model.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.detector import Detection

RcCommand = tuple[int, int, int, int]  # lr, fb, ud, yaw
HOVER: RcCommand = (0, 0, 0, 0)


@dataclass(frozen=True)
class TrackingGains:
    """Proportional gains: stick velocity produced by a full-scale error of 1.0."""

    yaw: float = 60.0
    ud: float = 40.0
    fb: float = 40.0
    #: Fraction of frame height the target should fill. Smaller = follow from further away.
    target_height: float = 0.5
    #: Errors below this are ignored, so the drone holds still instead of hunting.
    deadband: float = 0.06
    #: Hard cap on any channel, whatever the gains say.
    max_speed: int = 30


def pick_target(detections: list[Detection], label: str) -> Detection | None:
    """The largest box with the wanted label — in practice the nearest such object."""
    candidates = [d for d in detections if d.label == label]
    return max(candidates, key=lambda d: d.area, default=None)


def _channel(error: float, gain: float, gains: TrackingGains) -> int:
    if abs(error) < gains.deadband:
        return 0
    return int(max(-gains.max_speed, min(gains.max_speed, round(error * gain))))


def compute_rc(target: Detection | None, gains: TrackingGains) -> RcCommand:
    """Stick velocities that centre the target and hold it at the wanted size.

    No target means hover: the drone never keeps moving on a guess.
    """
    if target is None:
        return HOVER
    # Horizontal offset from centre, -1 (left edge) .. 1 (right edge): turn towards it.
    yaw = _channel((target.cx - 0.5) * 2, gains.yaw, gains)
    # Vertical offset; image y grows downward, so a target above centre means climb.
    ud = _channel((0.5 - target.cy) * 2, gains.ud, gains)
    # Too small in frame = too far away = fly forward; too big = back off.
    fb = _channel((gains.target_height - target.h) / gains.target_height, gains.fb, gains)
    return (0, fb, ud, yaw)
