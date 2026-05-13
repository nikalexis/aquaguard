# Implementation Spec

## Goal

Generate a modular ESPHome project for the Waveshare `ESP32-S3-ETH-8DI-8RO` that matches the approved controller behavior and exposes the agreed UI/API entities.

## File Layout

```text
esphome/
├── aquaguard-main.yaml
├── packages/
│   ├── device_base.yaml
│   ├── hardware.yaml
│   ├── ethernet.yaml
│   ├── time.yaml
│   ├── web.yaml
│   ├── persistence.yaml
│   ├── scripts.yaml
│   ├── diagnostics.yaml
│   └── zone.yaml
└── secrets.example.yaml
```

`aquaguard-main.yaml` should include `packages/zone.yaml` 8 times with ESPHome package variables.

Required zone include variables:

- `zone`
- `default_zone_name`
- `di_pin`
- `relay_pin`

Example:

```yaml
packages:
  zone_1: !include
    file: packages/zone.yaml
    vars:
      zone: "1"
      default_zone_name: "Zone 1"
      di_pin: GPIO4
      relay_pin: "0"
```

## Per-Zone Entity Names

- `zone_N_name`
- `zone_N_valve_wiring`
- `zone_N_meter_consumption_l`
- `zone_N_period_baseline_l`
- `zone_N_period_consumption_l`
- `zone_N_period_limit_active`
- `zone_N_period_limit_l`
- `zone_N_period_limit_exceeded`
- `zone_N_period_limit_stop`
- `zone_N_admin_stop`
- `zone_N_effective_stop`
- `zone_N_water_allowed`
- `zone_N_flow_rate_ema_5m`
- `zone_N_last_pulse_age`
- `zone_N_last_pulse_timestamp`

Friendly names should use `Zone N ...`.

## Hardware Facts

Use the official ESPHome device profile as the hardware source of truth:

- `esp32.board: esp32s3box`
- flash: `16MB`
- PSRAM: octal, `80MHz`
- Ethernet: `W5500`
- Ethernet pins: `clk GPIO15`, `mosi GPIO13`, `miso GPIO14`, `cs GPIO16`, `interrupt GPIO12`
- I2C: `sda GPIO42`, `scl GPIO41`, `100kHz`
- RTC: `pcf85063`
- relay expander: `pca9554`, address `0x20`
- relays: expander pins `0..7`, not direct ESP32 GPIO
- digital inputs: `GPIO4..GPIO11`, `INPUT_PULLUP`, inverted
- input debounce: `delayed_on_off: 10ms`
- RGB LED: `esp32_rmt_led_strip`, `WS2812`, `GPIO38`, `num_leds: 1`

## Shared Package Responsibilities

- `device_base.yaml`
  ESP32 platform, logger, API, optional OTA, boot hooks

- `hardware.yaml`
  DI pin mapping, relay pin mapping, I2C bus, board-specific electrical notes

- `ethernet.yaml`
  Ethernet PHY and addressing

- `time.yaml`
  `sntp` primary time, `pcf85063` RTC backup, RTC read on boot, RTC write after sync

- `web.yaml`
  local web UI

- `persistence.yaml`
  restore order, startup consistency, and `preferences.flash_write_interval: 5min`

- `scripts.yaml`
  shared non-zone helpers, if needed

- `diagnostics.yaml`
  uptime, restart reason, network diagnostics, optional time diagnostics

## Device LED

Use the onboard RGB LED on the board as a simple device-level status light:

- booting: blue
- healthy: green

Healthy means:

- Ethernet/DHCP is working
- SNTP time has synchronized

## Zone Template Responsibilities

`packages/zone.yaml` should define one reusable zone. Each include instance should define:

- writable `Zone Name`
- writable `Valve Wiring`
- pulse input
- relay output
- writable `Meter Consumption`
- writable `Period Baseline`
- writable `Period Limit Active`
- writable `Period Limit`
- writable `Admin Stop`
- read-only `Period Consumption`
- read-only `Period Limit Exceeded`
- read-only `Period Limit Stop`
- read-only `Effective Stop`
- read-only `Water Allowed`
- read-only `Flow Rate EMA 5m`
- read-only `Last Pulse Age`
- read-only `Last Pulse Timestamp`

Zone-specific persisted values should live in this template with IDs derived from `${zone}`.

## Period Alignment Responsibilities

Expose a shared `Period Alignment` UI group with:

- `Start New Period`
- `Automatic Yearly Period Alignment`
- `Period Alignment Month`
- `Period Alignment Day`
- read-only `Current Period Year`

`Start New Period` should copy every zone's `Meter Consumption` into that zone's `Period Baseline`, then re-evaluate all zones.

Automatic yearly alignment:

- default disabled
- default reset date January 1
- use SNTP time in the configured timezone
- initialize `Current Period Year` to the current calendar year on first SNTP sync if it is still `0`
- run after SNTP sync and daily shortly after midnight
- catch up after seasonal power-off if the reset date already passed
- ignore invalid dates such as February 31
- update `Current Period Year` after successful automatic alignment

## Runtime Rules

Pulse counting:

- each valid pulse increments `Meter Consumption` by `1`
- a pulse is valid only after debounce/filtering suppresses reed-switch contact bounce
- publish the updated meter consumption and period consumption after each increment
- rely on ESPHome persistence with `preferences.flash_write_interval: 5min` instead of forcing a manual flash write on every pulse
- store last-pulse time after each increment
- re-evaluate zone after each increment

Meter and period consumption:

- `Meter Consumption` is writable by admin
- implement `Meter Consumption` as one writable number entity in liters
- manual meter edits are for meter resynchronization
- `Period Baseline` is writable by admin and stores the meter reading at the start of the current period
- `Period Consumption` is read-only and calculated as `max(0, meter_consumption - period_baseline)`
- re-evaluate zone after meter or baseline edits
- `Start New Period` aligns all baselines to current meter values

Zone naming:

- `Zone Name` is writable by admin
- it is persisted
- it is for operator-facing labeling only
- do not use `Zone Name` as a stable internal entity ID

Valve wiring:

- `Valve Wiring` is a persisted admin selection with options `NC` and `NO`
- default is `NC`
- `NC` means relay `OFF` allows water and relay `ON` stops water
- `NO` means relay `ON` allows water and relay `OFF` stops water

Period limit logic:

- `period_limit_exceeded = period_consumption >= period_limit`
- `period_limit_stop = period_limit_active AND period_limit_exceeded`

Admin stop:

- `Admin Stop = ON` forces water off
- `Admin Stop = OFF` removes forced stop

Final relay logic:

- `effective_stop = period_limit_stop OR admin_stop`
- `water_allowed = NOT effective_stop`
- in `NC` mode, relay `ON` when `effective_stop = true`
- in `NO` mode, relay `ON` when `effective_stop = false`

## Flow Rate

- use an internal raw rate sensor from the pulse input
- expose only `Flow Rate EMA 5m`
- unit: `L/min`
- EMA tuned to approximate 5 minutes

## Time and Pulse History

- use `SNTP` over Ethernet as primary time source
- use onboard `PCF85063` RTC as backup
- `Last Pulse Age` is a read-only numeric sensor
- `Last Pulse Timestamp` is a read-only text sensor
- if valid time is unavailable after boot, timestamp should remain unknown until sync

## Persistence

Persist at minimum:

- `Zone Name`
- `Valve Wiring`
- `Meter Consumption`
- `Period Baseline`
- `Period Limit Active`
- `Period Limit`
- `Admin Stop`
- last-pulse epoch
- automatic yearly period alignment enabled
- period alignment month/day
- current period year

Default values:

- `Zone Name = Zone N`
- `Valve Wiring = NC`
- `Meter Consumption = 0`
- `Period Baseline = 0`
- `Period Limit Active = OFF`
- `Period Limit = 0`
- `Admin Stop = OFF`
- `Automatic Yearly Period Alignment = OFF`
- `Period Alignment Month = 1`
- `Period Alignment Day = 1`
- `Current Period Year = 0`

Flash-write caution:

- meter consumption may change frequently
- use `preferences.flash_write_interval: 5min`
- do not force immediate flash writes on every pulse
- accept that after sudden power loss, up to about 5 minutes of recent pulses may need manual resync from the mechanical meter

Boot restore order:

1. restore persisted values
2. compute `period_consumption`, `period_limit_exceeded`, `period_limit_stop`, `effective_stop`
3. apply relay state
4. publish entities

## Acceptance Criteria

- one top-level ESPHome file plus shared packages
- one reusable zone template included 8 times
- Ethernet only
- native API enabled
- local web UI enabled
- per-zone relay contact mode defaults to `NC` and can be changed to `NO`
- persisted meter consumption, period baseline, period limit, and control state
- period-alignment controls and current period year
- public per-zone flow, pulse-history, and stop-state diagnostics
- raw flow sensor kept internal
