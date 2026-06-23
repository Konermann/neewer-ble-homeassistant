"""Button platform for Neewer BLE Lights."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device import NeewerLightDevice
from .entity import NeewerEntityMixin

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE buttons from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([NeewerReconnectButton(device, entry)])


class NeewerReconnectButton(NeewerEntityMixin, ButtonEntity):
    """Button that refreshes the active BLE connection."""

    _attr_has_entity_name = True
    _attr_name = "Reconnect"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bluetooth-transfer"

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the button."""
        self._setup_neewer_entity(device, entry, "reconnect")

    async def async_press(self) -> None:
        """Refresh the light's BLE connection."""
        _LOGGER.info("Reconnecting %s via button entity", self._device.name)

        if self._device.is_connected:
            await self._device.reconnect()
        else:
            await self._device.connect()
