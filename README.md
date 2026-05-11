# AquaGuard ESPHome Controller

ESPHome design for a Waveshare `ESP32-S3-ETH-8DI-8RO` used as an 8-zone water monitoring and shutoff controller.

The first ESPHome YAML implementation lives under `esphome/`.

## Scope

- 8 reed-switch pulse inputs, `1 L/pulse`
- 8 relay-controlled valves, one per meter
- configurable relay contact mode per zone, default `NC`
- Ethernet only
- local web UI
- Home Assistant via ESPHome native API
- persisted consumption and control state across reboot

## Hardware Model

Based on the official ESPHome device profile:

- MCU: `ESP32-S3-WROOM-1U-N16R8`
- Ethernet: `W5500`
- relay expander: `PCA9554/TCA9554` at I2C address `0x20`
- digital inputs: `GPIO4` to `GPIO11`
- relay outputs: expander pins `0` to `7`
- RTC: `PCF85063`
- I2C: `SDA GPIO42`, `SCL GPIO41`
- RGB LED: `WS2812` on `GPIO38`

## Control Model

Per zone:

- `Zone Name` is a persisted writable friendly label
- `Valve Wiring` selects the relay contact behavior: `NC` or `NO`
- `Consumption` is the persisted liter counter and the single writable source of truth
- `Limit Active` enables/disables limit enforcement
- `Limit` is the configured consumption threshold in liters
- `Admin Stop` forces water off regardless of limit

Computed logic:

- `Limit Exceeded = consumption >= limit`
- `Limit Stop = limit_active AND limit_exceeded`
- `Effective Stop = limit_stop OR admin_stop`
- `Water Allowed = NOT effective_stop`

Relay behavior:

- `NC` mode, default fail-open: relay/GPIO `0` allows water, relay/GPIO `1` stops water
- `NO` mode, controller-forced: relay/GPIO `1` allows water, relay/GPIO `0` stops water

Pulse validity:

- a pulse is counted only after debounce/filtering suppresses reed-switch contact bounce

## Time Model

- `SNTP` is the primary time source over Ethernet
- onboard `PCF85063` RTC is the backup time source
- RTC is read on boot and updated after SNTP sync

This supports reliable `Last Pulse Age` and `Last Pulse Timestamp` values.

## Device LED

Use the onboard RGB LED as a simple device-level indicator:

- blue while booting
- green when healthy

`Healthy` means:

- Ethernet/DHCP is up
- SNTP time is synchronized

## Exposed Per-Zone UI/API Entities

Writable:

- `Zone Name`
- `Valve Wiring`
- `Consumption`
- `Limit Active`
- `Limit`
- `Admin Stop`

Read-only:

- `Limit Exceeded`
- `Limit Stop`
- `Effective Stop`
- `Water Allowed`
- `Flow Rate EMA 5m`
- `Last Pulse Age`
- `Last Pulse Timestamp`

`Flow Rate EMA 5m` is public. The raw flow-rate source remains internal.

`Zone Name` is for operator-facing labels only. ESPHome entity IDs remain stable and zone-based.

## Implementation Notes

- `Consumption` should be implemented as a single writable number entity in liters.
- Use `preferences.flash_write_interval: 5min` to batch flash writes and reduce wear.
- Consumption should still be updated in RAM and published on every accepted pulse.
- After an unexpected power loss, up to about 5 minutes of recent pulses may need manual resync from the mechanical meter.
- Default values: `Zone Name = Zone N`, `Valve Wiring = NC`, `Consumption = 0`, `Limit Active = OFF`, `Limit = 0`, `Admin Stop = OFF`.

## Planned Structure

```text
.
├── README.md
├── docs/
│   ├── architecture.md
│   └── implementation-spec.md
└── esphome/
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

`aquaguard-main.yaml` includes `packages/zone.yaml` 8 times with per-zone variables for zone number, default name, digital input pin, and relay expander pin.

## ESPHome Usage

Create `esphome/secrets.yaml` from `esphome/secrets.example.yaml`, then validate from the repo root with:

```sh
esphome config esphome/aquaguard-main.yaml
```

Or with Docker:

```sh
docker run --rm -v "$PWD":/config -w /config ghcr.io/esphome/esphome:2026.4.5 config esphome/aquaguard-main.yaml
docker run --rm -v "$PWD":/config -w /config ghcr.io/esphome/esphome:2026.4.5 compile esphome/aquaguard-main.yaml
```

## Next Review Focus

Before flashing hardware, confirm:

- ESPHome validation/compile output
- the selected `NC`/`NO` relay logic per zone
- the physical DI/relay-to-zone wiring
- whether any additional diagnostics should be exposed
