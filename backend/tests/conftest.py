import os

# Force mock mode before any app imports
os.environ["TELLO_USE_MOCK_DRONE"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.drone_manager import DroneManager, MockTello
from app.services.telemetry_service import TelemetryService


@pytest.fixture(autouse=True)
def isolated_flight_log(tmp_path, monkeypatch):
    """Point the flight log at a per-test temp file so tests never touch real data."""
    monkeypatch.setattr(settings, "flight_log_path", str(tmp_path / "flights.db"))


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
