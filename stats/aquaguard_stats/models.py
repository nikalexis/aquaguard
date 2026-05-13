from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


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
    meter_consumption_l: float | None
    daily_consumption_l: float | None
    partial: bool
    missing: bool = False


@dataclass(frozen=True)
class AvailableMonth:
    year: int
    month: int


@dataclass(frozen=True)
class HistoryRange:
    mode: str
    start_date: date
    end_date: date
    selected_year: int
    selected_month: int
    available_months: list[AvailableMonth]
    current_year: int
    current_month: int
    first_year: int
    first_month: int

    @property
    def is_monthly(self) -> bool:
        return self.mode == "monthly"

    @property
    def label(self) -> str:
        if self.is_monthly:
            return self.start_date.strftime("%B %Y")
        return "Last 30 days"

    @property
    def previous_month(self) -> AvailableMonth | None:
        if self.selected_year == self.first_year and self.selected_month == self.first_month:
            return None
        if self.selected_month == 1:
            return AvailableMonth(year=self.selected_year - 1, month=12)
        return AvailableMonth(year=self.selected_year, month=self.selected_month - 1)

    @property
    def next_month(self) -> AvailableMonth | None:
        if self.selected_year == self.current_year and self.selected_month == self.current_month:
            return None
        if self.selected_month == 12:
            return AvailableMonth(year=self.selected_year + 1, month=1)
        return AvailableMonth(year=self.selected_year, month=self.selected_month + 1)


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
        build_zone_dashboard_state(
            zone,
            warning_threshold,
            live_available=error is None,
        )
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
    live_available: bool = True,
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

    if not live_available:
        status_level = "offline"
        status_label = "Unknown"

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


def snapshots_to_calendar_daily_points(
    snapshots: list[ZoneDailySnapshot],
    start_date: date,
    end_date: date,
) -> list[DailyConsumptionPoint]:
    snapshots_by_date = {
        snapshot.snapshot_date: snapshot
        for snapshot in snapshots
    }
    points: list[DailyConsumptionPoint] = []
    previous_snapshot: ZoneDailySnapshot | None = None
    previous_calendar_day_had_snapshot = False

    current = start_date
    while current <= end_date:
        snapshot = snapshots_by_date.get(current)
        if snapshot is None:
            points.append(
                DailyConsumptionPoint(
                    snapshot_date=current,
                    zone_name="",
                    meter_consumption_l=None,
                    daily_consumption_l=None,
                    partial=False,
                    missing=True,
                )
            )
            previous_calendar_day_had_snapshot = False
            current += timedelta(days=1)
            continue

        if previous_snapshot is None or not previous_calendar_day_had_snapshot:
            daily_consumption = None
            partial = True
        else:
            delta = snapshot.meter_consumption_l - previous_snapshot.meter_consumption_l
            daily_consumption = delta if delta >= 0 else None
            partial = delta < 0

        points.append(
            DailyConsumptionPoint(
                snapshot_date=current,
                zone_name=snapshot.zone_name,
                meter_consumption_l=snapshot.meter_consumption_l,
                daily_consumption_l=daily_consumption,
                partial=partial,
                missing=False,
            )
        )
        previous_snapshot = snapshot
        previous_calendar_day_had_snapshot = True
        current += timedelta(days=1)

    return points
