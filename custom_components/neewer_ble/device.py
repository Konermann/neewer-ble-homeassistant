"""High-level Neewer BLE light device API."""

from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
import time
from collections.abc import Callable
from typing import Any

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from .connection import NeewerBLEConnection
from .const import CMD_GET_CHANNEL_STATUS, CMD_GET_POWER_STATUS
from .models import ModelInfo, detect_model, is_neewer_device, normalize_model_info
from .performance import (
    poll_backoff_seconds,
    query_timeout_for_failures,
    signal_quality_label,
)
from .protocol import NeewerProtocol

_LOGGER = logging.getLogger(__name__)

CONNECT_STATE_SYNC_TIMEOUT = 0.75


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

        self._is_on: bool | None = None
        self._brightness = default_brightness
        self._color_temp = self._protocol.kelvin_to_internal(default_color_temp)
        self._hue = 0
        self._saturation = 100
        self._last_poll_success = False
        self._poll_failures = 0
        self._poll_backoff_until = 0.0
        self._last_poll_skip_reason: str | None = None

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
    def is_on(self) -> bool | None:
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

    @property
    def connection_status(self) -> str:
        """Return a concise BLE connection status."""
        return self._connection.connection_status

    @property
    def last_connection_operation(self) -> str | None:
        """Return the last BLE connection operation."""
        return self._connection.last_operation

    @property
    def last_connection_error(self) -> str | None:
        """Return the last BLE connection error."""
        return self._connection.last_error

    @property
    def last_connection_timing(self) -> dict | None:
        """Return timing details for the last BLE operation."""
        return self._connection.last_timing

    def add_update_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Add a callback for connection or signal updates."""
        return self._connection.add_update_callback(callback)

    def update_ble_device(self, ble_device: BLEDevice, rssi: int | None = None) -> None:
        """Update the cached BLE device details from Home Assistant."""
        self._connection.update_ble_device(ble_device, rssi)

    async def connect(self, sync_state: bool = True) -> bool:
        """Connect to the device."""
        was_connected = self.is_connected
        connected = await self._connection.connect()
        if connected and sync_state and not was_connected:
            await self.async_sync_state_after_connect()

        return connected

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        await self._connection.disconnect()

    async def reconnect(self) -> bool:
        """Disconnect and establish a fresh BLE connection."""
        connected = await self._connection.reconnect()
        if connected:
            await self.async_sync_state_after_connect()

        return connected

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

            commands = self._power_on_commands(
                self._protocol.build_hsi_command(
                    self._hue,
                    self._saturation,
                    self._brightness,
                )
            )
            success = await self._write_commands(commands)
            self._set_on_if_success(success, True)
            return success

        if self.is_cct_only:
            try:
                commands = [
                    self._protocol.build_brightness_only_command(self._brightness),
                    self._protocol.build_temp_only_command(self._color_temp),
                ]
                if self._is_on is not True:
                    commands.insert(0, self._protocol.build_power_command(True))

                success = await self._write_commands(commands)
                self._set_on_if_success(success, True)
                return success
            except Exception as err:
                _LOGGER.error("Error in multi-command sequence: %s", err)
                await self.disconnect()
                return False

        commands = self._power_on_commands(
            self._protocol.build_cct_command(self._brightness, self._color_temp)
        )
        success = await self._write_commands(commands)
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
            command = self._protocol.build_brightness_only_command(self._brightness)
        else:
            command = self._protocol.build_cct_command(self._brightness, self._color_temp)

        commands = self._power_on_commands(command)
        success = await self._write_commands(commands)
        self._set_on_if_success(success, True)
        return success

    async def set_color_temp(self, kelvin: int) -> bool:
        """Set color temperature in Kelvin."""
        self._color_temp = self._protocol.kelvin_to_internal(kelvin)

        if self._is_on is False:
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

        commands = self._power_on_commands(
            self._protocol.build_hsi_command(
                self._hue,
                self._saturation,
                self._brightness,
            )
        )
        success = await self._write_commands(commands)
        self._set_on_if_success(success, True)
        return success

    async def async_get_power_status(self, timeout: float | None = None) -> bool | None:
        """Query the device power status."""
        if timeout is None:
            timeout = query_timeout_for_failures(self._poll_failures, self.rssi)

        response = await self._connection.query(CMD_GET_POWER_STATUS, timeout=timeout)
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
        timeout = query_timeout_for_failures(self._poll_failures, self.rssi)
        response = await self._connection.query(CMD_GET_CHANNEL_STATUS, timeout=timeout)
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
        """Manually query the device for current state."""
        try:
            backoff_remaining = self._poll_backoff_remaining()
            if backoff_remaining > 0:
                self._last_poll_success = False
                self._last_poll_skip_reason = "query_backoff"
                _LOGGER.debug(
                    "Skipping poll for %s for %.1fs after repeated query failures",
                    self._name,
                    backoff_remaining,
                )
                return False

            if self._connection.wrote_within(2.0):
                _LOGGER.debug("Skipping poll for %s after recent command", self._name)
                self._last_poll_skip_reason = "recent_write"
                return False

            power_status = await self.async_get_power_status()
            if power_status is not None:
                self._is_on = power_status
                self._last_poll_success = True
                self._record_poll_result(True)
                _LOGGER.debug("Updated state for %s: is_on=%s", self._name, self._is_on)
                return True

            self._last_poll_success = False
            self._record_poll_result(False)
            return False
        except Exception as err:
            _LOGGER.debug("Error polling %s: %s", self._name, err)
            self._last_poll_success = False
            self._record_poll_result(False)
            return False

    async def async_sync_state_after_connect(self) -> bool:
        """Try once to sync power state after a new BLE connection."""
        power_status = await self.async_get_power_status(
            timeout=CONNECT_STATE_SYNC_TIMEOUT
        )
        if power_status is None:
            self._last_poll_success = False
            self._record_poll_result(False)
            self._connection.notify_update_callbacks()
            return False

        self._is_on = power_status
        self._last_poll_success = True
        self._record_poll_result(True)
        self._connection.notify_update_callbacks()
        return True

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
            "adaptive": self.adaptive_performance,
            "connection": self._connection.diagnostic_dump(),
        }

    @property
    def adaptive_performance(self) -> dict[str, Any]:
        """Return adaptive performance settings and current backoff state."""
        return {
            "signal_quality": signal_quality_label(self.rssi),
            "inter_command_delay_ms": round(
                self._connection.command_delay_for(2) * 1000,
                1,
            ),
            "poll_query_timeout_ms": round(
                query_timeout_for_failures(self._poll_failures, self.rssi) * 1000,
                1,
            ),
            "status_query_mode": "connect_only",
            "poll_failures": self._poll_failures,
            "poll_backoff_remaining_s": self._poll_backoff_remaining(),
            "last_poll_skip_reason": self._last_poll_skip_reason,
        }

    async def async_benchmark(self) -> dict[str, Any]:
        """Run a lightweight BLE benchmark without changing light output."""
        total_started_at = time.perf_counter()

        connect_started_at = time.perf_counter()
        connected = await self.connect(sync_state=False)
        connect_ms = _elapsed_ms(connect_started_at)

        power_status = None
        query_ms = None
        if connected:
            query_started_at = time.perf_counter()
            power_status = await self.async_get_power_status()
            query_ms = _elapsed_ms(query_started_at)
            self._record_poll_result(power_status is not None)

        return {
            "connected": connected,
            "connect_ms": connect_ms,
            "power_status": power_status,
            "power_query_ms": query_ms,
            "total_ms": _elapsed_ms(total_started_at),
            "adaptive": self.adaptive_performance,
            "recommendations": self._benchmark_recommendations(
                connected,
                power_status is not None,
            ),
            "connection": self._connection.diagnostic_dump(),
        }

    async def _write_command(self, command: list[int], keep_connected: bool = True) -> bool:
        """Write a single command."""
        return await self._write_commands([command], keep_connected=keep_connected)

    async def _write_commands(
        self,
        commands: list[list[int]],
        delay: float | None = None,
        keep_connected: bool = True,
    ) -> bool:
        """Write one or more commands."""
        return await self._connection.write_commands(commands, delay, keep_connected)

    def _power_on_commands(self, command: list[int]) -> list[list[int]]:
        """Return command sequence, including power-on only when needed."""
        if self._is_on is True:
            return [command]

        return [self._protocol.build_power_command(True), command]

    def _set_on_if_success(self, success: bool, is_on: bool) -> None:
        """Update cached power state after a successful command."""
        if success:
            self._is_on = is_on

    def _record_poll_result(self, success: bool) -> None:
        """Update adaptive polling state from a status-query result."""
        if success:
            self._poll_failures = 0
            self._poll_backoff_until = 0.0
            self._last_poll_skip_reason = None
            return

        self._poll_failures += 1
        backoff = poll_backoff_seconds(self._poll_failures)
        if backoff:
            self._poll_backoff_until = time.monotonic() + backoff
            self._last_poll_skip_reason = "query_backoff"
            _LOGGER.debug(
                "Backing off status polls for %s by %ds after %d failures",
                self._name,
                backoff,
                self._poll_failures,
            )
        else:
            self._last_poll_skip_reason = "query_failed"

    def _poll_backoff_remaining(self) -> float:
        """Return remaining adaptive poll backoff in seconds."""
        return round(max(0.0, self._poll_backoff_until - time.monotonic()), 1)

    def _benchmark_recommendations(
        self,
        connected: bool,
        query_success: bool,
    ) -> list[str]:
        """Return concise benchmark guidance."""
        recommendations: list[str] = []
        if not connected:
            recommendations.append(
                "Connection failed. Check range, power, and whether another app is connected."
            )
        if self.rssi is not None and self.rssi < -85:
            recommendations.append(
                "Bluetooth signal is weak; keeping the connection open matters more "
                "than reconnecting."
            )
        if connected and not query_success:
            recommendations.append(
                "Status queries are timing out; normal light control will avoid "
                "recurring status polls."
            )

        if not recommendations:
            recommendations.append("Connection timing looks healthy.")

        return recommendations

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


def _elapsed_ms(started_at: float) -> float:
    """Return elapsed milliseconds rounded for diagnostics."""
    return round((time.perf_counter() - started_at) * 1000, 1)


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
