"""Notification helpers for Neewer BLE Lights."""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant

from .device import NeewerLightDevice


def clear_connection_notification(
    hass: HomeAssistant,
    device: NeewerLightDevice,
) -> None:
    """Clear an old connection failure notification."""
    persistent_notification.async_dismiss(
        hass,
        _connection_notification_id(device),
    )


def create_connection_failure_notification(
    hass: HomeAssistant,
    device: NeewerLightDevice,
    action: str,
) -> None:
    """Create a connection failure notification with useful context."""
    reason = device.last_connection_error or "No error detail was reported."
    rssi = f"{device.rssi} dBm" if device.rssi is not None else "unknown"

    persistent_notification.async_create(
        hass,
        (
            f"{action} failed for **{device.name}**.\n\n"
            f"- Address: `{device.address}`\n"
            f"- Status: `{device.connection_status}`\n"
            f"- Last operation: `{device.last_connection_operation or 'unknown'}`\n"
            f"- Reason: `{reason}`\n"
            f"- RSSI: `{rssi}`\n\n"
            "Check that the light is powered on, in range, and not connected "
            "to another Bluetooth app."
        ),
        title=f"Neewer BLE {action.lower()} failed",
        notification_id=_connection_notification_id(device),
    )


def _connection_notification_id(device: NeewerLightDevice) -> str:
    """Return a stable notification id for connection failures."""
    return f"neewer_ble_connection_{device.address.replace(':', '_').lower()}"
