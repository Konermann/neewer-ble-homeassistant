"""The Neewer BLE Lights integration."""

from __future__ import annotations

import logging

from bleak.backends.device import BLEDevice

from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
)
try:
    from homeassistant.components.bluetooth import async_last_service_info
except ImportError:
    async_last_service_info = None

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ADVERTISED_NAME,
    DOMAIN,
    DEFAULT_BRIGHTNESS,
    CONF_DEFAULT_BRIGHTNESS,
    CONF_DEFAULT_COLOR_TEMP,
    CONF_POWER_OFF_WITH_BRIGHTNESS_ZERO,
)
from .device import NeewerLightDevice
from .models import default_color_temp_for_options, model_from_options

_LOGGER = logging.getLogger(__name__)

CONFIG_ENTRY_VERSION = 3

PRIMARY_CONTROL_SUFFIXES = {
    "connection",
    "reconnect",
}

ADVANCED_OPTION_SUFFIXES = {
    "cct_max_kelvin",
    "cct_min_kelvin",
    "cct_only",
    "default_brightness",
    "default_color_temp",
    "light_type",
    "model_override",
    "power_off_with_brightness_zero",
    "supports_rgb",
}

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Neewer BLE Lights from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    name: str = entry.data.get("name", "Neewer Light")
    advertised_name: str = entry.data.get(CONF_ADVERTISED_NAME, name)

    _LOGGER.info("Setting up Neewer BLE device: %s (%s)", name, address)

    # Try to get the BLE device
    address_upper = address.upper()
    service_info = None
    if async_last_service_info is not None:
        service_info = async_last_service_info(hass, address_upper, connectable=True)

    ble_device = async_ble_device_from_address(hass, address_upper, connectable=True)
    if ble_device is None and service_info is not None:
        ble_device = service_info.device

    if ble_device is None:
        _LOGGER.warning(
            "Device %s not found via HA Bluetooth, creating placeholder with name '%s'",
            address,
            name,
        )
        # Create a minimal BLE device object for connection attempts
        # The actual connection will happen when commands are sent
        ble_device = BLEDevice(
            address=address,
            name=advertised_name,
            details={},
            rssi=-100,
        )
    else:
        _LOGGER.info("Found BLE device: %s (%s)", ble_device.name, ble_device.address)

    # Get options with defaults
    default_brightness = entry.options.get(CONF_DEFAULT_BRIGHTNESS, DEFAULT_BRIGHTNESS)
    model_info = model_from_options(advertised_name, entry.options)
    default_color_temp = default_color_temp_for_options(
        advertised_name,
        entry.options,
    )
    power_off_with_brightness_zero = entry.options.get(
        CONF_POWER_OFF_WITH_BRIGHTNESS_ZERO, False
    )

    # Create the device handler
    device = NeewerLightDevice(
        ble_device,
        model_info=model_info,
        default_brightness=default_brightness,
        default_color_temp=default_color_temp,
        power_off_with_brightness_zero=power_off_with_brightness_zero,
    )
    if service_info is not None:
        device.update_ble_device(service_info.device, service_info.rssi)

    _LOGGER.info(
        "Created device handler - Model: %s, RGB: %s, Infinity: %s, "
        "Default Bri: %d, Default CT: %dK",
        device.model_name,
        device.supports_rgb,
        device.uses_infinity_protocol,
        default_brightness,
        default_color_temp,
    )

    # Store the device
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = device

    # Start connecting immediately so the first user command does not pay the
    # full BLE connection cost.
    _LOGGER.debug("Scheduling initial BLE connection for %s", name)
    initial_connect_task = hass.async_create_task(device.connect())
    entry.async_on_unload(initial_connect_task.cancel)

    # Set up platforms
    _LOGGER.debug("Forwarding setup to platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    _LOGGER.info("Setup complete for %s", name)
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Neewer BLE device: %s", entry.data.get(CONF_ADDRESS))

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Disconnect and clean up
        device: NeewerLightDevice = hass.data[DOMAIN].pop(entry.entry_id)
        await device.disconnect()

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", entry.version)

    if entry.version < 2:
        _migrate_entity_registry(hass, entry, hide_advanced=True)
    elif entry.version < 3:
        _migrate_entity_registry(hass, entry, hide_advanced=False)

    if entry.version < CONFIG_ENTRY_VERSION:
        hass.config_entries.async_update_entry(entry, version=CONFIG_ENTRY_VERSION)

    return True


def _migrate_entity_registry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    hide_advanced: bool,
) -> None:
    """Move primary controls and tuck advanced option entities away once."""
    address = entry.data.get(CONF_ADDRESS)
    if not address:
        return

    base_unique_id = address.replace(":", "_").lower()
    entity_registry = er.async_get(hass)

    for registry_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        suffix = _registry_entry_suffix(registry_entry.unique_id, base_unique_id)
        if suffix in PRIMARY_CONTROL_SUFFIXES:
            if registry_entry.entity_category is not None:
                entity_registry.async_update_entity(
                    registry_entry.entity_id,
                    entity_category=None,
                )
            continue

        if suffix in ADVANCED_OPTION_SUFFIXES:
            update_kwargs = {}
            should_hide = hide_advanced and registry_entry.hidden_by is None
            if should_hide:
                update_kwargs["hidden_by"] = er.RegistryEntryHider.INTEGRATION

            if (
                registry_entry.disabled_by is None
                and (
                    should_hide
                    or registry_entry.hidden_by
                    == er.RegistryEntryHider.INTEGRATION
                )
            ):
                update_kwargs["disabled_by"] = er.RegistryEntryDisabler.INTEGRATION

            if update_kwargs:
                entity_registry.async_update_entity(
                    registry_entry.entity_id,
                    **update_kwargs,
                )


def _registry_entry_suffix(unique_id: str, base_unique_id: str) -> str | None:
    """Return the entity-specific unique-id suffix for this device."""
    prefix = f"{base_unique_id}_"
    if not unique_id.startswith(prefix):
        return None

    return unique_id[len(prefix) :]
