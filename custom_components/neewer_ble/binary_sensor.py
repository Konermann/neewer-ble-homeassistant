"""Binary sensor platform for Neewer BLE Lights."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .neewer_device import NeewerLightDevice


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE binary sensors from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([NeewerConnectionSensor(device, entry)])


class NeewerConnectionSensor(BinarySensorEntity):
    """Representation of the BLE connection state."""

    _attr_has_entity_name = True
    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
        self._device = device
        self._attr_unique_id = f"{device.address.replace(':', '_').lower()}_connected"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            name=entry.data.get(CONF_NAME, device.name),
            manufacturer="Neewer",
            model=device.model_name,
        )

    @property
    def is_on(self) -> bool:
        """Return true if Home Assistant currently has a BLE connection."""
        return self._device.is_connected

    async def async_added_to_hass(self) -> None:
        """Register for device updates."""
        self.async_on_remove(
            self._device.add_update_callback(self._handle_device_update)
        )

    @callback
    def _handle_device_update(self) -> None:
        """Handle updated device state."""
        self.async_write_ha_state()
