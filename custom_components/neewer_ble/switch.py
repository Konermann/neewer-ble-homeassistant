"""Switch platform for Neewer BLE Lights."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ADVERTISED_NAME,
    CONF_CCT_ONLY,
    CONF_POWER_OFF_WITH_BRIGHTNESS_ZERO,
    CONF_SUPPORTS_RGB,
    DOMAIN,
)
from .device import NeewerLightDevice
from .entity import NeewerEntityMixin
from .models import base_model_for_options
from .notifications import (
    clear_connection_notification,
    create_connection_failure_notification,
)
from .options import update_entry_option

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SwitchDescription:
    """Description for a configurable switch option."""

    key: str
    name: str
    unique_suffix: str
    icon: str
    default_value: bool


OPTION_SWITCH_DESCRIPTIONS = (
    SwitchDescription(
        key=CONF_POWER_OFF_WITH_BRIGHTNESS_ZERO,
        name="Use Brightness 0 Off",
        unique_suffix="power_off_with_brightness_zero",
        icon="mdi:brightness-5",
        default_value=False,
    ),
    SwitchDescription(
        key=CONF_SUPPORTS_RGB,
        name="Supports RGB / HS Color",
        unique_suffix="supports_rgb",
        icon="mdi:palette",
        default_value=False,
    ),
    SwitchDescription(
        key=CONF_CCT_ONLY,
        name="Separate CCT Commands",
        unique_suffix="cct_only",
        icon="mdi:tune-variant",
        default_value=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE switches from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [NeewerConnectionSwitch(device, entry)]
        + [
            NeewerOptionSwitch(device, entry, description)
            for description in OPTION_SWITCH_DESCRIPTIONS
        ]
    )


class NeewerConnectionSwitch(NeewerEntityMixin, SwitchEntity):
    """Switch that connects or disconnects the BLE client."""

    _attr_has_entity_name = True
    _attr_name = "Connection"

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self._setup_neewer_entity(device, entry, "connection")

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
        if await self._device.connect():
            clear_connection_notification(self.hass, self._device)
        else:
            create_connection_failure_notification(self.hass, self._device, "Connect")

    async def async_turn_off(self, **kwargs) -> None:
        """Disconnect from the light."""
        if not self._device.is_connected:
            _LOGGER.debug("%s is already disconnected", self._device.name)
            return

        _LOGGER.info("Disconnecting from %s via switch entity", self._device.name)
        await self._device.disconnect()


class NeewerOptionSwitch(NeewerEntityMixin, SwitchEntity):
    """Switch entity that updates a config entry option."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_entity_registry_visible_default = False

    def __init__(
        self,
        device: NeewerLightDevice,
        entry: ConfigEntry,
        description: SwitchDescription,
    ) -> None:
        """Initialize the switch."""
        self._entry = entry
        self._description = description
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._setup_neewer_entity(device, entry, description.unique_suffix)

    @property
    def is_on(self) -> bool:
        """Return true if the option is enabled."""
        return self._entry.options.get(
            self._description.key,
            self._default_value,
        )

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the option."""
        update_entry_option(self.hass, self._entry, self._description.key, True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the option."""
        update_entry_option(self.hass, self._entry, self._description.key, False)

    @property
    def _default_value(self) -> bool:
        """Return the default value for the current model."""
        if self._description.key in (CONF_SUPPORTS_RGB, CONF_CCT_ONLY):
            device_name = self._entry.data.get(
                CONF_ADVERTISED_NAME,
                self._entry.data.get(CONF_NAME, self._device.name),
            )
            base_model = base_model_for_options(device_name, self._entry.options)

            if self._description.key == CONF_SUPPORTS_RGB:
                return base_model.rgb

            return base_model.cct_only

        return self._description.default_value
