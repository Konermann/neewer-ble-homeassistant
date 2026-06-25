"""Model definitions and detection for Neewer BLE lights."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .const import (
    CONF_CCT_MAX_KELVIN,
    CONF_CCT_MIN_KELVIN,
    CONF_CCT_ONLY,
    CONF_LIGHT_TYPE,
    CONF_MODEL_OVERRIDE,
    CONF_SUPPORTS_RGB,
    MODEL_AUTO,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelInfo:
    """Capabilities and protocol variant for a Neewer light model."""

    name: str
    rgb: bool
    cct_range: tuple[int, int]
    cct_only: bool
    light_type: int


# Light types per NeewerLite-Python:
#   0 = Old-style: CCT uses [0x78, 0x87, 0x02, bri, temp]
#   1 = Infinity: Full infinity protocol with MAC address embedded
#   2 = Infinity-hybrid: CCT uses [0x78, 0x87, 0x03, bri, temp, GM]
SUPPORTED_MODELS: dict[str, ModelInfo] = {
    # MS Series (COB lights) - Infinity protocol
    "20220035": ModelInfo("MS150B", False, (2700, 6500), False, 1),
    "20230080": ModelInfo("MS60C", True, (2700, 6500), False, 1),

    # RGB Panel lights - Standard protocol (type 0)
    "RGB660PRO": ModelInfo("RGB660 PRO", True, (3200, 5600), False, 0),
    "RGB660": ModelInfo("RGB660", True, (3200, 5600), False, 0),
    "RGB480": ModelInfo("RGB480", True, (3200, 5600), False, 0),
    "RGB530": ModelInfo("RGB530", True, (3200, 5600), False, 0),
    "RGB530PRO": ModelInfo("RGB530 PRO", True, (3200, 5600), False, 0),
    "RGB176": ModelInfo("RGB176", True, (3200, 5600), False, 0),
    "RGB960": ModelInfo("RGB960", True, (3200, 5600), False, 0),

    # SL/SNL Series (Bi-color panels) - CCT-only lights use separate commands
    "SL80": ModelInfo("SL-80", False, (3200, 8500), True, 0),
    "SNL660": ModelInfo("SNL-660", False, (3200, 5600), True, 0),
    "SNL530": ModelInfo("SNL-530", False, (3200, 5600), True, 0),
    "SNL480": ModelInfo("SNL-480", False, (3200, 5600), True, 0),

    # GL Series (Key lights) - Infinity protocol
    "20220001": ModelInfo("GL1", False, (2900, 7000), False, 1),

    # CB Series - Infinity protocol
    "20220051": ModelInfo("CB100C", True, (2700, 6500), False, 1),
    "20220055": ModelInfo("CB300B", False, (2700, 6500), False, 1),

    # RGB512/RGB800 - Infinity-hybrid (type 2)
    "RGB512": ModelInfo("RGB512", True, (2500, 10000), False, 2),
    "RGB800": ModelInfo("RGB800", True, (2500, 10000), False, 2),

    # Light wands - Standard protocol
    "RGB1": ModelInfo("RGB1", True, (3200, 5600), False, 0),
    "TL60": ModelInfo("TL60 RGB", True, (2700, 6500), False, 0),
}

UNKNOWN_MODEL = ModelInfo("Unknown", False, (3200, 5600), False, 0)


def normalize_model_info(model_info: ModelInfo | dict[str, Any] | None) -> ModelInfo | None:
    """Return a typed model info object for older dict-style callers."""
    if model_info is None or isinstance(model_info, ModelInfo):
        return model_info

    return ModelInfo(
        name=model_info.get("name", UNKNOWN_MODEL.name),
        rgb=model_info.get("rgb", UNKNOWN_MODEL.rgb),
        cct_range=model_info.get("cct_range", UNKNOWN_MODEL.cct_range),
        cct_only=model_info.get("cct_only", UNKNOWN_MODEL.cct_only),
        light_type=model_info.get("light_type", UNKNOWN_MODEL.light_type),
    )


def is_neewer_device(name: str | None) -> bool:
    """Return true when a BLE name appears to be a Neewer light."""
    if not name:
        return False

    name_upper = name.upper()
    return "NEEWER" in name_upper or name_upper.startswith("NW-")


def detect_model(name: str) -> ModelInfo:
    """Detect model info from a BLE device name."""
    name_upper = name.upper()
    name_clean = (
        name_upper.replace("NEEWER-", "")
        .replace("NEEWER", "")
        .replace("-", "")
        .replace(" ", "")
    )
    if not name_clean:
        _LOGGER.debug("Unknown model, using defaults for: %s", name)
        return UNKNOWN_MODEL

    for code, info in SUPPORTED_MODELS.items():
        code_clean = code.upper().replace("-", "").replace(" ", "")
        model_name_clean = info.name.upper().replace("-", "").replace(" ", "")
        if (
            code_clean in name_clean
            or model_name_clean in name_clean
            or (len(name_clean) >= 4 and name_clean in code_clean)
            or (len(name_clean) >= 4 and name_clean in model_name_clean)
        ):
            _LOGGER.debug(
                "Detected model: %s (light_type=%d, cct_only=%s)",
                info.name,
                info.light_type,
                info.cct_only,
            )
            return info

    _LOGGER.debug("Unknown model, using defaults for: %s", name)
    return UNKNOWN_MODEL


def friendly_name(name: str | None) -> str:
    """Return a user-facing name for a BLE advertised device name."""
    if not name:
        return "Neewer Light"

    model_info = detect_model(name)
    if model_info == UNKNOWN_MODEL:
        return "Neewer Light"

    return f"Neewer {model_info.name}"


def model_options() -> dict[str, str]:
    """Return model choices for the options flow."""
    options = {MODEL_AUTO: "Auto detect"}
    options.update(
        {
            code: f"{info.name} ({code})"
            for code, info in sorted(SUPPORTED_MODELS.items(), key=lambda item: item[1].name)
        }
    )
    return options


def base_model_for_options(name: str, options: dict[str, Any]) -> ModelInfo:
    """Return the selected or detected base model before parameter overrides."""
    model_code = options.get(CONF_MODEL_OVERRIDE, MODEL_AUTO)
    if model_code != MODEL_AUTO and model_code in SUPPORTED_MODELS:
        return SUPPORTED_MODELS[model_code]

    return detect_model(name)


def model_from_options(name: str, options: dict[str, Any]) -> ModelInfo:
    """Return model info after applying config-entry overrides."""
    base_model = base_model_for_options(name, options)
    min_k, max_k = base_model.cct_range

    return ModelInfo(
        name=base_model.name,
        rgb=options.get(CONF_SUPPORTS_RGB, base_model.rgb),
        cct_range=(
            options.get(CONF_CCT_MIN_KELVIN, min_k),
            options.get(CONF_CCT_MAX_KELVIN, max_k),
        ),
        cct_only=options.get(CONF_CCT_ONLY, base_model.cct_only),
        light_type=options.get(CONF_LIGHT_TYPE, base_model.light_type),
    )
