"""Neewer BLE protocol command builders."""

from __future__ import annotations

from collections.abc import Callable

from .models import ModelInfo

# Standard protocol command bytes
STD_POWER_CMD = 0x81
STD_BRI_CMD = 0x82
STD_TEMP_CMD = 0x83
STD_HSI_CMD = 0x86
STD_CCT_CMD = 0x87

# Infinity protocol command bytes
INF_POWER_CMD = 0x8D
INF_HSI_CMD = 0x8F
INF_CCT_CMD = 0x90

GM_NEUTRAL = 50


class NeewerProtocol:
    """Build byte commands for one Neewer light protocol variant."""

    def __init__(
        self,
        model_info: ModelInfo,
        mac_bytes_provider: Callable[[], list[int]],
    ) -> None:
        """Initialize the protocol helper."""
        self._model_info = model_info
        self._mac_bytes_provider = mac_bytes_provider

    @property
    def light_type(self) -> int:
        """Return the light type (0=standard, 1=infinity, 2=infinity-hybrid)."""
        return self._model_info.light_type

    @property
    def uses_infinity_protocol(self) -> bool:
        """Return true if this model uses the full Infinity protocol."""
        return self.light_type == 1

    def build_cct_command(self, brightness: int, color_temp: int) -> list[int]:
        """Build a CCT command."""
        temp_protocol = self.internal_to_protocol_temp(color_temp)

        if self.light_type == 1:
            cmd = [0x78, INF_CCT_CMD, 0x0B]
            cmd.extend(self._mac_bytes_provider())
            cmd.extend([STD_CCT_CMD, brightness, temp_protocol, GM_NEUTRAL, 0x04])
        elif self.light_type == 2:
            cmd = [0x78, STD_CCT_CMD, 0x03, brightness, temp_protocol, GM_NEUTRAL]
        else:
            cmd = [0x78, STD_CCT_CMD, 0x02, brightness, temp_protocol]

        return add_checksum(cmd)

    def build_hsi_command(self, hue: int, saturation: int, intensity: int) -> list[int]:
        """Build an HSI command for RGB lights."""
        hue_low = hue & 0xFF
        hue_high = (hue >> 8) & 0xFF

        if self.uses_infinity_protocol:
            cmd = [0x78, INF_HSI_CMD, 0x0B]
            cmd.extend(self._mac_bytes_provider())
            cmd.extend([STD_HSI_CMD, hue_low, hue_high, saturation, intensity])
        else:
            cmd = [0x78, STD_HSI_CMD, 0x04, hue_low, hue_high, saturation, intensity]

        return add_checksum(cmd)

    def build_power_command(self, on: bool) -> list[int]:
        """Build a power command."""
        if self.uses_infinity_protocol:
            cmd = [0x78, INF_POWER_CMD, 0x08]
            cmd.extend(self._mac_bytes_provider())
            cmd.extend([STD_POWER_CMD, 1 if on else 2])
        else:
            cmd = [0x78, STD_POWER_CMD, 0x01, 1 if on else 2]

        return add_checksum(cmd)

    def build_brightness_only_command(self, brightness: int) -> list[int]:
        """Build a brightness-only command for older CCT-only lights."""
        return add_checksum([0x78, STD_BRI_CMD, 0x01, brightness])

    def build_temp_only_command(self, color_temp: int) -> list[int]:
        """Build a temperature-only command for older CCT-only lights."""
        temp_protocol = self.internal_to_protocol_temp(color_temp)
        return add_checksum([0x78, STD_TEMP_CMD, 0x01, temp_protocol])

    def kelvin_to_internal(self, kelvin: int) -> int:
        """Convert Kelvin to the internal 0-100 color temperature scale."""
        min_k, max_k = self._model_info.cct_range
        kelvin = max(min_k, min(max_k, kelvin))
        return int(((kelvin - min_k) / (max_k - min_k)) * 100)

    def internal_to_kelvin(self, internal: int) -> int:
        """Convert internal 0-100 color temperature to Kelvin."""
        min_k, max_k = self._model_info.cct_range
        return int(min_k + (internal / 100) * (max_k - min_k))

    def internal_to_protocol_temp(self, internal: int) -> int:
        """Convert internal 0-100 color temperature to protocol value."""
        min_k, max_k = self._model_info.cct_range
        internal = max(0, min(100, internal))
        min_protocol = round(min_k / 100)
        max_protocol = round(max_k / 100)
        return round(min_protocol + (internal / 100) * (max_protocol - min_protocol))


def calculate_checksum(data: list[int]) -> int:
    """Calculate protocol checksum."""
    checksum = 0
    for byte in data:
        checksum += byte + 256 if byte < 0 else byte
    return checksum & 0xFF


def add_checksum(cmd: list[int]) -> list[int]:
    """Return command bytes with checksum appended."""
    return cmd + [calculate_checksum(cmd)]
