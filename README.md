# AquaGuard ESPHome Controller

ESPHome design for a Waveshare `ESP32-S3-ETH-8DI-8RO` used as an 8-zone water monitoring and shutoff controller.

This repo is still in the spec phase. No ESPHome YAML has been generated yet.

## Scope

- 8 reed-switch pulse inputs, `1 L/pulse`
- 8 relay-controlled valves, one per meter
- valves wired to relay `NC` contact
- Ethernet only
- local web UI
- Home Assistant via ESPHome native API
- persisted consumption and control state across reboot

## Control Model

Per zone:

- `Zone Name` is a persisted writable friendly label
- `Consumption` is the persisted liter counter and the single writable source of truth
- `Limit Active` enables/disables limit enforcement
- `Limit` is the configured consumption threshold in liters
- `Admin Stop` forces water off regardless of limit

Computed logic:

- `Limit Exceeded = consumption >= limit`
- `Limit Stop = limit_active AND limit_exceeded`
- `Effective Stop = limit_stop OR admin_stop`
- `Water Allowed = NOT effective_stop`

Relay behavior with valve on `NC`:

- relay/GPIO `0` = coil de-energized = water allowed
- relay/GPIO `1` = coil energized = water stopped

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
- white flash on every accepted pulse

`Healthy` means:

- Ethernet/DHCP is up
- SNTP time is synchronized

## Exposed Per-Zone UI/API Entities

Writable:

- `Zone Name`
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

`Zone Name` is for operator-facing labels only and should not be used as a stable internal ID.

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

## Review Focus

Before YAML generation, confirm:

- the modular file layout
- the `NC` relay logic
- whether writable entities should be editable from both web UI and Home Assistant
- whether any additional diagnostics should be exposed
