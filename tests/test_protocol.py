"""Unit tests for Neewer BLE protocol helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


COMPONENT_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "neewer_ble"
)
PACKAGE_NAME = "neewer_ble"


def load_component_module(name: str):
    """Load one integration module without importing Home Assistant platforms."""
    package = sys.modules.setdefault(PACKAGE_NAME, types.ModuleType(PACKAGE_NAME))
    package.__path__ = [str(COMPONENT_DIR)]

    full_name = f"{PACKAGE_NAME}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]

    spec = importlib.util.spec_from_file_location(
        full_name,
        COMPONENT_DIR / f"{name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


const = load_component_module("const")
models = load_component_module("models")
performance = load_component_module("performance")
protocol = load_component_module("protocol")


class NeewerProtocolTest(unittest.TestCase):
    """Verify generated Neewer BLE command bytes."""

    def test_checksum_wraps_to_single_byte(self) -> None:
        """Checksum is the low byte of the command sum."""
        self.assertEqual(protocol.calculate_checksum([0x78, 0x81, 0x01, 0x02]), 0xFC)

    def test_standard_power_off_command(self) -> None:
        """Standard protocol sends the known power-off payload."""
        model = models.ModelInfo("Test", False, (2700, 6500), False, 0)
        neewer_protocol = protocol.NeewerProtocol(model, lambda: [1, 2, 3, 4, 5, 6])

        self.assertEqual(
            neewer_protocol.build_power_command(False),
            [0x78, 0x81, 0x01, 0x02, 0xFC],
        )

    def test_infinity_cct_maps_full_kelvin_range(self) -> None:
        """Infinity CCT commands use model Kelvin limits for protocol temperature."""
        model = models.ModelInfo("MS150B", False, (2700, 6500), False, 1)
        neewer_protocol = protocol.NeewerProtocol(model, lambda: [1, 2, 3, 4, 5, 6])

        warm = neewer_protocol.build_cct_command(
            50, neewer_protocol.kelvin_to_internal(2700)
        )
        cool = neewer_protocol.build_cct_command(
            50, neewer_protocol.kelvin_to_internal(6500)
        )

        self.assertEqual(warm[11], 27)
        self.assertEqual(cool[11], 65)

    def test_model_options_override_capabilities(self) -> None:
        """Options can override detected model parameters."""
        model = models.model_from_options(
            "Unknown",
            {
                const.CONF_MODEL_OVERRIDE: "20220035",
                const.CONF_CCT_MIN_KELVIN: 2600,
                const.CONF_CCT_MAX_KELVIN: 7000,
                const.CONF_SUPPORTS_RGB: True,
                const.CONF_CCT_ONLY: True,
                const.CONF_LIGHT_TYPE: 2,
            },
        )

        self.assertEqual(model.name, "MS150B")
        self.assertTrue(model.rgb)
        self.assertEqual(model.cct_range, (2600, 7000))
        self.assertTrue(model.cct_only)
        self.assertEqual(model.light_type, 2)

    def test_default_color_temp_uses_model_minimum(self) -> None:
        """The implicit default CCT is the warmest supported model value."""
        self.assertEqual(
            models.default_color_temp_for_options("NW-20220051&FFFFFFFF", {}),
            2700,
        )

    def test_default_color_temp_uses_overridden_minimum(self) -> None:
        """The implicit default follows configured CCT range overrides."""
        self.assertEqual(
            models.default_color_temp_for_options(
                "NW-20220051&FFFFFFFF",
                {const.CONF_CCT_MIN_KELVIN: 2600},
            ),
            2600,
        )

    def test_default_color_temp_allows_explicit_override(self) -> None:
        """A configured default CCT still wins over the implicit model minimum."""
        self.assertEqual(
            models.default_color_temp_for_options(
                "NW-20220051&FFFFFFFF",
                {const.CONF_DEFAULT_COLOR_TEMP: 3200},
            ),
            3200,
        )

    def test_friendly_name_uses_detected_model_name(self) -> None:
        """Discovered devices get a user-facing model name."""
        self.assertEqual(
            models.friendly_name("NW-20220051&FFFFFFFF"),
            "Neewer CB100C",
        )
        self.assertEqual(
            models.detect_model("Neewer CB100C").name,
            "CB100C",
        )


class NeewerPerformanceTest(unittest.TestCase):
    """Verify adaptive BLE performance helper behavior."""

    def test_command_delay_tracks_signal_quality(self) -> None:
        """Weak RSSI gets safer command spacing than strong RSSI."""
        self.assertEqual(performance.command_delay_for_rssi(-65), 0.02)
        self.assertEqual(performance.command_delay_for_rssi(-88), 0.04)
        self.assertEqual(performance.command_delay_for_rssi(None), 0.05)

    def test_command_delay_moves_toward_signal_baseline(self) -> None:
        """Successful writes reduce delay while failures increase it."""
        self.assertEqual(performance.next_command_delay(0.06, -88, True), 0.055)
        self.assertEqual(performance.next_command_delay(0.04, -88, True), 0.04)
        self.assertEqual(performance.next_command_delay(0.04, -88, False), 0.06)

    def test_poll_backoff_starts_after_repeated_query_failures(self) -> None:
        """Polling backs off only after several consecutive misses."""
        self.assertEqual(performance.poll_backoff_seconds(2), 0)
        self.assertEqual(performance.poll_backoff_seconds(3), 30)
        self.assertEqual(performance.poll_backoff_seconds(4), 60)

    def test_query_timeout_accounts_for_weak_signal(self) -> None:
        """Weak links get a little more time without blocking indefinitely."""
        self.assertEqual(performance.query_timeout_for_failures(0, -70), 0.5)
        self.assertEqual(performance.query_timeout_for_failures(0, -88), 0.65)
        self.assertEqual(performance.query_timeout_for_failures(2, -88), 0.75)
        self.assertEqual(performance.query_timeout_for_failures(10, -88), 0.75)


if __name__ == "__main__":
    unittest.main()
