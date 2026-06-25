"""Neewer BLE protocol command builders."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import ModelInfo

# Standard protocol command bytes
STD_POWER_CMD = 0x81
STD_BRI_CMD = 0x82
STD_TEMP_CMD = 0x83
STD_HSI_CMD = 0x86
STD_CCT_CMD = 0x87
STD_SCENE_CMD = 0x88

# Infinity protocol command bytes
INF_POWER_CMD = 0x8D
INF_HSI_CMD = 0x8F
INF_CCT_CMD = 0x90
INF_SCENE_CMD = 0x91
INF_SCENE_PAYLOAD_CMD = 0x8B

GM_NEUTRAL = 50
DEFAULT_SCENE_SPEED = 5
DEFAULT_SCENE_SPECIAL = 1
_STATE_MODE_BYTES = {
    STD_POWER_CMD,
    STD_HSI_CMD,
    STD_CCT_CMD,
    STD_SCENE_CMD,
    INF_SCENE_CMD,
    INF_SCENE_PAYLOAD_CMD,
}


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

    def build_effect_commands(
        self,
        effect_id: int,
        brightness: int,
        color_temp: int,
        hue: int,
        saturation: int,
    ) -> list[list[int]]:
        """Build scene/FX command sequence."""
        if self.light_type == 0:
            return [self._build_standard_effect_command(effect_id, brightness)]

        base_command = self._build_extended_effect_base_command(
            effect_id,
            brightness,
            color_temp,
            hue,
            saturation,
        )

        if self.light_type == 2:
            command = list(base_command)
            command[1] = INF_SCENE_PAYLOAD_CMD
            command[2] = len(command) - 3
            return [add_checksum(command)]

        command = [0x78, INF_SCENE_CMD, 6 + (len(base_command) - 2)]
        command.extend(self._mac_bytes_provider())
        command.extend(
            [
                INF_SCENE_PAYLOAD_CMD,
                convert_effect_id_for_protocol(self.light_type, effect_id),
            ]
        )
        command.extend(base_command[4:])

        return [
            self.build_power_command(False),
            self.build_power_command(True),
            add_checksum(command),
        ]

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

    def protocol_temp_to_internal(self, protocol_temp: int) -> int:
        """Convert protocol color temperature units to internal 0-100 scale."""
        min_protocol, max_protocol = self._protocol_temp_range()
        if min_protocol == max_protocol:
            return 0

        protocol_temp = max(min_protocol, min(max_protocol, protocol_temp))
        return round(
            ((protocol_temp - min_protocol) / (max_protocol - min_protocol)) * 100
        )

    def parse_state_payload(self, data: bytes | list[int]) -> dict[str, Any] | None:
        """Parse a light state payload from a status/query response."""
        command = self._extract_state_command(data)
        if command is None or len(command) < 4:
            return None

        mode = command[1]
        if mode == STD_POWER_CMD and len(command) >= 4:
            return {"mode": "power", "is_on": command[3] == 1}

        if mode == STD_HSI_CMD and len(command) >= 7:
            return {
                "mode": "hs",
                "hue": command[3] + (256 * command[4]),
                "saturation": command[5],
                "brightness": command[6],
            }

        if mode == STD_CCT_CMD and len(command) >= 5:
            return {
                "mode": "cct",
                "brightness": command[3],
                "color_temp": self.protocol_temp_to_internal(command[4]),
            }

        if mode in (STD_SCENE_CMD, INF_SCENE_PAYLOAD_CMD) and len(command) >= 5:
            return self._parse_effect_state(command)

        if mode == INF_SCENE_CMD:
            nested_command = self._extract_infinity_scene_payload(command)
            if nested_command is not None:
                return self._parse_effect_state(nested_command)

        return None

    def _build_standard_effect_command(
        self,
        effect_id: int,
        brightness: int,
    ) -> list[int]:
        """Build a classic scene command."""
        brightness = max(0, min(100, brightness))
        effect_id = convert_effect_id_for_protocol(self.light_type, effect_id)

        if self.light_type == 0:
            return add_checksum([0x78, STD_SCENE_CMD, 0x02, brightness, effect_id])

        return add_checksum([0x78, STD_SCENE_CMD, 0x02, effect_id, brightness])

    def _build_extended_effect_base_command(
        self,
        effect_id: int,
        brightness: int,
        color_temp: int,
        hue: int,
        saturation: int,
    ) -> list[int]:
        """Build the model-independent extended scene payload."""
        brightness = max(0, min(100, brightness))
        bright_min = 0
        bright_max = max(1, brightness)
        temp = self.internal_to_protocol_temp(color_temp)
        temp_min, temp_max = self._protocol_temp_range()
        hue_low, hue_high = _split_hue(hue)
        saturation = max(0, min(100, saturation))
        speed = DEFAULT_SCENE_SPEED
        sparks = 0
        special = DEFAULT_SCENE_SPECIAL

        payload = [effect_id]
        if effect_id == 1:
            payload.extend([brightness, temp, speed])
        elif effect_id in (2, 3, 6, 8):
            payload.extend([brightness, temp, GM_NEUTRAL, speed])
        elif effect_id == 4:
            payload.extend([brightness, temp, GM_NEUTRAL, speed, sparks])
        elif effect_id == 5:
            payload.extend([bright_min, bright_max, temp, GM_NEUTRAL, speed])
        elif effect_id in (7, 9):
            payload.extend([brightness, hue_low, hue_high, saturation, speed])
        elif effect_id == 10:
            payload.extend([brightness, special, speed])
        elif effect_id == 11:
            payload.extend(
                [bright_min, bright_max, temp, GM_NEUTRAL, speed, sparks]
            )
        elif effect_id == 12:
            payload.extend([brightness, 0, 0, 104, 1, speed])
        elif effect_id == 13:
            payload.extend([brightness, temp_min, temp_max, speed])
        elif effect_id == 14:
            payload = [14, 0, bright_min, bright_max, 0, 0, temp, speed]
        elif effect_id == 15:
            payload = [14, 1, bright_min, bright_max, hue_low, hue_high, 0, speed]
        elif effect_id == 16:
            payload = [15, bright_min, bright_max, temp, GM_NEUTRAL, speed]
        elif effect_id == 17:
            payload = [16, brightness, special, speed, sparks]
        elif effect_id == 18:
            payload = [17, brightness, special, speed]
        else:
            payload.extend([brightness])

        return [0x78, STD_SCENE_CMD, len(payload), *payload]

    def _protocol_temp_range(self) -> tuple[int, int]:
        """Return min/max color temperature values in protocol units."""
        min_k, max_k = self._model_info.cct_range
        return round(min_k / 100), round(max_k / 100)

    def _extract_state_command(self, data: bytes | list[int]) -> list[int] | None:
        """Return an embedded Neewer command from a status response."""
        payload = list(data)
        if len(payload) < 2 or payload[0] != 0x78:
            return None

        if payload[1] in _STATE_MODE_BYTES:
            return payload

        if payload[1] != 0x01:
            return None

        for index in range(2, min(len(payload), 8)):
            if payload[index] == 0x78 and _has_state_mode_at(payload, index + 1):
                return payload[index:]

            if payload[index] in _STATE_MODE_BYTES:
                return [0x78, *payload[index:]]

        return None

    def _extract_infinity_scene_payload(
        self,
        command: list[int],
    ) -> list[int] | None:
        """Return the nested scene payload from a wrapped Infinity scene command."""
        try:
            payload_mode_index = command.index(INF_SCENE_PAYLOAD_CMD)
        except ValueError:
            return None

        if payload_mode_index + 1 >= len(command):
            return None

        nested = [
            0x78,
            INF_SCENE_PAYLOAD_CMD,
            len(command) - payload_mode_index - 1,
        ]
        nested.extend(command[payload_mode_index + 1 :])
        return nested

    def _parse_effect_state(self, command: list[int]) -> dict[str, Any] | None:
        """Parse a scene/FX payload."""
        if self.light_type == 0 and command[1] == STD_SCENE_CMD:
            return {
                "mode": "effect",
                "brightness": command[3],
                "effect_id": command[4],
            }

        effect_id = command[3]
        state: dict[str, Any] = {"mode": "effect", "effect_id": effect_id}

        if len(command) > 4:
            state["brightness"] = command[4]

        if effect_id in (1, 2, 3, 4, 6, 8) and len(command) > 5:
            state["color_temp"] = self.protocol_temp_to_internal(command[5])
        elif effect_id in (5, 11, 16) and len(command) > 6:
            state["brightness"] = command[5]
            state["color_temp"] = self.protocol_temp_to_internal(command[6])
        elif effect_id in (7, 9) and len(command) > 7:
            state["hue"] = command[5] + (256 * command[6])
            state["saturation"] = command[7]
        elif effect_id == 13 and len(command) > 5:
            state["color_temp"] = self.protocol_temp_to_internal(command[5])
        elif effect_id == 14 and len(command) > 9:
            state["brightness"] = command[6]
            if command[4] == 0:
                state["color_temp"] = self.protocol_temp_to_internal(command[9])
            else:
                state["hue"] = command[7] + (256 * command[8])
        elif effect_id == 15 and len(command) > 8:
            state["brightness"] = command[6]
            state["hue"] = command[7] + (256 * command[8])

        return state


def calculate_checksum(data: list[int]) -> int:
    """Calculate protocol checksum."""
    checksum = 0
    for byte in data:
        checksum += byte + 256 if byte < 0 else byte
    return checksum & 0xFF


def add_checksum(cmd: list[int]) -> list[int]:
    """Return command bytes with checksum appended."""
    return cmd + [calculate_checksum(cmd)]


def convert_effect_id_for_protocol(light_type: int, effect_id: int) -> int:
    """Convert effect ids between classic and Infinity protocol variants."""
    if light_type > 0:
        if effect_id > 20:
            return {
                21: 10,
                22: 8,
                23: 12,
                24: 12,
                25: 17,
                26: 11,
                27: 1,
                28: 2,
                29: 15,
            }.get(effect_id, effect_id)
        return effect_id

    if effect_id < 20:
        return {
            10: 1,
            16: 4,
            17: 5,
            11: 6,
            1: 7,
            2: 8,
            15: 9,
        }.get(effect_id, 10)

    return effect_id - 20


def _split_hue(hue: int) -> tuple[int, int]:
    """Split a 0-360 hue into low/high protocol bytes."""
    hue = max(0, min(360, hue))
    return hue & 0xFF, (hue >> 8) & 0xFF


def _has_state_mode_at(payload: list[int], index: int) -> bool:
    """Return true if an index points at a known state command byte."""
    return index < len(payload) and payload[index] in _STATE_MODE_BYTES
