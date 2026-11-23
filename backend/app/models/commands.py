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
    forward = "forward"
    back = "back"
    left = "left"
    right = "right"


class MoveRequest(BaseModel):
    direction: MoveDirection
    distance_cm: int = Field(..., ge=20, le=500, description="Distance in cm (20-500)")


class RotateRequest(BaseModel):
    direction: RotateDirection
    angle_deg: int = Field(..., ge=1, le=360, description="Angle in degrees (1-360)")


class FlipRequest(BaseModel):
    direction: FlipDirection


class RcRequest(BaseModel):
    """Continuous stick input. Each channel is a velocity from -100 to 100."""

    lr: int = Field(0, ge=-100, le=100, description="Left (-) / right (+)")
    fb: int = Field(0, ge=-100, le=100, description="Back (-) / forward (+)")
    ud: int = Field(0, ge=-100, le=100, description="Down (-) / up (+)")
    yaw: int = Field(0, ge=-100, le=100, description="Counter-clockwise (-) / clockwise (+)")


class CommandResponse(BaseModel):
    ok: bool
    message: str = ""
    error: str | None = None


class ConnectResponse(BaseModel):
    ok: bool
    status: str
    battery: int | None = None
