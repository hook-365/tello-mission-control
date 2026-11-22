"""Stick control (game controller / hold-to-fly keyboard).

The browser streams stick positions ~20x a second over ``/api/ws/rc``.
``POST /api/control/rc`` does the same for one update (handy for scripts).

Safety: input is refused unless the drone is connected and flying and no
sequence is running; if updates stop arriving the drone manager's watchdog
zeros the sticks (hover), and closing the socket zeros them too.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.models.commands import CommandResponse, RcRequest
from app.services.drone_manager import DroneNotConnectedError, DroneNotFlyingError

router = APIRouter(tags=["rc"])
logger = logging.getLogger(__name__)


def _sequence_running(app) -> bool:
    runner = getattr(app.state, "sequence_runner", None)
    return runner is not None and runner.is_running


async def _apply(app, body: RcRequest) -> tuple[bool, str | None]:
    """Returns (accepted, reason-if-not)."""
    if _sequence_running(app):
        return False, "A sequence is running"
    dm = app.state.drone_manager
    try:
        sent = await dm.send_rc(body.lr, body.fb, body.ud, body.yaw)
    except DroneNotConnectedError:
        return False, "Drone is not connected"
    except DroneNotFlyingError:
        return False, "Take off first"
    if not sent:
        return False, "Busy with another command"
    return True, None


@router.post("/api/control/rc", response_model=CommandResponse)
async def rc(request: Request, body: RcRequest):
    ok, reason = await _apply(request.app, body)
    if not ok:
        raise HTTPException(status_code=409, detail=reason)
    return CommandResponse(ok=True, message="rc sent")


@router.websocket("/api/ws/rc")
async def rc_ws(websocket: WebSocket):
    await websocket.accept()
    app = websocket.app
    last_reason: object = ...  # only tell the client when the answer changes
    try:
        while True:
            raw = await websocket.receive_json()
            try:
                body = RcRequest.model_validate(raw)
            except ValidationError:
                ok, reason = False, "Bad stick message"
            else:
                ok, reason = await _apply(app, body)
            if reason != last_reason:
                last_reason = reason
                await websocket.send_json({"type": "rc_status", "ok": ok, "error": reason})
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        # Controller gone: stop and hover.
        try:
            await app.state.drone_manager.stop_rc()
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to stop sticks on disconnect: %s", e)
