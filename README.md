# AquaGuard ESPHome Controller

ESPHome design for a Waveshare `ESP32-S3-ETH-8DI-8RO` used as an 8-zone water monitoring and shutoff controller.

The first ESPHome YAML implementation lives under `esphome/`.

The stats dashboard lives under `stats/`. It is a FastAPI app that reads the AquaGuard ESPHome native API directly, stores daily noon snapshots in SQLite, and displays period totals plus per-zone daily consumption charts.

## Scope

- 8 reed-switch pulse inputs, `1 L/pulse`
- 8 relay-controlled valves, one per meter
- configurable relay contact mode per zone, default `NC`
- Ethernet only
- local web UI
- Home Assistant via ESPHome native API
- persisted meter consumption, period baseline, period limit, and control state across reboot
- manual and optional automatic period-baseline alignment

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
- `Meter Consumption` is the persisted physical meter counter in liters
- `Period Baseline` is the persisted meter reading used as the current period starting point
- `Period Limit Active` enables/disables period limit enforcement
- `Period Limit` is the configured period consumption threshold in liters
- `Admin Stop` forces water off regardless of period limit

Computed logic:

- `Period Consumption = max(0, meter_consumption - period_baseline)`
- `Period Limit Exceeded = period_consumption >= period_limit`
- `Period Limit Stop = period_limit_active AND period_limit_exceeded`
- `Effective Stop = period_limit_stop OR admin_stop`
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

## Period Alignment

The local UI includes a `Period Alignment` section for starting a new accounting/irrigation period.

- `Start New Period` copies every zone's `Meter Consumption` into that zone's `Period Baseline`
- `Automatic Yearly Period Alignment` optionally performs the same action once per configured period year
- `Period Alignment Month` and `Period Alignment Day` define the yearly reset date, defaulting to January 1
- `Current Period Year` is read-only and shows the active period year

On first SNTP sync, `Current Period Year` is initialized to the current calendar year if it is still unset.

If AquaGuard is powered off during the reset date, automatic alignment catches up after boot once SNTP time is valid. Invalid dates such as February 31 do not trigger automatic alignment.

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
- `Meter Consumption`
- `Period Baseline`
- `Period Limit Active`
- `Period Limit`
- `Admin Stop`

Read-only:

- `Period Consumption`
- `Period Limit Exceeded`
- `Period Limit Stop`
- `Effective Stop`
- `Water Allowed`
- `Flow Rate 60s`
- `Last Pulse Age`
- `Last Pulse Timestamp`

`Flow Rate 60s` is public and reports accepted pulses over the last minute as `L/min`.

`Zone Name` is for operator-facing labels only. ESPHome entity IDs remain stable and zone-based.

## Implementation Notes

- `Meter Consumption` should be implemented as a single writable number entity in liters.
- `Period Baseline` should be implemented as a writable number entity in liters.
- `Period Consumption` should be read-only and clamped to `0` if the meter reading is lower than the baseline.
- `Start New Period` should align all period baselines to the current meter values.
- `Automatic Yearly Period Alignment` defaults to `OFF`; default reset date is January 1.
- Use `preferences.flash_write_interval: 5min` to batch flash writes and reduce wear.
- Meter consumption and period consumption should still be updated in RAM and published on every accepted pulse.
- After an unexpected power loss, up to about 5 minutes of recent pulses may need manual resync from the mechanical meter.
- Default values: `Zone Name = Zone N`, `Valve Wiring = NC`, `Meter Consumption = 0`, `Period Baseline = 0`, `Period Limit Active = OFF`, `Period Limit = 0`, `Admin Stop = OFF`.

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

## Stats Dashboard Usage

Build and run the dashboard on a Docker host:

```sh
cd stats
docker compose up --build
```

Set `AQUAGUARD_ESPHOME_HOST` and `AQUAGUARD_API_ENCRYPTION_KEY` in `stats/compose.yaml` or your Docker environment before deploying. The dashboard listens on `http://localhost:8080` and stores SQLite data under `stats/data/` by default.

## Next Review Focus

Before flashing hardware, confirm:

- ESPHome validation/compile output
- the selected `NC`/`NO` relay logic per zone
- the physical DI/relay-to-zone wiring
- whether any additional diagnostics should be exposed
