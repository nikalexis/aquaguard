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
│   ├── globals.yaml
│   ├── scripts.yaml
│   ├── diagnostics.yaml
│   └── zones/
│       ├── zone_1.yaml
│       ├── zone_2.yaml
│       ├── zone_3.yaml
│       ├── zone_4.yaml
│       ├── zone_5.yaml
│       ├── zone_6.yaml
│       ├── zone_7.yaml
│       └── zone_8.yaml
└── secrets.example.yaml
```

## Per-Zone Entity Names

- `zone_N_name`
- `zone_N_consumption_l`
- `zone_N_limit_active`
- `zone_N_limit_l`
- `zone_N_limit_exceeded`
- `zone_N_limit_stop`
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
  restore order and startup consistency

- `globals.yaml`
  persisted consumption, limit toggle, limit value, admin stop, last-pulse epoch

- `scripts.yaml`
  shared evaluation/apply scripts

- `diagnostics.yaml`
  uptime, restart reason, network diagnostics, optional time diagnostics

## Device LED

Use the onboard RGB LED on the board as a simple device-level status light:

- booting: blue
- healthy: green
- pulse received: brief white flash

Healthy means:

- Ethernet/DHCP is working
- SNTP time has synchronized

The pulse flash should be triggered only for accepted pulses after debounce/filtering.

## Zone File Responsibilities

Each `zone_N.yaml` should define:

- writable `Zone Name`
- pulse input
- relay output
- writable `Consumption`
- writable `Limit Active`
- writable `Limit`
- writable `Admin Stop`
- read-only `Limit Exceeded`
- read-only `Limit Stop`
- read-only `Effective Stop`
- read-only `Water Allowed`
- read-only `Flow Rate EMA 5m`
- read-only `Last Pulse Age`
- read-only `Last Pulse Timestamp`

## Runtime Rules

Pulse counting:

- each valid pulse increments `Consumption` by `1`
- a pulse is valid only after debounce/filtering suppresses reed-switch contact bounce
- persist after each increment
- store last-pulse time after each increment
- re-evaluate zone after each increment

Consumption resync:

- `Consumption` is writable by admin
- implement `Consumption` as one writable number entity in liters
- manual edits are for meter resynchronization
- re-evaluate zone after each edit

Zone naming:

- `Zone Name` is writable by admin
- it is persisted
- it is for operator-facing labeling only
- do not use `Zone Name` as a stable internal entity ID

Limit logic:

- `limit_exceeded = consumption >= limit`
- `limit_stop = limit_active AND limit_exceeded`

Admin stop:

- `Admin Stop = ON` forces water off
- `Admin Stop = OFF` removes forced stop

Final relay logic:

- `effective_stop = limit_stop OR admin_stop`
- `water_allowed = NOT effective_stop`
- relay `ON` when `effective_stop = true`
- relay `OFF` when `effective_stop = false`

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
- `Consumption`
- `Limit Active`
- `Limit`
- `Admin Stop`
- last-pulse epoch

Default values:

- `Zone Name = Zone N`
- `Consumption = 0`
- `Limit Active = ON`
- `Limit = 0`
- `Admin Stop = OFF`

Flash-write caution:

- consumption may change frequently
- avoid forcing flash writes on every pulse if ESPHome restore/preference batching can handle it
- keep `Consumption` recoverable across reboot without turning every liter into an immediate manual flash write

Boot restore order:

1. restore persisted values
2. compute `limit_exceeded`, `limit_stop`, `effective_stop`
3. apply relay state
4. publish entities

## Acceptance Criteria

- one top-level ESPHome file plus shared packages
- 8 modular zone files
- Ethernet only
- native API enabled
- local web UI enabled
- valves on relay `NC`
- persisted consumption and control state
- public per-zone flow, pulse-history, and stop-state diagnostics
- raw flow sensor kept internal
