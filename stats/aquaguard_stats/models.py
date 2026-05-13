from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


ZONE_COUNT = 8


@dataclass(frozen=True)
class ZoneLiveState:
    zone_id: int
    zone_name: str
    meter_consumption_l: float
    period_baseline_l: float
    period_consumption_l: float
    period_limit_l: float
    period_limit_active: bool
    effective_stop: bool
    water_allowed: bool
    flow_rate_l_min: float | None
    last_pulse_timestamp: str | None


@dataclass(frozen=True)
class ZoneDashboardState:
    live: ZoneLiveState
    utilization_percent: float | None
    status_level: str
    status_label: str


@dataclass(frozen=True)
class ZoneDailySnapshot:
    snapshot_date: date
    snapshot_at: datetime
    zone_id: int
    zone_name: str
    meter_consumption_l: float
    period_baseline_l: float
    period_consumption_l: float
    period_limit_l: float
    period_limit_active: bool


@dataclass(frozen=True)
class DailyConsumptionPoint:
    snapshot_date: date
    zone_name: str
    meter_consumption_l: float
    daily_consumption_l: float | None
    partial: bool


@dataclass(frozen=True)
class DashboardSummary:
    zones: list[ZoneDashboardState]
    total_period_consumption_l: float
    total_active_period_limit_l: float
    utilization_percent: float | None
    status_level: str
    live_available: bool
    error: str | None = None


def build_dashboard_summary(
    zones: list[ZoneLiveState],
    warning_threshold: float,
    error: str | None = None,
) -> DashboardSummary:
    total_consumption = sum(zone.period_consumption_l for zone in zones)
    total_limit = sum(
        zone.period_limit_l
        for zone in zones
        if zone.period_limit_active and zone.period_limit_l > 0
    )

    utilization_percent: float | None = None
    status_level = "ok"
    if total_limit > 0:
        utilization_percent = min((total_consumption / total_limit) * 100, 999.0)
        if utilization_percent >= 100:
            status_level = "alert"
        elif utilization_percent >= warning_threshold * 100:
            status_level = "warning"

    if error:
        status_level = "offline"

    zone_states = [
        build_zone_dashboard_state(zone, warning_threshold)
        for zone in zones
    ]

    return DashboardSummary(
        zones=zone_states,
        total_period_consumption_l=total_consumption,
        total_active_period_limit_l=total_limit,
        utilization_percent=utilization_percent,
        status_level=status_level,
        live_available=error is None,
        error=error,
    )


def build_zone_dashboard_state(
    zone: ZoneLiveState,
    warning_threshold: float,
) -> ZoneDashboardState:
    utilization_percent: float | None = None
    status_level = "ok"
    status_label = "Ok"

    if zone.period_limit_active and zone.period_limit_l > 0:
        utilization_percent = min(
            (zone.period_consumption_l / zone.period_limit_l) * 100,
            999.0,
        )
        if utilization_percent >= 100:
            status_level = "alert"
            status_label = "Limit reached"
        elif utilization_percent >= warning_threshold * 100:
            status_level = "warning"
            status_label = "Near limit"
    else:
        status_level = "inactive"
        status_label = "No active limit"

    if zone.effective_stop:
        status_level = "alert"
        status_label = "Stopped"

    return ZoneDashboardState(
        live=zone,
        utilization_percent=utilization_percent,
        status_level=status_level,
        status_label=status_label,
    )


def snapshots_to_daily_points(
    snapshots: list[ZoneDailySnapshot],
) -> list[DailyConsumptionPoint]:
    points: list[DailyConsumptionPoint] = []
    previous: ZoneDailySnapshot | None = None

    for snapshot in sorted(snapshots, key=lambda item: item.snapshot_date):
        if previous is None:
            daily_consumption = None
            partial = True
        else:
            delta = snapshot.meter_consumption_l - previous.meter_consumption_l
            daily_consumption = delta if delta >= 0 else None
            partial = delta < 0

        points.append(
            DailyConsumptionPoint(
                snapshot_date=snapshot.snapshot_date,
                zone_name=snapshot.zone_name,
                meter_consumption_l=snapshot.meter_consumption_l,
                daily_consumption_l=daily_consumption,
                partial=partial,
            )
        )
        previous = snapshot

    return points
