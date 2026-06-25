"""BLE connection management for Neewer lights."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .const import (
    MAX_CONNECTION_RETRIES,
    NEEWER_NOTIFY_CHARACTERISTIC_UUID,
    NEEWER_WRITE_CHARACTERISTIC_UUID,
)

_LOGGER = logging.getLogger(__name__)


class NeewerBLEConnection:
    """Owns one persistent BLE connection to a Neewer light."""

    def __init__(self, ble_device: BLEDevice, name: str) -> None:
        """Initialize the connection."""
        self._ble_device = ble_device
        self._name = name
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._disconnect_requested = False
        self._update_callbacks: set[Callable[[], None]] = set()
        self._notify_data: bytes | None = None
        self._notify_event = asyncio.Event()
        self._last_operation: str | None = None
        self._last_commands: list[list[int]] = []
        self._last_error: str | None = None
        self._rssi: int | None = getattr(ble_device, "rssi", None)
        self._last_timing: dict | None = None
        self._timing_stats: dict[str, dict[str, float | int]] = {}
        self._last_write_monotonic = 0.0

    @property
    def address(self) -> str:
        """Return the BLE address."""
        return self._ble_device.address

    @property
    def ble_device(self) -> BLEDevice:
        """Return the cached BLE device."""
        return self._ble_device

    @property
    def is_connected(self) -> bool:
        """Return true if the BLE client is connected."""
        return self._client is not None and self._client.is_connected

    @property
    def rssi(self) -> int | None:
        """Return the latest known RSSI."""
        return self._rssi

    @property
    def last_operation(self) -> str | None:
        """Return the last BLE operation."""
        return self._last_operation

    @property
    def last_error(self) -> str | None:
        """Return the last BLE error."""
        return self._last_error

    @property
    def last_timing(self) -> dict | None:
        """Return timing details for the last BLE operation."""
        return self._last_timing

    @property
    def connection_status(self) -> str:
        """Return a concise connection status for Home Assistant."""
        if self.is_connected:
            return "Connected"

        if self._last_operation in ("connect", "reconnect"):
            if self._last_error:
                return "Connection failed"
            return "Connecting"

        if self._last_operation == "unexpected_disconnect":
            return "Unexpectedly disconnected"

        if self._last_operation == "disconnect" and self._last_error:
            return "Disconnect failed"

        return "Disconnected"

    def wrote_within(self, seconds: float) -> bool:
        """Return true if a write completed recently."""
        if self._last_write_monotonic == 0.0:
            return False

        return time.monotonic() - self._last_write_monotonic < seconds

    def add_update_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Add a callback for connection or signal updates."""
        self._update_callbacks.add(callback)

        def remove_callback() -> None:
            self._update_callbacks.discard(callback)

        return remove_callback

    def notify_update_callbacks(self) -> None:
        """Notify listeners that connection state changed."""
        for callback in list(self._update_callbacks):
            callback()

    def update_ble_device(self, ble_device: BLEDevice, rssi: int | None = None) -> None:
        """Update cached BLE device details."""
        old_rssi = self.rssi
        self._ble_device = ble_device
        if rssi is not None:
            self._rssi = rssi
        else:
            self._rssi = getattr(ble_device, "rssi", None)

        if self.rssi != old_rssi:
            self.notify_update_callbacks()

    async def connect(self) -> bool:
        """Connect to the device using bleak-retry-connector."""
        if self.is_connected:
            self._last_error = None
            return True

        queued_at = time.perf_counter()
        async with self._lock:
            started_at = time.perf_counter()
            queue_wait_ms = _elapsed_ms(queued_at, started_at)
            if self.is_connected:
                self._last_error = None
                self._record_timing("connect", _elapsed_ms(started_at), queue_wait_ms)
                return True

            try:
                if self._client is not None and not self._client.is_connected:
                    self._client = None

                _LOGGER.debug("Connecting to %s", self.address)
                self._last_operation = "connect"
                self._last_error = None
                self.notify_update_callbacks()
                self._client = await establish_connection(
                    BleakClientWithServiceCache,
                    self._ble_device,
                    self._name,
                    self._handle_disconnect,
                    max_attempts=MAX_CONNECTION_RETRIES,
                )
                _LOGGER.info("Connected to %s", self._name)
                self._record_timing("connect", _elapsed_ms(started_at), queue_wait_ms)
                self.notify_update_callbacks()
                return True
            except BleakError as err:
                _LOGGER.error("Failed to connect to %s: %s", self._name, err)
                self._last_error = str(err)
            except Exception as err:
                _LOGGER.error("Unexpected error connecting to %s: %s", self._name, err)
                self._last_error = str(err)

            self._client = None
            self._record_timing("connect", _elapsed_ms(started_at), queue_wait_ms)
            self.notify_update_callbacks()
            return False

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        async with self._command_lock:
            await self._disconnect()

    async def reconnect(self) -> bool:
        """Disconnect, if needed, and establish a fresh BLE connection."""
        self._last_operation = "reconnect"
        self._last_error = None
        self.notify_update_callbacks()
        async with self._command_lock:
            if self.is_connected:
                await self._disconnect()
            return await self.connect()

    async def write_commands(
        self,
        commands: list[list[int]],
        delay: float = 0.0,
        keep_connected: bool = True,
    ) -> bool:
        """Write one or more commands as one serialized BLE operation."""
        queued_at = time.perf_counter()
        async with self._command_lock:
            started_at = time.perf_counter()
            queue_wait_ms = _elapsed_ms(queued_at, started_at)
            if not await self.connect():
                self._record_timing("write", _elapsed_ms(started_at), queue_wait_ms)
                return False

            success = False
            self._last_operation = "write"
            self._last_commands = [list(command) for command in commands]
            self._last_error = None
            try:
                for index, command in enumerate(commands):
                    _LOGGER.debug(
                        "Sending to %s: %s (decimal: %s)",
                        self._name,
                        [hex(b) for b in command],
                        command,
                    )
                    await self._client.write_gatt_char(
                        NEEWER_WRITE_CHARACTERISTIC_UUID,
                        bytes(command),
                        response=False,
                    )
                    if delay and index < len(commands) - 1:
                        await asyncio.sleep(delay)

                success = True
                self._last_write_monotonic = time.monotonic()
                self._record_timing("write", _elapsed_ms(started_at), queue_wait_ms)
                return True
            except BleakError as err:
                _LOGGER.error("Failed to send command: %s", err)
                self._last_error = str(err)
                self._record_timing("write", _elapsed_ms(started_at), queue_wait_ms)
                return False
            finally:
                if not success or not keep_connected:
                    await self._disconnect()

    async def query(
        self,
        command: list[int],
        timeout: float = 2.0,
        keep_connected: bool = True,
    ) -> bytes | None:
        """Send a query command and wait for a notification response."""
        queued_at = time.perf_counter()
        async with self._command_lock:
            started_at = time.perf_counter()
            queue_wait_ms = _elapsed_ms(queued_at, started_at)
            if not await self.connect():
                self._record_timing("query", _elapsed_ms(started_at), queue_wait_ms)
                return None

            success = False
            self._last_operation = "query"
            self._last_commands = [list(command)]
            self._last_error = None
            try:
                self._notify_data = None
                self._notify_event.clear()

                await self._client.start_notify(
                    NEEWER_NOTIFY_CHARACTERISTIC_UUID, self._notify_callback
                )
                _LOGGER.debug(
                    "Sending query to %s: %s", self._name, [hex(b) for b in command]
                )
                await self._client.write_gatt_char(
                    NEEWER_WRITE_CHARACTERISTIC_UUID,
                    bytes(command),
                    response=False,
                )

                try:
                    await asyncio.wait_for(self._notify_event.wait(), timeout=timeout)
                    success = True
                    self._record_timing("query", _elapsed_ms(started_at), queue_wait_ms)
                    return self._notify_data
                except asyncio.TimeoutError:
                    _LOGGER.debug("Timeout waiting for response from %s", self._name)
                    self._last_error = "timeout"
                    success = True
                    self._record_timing("query", _elapsed_ms(started_at), queue_wait_ms)
                    return None
                finally:
                    try:
                        await self._client.stop_notify(NEEWER_NOTIFY_CHARACTERISTIC_UUID)
                    except Exception:
                        pass
            except BleakError as err:
                _LOGGER.debug("Error querying %s: %s", self._name, err)
                self._last_error = str(err)
                self._record_timing("query", _elapsed_ms(started_at), queue_wait_ms)
                return None
            finally:
                if not success or not keep_connected:
                    await self._disconnect()

    async def _disconnect(self) -> None:
        """Disconnect without acquiring the command lock."""
        queued_at = time.perf_counter()
        async with self._lock:
            started_at = time.perf_counter()
            queue_wait_ms = _elapsed_ms(queued_at, started_at)
            self._last_operation = "disconnect"
            self._last_error = None
            self.notify_update_callbacks()
            client = self._client
            if client is None:
                self._record_timing(
                    "disconnect",
                    _elapsed_ms(started_at),
                    queue_wait_ms,
                )
                self.notify_update_callbacks()
                return

            if not client.is_connected:
                self._client = None
                self._record_timing(
                    "disconnect",
                    _elapsed_ms(started_at),
                    queue_wait_ms,
                )
                self.notify_update_callbacks()
                return

            try:
                self._disconnect_requested = True
                await asyncio.wait_for(client.disconnect(), timeout=5.0)
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout disconnecting from %s, forcing cleanup", self._name)
                self._last_error = "disconnect timeout"
            except Exception as err:
                _LOGGER.debug("Error disconnecting from %s: %s", self._name, err)
                self._last_error = str(err)
            finally:
                if self._client is client:
                    self._client = None
                self._disconnect_requested = False
                self._record_timing(
                    "disconnect",
                    _elapsed_ms(started_at),
                    queue_wait_ms,
                )
                self.notify_update_callbacks()

    def _handle_disconnect(self, client: BleakClient) -> None:
        """Handle an unexpected BLE disconnect."""
        if self._client is client:
            self._client = None

        self._last_operation = (
            "disconnect" if self._disconnect_requested else "unexpected_disconnect"
        )
        self.notify_update_callbacks()

        if not self._disconnect_requested:
            _LOGGER.warning("Disconnected from %s", self._name)

    def _notify_callback(self, sender: int, data: bytearray) -> None:
        """Handle notification data from the device."""
        _LOGGER.debug("Notification from %s: %s", self._name, [hex(b) for b in data])
        self._notify_data = bytes(data)
        self._notify_event.set()

    def diagnostic_dump(self) -> dict:
        """Return diagnostic details for the BLE connection."""
        return {
            "address": self.address,
            "connected": self.is_connected,
            "rssi": self.rssi,
            "last_operation": self._last_operation,
            "last_commands": self._last_commands,
            "last_error": self._last_error,
            "last_timing": self._last_timing,
            "timing_stats": self._timing_stats,
        }

    def _record_timing(
        self,
        operation: str,
        duration_ms: float,
        queue_wait_ms: float,
    ) -> None:
        """Record operation timing for diagnostics."""
        duration_ms = round(duration_ms, 1)
        queue_wait_ms = round(queue_wait_ms, 1)
        self._last_timing = {
            "operation": operation,
            "duration_ms": duration_ms,
            "queue_wait_ms": queue_wait_ms,
        }

        stats = self._timing_stats.setdefault(
            operation,
            {
                "count": 0,
                "avg_ms": 0.0,
                "last_ms": 0.0,
                "max_ms": 0.0,
            },
        )
        count = int(stats["count"]) + 1
        previous_avg = float(stats["avg_ms"])
        stats["count"] = count
        stats["last_ms"] = duration_ms
        stats["avg_ms"] = round(
            previous_avg + ((duration_ms - previous_avg) / count),
            1,
        )
        stats["max_ms"] = max(float(stats["max_ms"]), duration_ms)


def _elapsed_ms(started_at: float, ended_at: float | None = None) -> float:
    """Return elapsed milliseconds."""
    ended_at = ended_at or time.perf_counter()
    return (ended_at - started_at) * 1000
