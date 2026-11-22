"""Battery and Wi-Fi signal alert levels, shared by telemetry and the sequencer.

Thresholds live in config (TELLO_* env vars) so the frontend never hard-codes
them: telemetry frames carry the computed level, the UI just colours it.
"""
from __future__ import annotations

from typing import Literal

from app.config import settings

BatteryLevel = Literal["ok", "low", "critical"]
SignalLevel = Literal["ok", "weak", "critical", "unknown"]


def battery_level(pct: int) -> BatteryLevel:
    if pct <= settings.battery_critical_pct:
        return "critical"
    if pct <= settings.battery_low_pct:
        return "low"
    return "ok"


def signal_level(snr: int | None) -> SignalLevel:
    if snr is None:
        return "unknown"
    if snr <= settings.wifi_snr_critical:
        return "critical"
    if snr <= settings.wifi_snr_weak:
        return "weak"
    return "ok"


def parse_snr(raw: object) -> int | None:
    """Tello answers ``wifi?`` with a bare number like ``"90"``; anything else is unknown."""
    if isinstance(raw, int):
        value = raw
    else:
        text = str(raw).strip()
        if not text.lstrip("-").isdigit():
            return None
        value = int(text)
    if value < 0 or value > 100:
        return None
    return value
