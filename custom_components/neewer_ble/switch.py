"""Switch platform for Neewer BLE Lights."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .neewer_device import NeewerLightDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE switches from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([NeewerConnectionSwitch(device, entry)])


class NeewerConnectionSwitch(SwitchEntity):
    """Switch that connects or disconnects the BLE client."""

    _attr_has_entity_name = True
    _attr_name = "Connection"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self._device = device
        self._attr_unique_id = f"{device.address.replace(':', '_').lower()}_connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            name=entry.data.get(CONF_NAME, device.name),
            manufacturer="Neewer",
            model=device.model_name,
        )

    @property
    def icon(self) -> str:
        """Return the icon for the current connection state."""
        if self._device.is_connected:
            return "mdi:bluetooth-connect"
        return "mdi:bluetooth-off"

    @property
    def is_on(self) -> bool:
        """Return true if Home Assistant currently has a BLE connection."""
        return self._device.is_connected

    async def async_turn_on(self, **kwargs) -> None:
        """Connect to the light."""
        if self._device.is_connected:
            _LOGGER.debug("%s is already connected", self._device.name)
            return

        _LOGGER.info("Connecting to %s via switch entity", self._device.name)
        await self._device.connect()

    async def async_turn_off(self, **kwargs) -> None:
        """Disconnect from the light."""
        if not self._device.is_connected:
            _LOGGER.debug("%s is already disconnected", self._device.name)
            return

        _LOGGER.info("Disconnecting from %s via switch entity", self._device.name)
        await self._device.disconnect()

    async def async_added_to_hass(self) -> None:
        """Register for device updates."""
        self.async_on_remove(
            self._device.add_update_callback(self._handle_device_update)
        )

    @callback
    def _handle_device_update(self) -> None:
        """Handle updated device state."""
        self.async_write_ha_state()
