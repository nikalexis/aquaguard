from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta

from .config import Settings
from .esphome_client import AquaGuardAPIError, ESPHomeZoneReader
from .models import (
    DashboardSummary,
    AvailableMonth,
    DailyConsumptionPoint,
    HistoryRange,
    ZoneDailySnapshot,
    ZoneLiveState,
    build_dashboard_summary,
    calculate_daily_measurements,
)
from .repository import SnapshotRepository


class StatsService:
    def __init__(
        self,
        settings: Settings,
        repository: SnapshotRepository,
        reader: ESPHomeZoneReader,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.reader = reader

    async def get_live_zones(self) -> list[ZoneLiveState]:
        return await self.reader.read_zones()

    async def get_dashboard_summary(self) -> DashboardSummary:
        try:
            zones = await self.get_live_zones()
            return build_dashboard_summary(
                zones,
                warning_threshold=self.settings.warning_threshold,
            )
        except AquaGuardAPIError as exc:
            fallback_zones = _snapshots_to_fallback_zones(
                self.repository.list_latest_snapshots()
            )
            return build_dashboard_summary(
                fallback_zones,
                warning_threshold=self.settings.warning_threshold,
                error=str(exc),
            )

    async def record_noon_snapshot(self) -> int:
        zones = await self.get_live_zones()
        now = datetime.now(self.settings.zoneinfo)
        snapshots = [
            ZoneDailySnapshot(
                snapshot_date=now.date(),
                snapshot_at=now,
                zone_id=zone.zone_id,
                zone_name=zone.zone_name,
                meter_consumption_l=zone.meter_consumption_l,
                period_baseline_l=zone.period_baseline_l,
                period_consumption_l=zone.period_consumption_l,
                period_limit_l=zone.period_limit_l,
                period_limit_active=zone.period_limit_active,
            )
            for zone in zones
        ]
        rows = self.repository.upsert_snapshots(snapshots)
        self._recalculate_daily_measurements(
            zone_ids={snapshot.zone_id for snapshot in snapshots}
        )
        return rows

    def get_zone_daily_points(self, zone_id: int, limit: int = 90):
        snapshots = self.repository.list_zone_snapshots(zone_id=zone_id, limit=limit)
        if not snapshots:
            return []
        start_date = snapshots[0].snapshot_date
        end_date = snapshots[-1].snapshot_date
        points = self.repository.list_zone_daily_points_between(
            zone_id=zone_id,
            start_date=start_date,
            end_date=end_date,
        )
        return _fill_missing_daily_points(
            points,
            start_date,
            end_date,
            datetime.now(self.settings.zoneinfo),
        )

    def resolve_history_range(
        self,
        zone_id: int,
        range_mode: str | None,
        year: int | None,
        month: int | None,
    ) -> HistoryRange:
        today = datetime.now(self.settings.zoneinfo).date()
        available_months = self.repository.list_available_months(zone_id)
        current_month = AvailableMonth(year=today.year, month=today.month)
        if current_month not in available_months:
            available_months = [current_month, *available_months]
        available_months = [
            item
            for item in available_months
            if (item.year, item.month) <= (today.year, today.month)
        ]
        first_month = min(available_months, key=lambda item: (item.year, item.month))

        if range_mode == "monthly":
            selected_year = year if year is not None else today.year
            selected_month = month if month is not None else today.month
            if not 1 <= selected_month <= 12:
                selected_year = today.year
                selected_month = today.month
            elif selected_year < first_month.year or (
                selected_year == first_month.year
                and selected_month < first_month.month
            ):
                selected_year = first_month.year
                selected_month = first_month.month
            elif selected_year > today.year or (
                selected_year == today.year
                and selected_month > today.month
            ):
                selected_year = today.year
                selected_month = today.month
            elif not _valid_month(selected_year, selected_month):
                selected_year = today.year
                selected_month = today.month

            start_date = date(selected_year, selected_month, 1)
            last_day = monthrange(selected_year, selected_month)[1]
            end_date = date(selected_year, selected_month, last_day)
            if selected_year == today.year and selected_month == today.month:
                end_date = min(end_date, today)
            return HistoryRange(
                mode="monthly",
                start_date=start_date,
                end_date=end_date,
                selected_year=selected_year,
                selected_month=selected_month,
                available_months=available_months,
                current_year=today.year,
                current_month=today.month,
                first_year=first_month.year,
                first_month=first_month.month,
            )

        return HistoryRange(
            mode="last30",
            start_date=today - timedelta(days=29),
            end_date=today,
            selected_year=today.year,
            selected_month=today.month,
            available_months=available_months,
            current_year=today.year,
            current_month=today.month,
            first_year=first_month.year,
            first_month=first_month.month,
        )

    def get_zone_daily_points_for_range(
        self,
        zone_id: int,
        history_range: HistoryRange,
        live_zone: ZoneLiveState | None = None,
        live_available: bool | None = None,
    ):
        now = datetime.now(self.settings.zoneinfo)
        start_date = history_range.start_date
        end_date = history_range.end_date
        synthetic_date = _current_measurement_date(now)
        if (
            live_available is not None
            and synthetic_date >= start_date
            and end_date >= now.date()
        ):
            end_date = max(end_date, synthetic_date)

        points = self.repository.list_zone_daily_points_between(
            zone_id=zone_id,
            start_date=start_date,
            end_date=end_date,
        )
        filled_points = _fill_missing_daily_points(
            points,
            start_date,
            end_date,
            now,
            zone_name=live_zone.zone_name if live_zone else None,
        )
        if live_available is None:
            return filled_points
        baseline = self.repository.latest_zone_snapshot_before(
            zone_id=zone_id,
            snapshot_date=synthetic_date,
        )
        if synthetic_date > now.date() and (
            baseline is None or baseline.snapshot_date != now.date()
        ):
            baseline = None
        return _with_current_synthetic_point(
            filled_points,
            synthetic_date=synthetic_date,
            live_zone=live_zone,
            live_available=live_available,
            baseline=baseline,
        )

    def _recalculate_daily_measurements(self, zone_ids: set[int]) -> None:
        for zone_id in zone_ids:
            measurements = calculate_daily_measurements(
                self.repository.list_zone_snapshots(zone_id=zone_id, limit=10000),
                reset_threshold_l=self.settings.meter_reset_threshold_l,
            )
            self.repository.replace_zone_measurements(zone_id, measurements)


def _snapshots_to_fallback_zones(
    snapshots: list[ZoneDailySnapshot],
) -> list[ZoneLiveState]:
    return [
        ZoneLiveState(
            zone_id=snapshot.zone_id,
            zone_name=snapshot.zone_name,
            meter_consumption_l=snapshot.meter_consumption_l or 0.0,
            period_baseline_l=snapshot.period_baseline_l or 0.0,
            period_consumption_l=snapshot.period_consumption_l or 0.0,
            period_limit_l=snapshot.period_limit_l or 0.0,
            period_limit_active=bool(snapshot.period_limit_active),
            effective_stop=True,
            water_allowed=False,
            flow_rate_l_min=None,
            last_pulse_timestamp=None,
        )
        for snapshot in snapshots
    ]


def _valid_month(year: int, month: int) -> bool:
    return 1 <= month <= 12 and 1970 <= year <= 9999


def _fill_missing_daily_points(
    points: list[DailyConsumptionPoint],
    start_date: date,
    end_date: date,
    now: datetime,
    zone_name: str | None = None,
) -> list[DailyConsumptionPoint]:
    if not points and not zone_name:
        return []

    points_by_date = {
        point.snapshot_date: point
        for point in points
    }
    resolved_zone_name = zone_name or next(
        (point.zone_name for point in reversed(points) if point.zone_name),
        "",
    )
    filled_points: list[DailyConsumptionPoint] = []
    current = start_date
    while current <= end_date:
        point = points_by_date.get(current)
        if point is None:
            quality = _synthetic_quality_for_date(current, now)
            point = DailyConsumptionPoint(
                snapshot_date=current,
                zone_name=resolved_zone_name,
                meter_consumption_l=None,
                daily_consumption_l=None,
                measurement_quality=quality,
                partial=False,
                missing=quality == "missing",
                estimate_span_days=None,
            )
        filled_points.append(point)
        current += timedelta(days=1)
    return filled_points


def _synthetic_quality_for_date(snapshot_date: date, now: datetime) -> str:
    if snapshot_date == now.date() and now.time() < time(hour=12):
        return "expected"
    return "missing"


def _current_measurement_date(now: datetime) -> date:
    if now.time() < time(hour=12):
        return now.date()
    return now.date() + timedelta(days=1)


def _with_current_synthetic_point(
    points: list[DailyConsumptionPoint],
    synthetic_date: date,
    live_zone: ZoneLiveState | None,
    live_available: bool,
    baseline: ZoneDailySnapshot | None,
) -> list[DailyConsumptionPoint]:
    if not points:
        return points

    point_by_date = {
        point.snapshot_date: point
        for point in points
    }
    existing = point_by_date.get(synthetic_date)
    if existing and existing.meter_consumption_l is not None:
        return points

    point_by_date[synthetic_date] = _current_synthetic_point(
        synthetic_date=synthetic_date,
        live_zone=live_zone,
        live_available=live_available,
        baseline=baseline,
        fallback_zone_name=existing.zone_name if existing else "",
    )
    return [
        point_by_date[snapshot_date]
        for snapshot_date in sorted(point_by_date)
    ]


def _current_synthetic_point(
    synthetic_date: date,
    live_zone: ZoneLiveState | None,
    live_available: bool,
    baseline: ZoneDailySnapshot | None,
    fallback_zone_name: str,
) -> DailyConsumptionPoint:
    zone_name = (
        live_zone.zone_name
        if live_zone is not None
        else fallback_zone_name
    )
    if not live_available:
        return DailyConsumptionPoint(
            snapshot_date=synthetic_date,
            zone_name=zone_name,
            meter_consumption_l=None,
            daily_consumption_l=None,
            measurement_quality="offline",
            partial=False,
            missing=False,
            estimate_span_days=None,
        )

    if live_zone is None or baseline is None or baseline.meter_consumption_l is None:
        return _expected_synthetic_point(synthetic_date, zone_name)

    daily_consumption_l = live_zone.meter_consumption_l - baseline.meter_consumption_l
    if daily_consumption_l < 0:
        return _expected_synthetic_point(synthetic_date, zone_name)

    return DailyConsumptionPoint(
        snapshot_date=synthetic_date,
        zone_name=zone_name,
        meter_consumption_l=live_zone.meter_consumption_l,
        daily_consumption_l=daily_consumption_l,
        measurement_quality="current",
        partial=False,
        missing=False,
        estimate_span_days=None,
    )


def _expected_synthetic_point(
    synthetic_date: date,
    zone_name: str,
) -> DailyConsumptionPoint:
    return DailyConsumptionPoint(
        snapshot_date=synthetic_date,
        zone_name=zone_name,
        meter_consumption_l=None,
        daily_consumption_l=None,
        measurement_quality="expected",
        partial=False,
        missing=False,
        estimate_span_days=None,
    )
