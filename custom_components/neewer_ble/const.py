"""Constants for the Neewer BLE integration."""

DOMAIN = "neewer_ble"

# BLE Characteristic UUIDs
NEEWER_WRITE_CHARACTERISTIC_UUID = "69400002-b5a3-f393-e0a9-e50e24dcca99"
NEEWER_NOTIFY_CHARACTERISTIC_UUID = "69400003-b5a3-f393-e0a9-e50e24dcca99"

# Status query commands (per NeewerLite-Python)
CMD_GET_POWER_STATUS = [0x78, 0x85, 0x00, 0xFD]  # Response type 2: [3]=1 ON, [3]=2 STANDBY
CMD_GET_CHANNEL_STATUS = [0x78, 0x84, 0x00, 0xFC]  # Response type 1: current channel/mode

# Default values
DEFAULT_BRIGHTNESS = 100
DEFAULT_COLOR_TEMP = 3200

# Options flow config keys
CONF_DEFAULT_BRIGHTNESS = "default_brightness"
CONF_DEFAULT_COLOR_TEMP = "default_color_temp"

# Scan timeout
BLE_SCAN_TIMEOUT = 10

# Connection retry settings
MAX_CONNECTION_RETRIES = 3
