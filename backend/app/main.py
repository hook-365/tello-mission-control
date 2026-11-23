import importlib.util
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import control, flights, sequences, status, telemetry, video, vision
from app.services.drone_manager import DroneManager
from app.services.flight_recorder import FlightRecorder
from app.services.telemetry_service import TelemetryService
from app.services.vision_service import VisionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Tello Web Controller backend...")
    dm = DroneManager()
    ts = TelemetryService(dm)
    app.state.drone_manager = dm
    app.state.telemetry_service = ts
    recorder = None
    if settings.flight_log_enabled:
        try:
            recorder = FlightRecorder(settings.flight_log_path)
            await recorder.start()
            ts.subscribe(recorder.on_telemetry)
            dm.add_command_log_callback(recorder.on_command)
        except Exception as e:
            # A read-only or missing data dir must not stop the drone from flying.
            logger.error("Flight logging disabled: cannot open %s: %s", settings.flight_log_path, e)
            recorder = None
    app.state.flight_recorder = recorder
    vision_service = None
    if settings.vision_enabled:
        if importlib.util.find_spec("ultralytics") is None:
            logger.error(
                "TELLO_VISION_ENABLED is set but ultralytics is not installed "
                "(pip install -r requirements-vision.txt). Vision stays off."
            )
        else:
            from app.services.detector import load_default_detector

            vision_service = VisionService(dm, load_default_detector)
    app.state.vision_service = vision_service
    await ts.start()
    logger.info("Backend ready. Mock mode: %s", settings.use_mock_drone)

    yield

    # Shutdown
    logger.info("Shutting down...")
    await ts.stop()
    if vision_service:
        await vision_service.stop()
    await dm.shutdown()
    if recorder:
        await recorder.stop()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Tello Web Controller API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(control.router)
app.include_router(telemetry.router)
app.include_router(video.router)
app.include_router(sequences.router)
app.include_router(flights.router)
app.include_router(vision.router)
app.include_router(status.router)
