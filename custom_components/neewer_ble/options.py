"""Helpers for Home Assistant option entities."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


def update_entry_option(
    hass: HomeAssistant,
    entry: ConfigEntry,
    key: str,
    value: Any,
) -> None:
    """Update one config entry option and trigger the registered reload listener."""
    if entry.options.get(key) == value:
        return

    options = dict(entry.options)
    options[key] = value
    hass.config_entries.async_update_entry(entry, options=options)
