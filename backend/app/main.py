import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import control, media, rc, sequences, status, telemetry, video
from app.services.drone_manager import DroneManager
from app.services.media import MediaService
from app.services.sequence_runner import SequenceRunner
from app.services.sequence_store import SequenceStore
from app.services.telemetry_service import TelemetryService

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
    app.state.sequence_store = SequenceStore(settings.sequences_dir)
    app.state.media_service = MediaService(dm, settings.media_dir)
    app.state.sequence_runner = SequenceRunner(dm, app.state.media_service)
    await ts.start()
    logger.info("Backend ready. Mock mode: %s", settings.use_mock_drone)

    yield

    # Shutdown
    logger.info("Shutting down...")
    await app.state.sequence_runner.shutdown()
    await app.state.media_service.shutdown()
    await ts.stop()
    await dm.shutdown()
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
app.include_router(status.router)
app.include_router(rc.router)
app.include_router(media.router)
