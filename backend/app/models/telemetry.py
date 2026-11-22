from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class TemperatureData(BaseModel):
    high: float
    low: float


class AttitudeData(BaseModel):
    pitch: int
    roll: int
    yaw: int


class SpeedData(BaseModel):
    x: int
    y: int
    z: int


class TelemetryData(BaseModel):
    battery: int
    height: int  # cm
    flight_time: int  # seconds
    temperature: TemperatureData
    attitude: AttitudeData
    speed: SpeedData
    barometer: float
    tof_distance: int  # cm
    # Wi-Fi signal-to-noise from the drone's "wifi?" reply (None = not read yet)
    wifi_snr: int | None = None
    # Alert levels computed from config thresholds, so the UI doesn't hard-code them
    battery_level: Literal["ok", "low", "critical"] = "ok"
    signal_level: Literal["ok", "weak", "critical", "unknown"] = "unknown"


class TelemetryFrame(BaseModel):
    type: str = "telemetry"
    data: TelemetryData
    timestamp: datetime


class CommandLogEntry(BaseModel):
    type: str = "command_log"
    data: dict
