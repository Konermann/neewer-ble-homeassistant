"""Sensor platform for Neewer BLE Lights."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
)
try:
    from homeassistant.components.bluetooth import async_last_service_info
except ImportError:
    async_last_service_info = None

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


@dataclass(frozen=True)
class DeviceInfoSensorDescription:
    """Description for a diagnostic device-info sensor."""

    key: str
    name: str
    icon: str
    value_fn: Callable[[NeewerLightDevice], str]


def _protocol_label(device: NeewerLightDevice) -> str:
    """Return a human-readable protocol label."""
    if device.light_type == 1:
        return "Infinity"
    if device.light_type == 2:
        return "Infinity hybrid"
    return "Standard"


def _cct_range_label(device: NeewerLightDevice) -> str:
    """Return a human-readable CCT range."""
    min_kelvin, max_kelvin = device.color_temp_range
    return f"{min_kelvin}-{max_kelvin} K"


DEVICE_INFO_SENSORS = (
    DeviceInfoSensorDescription(
        key="bluetooth_address",
        name="Bluetooth Address",
        icon="mdi:bluetooth",
        value_fn=lambda device: device.address,
    ),
    DeviceInfoSensorDescription(
        key="advertised_name",
        name="Advertised Name",
        icon="mdi:tag-text",
        value_fn=lambda device: device.name,
    ),
    DeviceInfoSensorDescription(
        key="model",
        name="Model",
        icon="mdi:lightbulb-group",
        value_fn=lambda device: device.model_name,
    ),
    DeviceInfoSensorDescription(
        key="protocol_type",
        name="Protocol Type",
        icon="mdi:bluetooth-settings",
        value_fn=_protocol_label,
    ),
    DeviceInfoSensorDescription(
        key="cct_range",
        name="Color Temperature Range",
        icon="mdi:thermometer",
        value_fn=_cct_range_label,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE sensors from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [NeewerSignalStrengthSensor(device, entry)]
        + [
            NeewerDeviceInfoSensor(device, entry, description)
            for description in DEVICE_INFO_SENSORS
        ]
    )


class NeewerDeviceInfoSensor(NeewerEntityMixin, SensorEntity):
    """Representation of static BLE/device details."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(
        self,
        device: NeewerLightDevice,
        entry: ConfigEntry,
        description: DeviceInfoSensorDescription,
    ) -> None:
        """Initialize the diagnostic sensor."""
        self._description = description
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._setup_neewer_entity(device, entry, description.key)

    @property
    def native_value(self) -> str:
        """Return the diagnostic value."""
        return self._description.value_fn(self._device)


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
        service_info = None
        if async_last_service_info is not None:
            service_info = async_last_service_info(
                self.hass,
                self._device.address.upper(),
                connectable=True,
            )

        if service_info is not None:
            self._device.update_ble_device(service_info.device, service_info.rssi)
            return

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
