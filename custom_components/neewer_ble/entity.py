"""Shared entity helpers for Neewer BLE Lights."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo

from .const import DOMAIN
from .device import NeewerLightDevice


class NeewerEntityMixin:
    """Mixin with common Neewer entity attributes and callbacks."""

    _device: NeewerLightDevice

    def _setup_neewer_entity(
        self,
        device: NeewerLightDevice,
        entry: ConfigEntry,
        unique_suffix: str | None = None,
    ) -> None:
        """Set common unique id and device info attributes."""
        self._device = device
        base_unique_id = device.address.replace(":", "_").lower()
        self._attr_unique_id = (
            f"{base_unique_id}_{unique_suffix}" if unique_suffix else base_unique_id
        )
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, device.address)},
            identifiers={(DOMAIN, device.address)},
            name=entry.data.get(CONF_NAME, device.name),
            manufacturer="Neewer",
            model=device.model_name,
        )

    async def async_added_to_hass(self) -> None:
        """Register for device updates."""
        self.async_on_remove(
            self._device.add_update_callback(self._handle_device_update)
        )

    @callback
    def _handle_device_update(self) -> None:
        """Handle updated device state."""
        self.async_write_ha_state()
