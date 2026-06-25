"""Select platform for Neewer BLE Lights."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ADVERTISED_NAME,
    CONF_LIGHT_TYPE,
    CONF_MODEL_OVERRIDE,
    DOMAIN,
    LIGHT_TYPE_OPTIONS,
    MODEL_AUTO,
)
from .device import NeewerLightDevice
from .entity import NeewerEntityMixin
from .models import model_from_options, model_options
from .options import update_entry_option


@dataclass(frozen=True)
class SelectDescription:
    """Description for a configurable select option."""

    key: str
    name: str
    unique_suffix: str
    icon: str


SELECT_DESCRIPTIONS = (
    SelectDescription(
        key=CONF_MODEL_OVERRIDE,
        name="Model Override",
        unique_suffix="model_override",
        icon="mdi:lightbulb-question",
    ),
    SelectDescription(
        key=CONF_LIGHT_TYPE,
        name="Protocol Type",
        unique_suffix="light_type",
        icon="mdi:bluetooth-settings",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE select entities from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            NeewerOptionSelect(device, entry, description)
            for description in SELECT_DESCRIPTIONS
        ]
    )


class NeewerOptionSelect(NeewerEntityMixin, SelectEntity):
    """Select entity that updates a config entry option."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_entity_registry_visible_default = False
    _attr_has_entity_name = True

    def __init__(
        self,
        device: NeewerLightDevice,
        entry: ConfigEntry,
        description: SelectDescription,
    ) -> None:
        """Initialize the select entity."""
        self._entry = entry
        self._description = description
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._setup_neewer_entity(device, entry, description.unique_suffix)

    @property
    def options(self) -> list[str]:
        """Return available options."""
        return list(self._choices.values())

    @property
    def current_option(self) -> str | None:
        """Return the current option label."""
        choices = self._choices
        if self._description.key == CONF_MODEL_OVERRIDE:
            value = self._entry.options.get(CONF_MODEL_OVERRIDE, MODEL_AUTO)
            if value not in choices:
                value = MODEL_AUTO
            return choices[value]

        value = self._current_light_type
        return choices.get(value)

    async def async_select_option(self, option: str) -> None:
        """Update the stored option value."""
        reverse_choices = {label: value for value, label in self._choices.items()}
        if option not in reverse_choices:
            return

        update_entry_option(
            self.hass,
            self._entry,
            self._description.key,
            reverse_choices[option],
        )

    @property
    def _choices(self) -> dict:
        """Return raw option values mapped to display labels."""
        if self._description.key == CONF_MODEL_OVERRIDE:
            return model_options()

        return LIGHT_TYPE_OPTIONS

    @property
    def _current_light_type(self) -> int:
        """Return the effective protocol type."""
        device_name = self._entry.data.get(
            CONF_ADVERTISED_NAME,
            self._entry.data.get(CONF_NAME, self._device.name),
        )
        return model_from_options(device_name, self._entry.options).light_type
