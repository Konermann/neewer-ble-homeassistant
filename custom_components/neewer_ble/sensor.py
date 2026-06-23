"""Sensor platform for Neewer BLE Lights."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device import NeewerLightDevice
from .entity import NeewerEntityMixin

SCAN_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE sensors from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([NeewerSignalStrengthSensor(device, entry)])


class NeewerSignalStrengthSensor(NeewerEntityMixin, SensorEntity):
    """Representation of the latest known BLE signal strength."""

    _attr_has_entity_name = True
    _attr_name = "Signal Strength"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "dBm"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self._setup_neewer_entity(device, entry, "rssi")

    @property
    def native_value(self) -> int | None:
        """Return the latest known RSSI value."""
        return self._device.rssi

    async def async_update(self) -> None:
        """Refresh the cached BLE RSSI from Home Assistant."""
        ble_device = async_ble_device_from_address(
            self.hass,
            self._device.address.upper(),
            connectable=True,
        )

        if ble_device is not None:
            self._device.update_ble_device(ble_device)

    @callback
    def _handle_device_update(self) -> None:
        """Handle updated device state."""
        self.async_schedule_update_ha_state(True)
