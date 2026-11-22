"""Flight sequence models: steps, sequences and run status.

A sequence is an ordered list of steps. With ``auto_takeoff_land`` on (the
default) the runner takes off before the first step if needed and always lands
at the end, so a sequence can simply be "up 50, forward 100, spin 360, flip".
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

from app.models.commands import FlipDirection, MoveDirection, RotateDirection

MAX_STEPS = 50
# Tello auto-lands after ~15 s without a command, so keep hovers well below that.
MAX_WAIT_SECONDS = 10.0


class TakeoffStep(BaseModel):
    type: Literal["takeoff"] = "takeoff"


class LandStep(BaseModel):
    type: Literal["land"] = "land"


class MoveStep(BaseModel):
    type: Literal["move"] = "move"
    direction: MoveDirection
    distance_cm: int = Field(..., ge=20, le=500, description="Distance in cm (20-500)")


class RotateStep(BaseModel):
    type: Literal["rotate"] = "rotate"
    direction: RotateDirection
    angle_deg: int = Field(..., ge=1, le=360, description="Angle in degrees (1-360)")


class FlipStep(BaseModel):
    type: Literal["flip"] = "flip"
    direction: FlipDirection


class WaitStep(BaseModel):
    type: Literal["wait"] = "wait"
    seconds: float = Field(
        ..., ge=0.5, le=MAX_WAIT_SECONDS,
        description=f"Hover time in seconds (0.5-{MAX_WAIT_SECONDS:g})",
    )


class PhotoStep(BaseModel):
    type: Literal["photo"] = "photo"


class RecordStep(BaseModel):
    type: Literal["record"] = "record"
    action: Literal["start", "stop"]


ORBIT_MAX_SEGMENT_DEG = 30


class OrbitStep(BaseModel):
    """Circle a point in front of the drone, turning to keep the camera on it.

    Flown as short straight hops plus small turns (a Tello can't yaw while it
    flies a "go" line), so it's a polygon rather than a perfect circle.
    """

    type: Literal["orbit"] = "orbit"
    direction: Literal["left", "right"]
    radius_cm: int = Field(150, ge=50, le=300, description="Distance to the subject in cm (50-300)")
    degrees: int = Field(360, ge=30, le=360, description="How far around to go (30-360)")
    speed_cm_s: int = Field(30, ge=10, le=60, description="Flying speed in cm/s (10-60)")

    def segments(self) -> list[tuple[int, int, int]]:
        """(forward_cm, right_cm, turn_deg) for each hop; turn is towards the subject."""
        n = math.ceil(self.degrees / ORBIT_MAX_SEGMENT_DEG)
        # each hop must move more than 20 cm on some axis or the Tello rejects it
        while n > 1 and round(self.radius_cm * math.sin(math.radians(self.degrees / n))) <= 20:
            n -= 1
        hops: list[tuple[int, int, int]] = []
        turned = 0
        for i in range(1, n + 1):
            theta = math.radians(self.degrees / n)
            fwd = round(self.radius_cm * (1 - math.cos(theta)))
            side = round(self.radius_cm * math.sin(theta))
            target = round(self.degrees * i / n)
            hops.append((fwd, side if self.direction == "right" else -side, target - turned))
            turned = target
        return hops


class GlideStep(BaseModel):
    """One smooth straight line on several axes at once, e.g. back and up for a reveal."""

    type: Literal["glide"] = "glide"
    forward_cm: int = Field(0, ge=-500, le=500, description="Forward (+) or back (-) in cm")
    right_cm: int = Field(0, ge=-500, le=500, description="Right (+) or left (-) in cm")
    up_cm: int = Field(0, ge=-500, le=500, description="Up (+) or down (-) in cm")
    speed_cm_s: int = Field(30, ge=10, le=100, description="Speed in cm/s (10-100)")

    @model_validator(mode="after")
    def _big_enough(self) -> "GlideStep":
        if all(abs(v) <= 20 for v in (self.forward_cm, self.right_cm, self.up_cm)):
            raise ValueError("Glide needs at least one distance over 20 cm")
        return self


Step = Annotated[
    Union[
        TakeoffStep, LandStep, MoveStep, RotateStep, FlipStep, WaitStep,
        PhotoStep, RecordStep, OrbitStep, GlideStep,
    ],
    Field(discriminator="type"),
]

CAMERA_STEPS = (PhotoStep, RecordStep)
AIRBORNE_STEPS = (MoveStep, RotateStep, FlipStep, OrbitStep, GlideStep)


def _glide_words(step: "GlideStep") -> str:
    parts = []
    for value, pos, neg in (
        (step.forward_cm, "forward", "back"),
        (step.right_cm, "right", "left"),
        (step.up_cm, "up", "down"),
    ):
        if value:
            parts.append(f"{pos if value > 0 else neg} {abs(value)}")
    return ", ".join(parts) + " cm"

_ROTATE_WORDS = {RotateDirection.cw: "clockwise", RotateDirection.ccw: "counter-clockwise"}


def describe_step(step: BaseModel) -> str:
    """Human-friendly one-liner for a step, used in progress messages."""
    if isinstance(step, TakeoffStep):
        return "Take off"
    if isinstance(step, LandStep):
        return "Land"
    if isinstance(step, MoveStep):
        return f"{step.direction.value.capitalize()} {step.distance_cm} cm"
    if isinstance(step, RotateStep):
        return f"Spin {_ROTATE_WORDS[step.direction]} {step.angle_deg}°"
    if isinstance(step, FlipStep):
        return f"Flip {step.direction.value}"
    if isinstance(step, WaitStep):
        return f"Hover {step.seconds:g} s"
    if isinstance(step, PhotoStep):
        return "Take photo"
    if isinstance(step, RecordStep):
        return "Start recording" if step.action == "start" else "Stop recording"
    if isinstance(step, OrbitStep):
        return f"Orbit {step.direction} {step.degrees}° around a point {step.radius_cm} cm ahead"
    if isinstance(step, GlideStep):
        return f"Glide {_glide_words(step)}"
    return step.__class__.__name__


def flight_order_errors(steps: list, auto_takeoff_land: bool) -> list[str]:
    """Simulate airborne/landed state through the steps and report problems."""
    errors: list[str] = []
    flying = auto_takeoff_land and not (steps and isinstance(steps[0], TakeoffStep))
    for i, step in enumerate(steps, start=1):
        if isinstance(step, TakeoffStep):
            if flying:
                errors.append(f"Step {i}: takeoff while already in the air")
            flying = True
        elif isinstance(step, LandStep):
            if not flying:
                errors.append(f"Step {i}: land while already on the ground")
            flying = False
        elif isinstance(step, AIRBORNE_STEPS) and not flying:
            errors.append(f"Step {i}: '{describe_step(step)}' needs the drone in the air (add a takeoff first)")
    if flying and not auto_takeoff_land:
        errors.append("Sequence ends in the air: add a land step or turn on auto takeoff/land")
    return errors


class SequenceIn(BaseModel):
    """What a client sends to create, update or run a sequence."""

    name: str = Field(..., min_length=1, max_length=60)
    description: str = Field("", max_length=200)
    auto_takeoff_land: bool = True
    steps: list[Step] = Field(..., min_length=1, max_length=MAX_STEPS)

    @model_validator(mode="after")
    def _check(self) -> "SequenceIn":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Name can't be blank")
        errors = flight_order_errors(self.steps, self.auto_takeoff_land)
        if errors:
            raise ValueError("; ".join(errors))
        return self

    @property
    def has_flips(self) -> bool:
        return any(isinstance(s, FlipStep) for s in self.steps)

    @property
    def needs_camera(self) -> bool:
        return any(isinstance(s, CAMERA_STEPS) for s in self.steps)


class Sequence(SequenceIn):
    id: str
    builtin: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RunRequest(BaseModel):
    """Run a saved sequence by id, or an unsaved one straight from the builder."""

    sequence_id: str | None = None
    sequence: SequenceIn | None = None

    @model_validator(mode="after")
    def _one_of(self) -> "RunRequest":
        if (self.sequence_id is None) == (self.sequence is None):
            raise ValueError("Give exactly one of sequence_id or sequence")
        return self


class RunState(str, Enum):
    idle = "idle"
    running = "running"
    completed = "completed"
    aborted = "aborted"
    failed = "failed"


class RunStatus(BaseModel):
    run_id: str | None = None
    sequence_id: str | None = None
    sequence_name: str | None = None
    status: RunState = RunState.idle
    current_step: int = 0          # 1-based position in the planned run (incl. auto takeoff/land)
    total_steps: int = 0
    step_index: int | None = None  # index into the sequence's own steps; None for auto takeoff/land
    step_description: str = ""
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def running(self) -> bool:
        return self.status == RunState.running
