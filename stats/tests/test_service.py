import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from aquaguard_stats.config import Settings
from aquaguard_stats.models import ZoneDailySnapshot
from aquaguard_stats.repository import SnapshotRepository
from aquaguard_stats.service import StatsService


class HistoryRangeServiceTests(unittest.TestCase):
    def test_resolve_monthly_range_defaults_invalid_values_to_current_month(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                esphome_host="localhost",
                esphome_port=6053,
                api_encryption_key=None,
                db_path=Path(temp_dir) / "stats.sqlite3",
                timezone="Europe/Athens",
                warning_threshold=0.8,
                refresh_timeout_s=1,
                host="127.0.0.1",
                port=8080,
            )
            repository = SnapshotRepository(settings.db_path)
            repository.init_schema()
            repository.upsert_snapshots([
                ZoneDailySnapshot(
                    snapshot_date=date(2026, 5, 13),
                    snapshot_at=datetime(2026, 5, 13, 12),
                    zone_id=1,
                    zone_name="Zone 1",
                    meter_consumption_l=100,
                    period_baseline_l=0,
                    period_consumption_l=100,
                    period_limit_l=200,
                    period_limit_active=True,
                )
            ])
            service = StatsService(settings, repository, reader=None)

            history_range = service.resolve_history_range(
                zone_id=1,
                range_mode="monthly",
                year=2026,
                month=99,
            )

            self.assertEqual(history_range.mode, "monthly")
            self.assertEqual(history_range.selected_month, datetime.now(settings.zoneinfo).month)
            self.assertIn(
                (2026, 5),
                [(item.year, item.month) for item in history_range.available_months],
            )

