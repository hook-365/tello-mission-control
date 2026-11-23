import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.telemetry import TelemetryFrame

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

    vision_service = getattr(websocket.app.state, "vision_service", None)

    telemetry_service.subscribe(send_telemetry)
    drone_manager.add_command_log_callback(send_command_log)
    if vision_service:
        vision_service.subscribe(send_command_log)  # same shape: a JSON-able dict

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        telemetry_service.unsubscribe(send_telemetry)
        drone_manager.remove_command_log_callback(send_command_log)
        if vision_service:
            vision_service.unsubscribe(send_command_log)
