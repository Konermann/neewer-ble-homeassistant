"""Binary sensor platform for Neewer BLE Lights."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device import NeewerLightDevice
from .entity import NeewerEntityMixin


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE binary sensors from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([NeewerConnectionSensor(device, entry)])


class NeewerConnectionSensor(NeewerEntityMixin, BinarySensorEntity):
    """Representation of the BLE connection state."""

    _attr_has_entity_name = True
    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
        self._setup_neewer_entity(device, entry, "connected")

    @property
    def is_on(self) -> bool:
        """Return true if Home Assistant currently has a BLE connection."""
        return self._device.is_connected
