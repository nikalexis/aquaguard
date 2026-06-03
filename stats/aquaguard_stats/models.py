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
    snapshot_at: datetime | None
    zone_id: int
    zone_name: str
    meter_consumption_l: float | None
    period_baseline_l: float | None
    period_consumption_l: float | None
    period_limit_l: float | None
    period_limit_active: bool | None
    has_device_snapshot: bool = True
    daily_consumption_l: float | None = None
    measurement_quality: str = "partial"
    estimate_span_days: int | None = None


@dataclass(frozen=True)
class DailyConsumptionPoint:
    snapshot_date: date
    zone_name: str
    meter_consumption_l: float | None
    daily_consumption_l: float | None
    measurement_quality: str = "partial"
    partial: bool = True
    missing: bool = False
    estimate_span_days: int | None = None


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


def calculate_daily_measurements(
    snapshots: list[ZoneDailySnapshot],
    reset_threshold_l: float,
) -> list[ZoneDailySnapshot]:
    real_snapshots = [
        snapshot
        for snapshot in sorted(snapshots, key=lambda item: item.snapshot_date)
        if snapshot.has_device_snapshot and snapshot.meter_consumption_l is not None
    ]
    if not real_snapshots:
        return []

    measurements: list[ZoneDailySnapshot] = []
    previous: ZoneDailySnapshot | None = None

    for snapshot in real_snapshots:
        if previous is None:
            measurements.append(
                _with_measurement(
                    snapshot,
                    daily_consumption_l=None,
                    measurement_quality="partial",
                    estimate_span_days=None,
                )
            )
            previous = snapshot
            continue

        gap_days = (snapshot.snapshot_date - previous.snapshot_date).days
        if gap_days <= 0:
            previous = snapshot
            continue

        previous_meter = previous.meter_consumption_l or 0.0
        current_meter = snapshot.meter_consumption_l or 0.0
        delta = current_meter - previous_meter

        if delta < -reset_threshold_l:
            measurements.extend(
                _missing_measurements_between(previous, snapshot)
            )
            measurements.append(
                _with_measurement(
                    snapshot,
                    daily_consumption_l=0.0,
                    measurement_quality="reset",
                    estimate_span_days=None,
                )
            )
        elif gap_days > 1:
            daily_estimate = max(delta, 0.0) / gap_days
            measurements.extend(
                _estimated_measurements_between(
                    previous,
                    snapshot,
                    daily_consumption_l=daily_estimate,
                    estimate_span_days=gap_days,
                )
            )
            measurements.append(
                _with_measurement(
                    snapshot,
                    daily_consumption_l=daily_estimate,
                    measurement_quality="estimated",
                    estimate_span_days=gap_days,
                )
            )
        else:
            measurements.append(
                _with_measurement(
                    snapshot,
                    daily_consumption_l=max(delta, 0.0),
                    measurement_quality="exact",
                    estimate_span_days=None,
                )
            )

        previous = snapshot

    return measurements


def snapshots_to_daily_points(
    snapshots: list[ZoneDailySnapshot],
) -> list[DailyConsumptionPoint]:
    return [_snapshot_to_daily_point(snapshot) for snapshot in snapshots]


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


def _with_measurement(
    snapshot: ZoneDailySnapshot,
    daily_consumption_l: float | None,
    measurement_quality: str,
    estimate_span_days: int | None,
) -> ZoneDailySnapshot:
    return ZoneDailySnapshot(
        snapshot_date=snapshot.snapshot_date,
        snapshot_at=snapshot.snapshot_at,
        zone_id=snapshot.zone_id,
        zone_name=snapshot.zone_name,
        meter_consumption_l=snapshot.meter_consumption_l,
        period_baseline_l=snapshot.period_baseline_l,
        period_consumption_l=snapshot.period_consumption_l,
        period_limit_l=snapshot.period_limit_l,
        period_limit_active=snapshot.period_limit_active,
        has_device_snapshot=True,
        daily_consumption_l=daily_consumption_l,
        measurement_quality=measurement_quality,
        estimate_span_days=estimate_span_days,
    )


def _estimated_measurements_between(
    previous: ZoneDailySnapshot,
    current: ZoneDailySnapshot,
    daily_consumption_l: float,
    estimate_span_days: int,
) -> list[ZoneDailySnapshot]:
    return [
        _synthetic_measurement(
            snapshot_date=previous.snapshot_date + timedelta(days=offset),
            zone_id=current.zone_id,
            zone_name=current.zone_name or previous.zone_name,
            daily_consumption_l=daily_consumption_l,
            measurement_quality="estimated",
            estimate_span_days=estimate_span_days,
        )
        for offset in range(1, estimate_span_days)
    ]


def _missing_measurements_between(
    previous: ZoneDailySnapshot,
    current: ZoneDailySnapshot,
) -> list[ZoneDailySnapshot]:
    gap_days = (current.snapshot_date - previous.snapshot_date).days
    return [
        _synthetic_measurement(
            snapshot_date=previous.snapshot_date + timedelta(days=offset),
            zone_id=current.zone_id,
            zone_name=current.zone_name or previous.zone_name,
            daily_consumption_l=None,
            measurement_quality="missing",
            estimate_span_days=None,
        )
        for offset in range(1, gap_days)
    ]


def _synthetic_measurement(
    snapshot_date: date,
    zone_id: int,
    zone_name: str,
    daily_consumption_l: float | None,
    measurement_quality: str,
    estimate_span_days: int | None,
) -> ZoneDailySnapshot:
    return ZoneDailySnapshot(
        snapshot_date=snapshot_date,
        snapshot_at=None,
        zone_id=zone_id,
        zone_name=zone_name,
        meter_consumption_l=None,
        period_baseline_l=None,
        period_consumption_l=None,
        period_limit_l=None,
        period_limit_active=None,
        has_device_snapshot=False,
        daily_consumption_l=daily_consumption_l,
        measurement_quality=measurement_quality,
        estimate_span_days=estimate_span_days,
    )


def _snapshot_to_daily_point(snapshot: ZoneDailySnapshot) -> DailyConsumptionPoint:
    return DailyConsumptionPoint(
        snapshot_date=snapshot.snapshot_date,
        zone_name=snapshot.zone_name,
        meter_consumption_l=snapshot.meter_consumption_l,
        daily_consumption_l=snapshot.daily_consumption_l,
        measurement_quality=snapshot.measurement_quality,
        partial=snapshot.measurement_quality == "partial",
        missing=snapshot.measurement_quality == "missing",
        estimate_span_days=snapshot.estimate_span_days,
    )
