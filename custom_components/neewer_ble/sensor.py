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
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .neewer_device import NeewerLightDevice

SCAN_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE sensors from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([NeewerSignalStrengthSensor(device, entry)])


class NeewerSignalStrengthSensor(SensorEntity):
    """Representation of the latest known BLE signal strength."""

    _attr_has_entity_name = True
    _attr_name = "Signal Strength"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "dBm"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self._device = device
        self._attr_unique_id = f"{device.address.replace(':', '_').lower()}_rssi"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            name=entry.data.get(CONF_NAME, device.name),
            manufacturer="Neewer",
            model=device.model_name,
        )

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

    async def async_added_to_hass(self) -> None:
        """Register for device updates."""
        self.async_on_remove(
            self._device.add_update_callback(self._handle_device_update)
        )

    @callback
    def _handle_device_update(self) -> None:
        """Handle updated device state."""
        self.async_schedule_update_ha_state(True)
