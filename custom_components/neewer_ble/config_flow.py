"""Config flow for Neewer BLE Lights integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import (
    BLE_SCAN_TIMEOUT,
    CONF_ADVERTISED_NAME,
    CONF_CCT_MAX_KELVIN,
    CONF_CCT_MIN_KELVIN,
    CONF_CCT_ONLY,
    CONF_DEFAULT_COLOR_TEMP,
    CONF_DEFAULT_BRIGHTNESS,
    CONF_LIGHT_TYPE,
    CONF_MODEL_OVERRIDE,
    CONF_POWER_OFF_WITH_BRIGHTNESS_ZERO,
    CONF_SUPPORTS_RGB,
    DEFAULT_BRIGHTNESS,
    DEFAULT_COLOR_TEMP,
    DOMAIN,
    LIGHT_TYPE_OPTIONS,
    MODEL_AUTO,
)
from .models import (
    base_model_for_options,
    friendly_name,
    is_neewer_device,
    model_from_options,
    model_options,
)

_LOGGER = logging.getLogger(__name__)


class NeewerBLEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Neewer BLE Lights."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, BLEDevice] = {}
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return NeewerBLEOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("Bluetooth discovery: %s", discovery_info)
        
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        
        self._discovery_info = discovery_info
        
        # Check if this looks like a Neewer device
        advertised_name = discovery_info.name or ""
        if not is_neewer_device(advertised_name):
            return self.async_abort(reason="not_neewer_device")

        self.context["title_placeholders"] = {
            "name": friendly_name(advertised_name),
        }
        
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery of a Neewer device."""
        if user_input is not None:
            advertised_name = self._discovery_info.name or ""
            name = friendly_name(advertised_name)
            return self.async_create_entry(
                title=name,
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_NAME: name,
                    CONF_ADVERTISED_NAME: advertised_name,
                },
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": friendly_name(self._discovery_info.name),
                "address": self._discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input.get(CONF_ADDRESS)

            # Check if user selected manual entry
            if address == "manual":
                return await self.async_step_manual()

            if address in self._discovered_devices:
                device = self._discovered_devices[address]
                advertised_name = device.name or ""
                name = friendly_name(advertised_name)
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_ADDRESS: address,
                        CONF_NAME: name,
                        CONF_ADVERTISED_NAME: advertised_name,
                    },
                )
            else:
                errors["base"] = "device_not_found"

        # Scan for devices
        await self._async_discover_devices()

        # Build the selection schema - always include manual option
        device_options = {
            address: f"{friendly_name(device.name)} ({address})"
            for address, device in self._discovered_devices.items()
        }
        # Add manual entry option
        device_options["manual"] = "Enter address manually..."

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(device_options),
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual address entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper()
            name = user_input.get(CONF_NAME, "Neewer Light")
            
            # Validate address format (basic check)
            if len(address) != 17 or address.count(":") != 5:
                errors["base"] = "invalid_address"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_ADDRESS: address,
                        CONF_NAME: name,
                        CONF_ADVERTISED_NAME: name,
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_NAME, default="Neewer Light"): str,
                }
            ),
            errors=errors,
        )

    async def _async_discover_devices(self) -> None:
        """Discover Neewer BLE devices."""
        self._discovered_devices = {}

        # First check already discovered bluetooth devices in HA
        try:
            for discovery_info in async_discovered_service_info(self.hass, connectable=True):
                if is_neewer_device(discovery_info.name):
                    self._discovered_devices[discovery_info.address] = discovery_info.device
        except Exception as err:
            _LOGGER.debug("Error checking HA bluetooth discoveries: %s", err)

        # If no devices found via HA, do a direct scan
        if not self._discovered_devices:
            _LOGGER.debug("No devices from HA, performing direct BLE scan...")
            try:
                devices = await BleakScanner.discover(timeout=BLE_SCAN_TIMEOUT)
                for device in devices:
                    if is_neewer_device(device.name):
                        self._discovered_devices[device.address] = device
            except Exception as err:
                _LOGGER.error("BLE scan failed: %s", err)

        _LOGGER.debug("Discovered %d Neewer device(s)", len(self._discovered_devices))


class NeewerBLEOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Neewer BLE Lights."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        device_name = self.config_entry.data.get(
            CONF_ADVERTISED_NAME,
            self.config_entry.data.get(CONF_NAME, ""),
        )
        stored_options = dict(self.config_entry.options)
        options = stored_options

        if user_input is not None:
            options = self._normalize_user_options(
                device_name,
                dict(user_input),
                stored_options,
            )
            model_info = model_from_options(device_name, options)
            min_kelvin, max_kelvin = model_info.cct_range
            default_color_temp = options.get(
                CONF_DEFAULT_COLOR_TEMP,
                DEFAULT_COLOR_TEMP,
            )

            if min_kelvin >= max_kelvin:
                errors["base"] = "invalid_cct_range"
            elif not min_kelvin <= default_color_temp <= max_kelvin:
                errors["base"] = "default_color_temp_out_of_range"
            else:
                return self.async_create_entry(title="", data=options)

        available_models = model_options()
        model_code = options.get(CONF_MODEL_OVERRIDE, MODEL_AUTO)
        if model_code not in available_models:
            model_code = MODEL_AUTO

        base_model = base_model_for_options(device_name, options)
        base_min_kelvin, base_max_kelvin = base_model.cct_range

        current_brightness = options.get(
            CONF_DEFAULT_BRIGHTNESS, DEFAULT_BRIGHTNESS
        )
        current_color_temp = options.get(
            CONF_DEFAULT_COLOR_TEMP, DEFAULT_COLOR_TEMP
        )
        current_min_kelvin = options.get(CONF_CCT_MIN_KELVIN, base_min_kelvin)
        current_max_kelvin = options.get(CONF_CCT_MAX_KELVIN, base_max_kelvin)
        current_light_type = options.get(CONF_LIGHT_TYPE, base_model.light_type)
        if current_light_type not in LIGHT_TYPE_OPTIONS:
            current_light_type = base_model.light_type

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DEFAULT_BRIGHTNESS,
                        default=current_brightness,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                    vol.Optional(
                        CONF_DEFAULT_COLOR_TEMP,
                        default=current_color_temp,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
                    vol.Optional(
                        CONF_POWER_OFF_WITH_BRIGHTNESS_ZERO,
                        default=options.get(CONF_POWER_OFF_WITH_BRIGHTNESS_ZERO, False),
                    ): bool,
                    vol.Optional(
                        CONF_MODEL_OVERRIDE,
                        default=model_code,
                    ): vol.In(available_models),
                    vol.Optional(
                        CONF_CCT_MIN_KELVIN,
                        default=current_min_kelvin,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
                    vol.Optional(
                        CONF_CCT_MAX_KELVIN,
                        default=current_max_kelvin,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
                    vol.Optional(
                        CONF_SUPPORTS_RGB,
                        default=options.get(CONF_SUPPORTS_RGB, base_model.rgb),
                    ): bool,
                    vol.Optional(
                        CONF_CCT_ONLY,
                        default=options.get(CONF_CCT_ONLY, base_model.cct_only),
                    ): bool,
                    vol.Optional(
                        CONF_LIGHT_TYPE,
                        default=current_light_type,
                    ): vol.In(LIGHT_TYPE_OPTIONS),
                }
            ),
            errors=errors,
        )

    def _normalize_user_options(
        self,
        device_name: str,
        user_input: dict[str, Any],
        stored_options: dict[str, Any],
    ) -> dict[str, Any]:
        """Avoid saving unchanged detected model defaults as explicit overrides."""
        previous_base_model = base_model_for_options(device_name, stored_options)
        previous_min_kelvin, previous_max_kelvin = previous_base_model.cct_range
        previous_defaults = {
            CONF_CCT_MIN_KELVIN: previous_min_kelvin,
            CONF_CCT_MAX_KELVIN: previous_max_kelvin,
            CONF_SUPPORTS_RGB: previous_base_model.rgb,
            CONF_CCT_ONLY: previous_base_model.cct_only,
            CONF_LIGHT_TYPE: previous_base_model.light_type,
        }

        for key, previous_value in previous_defaults.items():
            if key not in stored_options and user_input.get(key) == previous_value:
                user_input.pop(key, None)

        return user_input
