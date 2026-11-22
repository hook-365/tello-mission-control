import os
import tempfile

# Force mock mode before any app imports
os.environ["TELLO_USE_MOCK_DRONE"] = "true"
# Keep saved sequences out of the source tree during tests
os.environ.setdefault("TELLO_SEQUENCES_DIR", tempfile.mkdtemp(prefix="tello-seq-test-"))
os.environ.setdefault("TELLO_MEDIA_DIR", tempfile.mkdtemp(prefix="tello-media-test-"))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.drone_manager import DroneManager, MockTello
from app.services.telemetry_service import TelemetryService


@pytest.fixture
def mock_tello():
    return MockTello()


@pytest.fixture
def drone_manager():
    return DroneManager()


@pytest.fixture
def test_client():
    """Synchronous test client with fresh DroneManager in mock mode."""
    dm = DroneManager()
    ts = TelemetryService(dm)
    app.state.drone_manager = dm
    app.state.telemetry_service = ts
    with TestClient(app) as client:
        yield client


@pytest.fixture
def seq_client(tmp_path, monkeypatch):
    """Test client with an isolated, empty sequences directory."""
    from app.config import settings

    monkeypatch.setattr(settings, "sequences_dir", str(tmp_path / "sequences"))
    with TestClient(app) as client:
        yield client
