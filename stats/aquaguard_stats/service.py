from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta

from .config import Settings
from .esphome_client import AquaGuardAPIError, ESPHomeZoneReader
from .models import (
    DashboardSummary,
    AvailableMonth,
    HistoryRange,
    ZoneDailySnapshot,
    ZoneLiveState,
    build_dashboard_summary,
    snapshots_to_calendar_daily_points,
    snapshots_to_daily_points,
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
        return self.repository.upsert_snapshots(snapshots)

    def get_zone_daily_points(self, zone_id: int, limit: int = 90):
        return snapshots_to_daily_points(
            self.repository.list_zone_snapshots(zone_id=zone_id, limit=limit)
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

        if range_mode == "monthly":
            selected_year = year if year is not None else today.year
            selected_month = month if month is not None else today.month
            if not _valid_month(selected_year, selected_month):
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
            )

        return HistoryRange(
            mode="last30",
            start_date=today - timedelta(days=29),
            end_date=today,
            selected_year=today.year,
            selected_month=today.month,
            available_months=available_months,
        )

    def get_zone_daily_points_for_range(
        self,
        zone_id: int,
        history_range: HistoryRange,
    ):
        snapshots = self.repository.list_zone_snapshots_between(
            zone_id=zone_id,
            start_date=history_range.start_date,
            end_date=history_range.end_date,
        )
        return snapshots_to_calendar_daily_points(
            snapshots,
            start_date=history_range.start_date,
            end_date=history_range.end_date,
        )


def _snapshots_to_fallback_zones(
    snapshots: list[ZoneDailySnapshot],
) -> list[ZoneLiveState]:
    return [
        ZoneLiveState(
            zone_id=snapshot.zone_id,
            zone_name=snapshot.zone_name,
            meter_consumption_l=snapshot.meter_consumption_l,
            period_baseline_l=snapshot.period_baseline_l,
            period_consumption_l=snapshot.period_consumption_l,
            period_limit_l=snapshot.period_limit_l,
            period_limit_active=snapshot.period_limit_active,
            effective_stop=False,
            water_allowed=True,
            flow_rate_l_min=None,
            last_pulse_timestamp=None,
        )
        for snapshot in snapshots
    ]


def _valid_month(year: int, month: int) -> bool:
    return 1 <= month <= 12 and 1970 <= year <= 9999
