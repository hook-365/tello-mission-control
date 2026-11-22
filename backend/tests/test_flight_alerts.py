"""Battery / Wi-Fi signal alerts and the sequencer's signal pre-flight check."""
import asyncio

import pytest
import pytest_asyncio

from app.config import settings
from app.models.sequences import SequenceIn
from app.services.drone_manager import DroneManager
from app.services.flight_alerts import battery_level, parse_snr, signal_level
from app.services.sequence_runner import PreflightError, SequenceRunner


@pytest.mark.parametrize(
    "raw, expected",
    [("90", 90), (" 42\r\n", 42), (55, 55), ("0", 0), ("ok", None), ("", None),
     ("error Not joystick", None), ("-5", None), ("250", None), (None, None)],
)
def test_parse_snr(raw, expected):
    assert parse_snr(raw) == expected


def test_battery_levels_follow_config(monkeypatch):
    monkeypatch.setattr(settings, "battery_low_pct", 30)
    monkeypatch.setattr(settings, "battery_critical_pct", 15)
    assert battery_level(100) == "ok"
    assert battery_level(31) == "ok"
    assert battery_level(30) == "low"
    assert battery_level(16) == "low"
    assert battery_level(15) == "critical"
    assert battery_level(0) == "critical"


def test_signal_levels_follow_config(monkeypatch):
    monkeypatch.setattr(settings, "wifi_snr_weak", 40)
    monkeypatch.setattr(settings, "wifi_snr_critical", 20)
    assert signal_level(None) == "unknown"
    assert signal_level(90) == "ok"
    assert signal_level(41) == "ok"
    assert signal_level(40) == "weak"
    assert signal_level(21) == "weak"
    assert signal_level(20) == "critical"


@pytest_asyncio.fixture
async def dm():
    d = DroneManager()
    await d.connect()
    yield d
    await d.shutdown()


@pytest.mark.asyncio
async def test_connect_reads_signal_and_telemetry_carries_levels(dm):
    assert dm.wifi_snr == settings.mock_wifi_snr
    t = await dm.get_telemetry()
    assert t["wifi_snr"] == settings.mock_wifi_snr
    assert t["battery_level"] == "ok"
    assert t["signal_level"] == "ok"


@pytest.mark.asyncio
async def test_telemetry_levels_change_with_drone_state(dm):
    dm.tello._battery = 12
    dm.tello._wifi_snr = 30
    await dm.refresh_wifi_snr()
    t = await dm.get_telemetry()
    assert (t["battery_level"], t["signal_level"], t["wifi_snr"]) == ("critical", "weak", 30)


@pytest.mark.asyncio
async def test_refresh_skips_while_a_command_holds_the_lock(dm):
    dm.tello._wifi_snr = 25
    async with dm._lock:
        assert await dm.refresh_wifi_snr() == settings.mock_wifi_snr  # cached, not queued
    assert await dm.refresh_wifi_snr() == 25


@pytest.mark.asyncio
async def test_refresh_keeps_last_reading_on_garbage_or_error(dm, monkeypatch):
    monkeypatch.setattr(dm.tello, "query_wifi_signal_noise_ratio", lambda: "ok")
    assert await dm.refresh_wifi_snr() == settings.mock_wifi_snr

    def boom():
        raise RuntimeError("timeout")

    monkeypatch.setattr(dm.tello, "query_wifi_signal_noise_ratio", boom)
    assert await dm.refresh_wifi_snr() == settings.mock_wifi_snr


@pytest.mark.asyncio
async def test_disconnect_forgets_signal():
    d = DroneManager()
    await d.connect()
    await d.disconnect()
    assert d.wifi_snr is None
    t = await d.get_telemetry()
    assert t["signal_level"] == "unknown" and t["wifi_snr"] is None


def _seq():
    return SequenceIn(name="t", steps=[{"type": "wait", "seconds": 0.5}])


@pytest.mark.asyncio
async def test_preflight_blocks_on_critical_signal(dm):
    dm.tello._wifi_snr = 10
    runner = SequenceRunner(dm)
    with pytest.raises(PreflightError) as exc:
        await runner.preflight(_seq())
    assert any("Wi-Fi signal is very weak" in p for p in exc.value.problems)


@pytest.mark.asyncio
async def test_preflight_allows_weak_signal(dm):
    dm.tello._wifi_snr = 35  # weak, not critical: the UI warns, the run is allowed
    runner = SequenceRunner(dm)
    await runner.preflight(_seq())


def test_status_endpoint_reports_signal(test_client):
    assert test_client.get("/api/status").json()["wifi_snr"] is None
    test_client.post("/api/control/connect")
    body = test_client.get("/api/status").json()
    assert body["connected"] is True
    assert body["wifi_snr"] == settings.mock_wifi_snr


@pytest.mark.asyncio
async def test_telemetry_service_polls_signal(dm, monkeypatch):
    from app.services.telemetry_service import TelemetryService

    monkeypatch.setattr(settings, "wifi_poll_interval_s", 0.01)
    monkeypatch.setattr(settings, "telemetry_poll_hz", 50.0)
    frames = []

    async def cb(frame):
        frames.append(frame)

    ts = TelemetryService(dm)
    ts.subscribe(cb)
    dm.tello._wifi_snr = 33
    await ts.start()
    try:
        for _ in range(100):
            if frames and frames[-1].data.wifi_snr == 33:
                break
            await asyncio.sleep(0.01)
    finally:
        await ts.stop()
    assert frames[-1].data.wifi_snr == 33
    assert frames[-1].data.signal_level == "weak"
