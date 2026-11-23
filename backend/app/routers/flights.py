from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/flights", tags=["flights"])


def _get_recorder(request: Request):
    recorder = getattr(request.app.state, "flight_recorder", None)
    if recorder is None:
        raise HTTPException(status_code=503, detail="Flight logging is disabled")
    return recorder


@router.get("")
async def list_flights(request: Request):
    """Recorded sessions, newest first, with frame and command counts."""
    return await _get_recorder(request).list_sessions()


@router.get("/{flight_id}")
async def get_flight(request: Request, flight_id: int):
    """One session with its full telemetry and command log, oldest first."""
    session = await _get_recorder(request).get_session(flight_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    return session


@router.delete("/{flight_id}")
async def delete_flight(request: Request, flight_id: int):
    recorder = _get_recorder(request)
    if recorder.active_session_id == flight_id:
        raise HTTPException(status_code=409, detail="Flight is still being recorded")
    if not await recorder.delete_session(flight_id):
        raise HTTPException(status_code=404, detail="Flight not found")
    return {"ok": True, "message": f"Deleted flight {flight_id}"}
