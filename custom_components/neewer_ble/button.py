"""Button platform for Neewer BLE Lights."""

from __future__ import annotations

import json
import logging

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
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
    """Set up Neewer BLE buttons from a config entry."""
    device: NeewerLightDevice = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            NeewerReconnectButton(device, entry),
            NeewerDiagnosticDumpButton(device, entry),
            NeewerBenchmarkButton(device, entry),
        ]
    )


class NeewerReconnectButton(NeewerEntityMixin, ButtonEntity):
    """Button that refreshes the active BLE connection."""

    _attr_has_entity_name = True
    _attr_name = "Reconnect"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bluetooth-transfer"

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the button."""
        self._setup_neewer_entity(device, entry, "reconnect")

    async def async_press(self) -> None:
        """Refresh the light's BLE connection."""
        _LOGGER.info("Reconnecting %s via button entity", self._device.name)

        if self._device.is_connected:
            await self._device.reconnect()
        else:
            await self._device.connect()


class NeewerDiagnosticDumpButton(NeewerEntityMixin, ButtonEntity):
    """Button that creates a diagnostic dump for troubleshooting."""

    _attr_has_entity_name = True
    _attr_name = "Diagnostic Dump"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clipboard-text-search"

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the button."""
        self._setup_neewer_entity(device, entry, "diagnostic_dump")

    async def async_press(self) -> None:
        """Create a diagnostic dump notification."""
        dump = self._device.diagnostic_dump()
        dump_text = json.dumps(dump, indent=2, sort_keys=True)

        _LOGGER.info(
            "Neewer diagnostic dump for %s:\n%s",
            self._device.name,
            dump_text,
        )
        persistent_notification.async_create(
            self.hass,
            f"```json\n{dump_text}\n```",
            title=f"Neewer BLE diagnostics: {self._device.name}",
            notification_id=(
                "neewer_ble_diagnostics_"
                f"{self._device.address.replace(':', '_').lower()}"
            ),
        )


class NeewerBenchmarkButton(NeewerEntityMixin, ButtonEntity):
    """Button that runs a lightweight BLE benchmark."""

    _attr_has_entity_name = True
    _attr_name = "BLE Benchmark"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:speedometer"

    def __init__(self, device: NeewerLightDevice, entry: ConfigEntry) -> None:
        """Initialize the button."""
        self._setup_neewer_entity(device, entry, "ble_benchmark")

    async def async_press(self) -> None:
        """Run a BLE benchmark and show the result."""
        benchmark = await self._device.async_benchmark()
        benchmark_text = json.dumps(benchmark, indent=2, sort_keys=True)

        _LOGGER.info(
            "Neewer BLE benchmark for %s:\n%s",
            self._device.name,
            benchmark_text,
        )
        persistent_notification.async_create(
            self.hass,
            f"```json\n{benchmark_text}\n```",
            title=f"Neewer BLE benchmark: {self._device.name}",
            notification_id=(
                "neewer_ble_benchmark_"
                f"{self._device.address.replace(':', '_').lower()}"
            ),
        )
