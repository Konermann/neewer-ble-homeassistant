"""Compatibility exports for the Neewer BLE device API."""

from .device import NeewerLightDevice, discover_neewer_lights

__all__ = ["NeewerLightDevice", "discover_neewer_lights"]
