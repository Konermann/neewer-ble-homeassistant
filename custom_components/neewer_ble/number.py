"""Number platform for Neewer BLE Lights."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CCT_MAX_KELVIN,
    CONF_CCT_MIN_KELVIN,
    CONF_DEFAULT_BRIGHTNESS,
    CONF_DEFAULT_COLOR_TEMP,
    DEFAULT_BRIGHTNESS,
    DEFAULT_COLOR_TEMP,
    DOMAIN,
)
from .device import NeewerLightDevice
from .entity import NeewerEntityMixin
from .models import model_from_options
from .options import update_entry_option


@dataclass(frozen=True)
class NumberDescription:
    """Description for a configurable numeric option."""

    key: str
    name: str
    unique_suffix: str
    icon: str
    native_min_value: int
    native_max_value: int
    native_step: int
    native_unit_of_measurement: str | None
    default_value: int


NUMBER_DESCRIPTIONS = (
    NumberDescription(
        key=CONF_DEFAULT_BRIGHTNESS,
        name="Default Brightness",
        unique_suffix="default_brightness",
        icon="mdi:brightness-percent",
        native_min_value=1,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        default_value=DEFAULT_BRIGHTNESS,
    ),
    NumberDescription(
        key=CONF_DEFAULT_COLOR_TEMP,
        name="Default Color Temperature",
        unique_suffix="default_color_temp",
        icon="mdi:thermometer",
        native_min_value=1000,
        native_max_value=10000,
        native_step=1,
        native_unit_of_measurement="K",
        default_value=DEFAULT_COLOR_TEMP,
    ),
    NumberDescription(
        key=CONF_CCT_MIN_KELVIN,
        name="Lowest Color Temperature",
        unique_suffix="cct_min_kelvin",
        icon="mdi:thermometer-low",
        native_min_value=1000,
        native_max_value=10000,
        native_step=1,
        native_unit_of_measurement="K",
        default_value=DEFAULT_COLOR_TEMP,
    ),
    NumberDescription(
        key=CONF_CCT_MAX_KELVIN,
        name="Highest Color Temperature",
        unique_suffix="cct_max_kelvin",
        icon="mdi:thermometer-high",
        native_min_value=1000,
        native_max_value=10000,
        native_step=1,
        native_unit_of_measurement="K",
        default_value=DEFAULT_COLOR_TEMP,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE number entities from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            NeewerOptionNumber(device, entry, description)
            for description in NUMBER_DESCRIPTIONS
        ]
    )


class NeewerOptionNumber(NeewerEntityMixin, NumberEntity):
    """Number entity that updates a config entry option."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        device: NeewerLightDevice,
        entry: ConfigEntry,
        description: NumberDescription,
    ) -> None:
        """Initialize the number entity."""
        self._entry = entry
        self._description = description
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_native_step = description.native_step
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._setup_neewer_entity(device, entry, description.unique_suffix)

    @property
    def native_value(self) -> int:
        """Return the current option value."""
        if self._description.key in (
            CONF_CCT_MIN_KELVIN,
            CONF_CCT_MAX_KELVIN,
        ):
            min_kelvin, max_kelvin = self._current_cct_range
            if self._description.key == CONF_CCT_MIN_KELVIN:
                return min_kelvin
            return max_kelvin

        return self._entry.options.get(
            self._description.key,
            self._description.default_value,
        )

    @property
    def native_min_value(self) -> int:
        """Return the minimum allowed value."""
        if self._description.key == CONF_DEFAULT_COLOR_TEMP:
            return self._current_cct_range[0]
        if self._description.key == CONF_CCT_MAX_KELVIN:
            return self._current_cct_range[0] + 1
        return self._description.native_min_value

    @property
    def native_max_value(self) -> int:
        """Return the maximum allowed value."""
        if self._description.key == CONF_DEFAULT_COLOR_TEMP:
            return self._current_cct_range[1]
        if self._description.key == CONF_CCT_MIN_KELVIN:
            return self._current_cct_range[1] - 1
        return self._description.native_max_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the stored option value."""
        new_value = int(value)
        self._validate_value(new_value)
        update_entry_option(
            self.hass,
            self._entry,
            self._description.key,
            new_value,
        )

    @property
    def _current_cct_range(self) -> tuple[int, int]:
        """Return the currently effective CCT range."""
        device_name = self._entry.data.get(CONF_NAME, self._device.name)
        return model_from_options(device_name, self._entry.options).cct_range

    def _validate_value(self, value: int) -> None:
        """Validate a value before saving it to options."""
        min_kelvin, max_kelvin = self._current_cct_range

        if self._description.key == CONF_CCT_MIN_KELVIN and value >= max_kelvin:
            raise HomeAssistantError(
                "Lowest color temperature must be lower than highest color temperature"
            )

        if self._description.key == CONF_CCT_MAX_KELVIN and value <= min_kelvin:
            raise HomeAssistantError(
                "Highest color temperature must be higher than lowest color temperature"
            )

        if self._description.key == CONF_DEFAULT_COLOR_TEMP:
            if not min_kelvin <= value <= max_kelvin:
                raise HomeAssistantError(
                    "Default color temperature must be within the configured range"
                )
