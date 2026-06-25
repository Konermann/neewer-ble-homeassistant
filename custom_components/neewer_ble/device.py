"""High-level Neewer BLE light device API."""

from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
from collections.abc import Callable
from typing import Any

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from .connection import NeewerBLEConnection
from .const import CMD_GET_CHANNEL_STATUS, CMD_GET_POWER_STATUS
from .models import ModelInfo, detect_model, is_neewer_device, normalize_model_info
from .protocol import NeewerProtocol

_LOGGER = logging.getLogger(__name__)


class NeewerLightDevice:
    """Represents a Neewer BLE light device."""

    def __init__(
        self,
        ble_device: BLEDevice,
        model_info: ModelInfo | dict[str, Any] | None = None,
        default_brightness: int = 100,
        default_color_temp: int = 3200,
        power_off_with_brightness_zero: bool = False,
    ) -> None:
        """Initialize the Neewer light device."""
        self._connection = NeewerBLEConnection(
            ble_device,
            ble_device.name or "Unknown Neewer Light",
        )
        self._address = ble_device.address
        self._name = ble_device.name or "Unknown Neewer Light"
        self._model_info = normalize_model_info(model_info) or detect_model(self._name)
        self._protocol = NeewerProtocol(self._model_info, self._get_mac_bytes)

        self._hw_mac_address: str | None = None
        self._default_brightness = default_brightness
        self._default_color_temp = default_color_temp
        self._power_off_with_brightness_zero = power_off_with_brightness_zero

        self._is_on = False
        self._brightness = default_brightness
        self._color_temp = self._protocol.kelvin_to_internal(default_color_temp)
        self._hue = 0
        self._saturation = 100
        self._last_poll_success = False

    @property
    def address(self) -> str:
        """Return the BLE address."""
        return self._address

    @property
    def name(self) -> str:
        """Return the device name."""
        return self._name

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model_info.name

    @property
    def supports_rgb(self) -> bool:
        """Return true if device supports RGB."""
        return self._model_info.rgb

    @property
    def light_type(self) -> int:
        """Return the light type (0=standard, 1=infinity, 2=infinity-hybrid)."""
        return self._model_info.light_type

    @property
    def uses_infinity_protocol(self) -> bool:
        """Return true if device uses the full Infinity protocol."""
        return self._protocol.uses_infinity_protocol

    @property
    def is_cct_only(self) -> bool:
        """Return true if device needs separate brightness/temp commands."""
        return self._model_info.cct_only

    @property
    def color_temp_range(self) -> tuple[int, int]:
        """Return the color temperature range in Kelvin."""
        return self._model_info.cct_range

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._is_on

    @property
    def brightness(self) -> int:
        """Return brightness (0-100)."""
        return self._brightness

    @property
    def hue(self) -> int:
        """Return the cached hue."""
        return self._hue

    @property
    def saturation(self) -> int:
        """Return the cached saturation."""
        return self._saturation

    @property
    def color_temp_kelvin(self) -> int:
        """Return color temperature in Kelvin."""
        return self._protocol.internal_to_kelvin(self._color_temp)

    @property
    def is_connected(self) -> bool:
        """Return true if connected."""
        return self._connection.is_connected

    @property
    def rssi(self) -> int | None:
        """Return the latest known Bluetooth RSSI in dBm."""
        return self._connection.rssi

    def add_update_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Add a callback for connection or signal updates."""
        return self._connection.add_update_callback(callback)

    def update_ble_device(self, ble_device: BLEDevice, rssi: int | None = None) -> None:
        """Update the cached BLE device details from Home Assistant."""
        self._connection.update_ble_device(ble_device, rssi)

    async def connect(self) -> bool:
        """Connect to the device."""
        return await self._connection.connect()

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        await self._connection.disconnect()

    async def reconnect(self) -> bool:
        """Disconnect and establish a fresh BLE connection."""
        return await self._connection.reconnect()

    async def turn_on(
        self,
        brightness: int | None = None,
        color_temp_kelvin: int | None = None,
        hue: int | None = None,
        saturation: int | None = None,
    ) -> bool:
        """Turn on the light with optional parameters."""
        if brightness is not None:
            self._brightness = max(0, min(100, brightness))

        if color_temp_kelvin is not None:
            self._color_temp = self._protocol.kelvin_to_internal(color_temp_kelvin)

        if self.supports_rgb and hue is not None:
            self._hue = max(0, min(360, hue))
            if saturation is not None:
                self._saturation = max(0, min(100, saturation))

            success = await self._write_commands(
                [
                    self._protocol.build_power_command(True),
                    self._protocol.build_hsi_command(
                        self._hue, self._saturation, self._brightness
                    ),
                ],
                delay=0.05,
            )
            self._set_on_if_success(success, True)
            return success

        if self.is_cct_only:
            try:
                success = await self._write_commands(
                    [
                        self._protocol.build_power_command(True),
                        self._protocol.build_brightness_only_command(self._brightness),
                        self._protocol.build_temp_only_command(self._color_temp),
                    ],
                    delay=0.05,
                )
                self._set_on_if_success(success, True)
                return success
            except Exception as err:
                _LOGGER.error("Error in multi-command sequence: %s", err)
                await self.disconnect()
                return False

        success = await self._write_commands(
            [
                self._protocol.build_power_command(True),
                self._protocol.build_cct_command(self._brightness, self._color_temp),
            ],
            delay=0.05,
        )
        self._set_on_if_success(success, True)
        return success

    async def turn_off(self) -> bool:
        """Turn off the light using the configured off behavior."""
        if self._power_off_with_brightness_zero:
            if self.is_cct_only:
                command = self._protocol.build_brightness_only_command(0)
            else:
                command = self._protocol.build_cct_command(0, self._color_temp)
        else:
            command = self._protocol.build_power_command(False)

        success = await self._write_command(command)
        self._set_on_if_success(success, False)
        return success

    async def set_brightness(self, brightness: int) -> bool:
        """Set brightness (0-100)."""
        self._brightness = max(0, min(100, brightness))

        if self._brightness == 0:
            return await self.turn_off()

        if self.is_cct_only:
            commands = [
                self._protocol.build_power_command(True),
                self._protocol.build_brightness_only_command(self._brightness),
            ]
        else:
            commands = [
                self._protocol.build_power_command(True),
                self._protocol.build_cct_command(self._brightness, self._color_temp),
            ]

        success = await self._write_commands(commands, delay=0.05)
        self._set_on_if_success(success, True)
        return success

    async def set_color_temp(self, kelvin: int) -> bool:
        """Set color temperature in Kelvin."""
        self._color_temp = self._protocol.kelvin_to_internal(kelvin)

        if not self._is_on:
            return True

        if self.is_cct_only:
            command = self._protocol.build_temp_only_command(self._color_temp)
        else:
            command = self._protocol.build_cct_command(self._brightness, self._color_temp)

        return await self._write_command(command)

    async def set_rgb(
        self, hue: int, saturation: int, brightness: int | None = None
    ) -> bool:
        """Set RGB color using HSI values."""
        if not self.supports_rgb:
            _LOGGER.warning("Device %s does not support RGB", self._name)
            return False

        self._hue = max(0, min(360, hue))
        self._saturation = max(0, min(100, saturation))
        if brightness is not None:
            self._brightness = max(0, min(100, brightness))

        success = await self._write_commands(
            [
                self._protocol.build_power_command(True),
                self._protocol.build_hsi_command(
                    self._hue, self._saturation, self._brightness
                ),
            ],
            delay=0.05,
        )
        self._set_on_if_success(success, True)
        return success

    async def async_get_power_status(self) -> bool | None:
        """Query the device power status."""
        response = await self._connection.query(CMD_GET_POWER_STATUS)
        if response is None or len(response) < 4:
            _LOGGER.debug("Failed to get power status from %s", self._name)
            return None

        if response[0] == 0x78 and response[1] == 0x02:
            power_state = response[3]
            is_on = power_state == 1
            _LOGGER.debug(
                "Power status for %s: %s (raw: %d)",
                self._name,
                "ON" if is_on else "STANDBY",
                power_state,
            )
            return is_on

        _LOGGER.debug(
            "Unexpected response type from %s: %s",
            self._name,
            [hex(b) for b in response],
        )
        return None

    async def async_get_channel_status(self) -> dict | None:
        """Query the device channel/mode status."""
        response = await self._connection.query(CMD_GET_CHANNEL_STATUS)
        if response is None or len(response) < 4:
            _LOGGER.debug("Failed to get channel status from %s", self._name)
            return None

        if response[0] == 0x78 and response[1] == 0x01:
            channel = response[3] if len(response) > 3 else 0
            _LOGGER.debug("Channel status for %s: channel=%d", self._name, channel)
            return {"channel": channel, "raw": list(response)}

        _LOGGER.debug(
            "Unexpected response type from %s: %s",
            self._name,
            [hex(b) for b in response],
        )
        return None

    async def async_update(self) -> bool:
        """Poll the device for current state."""
        try:
            power_status = await self.async_get_power_status()
            if power_status is not None:
                self._is_on = power_status
                self._last_poll_success = True
                _LOGGER.debug("Updated state for %s: is_on=%s", self._name, self._is_on)
                return True

            self._last_poll_success = False
            return False
        except Exception as err:
            _LOGGER.debug("Error polling %s: %s", self._name, err)
            self._last_poll_success = False
            return False

    @property
    def last_poll_success(self) -> bool:
        """Return true if the last poll was successful."""
        return self._last_poll_success

    def set_defaults(self, brightness: int, color_temp_kelvin: int) -> None:
        """Update default values."""
        self._default_brightness = brightness
        self._default_color_temp = color_temp_kelvin
        _LOGGER.debug(
            "Updated defaults for %s: brightness=%d, color_temp=%dK",
            self._name,
            brightness,
            color_temp_kelvin,
        )

    def diagnostic_dump(self) -> dict[str, Any]:
        """Return diagnostic details for troubleshooting."""
        return {
            "name": self.name,
            "address": self.address,
            "model": {
                "name": self.model_name,
                "supports_rgb": self.supports_rgb,
                "cct_range": list(self.color_temp_range),
                "cct_only": self.is_cct_only,
                "light_type": self.light_type,
                "uses_infinity_protocol": self.uses_infinity_protocol,
            },
            "state": {
                "is_on": self.is_on,
                "brightness": self.brightness,
                "color_temp_kelvin": self.color_temp_kelvin,
                "hue": self.hue,
                "saturation": self.saturation,
                "last_poll_success": self.last_poll_success,
            },
            "defaults": {
                "brightness": self._default_brightness,
                "color_temp_kelvin": self._default_color_temp,
            },
            "options": {
                "power_off_with_brightness_zero": self._power_off_with_brightness_zero,
            },
            "connection": self._connection.diagnostic_dump(),
        }

    async def _write_command(self, command: list[int], keep_connected: bool = True) -> bool:
        """Write a single command."""
        return await self._write_commands([command], keep_connected=keep_connected)

    async def _write_commands(
        self,
        commands: list[list[int]],
        delay: float = 0.0,
        keep_connected: bool = True,
    ) -> bool:
        """Write one or more commands."""
        return await self._connection.write_commands(commands, delay, keep_connected)

    def _set_on_if_success(self, success: bool, is_on: bool) -> None:
        """Update cached power state after a successful command."""
        if success:
            self._is_on = is_on

    def _get_hardware_mac_macos(self) -> str | None:
        """Get hardware MAC address on macOS using system_profiler."""
        try:
            result = subprocess.run(
                ["system_profiler", "SPBluetoothDataType"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout
            name_offset = output.find(self._name)
            if name_offset == -1:
                _LOGGER.debug("Device %s not found in system_profiler output", self._name)
                return None

            address_offset = output.find("Address:", name_offset)
            if address_offset == -1:
                _LOGGER.debug("Address not found for %s", self._name)
                return None

            mac_start = address_offset + 9
            mac_str = output[mac_start : mac_start + 17].strip()
            mac_clean = mac_str.replace("-", ":").upper()
            parts = mac_clean.split(":")
            if len(parts) == 6 and all(len(p) == 2 for p in parts):
                _LOGGER.debug("Found hardware MAC for %s: %s", self._name, mac_clean)
                return mac_clean

            _LOGGER.debug("Invalid MAC format found: %s", mac_str)
            return None
        except subprocess.TimeoutExpired:
            _LOGGER.warning("system_profiler timed out")
            return None
        except Exception as err:
            _LOGGER.debug("Error getting hardware MAC: %s", err)
            return None

    def _get_mac_bytes(self) -> list[int]:
        """Convert MAC address string to protocol bytes."""
        if self.uses_infinity_protocol and platform.system() == "Darwin":
            if self._hw_mac_address is None:
                self._hw_mac_address = self._get_hardware_mac_macos()

            if self._hw_mac_address:
                parts = self._hw_mac_address.replace("-", ":").split(":")
                if len(parts) == 6:
                    return [int(p, 16) for p in parts]

            _LOGGER.warning(
                "Could not get hardware MAC for %s on macOS, Infinity commands may fail",
                self._name,
            )

        parts = self._address.replace("-", ":").split(":")
        if len(parts) == 6:
            return [int(p, 16) for p in parts]

        _LOGGER.warning("Unexpected MAC format: %s", self._address)
        return [0, 0, 0, 0, 0, 0]


async def discover_neewer_lights(timeout: float = 10.0) -> list[BLEDevice]:
    """Discover Neewer BLE lights."""
    _LOGGER.debug("Scanning for Neewer lights...")
    devices = []

    def detection_callback(device: BLEDevice, advertisement_data) -> None:
        if is_neewer_device(device.name):
            _LOGGER.debug("Found Neewer device: %s (%s)", device.name, device.address)
            devices.append(device)

    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()

    _LOGGER.info("Found %d Neewer device(s)", len(devices))
    return devices
