from enum import Enum

from pydantic import BaseModel, Field


class MoveDirection(str, Enum):
    forward = "forward"
    back = "back"
    left = "left"
    right = "right"
    up = "up"
    down = "down"


class RotateDirection(str, Enum):
    cw = "cw"
    ccw = "ccw"


class FlipDirection(str, Enum):
    left = "left"
    right = "right"
    forward = "forward"
    back = "back"


# djitellopy's flip() takes single-letter codes
FLIP_CODES: dict[FlipDirection, str] = {
    FlipDirection.left: "l",
    FlipDirection.right: "r",
    FlipDirection.forward: "f",
    FlipDirection.back: "b",
}


class MoveRequest(BaseModel):
    direction: MoveDirection
    distance_cm: int = Field(..., ge=20, le=500, description="Distance in cm (20-500)")


class RotateRequest(BaseModel):
    direction: RotateDirection
    angle_deg: int = Field(..., ge=1, le=360, description="Angle in degrees (1-360)")


class FlipRequest(BaseModel):
    direction: FlipDirection


class RcRequest(BaseModel):
    """Stick input, each axis -100..100 (percent of max speed). Positive = right/forward/up/clockwise."""

    lr: int = Field(0, ge=-100, le=100)
    fb: int = Field(0, ge=-100, le=100)
    ud: int = Field(0, ge=-100, le=100)
    yaw: int = Field(0, ge=-100, le=100)


class CommandResponse(BaseModel):
    ok: bool
    message: str = ""
    error: str | None = None


class ConnectResponse(BaseModel):
    ok: bool
    status: str
    battery: int | None = None
