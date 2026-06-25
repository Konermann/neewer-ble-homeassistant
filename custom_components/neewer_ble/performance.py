"""Adaptive performance helpers for Neewer BLE Lights."""

from __future__ import annotations

MIN_INTER_COMMAND_DELAY = 0.02
DEFAULT_INTER_COMMAND_DELAY = 0.05
MAX_INTER_COMMAND_DELAY = 0.10

DEFAULT_QUERY_TIMEOUT = 0.5
WEAK_SIGNAL_QUERY_TIMEOUT = 0.65
SLOW_QUERY_TIMEOUT = 0.75
MAX_QUERY_TIMEOUT = 0.9


def command_delay_for_rssi(rssi: int | None) -> float:
    """Return a conservative inter-command delay for the current RSSI."""
    if rssi is None:
        return DEFAULT_INTER_COMMAND_DELAY
    if rssi >= -75:
        return MIN_INTER_COMMAND_DELAY
    if rssi >= -85:
        return 0.03
    if rssi >= -92:
        return 0.04
    return 0.06


def next_command_delay(current: float, rssi: int | None, success: bool) -> float:
    """Adjust inter-command delay based on recent write health."""
    baseline = command_delay_for_rssi(rssi)
    if success:
        if current <= baseline:
            return baseline
        return round(max(baseline, current - 0.005), 3)

    return round(min(MAX_INTER_COMMAND_DELAY, max(current, baseline) + 0.02), 3)


def query_timeout_for_failures(failures: int, rssi: int | None) -> float:
    """Return the query timeout to use for slow/weak BLE links."""
    timeout = DEFAULT_QUERY_TIMEOUT
    if rssi is not None and rssi < -85:
        timeout = WEAK_SIGNAL_QUERY_TIMEOUT
    if failures >= 2:
        timeout = max(timeout, SLOW_QUERY_TIMEOUT)

    return min(MAX_QUERY_TIMEOUT, timeout)


def poll_backoff_seconds(failures: int) -> int:
    """Return polling backoff after repeated status-query failures."""
    if failures < 3:
        return 0

    return min(300, 30 * (2 ** (failures - 3)))


def signal_quality_label(rssi: int | None) -> str:
    """Return a human-readable RSSI quality label."""
    if rssi is None:
        return "unknown"
    if rssi >= -70:
        return "good"
    if rssi >= -85:
        return "fair"
    if rssi >= -92:
        return "weak"
    return "very weak"
