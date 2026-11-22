"""Flight sequence models: steps, sequences and run status.

A sequence is an ordered list of steps. With ``auto_takeoff_land`` on (the
default) the runner takes off before the first step if needed and always lands
at the end, so a sequence can simply be "up 50, forward 100, spin 360, flip".
"""

from __future__ import annotations

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


Step = Annotated[
    Union[TakeoffStep, LandStep, MoveStep, RotateStep, FlipStep, WaitStep],
    Field(discriminator="type"),
]

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
        elif isinstance(step, (MoveStep, RotateStep, FlipStep)) and not flying:
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
