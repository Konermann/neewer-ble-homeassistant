# Neewer BLE Lights Extended for Home Assistant

<p align="center">
  <img
    src="https://raw.githubusercontent.com/Konermann/neewer-ble-homeassistant/main/custom_components/neewer_ble/brand/logo.png"
    alt="Neewer BLE Lights Extended"
    width="720"
  >
</p>

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Control Neewer LED lights from Home Assistant over Bluetooth Low Energy (BLE).

This repository is a fork of
[darinlarimore/neewer-ble-homeassistant](https://github.com/darinlarimore/neewer-ble-homeassistant).

## Why This Fork?

The upstream project appears to be inactive, and this fork continues the work
for current Home Assistant versions and newer Neewer lights.

The goal is to keep the original integration spirit while adding reliability
improvements, connection controls, diagnostics, model overrides, and tested
support for additional devices.

## Highlights

| Area | Included |
| --- | --- |
| Light control | Power, brightness, color temperature, RGB/HS color, and FX effects on supported models |
| Bluetooth | Persistent connection, reconnect button, connect/disconnect switch, connect-time state sync |
| Diagnostics | Connection status, failure notifications, RSSI, adaptive timing, dump and benchmark buttons |
| Model tuning | Model override, protocol override, CCT min/max, RGB/CCT capability flags |
| Off behavior | Choose real Neewer power-off command or brightness `0` off mode |

## Supported Devices

| Status | Models |
| --- | --- |
| Tested | **MS150B**, **CB100C** |
| Expected to work | MS60C, RGB660 / RGB660 PRO, RGB480 / RGB530, SL-80, SNL-660, GL1, CB300B, RGB1, TL60 RGB |

Unknown Neewer BLE lights may still work with model/capability overrides.

## Requirements

- Home Assistant 2024.1.0 or newer
- A Bluetooth adapter on the Home Assistant host, or an ESPHome Bluetooth Proxy
- A Neewer light with Bluetooth control enabled

<details>
<summary><strong>Installation</strong></summary>

### HACS

1. Open HACS.
2. Open **Custom repositories**.
3. Add the URL of this fork as an **Integration** repository.
4. Install **Neewer BLE Lights Extended**.
5. Restart Home Assistant.

### Manual

1. Copy `custom_components/neewer_ble` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

</details>

<details>
<summary><strong>Setup</strong></summary>

### Automatic discovery

If the light is powered on and in range, Home Assistant should discover it.
Open the discovery notification and confirm the device.

### Manual setup

1. Go to **Settings** -> **Devices & Services**.
2. Select **Add Integration**.
3. Search for **Neewer BLE Lights Extended**.
4. Select a discovered light or enter the Bluetooth address manually.

</details>

## Usage

After setup, the light appears as a normal Home Assistant light entity. You can:

- Turn the light on and off.
- Set brightness and color temperature.
- Set RGB/HS color on supported lights.
- Select FX effects from the light entity's effect control on supported lights.
- Disconnect Home Assistant from the light so another Bluetooth app can connect.
- Reconnect a stale BLE session.
- Create a diagnostic dump from the device page.
- Run a BLE benchmark and let the integration adapt polling/command timing.
- Read the lamp state once after connecting and avoid recurring BLE status
  polls during normal light control.

## Options

Options are available in two places:

- **Settings** -> **Devices & Services** -> the integration's options dialog
- The Home Assistant device page, as hidden-by-default advanced config entities

The everyday Bluetooth connection switch and reconnect button are primary device
controls. Model and default-value overrides are hidden by default to keep the
device page focused on normal light control.

| Option | Use |
| --- | --- |
| Default brightness | Brightness used when turning on without an explicit value |
| Default color temperature | Color temperature used when turning on. Uses the lowest configured CCT if unset. |
| Brightness `0` off mode | Sends zero brightness instead of the Neewer power-off command |
| Model override | Forces a known model profile when auto-detection is wrong |
| Lowest/highest CCT | Overrides the model Kelvin range, for example `2700` to `6500` |
| Supports RGB / HS color | Enables or disables RGB color support |
| Separate CCT commands | Uses separate brightness and temperature commands for older CCT lights |
| Protocol type | Selects standard, Infinity, or Infinity-hybrid command format |

<details>
<summary><strong>Example Automations</strong></summary>

```yaml
automation:
  - alias: "Studio Light On When Recording"
    trigger:
      - platform: state
        entity_id: binary_sensor.camera_active
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.neewer_ms150b
        data:
          brightness_pct: 80
          color_temp_kelvin: 5600
```

```yaml
script:
  video_call_lighting:
    sequence:
      - service: light.turn_on
        target:
          entity_id: light.neewer_ms150b
        data:
          brightness_pct: 60
          color_temp_kelvin: 4500
```

</details>

<details>
<summary><strong>Troubleshooting</strong></summary>

### Light is not discovered

- Make sure the light is powered on and in range.
- Check that Bluetooth is enabled on the Home Assistant host.
- Check that no other app is already connected to the light.
- Try manual setup with the Bluetooth address.

### Another Bluetooth app cannot connect

Turn off the integration's **Connection** switch. Home Assistant will release the
BLE session so another app can connect.

### Light stops responding

- Press the **Reconnect** button.
- Restart the light if the BLE stack is stuck.
- Check RSSI on the device page; weak signal can cause delayed commands.
- Press **Diagnostic Dump** and include the JSON when opening an issue.

### Color temperature looks wrong

Open the options or device config entities and check:

- Model override
- Lowest/highest CCT values
- Protocol type

For an MS150B or CB100C, the expected CCT range is `2700` to `6500`.

</details>

<details>
<summary><strong>Development</strong></summary>

Model definitions live in `custom_components/neewer_ble/models.py`.

Run the lightweight unit tests with:

```bash
python3 -m unittest discover -s tests
```

This integration builds on reverse-engineered Neewer BLE protocol work from:

- [NeewerLite](https://github.com/keefo/NeewerLite)
- [NeewerLite-Python](https://github.com/taburineagle/NeewerLite-Python)

</details>

## License

MIT License. See [LICENSE](LICENSE).

## Disclaimer

This is an unofficial integration and is not affiliated with or endorsed by Neewer.
