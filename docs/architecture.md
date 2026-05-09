# Architecture

## Overview

The controller is an Ethernet-only ESPHome node for the Waveshare `ESP32-S3-ETH-8DI-8RO`. It manages 8 identical zones. Each zone has:

- 1 persisted writable friendly name
- 1 reed-switch meter input
- 1 persisted consumption counter in liters
- 1 persisted `Limit Active` toggle
- 1 persisted consumption `Limit`
- 1 persisted `Admin Stop` toggle
- 1 relay output controlling one valve

## Zone Logic

Pulse handling:

- each valid pulse adds `1` liter to `Consumption`
- a pulse is valid only after debounce/filtering suppresses reed-switch contact bounce
- `Consumption` is persisted
- admin may manually edit `Consumption` to resync with the mechanical meter

Stop logic:

- `Limit Exceeded = consumption >= limit`
- `Limit Stop = limit_active AND limit_exceeded`
- `Effective Stop = limit_stop OR admin_stop`
- `Water Allowed = NOT effective_stop`

Relay behavior:

- valve is wired to the relay `NC` contact
- relay `OFF` / GPIO `0` = water allowed
- relay `ON` / GPIO `1` = water stopped

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

## Device LED

Use the onboard RGB LED only for device-level status:

- blue while booting
- green when the controller is healthy
- brief white flash on each accepted pulse

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
- `Consumption`
- `Limit Active`
- `Limit`
- `Admin Stop`

Read-only per zone:

- `Limit Exceeded`
- `Limit Stop`
- `Effective Stop`
- `Water Allowed`
- `Flow Rate EMA 5m`
- `Last Pulse Age`
- `Last Pulse Timestamp`

`Zone Name` should be used as the operator-facing label where practical, while internal entity IDs remain zone-based.

## File Responsibilities

Top level:

- `aquaguard-main.yaml`: imports packages and holds top-level substitutions

Shared packages:

- `device_base.yaml`: ESP32 platform, logger, API, base services
- `hardware.yaml`: pin mapping, buses, board-specific hardware definitions
- `ethernet.yaml`: Ethernet config
- `time.yaml`: SNTP + RTC config
- `web.yaml`: web UI
- `persistence.yaml`: boot ordering and restore behavior
- `globals.yaml`: persisted scalar state
- `scripts.yaml`: shared zone scripts
- `diagnostics.yaml`: node-level diagnostics

Per zone:

- `zones/zone_N.yaml`: input, relay, entities, and zone automations

## Integration

Primary integration path:

- ESPHome native `api`

This covers:

- reading consumption
- updating writable zone controls
- reading status and diagnostics

MQTT is not required by the current design.
