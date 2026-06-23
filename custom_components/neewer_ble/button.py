"""Button platform for Neewer BLE Lights."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
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
    """Set up Neewer BLE buttons from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            NeewerConnectionButton(
                device, entry, "connect", "Connect", "mdi:bluetooth-connect"
            ),
            NeewerConnectionButton(
                device, entry, "disconnect", "Disconnect", "mdi:bluetooth-off"
            ),
            NeewerConnectionButton(
                device, entry, "reconnect", "Reconnect", "mdi:bluetooth-transfer"
            ),
        ]
    )


class NeewerConnectionButton(ButtonEntity):
    """Button that manages the active BLE connection."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        device: NeewerLightDevice,
        entry: ConfigEntry,
        action: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the button."""
        self._device = device
        self._action = action
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{device.address.replace(':', '_').lower()}_{action}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            name=entry.data.get(CONF_NAME, device.name),
            manufacturer="Neewer",
            model=device.model_name,
        )

    @property
    def available(self) -> bool:
        """Return whether this action currently applies."""
        if self._action == "connect":
            return not self._device.is_connected
        if self._action == "disconnect":
            return self._device.is_connected
        return True

    async def async_press(self) -> None:
        """Manage the light's BLE connection."""
        _LOGGER.info(
            "Running %s action for %s via button entity",
            self._action,
            self._device.name,
        )

        if self._action == "connect":
            if self._device.is_connected:
                _LOGGER.debug("%s is already connected", self._device.name)
                return
            await self._device.connect()
        elif self._action == "disconnect":
            if not self._device.is_connected:
                _LOGGER.debug("%s is already disconnected", self._device.name)
                return
            await self._device.disconnect()
        elif self._action == "reconnect":
            if self._device.is_connected:
                await self._device.reconnect()
            else:
                await self._device.connect()

    async def async_added_to_hass(self) -> None:
        """Register for device updates."""
        self.async_on_remove(
            self._device.add_update_callback(self._handle_device_update)
        )

    @callback
    def _handle_device_update(self) -> None:
        """Handle updated device state."""
        self.async_write_ha_state()
