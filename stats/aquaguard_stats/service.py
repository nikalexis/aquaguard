from __future__ import annotations

from datetime import datetime

from .config import Settings
from .esphome_client import AquaGuardAPIError, ESPHomeZoneReader
from .models import (
    DashboardSummary,
    ZoneDailySnapshot,
    ZoneLiveState,
    build_dashboard_summary,
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

