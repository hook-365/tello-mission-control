from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.detector import VisionUnavailableError

router = APIRouter(prefix="/api/vision", tags=["vision"])

_DISABLED = "Vision is disabled (set TELLO_VISION_ENABLED=true)"


class DetectRequest(BaseModel):
    enabled: bool


class TrackRequest(BaseModel):
    enabled: bool
    target: str | None = Field(None, description="Label to follow, e.g. 'person'")


def _service(request: Request):
    service = getattr(request.app.state, "vision_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail=_DISABLED)
    return service


@router.get("")
async def vision_state(request: Request):
    service = getattr(request.app.state, "vision_service", None)
    if service is None:
        return {"available": False, "detecting": False, "tracking": False}
    return service.state()


@router.post("/detect")
async def set_detect(request: Request, body: DetectRequest):
    """Switch object detection on or off. The first switch-on loads the model."""
    service = _service(request)
    try:
        await service.set_detecting(body.enabled)
    except VisionUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # model file missing, weight download failed, bad device...
        raise HTTPException(status_code=503, detail=f"Could not load the detector: {e}")
    return service.state()


@router.post("/track")
async def set_track(request: Request, body: TrackRequest):
    """Start or stop following a target. Starting needs the drone airborne."""
    service = _service(request)
    if body.enabled and not request.app.state.drone_manager.is_flying:
        raise HTTPException(status_code=409, detail="Drone is not flying")
    runner = getattr(request.app.state, "sequence_runner", None)
    if body.enabled and runner is not None and runner.is_running:
        raise HTTPException(status_code=409, detail="A sequence is running. Abort it first.")
    try:
        await service.set_tracking(body.enabled, body.target)
    except VisionUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Could not load the detector: {e}")
    return service.state()
