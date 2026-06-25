"""Light platform for Neewer BLE Lights."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device import NeewerLightDevice
from .entity import NeewerEntityMixin

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neewer BLE light from a config entry."""
    _LOGGER.debug("Setting up light entity for entry: %s", entry.entry_id)

    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.debug(
        "Creating light entity - Name: %s, Model: %s, RGB: %s, Infinity: %s",
        device.name,
        device.model_name,
        device.supports_rgb,
        device.uses_infinity_protocol,
    )

    async_add_entities([NeewerBLELight(device, entry)])


class NeewerBLELight(NeewerEntityMixin, LightEntity):
    """Representation of a Neewer BLE Light."""

    _attr_has_entity_name = True
    _attr_name = None  # Use device name
    _attr_should_poll = False

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the light."""
        self._setup_neewer_entity(device, entry)

        # Determine supported color modes
        if device.supports_rgb:
            supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.HS}
            self._attr_color_mode = ColorMode.COLOR_TEMP
        else:
            supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_color_mode = ColorMode.COLOR_TEMP
        self._attr_supported_color_modes = supported_color_modes

        # Color temperature range
        min_kelvin, max_kelvin = device.color_temp_range
        self._attr_min_color_temp_kelvin = min_kelvin
        self._attr_max_color_temp_kelvin = max_kelvin

        if device.effect_list:
            self._attr_supported_features = LightEntityFeature.EFFECT
            self._attr_effect_list = device.effect_list

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._device.is_on

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        # Convert 0-100 to 0-255
        return int(self._device.brightness * 2.55)

    @property
    def color_mode(self) -> ColorMode:
        """Return the current color mode."""
        if self._device.effect is not None:
            return ColorMode.BRIGHTNESS

        if self._device.color_mode == "hs" and self._device.supports_rgb:
            return ColorMode.HS

        return ColorMode.COLOR_TEMP

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return supported color modes."""
        return self._attr_supported_color_modes

    @property
    def supported_features(self) -> LightEntityFeature:
        """Return supported light features."""
        return self._attr_supported_features

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        return self._device.color_temp_kelvin

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hue and saturation color value."""
        if self._device.supports_rgb:
            return (self._device.hue, self._device.saturation)
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available.

        Always returns True since BLE connections are on-demand.
        The connection status entity exposes BLE health separately.
        """
        return True

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        has_brightness = ATTR_BRIGHTNESS in kwargs
        has_color_temp = ATTR_COLOR_TEMP_KELVIN in kwargs
        has_effect = ATTR_EFFECT in kwargs
        has_hs = ATTR_HS_COLOR in kwargs

        brightness = kwargs.get(ATTR_BRIGHTNESS)
        color_temp_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        effect = kwargs.get(ATTR_EFFECT)
        hs_color = kwargs.get(ATTR_HS_COLOR)

        # Convert HA brightness (0-255) to Neewer (0-100)
        brightness_pct = int(brightness / 2.55) if brightness is not None else None

        if has_effect and effect is not None:
            await self._device.set_effect(effect, brightness_pct)
        elif has_hs and hs_color is not None and self._device.supports_rgb:
            # RGB mode
            hue, saturation = hs_color
            await self._device.set_rgb(
                hue=int(hue),
                saturation=int(saturation),
                brightness=brightness_pct,
            )
            self._attr_color_mode = ColorMode.HS
        elif has_color_temp:
            # Explicit color temperature request switches to CCT mode.
            await self._device.turn_on(
                brightness=brightness_pct,
                color_temp_kelvin=color_temp_kelvin,
            )
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif has_brightness:
            # Brightness alone should not switch the current color mode.
            if brightness_pct == 0:
                await self._device.set_brightness(0)
            elif self._device.effect is not None:
                await self._device.set_effect(self._device.effect, brightness_pct)
            elif self.color_mode == ColorMode.HS and self._device.supports_rgb:
                await self._device.set_rgb(
                    hue=self._device.hue,
                    saturation=self._device.saturation,
                    brightness=brightness_pct,
                )
            elif brightness_pct is not None:
                await self._device.set_brightness(brightness_pct)
        elif self.color_mode == ColorMode.HS and self._device.supports_rgb:
            await self._device.set_rgb(
                hue=self._device.hue,
                saturation=self._device.saturation,
            )
        else:
            # CCT mode
            await self._device.turn_on()
            self._attr_color_mode = ColorMode.COLOR_TEMP

        self.async_write_ha_state()

    @property
    def effect(self) -> str | None:
        """Return the active FX effect."""
        return self._device.effect

    @property
    def effect_list(self) -> list[str]:
        """Return supported FX effects."""
        return self._device.effect_list

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self._device.turn_off()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Handle removal from Home Assistant."""
        await self._device.disconnect()

    async def async_update(self) -> None:
        """Manually fetch current power state from the light."""
        if not self._device.is_connected:
            return

        _LOGGER.debug("Manually syncing state for %s", self._device.name)
        await self._device.async_update()
