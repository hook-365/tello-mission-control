import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.models.telemetry import TelemetryData

router = APIRouter(tags=["status"])
logger = logging.getLogger(__name__)


class StatusResponse(BaseModel):
    connected: bool
    flying: bool
    streaming: bool
    battery: int
    wifi_snr: int | None = None


@router.get("/api/status", response_model=StatusResponse)
async def get_status(request: Request):
    dm = request.app.state.drone_manager
    battery = 0
    if dm.is_connected:
        try:
            battery = await dm.get_battery()
        except Exception:
            battery = -1
    return StatusResponse(
        connected=dm.is_connected,
        flying=dm.is_flying,
        streaming=dm.is_streaming,
        battery=battery,
        wifi_snr=dm.wifi_snr,
    )


@router.get("/api/telemetry", response_model=TelemetryData)
async def get_telemetry(request: Request):
    """Latest telemetry snapshot, for clients that cannot hold a WebSocket open."""
    dm = request.app.state.drone_manager
    if not dm.is_connected:
        raise HTTPException(status_code=409, detail="Drone is not connected")
    return TelemetryData(**await dm.get_telemetry())
