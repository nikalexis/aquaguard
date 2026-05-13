# Architecture

## Overview

The controller is an Ethernet-only ESPHome node for the Waveshare `ESP32-S3-ETH-8DI-8RO`. It manages 8 identical zones. Each zone has:

- 1 persisted writable friendly name
- 1 persisted `Valve Wiring` selection, default `NC`
- 1 reed-switch meter input
- 1 persisted `Meter Consumption` counter in liters
- 1 persisted `Period Baseline` meter reading in liters
- 1 read-only calculated `Period Consumption` value in liters
- 1 persisted `Period Limit Active` toggle
- 1 persisted `Period Limit`
- 1 persisted `Admin Stop` toggle
- 1 relay output controlling one valve

The device also has shared period-alignment controls:

- 1 manual `Start New Period` button
- 1 persisted `Automatic Yearly Period Alignment` toggle, default `OFF`
- persisted `Period Alignment Month` and `Period Alignment Day`, default January 1
- read-only `Current Period Year`

## Hardware

The implementation should follow the official ESPHome device profile:

- MCU: `ESP32-S3-WROOM-1U-N16R8`, 16 MB flash, 8 MB PSRAM
- ESPHome board target: `esp32s3box`
- Ethernet: `W5500`
- Ethernet pins: `CLK GPIO15`, `MOSI GPIO13`, `MISO GPIO14`, `CS GPIO16`, `INT GPIO12`
- I2C pins: `SDA GPIO42`, `SCL GPIO41`
- RTC: `PCF85063`
- relay expander: `PCA9554/TCA9554`, address `0x20`
- relay outputs: expander pins `0` to `7`
- digital inputs: `DI1 GPIO4`, `DI2 GPIO5`, `DI3 GPIO6`, `DI4 GPIO7`, `DI5 GPIO8`, `DI6 GPIO9`, `DI7 GPIO10`, `DI8 GPIO11`
- RGB LED: `WS2812`, `GPIO38`, 1 LED

## Zone Logic

Pulse handling:

- each valid pulse adds `1` liter to `Meter Consumption`
- a pulse is valid only after debounce/filtering suppresses reed-switch contact bounce
- `Meter Consumption` is persisted
- admin may manually edit `Meter Consumption` to resync with the mechanical meter
- admin may set `Period Baseline` to the meter reading at the beginning of a billing or monitoring period
- `Period Consumption = max(0, meter_consumption - period_baseline)`

Stop logic:

- `Period Limit Exceeded = period_consumption >= period_limit`
- `Period Limit Stop = period_limit_active AND period_limit_exceeded`
- `Effective Stop = period_limit_stop OR admin_stop`
- `Water Allowed = NOT effective_stop`

Relay behavior:

- `Valve Wiring = NC`: relay `OFF` / GPIO `0` allows water, relay `ON` / GPIO `1` stops water
- `Valve Wiring = NO`: relay `ON` / GPIO `1` allows water, relay `OFF` / GPIO `0` stops water
- `NC` is the default/fail-open mode; `NO` is controller-forced and stops water if the controller loses power

The relay state is computed from persisted zone state after reboot. It is not treated as an independent source of truth.

## Time and Pulse History

Time sources:

- `SNTP` primary
- onboard `PCF85063` RTC backup

Behavior:

- read RTC on boot
- after SNTP sync, write time back to RTC

Per zone pulse-history entities:

- `Last Pulse Age` as read-only sensor
- `Last Pulse Timestamp` as read-only text sensor

## Period Alignment

Manual alignment:

- `Start New Period` copies each zone's `Meter Consumption` into its `Period Baseline`
- each zone recomputes `Period Consumption` and stop state after alignment
- when time is valid, manual alignment updates `Current Period Year` to the active configured period year

Automatic alignment:

- runs only when `Automatic Yearly Period Alignment` is enabled
- uses the configured month/day in the device timezone
- aligns once per period year when the reset date has passed
- catches up after seasonal power-off once SNTP time is valid
- ignores invalid configured dates such as February 31

`Current Period Year` tracks the configured period year whose baselines are active. Before the configured reset date, that may be the previous calendar year.

On first SNTP sync, if `Current Period Year` is still `0`, it is initialized to the current calendar year.

## Device LED

Use the onboard RGB LED only for device-level status:

- blue while booting
- green when the controller is healthy

Healthy means:

- Ethernet link/DHCP is established
- SNTP time is valid

## Flow Rate

Per zone:

- public read-only `Flow Rate EMA 5m` in `L/min`
- internal raw pulse-rate sensor only for implementation

Because `1 pulse = 1 L`, pulse rate in pulses/min maps directly to `L/min`.

## Exposed Entities

Writable per zone:

- `Zone Name`
- `Valve Wiring`
- `Meter Consumption`
- `Period Baseline`
- `Period Limit Active`
- `Period Limit`
- `Admin Stop`

Read-only per zone:

- `Period Consumption`
- `Period Limit Exceeded`
- `Period Limit Stop`
- `Effective Stop`
- `Water Allowed`
- `Flow Rate EMA 5m`
- `Last Pulse Age`
- `Last Pulse Timestamp`

`Zone Name` should be used as the operator-facing label where practical. It should not be used as a stable internal entity ID because ESPHome entity IDs are static.

## Defaults and Persistence

Default per zone:

- `Zone Name = Zone N`
- `Valve Wiring = NC`
- `Meter Consumption = 0`
- `Period Baseline = 0`
- `Period Limit Active = OFF`
- `Period Limit = 0`
- `Admin Stop = OFF`

Persistence should cover writable zone state and last-pulse epoch. The YAML should publish every accepted pulse immediately in RAM and expose the updated meter and period consumption through the API/UI, but use `preferences.flash_write_interval: 5min` so flash commits are batched. After unexpected power loss, up to about 5 minutes of recent pulses may need manual resync from the mechanical meter.

Shared period-alignment persistence should cover automatic alignment enablement, alignment month/day, and current period year.

## File Responsibilities

Top level:

- `aquaguard-main.yaml`: imports packages and holds top-level substitutions

Shared packages:

- `device_base.yaml`: ESP32 platform, logger, API, base services
- `hardware.yaml`: pin mapping, buses, board-specific hardware definitions
- `ethernet.yaml`: Ethernet config
- `time.yaml`: SNTP + RTC config
- `web.yaml`: web UI
- `persistence.yaml`: boot ordering, restore behavior, and `preferences.flash_write_interval: 5min`
- `scripts.yaml`: shared non-zone helpers and period-alignment controls
- `diagnostics.yaml`: node-level diagnostics

Per zone:

- `zone.yaml`: reusable zone template included 8 times with package variables

The top-level file should include `packages/zone.yaml` once per zone with variables for zone number, default zone name, digital input pin, and relay expander pin. Zone-specific persisted values belong in the reusable template using IDs derived from the zone number.

## Integration

Primary integration path:

- ESPHome native `api`

This covers:

- reading meter and period consumption
- updating writable zone controls
- reading status and diagnostics

MQTT is not required by the current design.
