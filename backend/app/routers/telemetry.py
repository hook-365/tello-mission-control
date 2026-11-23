import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pydantic import ValidationError

from app.models.commands import RcRequest
from app.models.telemetry import TelemetryFrame
from app.services.drone_manager import DroneNotConnectedError, DroneNotFlyingError

router = APIRouter(tags=["telemetry"])
logger = logging.getLogger(__name__)


@router.websocket("/api/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    await websocket.accept()
    telemetry_service = websocket.app.state.telemetry_service
    drone_manager = websocket.app.state.drone_manager

    async def send_telemetry(frame: TelemetryFrame):
        await websocket.send_text(frame.model_dump_json())

    async def send_command_log(entry: dict):
        await websocket.send_text(json.dumps(entry))

    telemetry_service.subscribe(send_telemetry)
    drone_manager.add_command_log_callback(send_command_log)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        telemetry_service.unsubscribe(send_telemetry)
        drone_manager.remove_command_log_callback(send_command_log)


@router.websocket("/api/ws/control")
async def control_ws(websocket: WebSocket):
    """Stick input channel: the client sends ``{"lr","fb","ud","yaw"}`` frames (~20 Hz).

    Rejected frames get an ``{"ok": false, "error": ...}`` reply and the socket
    stays open. Closing the socket zeroes the sticks.
    """
    await websocket.accept()
    drone_manager = websocket.app.state.drone_manager

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                rc = RcRequest.model_validate_json(raw)
                await drone_manager.send_rc(rc.lr, rc.fb, rc.ud, rc.yaw)
            except ValidationError:
                await websocket.send_json({"ok": False, "error": "Invalid RC frame"})
            except DroneNotConnectedError:
                await websocket.send_json({"ok": False, "error": "Drone is not connected"})
            except DroneNotFlyingError:
                await websocket.send_json({"ok": False, "error": "Drone is not flying"})
    except WebSocketDisconnect:
        logger.info("Control WebSocket client disconnected")
    finally:
        await drone_manager.stop_rc()
