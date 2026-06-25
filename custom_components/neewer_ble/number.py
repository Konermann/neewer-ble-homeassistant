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
    CONF_ADVERTISED_NAME,
    CONF_CCT_MAX_KELVIN,
    CONF_CCT_MIN_KELVIN,
    CONF_DEFAULT_BRIGHTNESS,
    CONF_DEFAULT_COLOR_TEMP,
    DEFAULT_BRIGHTNESS,
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


@dataclass(frozen=True)
class RuntimeNumberDescription:
    """Description for a live device numeric control."""

    key: str
    name: str
    unique_suffix: str
    icon: str
    native_min_value: int
    native_max_value: int
    native_step: int
    native_unit_of_measurement: str | None
    mode: NumberMode = NumberMode.SLIDER


CCT_COLOR_TEMP = "cct_color_temp"
CCT_GREEN_MAGENTA = "cct_green_magenta"
FX_SPEED = "fx_speed"
FX_STRENGTH = "fx_strength"

CCT_NUMBER_DESCRIPTIONS = (
    RuntimeNumberDescription(
        key=CCT_COLOR_TEMP,
        name="CCT Color Temperature",
        unique_suffix="cct_color_temperature",
        icon="mdi:thermometer",
        native_min_value=1000,
        native_max_value=10000,
        native_step=1,
        native_unit_of_measurement="K",
    ),
    RuntimeNumberDescription(
        key=CCT_GREEN_MAGENTA,
        name="CCT Green/Magenta",
        unique_suffix="cct_green_magenta",
        icon="mdi:tune-variant",
        native_min_value=-50,
        native_max_value=50,
        native_step=1,
        native_unit_of_measurement=None,
    ),
)

FX_NUMBER_DESCRIPTIONS = (
    RuntimeNumberDescription(
        key=FX_SPEED,
        name="FX Speed",
        unique_suffix="fx_speed",
        icon="mdi:speedometer",
        native_min_value=1,
        native_max_value=10,
        native_step=1,
        native_unit_of_measurement=None,
    ),
    RuntimeNumberDescription(
        key=FX_STRENGTH,
        name="FX Strength",
        unique_suffix="fx_strength",
        icon="mdi:waveform",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        native_unit_of_measurement=None,
    ),
)


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
        default_value=0,
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
        default_value=0,
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
        default_value=0,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE number entities from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]
    runtime_descriptions = [CCT_NUMBER_DESCRIPTIONS[0]]
    if device.supports_green_magenta:
        runtime_descriptions.append(CCT_NUMBER_DESCRIPTIONS[1])
    if device.supports_effect_tuning:
        runtime_descriptions.extend(FX_NUMBER_DESCRIPTIONS)

    async_add_entities(
        [
            NeewerRuntimeNumber(device, entry, description)
            for description in runtime_descriptions
        ]
        + [
            NeewerOptionNumber(device, entry, description)
            for description in NUMBER_DESCRIPTIONS
        ]
    )


class NeewerRuntimeNumber(NeewerEntityMixin, NumberEntity):
    """Number entity that controls live lamp settings."""

    _attr_has_entity_name = True

    def __init__(
        self,
        device: NeewerLightDevice,
        entry: ConfigEntry,
        description: RuntimeNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        self._description = description
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_mode = description.mode
        self._attr_native_step = description.native_step
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._setup_neewer_entity(device, entry, description.unique_suffix)

    @property
    def native_value(self) -> int:
        """Return the current live device value."""
        if self._description.key == CCT_COLOR_TEMP:
            return self._device.color_temp_kelvin
        if self._description.key == CCT_GREEN_MAGENTA:
            return self._device.green_magenta
        if self._description.key == FX_SPEED:
            return self._device.effect_speed
        if self._description.key == FX_STRENGTH:
            return self._device.effect_strength

        return 0

    @property
    def native_min_value(self) -> int:
        """Return the minimum allowed value."""
        if self._description.key == CCT_COLOR_TEMP:
            return self._device.color_temp_range[0]

        return self._description.native_min_value

    @property
    def native_max_value(self) -> int:
        """Return the maximum allowed value."""
        if self._description.key == CCT_COLOR_TEMP:
            return self._device.color_temp_range[1]

        return self._description.native_max_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the live device value."""
        new_value = int(value)

        if self._description.key == CCT_COLOR_TEMP:
            success = await self._device.set_color_temp(new_value)
        elif self._description.key == CCT_GREEN_MAGENTA:
            success = await self._device.set_green_magenta(new_value)
        elif self._description.key == FX_SPEED:
            success = await self._device.set_effect_speed(new_value)
        elif self._description.key == FX_STRENGTH:
            success = await self._device.set_effect_strength(new_value)
        else:
            return

        if not success:
            raise HomeAssistantError(f"Failed to update {self._attr_name}")

        self._device.notify_update_callbacks()


class NeewerOptionNumber(NeewerEntityMixin, NumberEntity):
    """Number entity that updates a config entry option."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_entity_registry_visible_default = False
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

        if self._description.key == CONF_DEFAULT_COLOR_TEMP:
            return self._entry.options.get(
                self._description.key,
                self._current_cct_range[0],
            )

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
        device_name = self._entry.data.get(
            CONF_ADVERTISED_NAME,
            self._entry.data.get(CONF_NAME, self._device.name),
        )
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
