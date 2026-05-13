import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from aquaguard_stats.config import Settings
from aquaguard_stats.models import ZoneDailySnapshot
from aquaguard_stats.repository import SnapshotRepository
from aquaguard_stats.service import StatsService


class HistoryRangeServiceTests(unittest.TestCase):
    def make_service(self):
        temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            esphome_host="localhost",
            esphome_port=6053,
            api_encryption_key=None,
            db_path=Path(temp_dir.name) / "stats.sqlite3",
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
        return temp_dir, settings, StatsService(settings, repository, reader=None)

    def test_resolve_monthly_range_defaults_invalid_values_to_current_month(self):
        temp_dir, settings, service = self.make_service()
        with temp_dir:
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

    def test_resolve_monthly_range_clamps_future_month_to_current(self):
        temp_dir, settings, service = self.make_service()
        with temp_dir:
            today = datetime.now(settings.zoneinfo).date()
            future_month = today.month + 1 if today.month < 12 else 1
            future_year = today.year if today.month < 12 else today.year + 1

            history_range = service.resolve_history_range(
                zone_id=1,
                range_mode="monthly",
                year=future_year,
                month=future_month,
            )

            self.assertEqual(history_range.selected_year, today.year)
            self.assertEqual(history_range.selected_month, today.month)
            self.assertIsNone(history_range.next_month)

    def test_resolve_monthly_range_clamps_before_oldest_month(self):
        temp_dir, _settings, service = self.make_service()
        with temp_dir:
            service.repository.upsert_snapshots([
                ZoneDailySnapshot(
                    snapshot_date=date(2026, 3, 15),
                    snapshot_at=datetime(2026, 3, 15, 12),
                    zone_id=1,
                    zone_name="Zone 1",
                    meter_consumption_l=50,
                    period_baseline_l=0,
                    period_consumption_l=50,
                    period_limit_l=200,
                    period_limit_active=True,
                )
            ])

            history_range = service.resolve_history_range(
                zone_id=1,
                range_mode="monthly",
                year=2025,
                month=12,
            )

            self.assertEqual(history_range.selected_year, 2026)
            self.assertEqual(history_range.selected_month, 3)
            self.assertEqual(history_range.first_year, 2026)
            self.assertEqual(history_range.first_month, 3)
            self.assertIsNone(history_range.previous_month)

    def test_resolve_monthly_range_clamps_very_old_year_to_oldest_month(self):
        temp_dir, _settings, service = self.make_service()
        with temp_dir:
            service.repository.upsert_snapshots([
                ZoneDailySnapshot(
                    snapshot_date=date(2026, 3, 15),
                    snapshot_at=datetime(2026, 3, 15, 12),
                    zone_id=1,
                    zone_name="Zone 1",
                    meter_consumption_l=50,
                    period_baseline_l=0,
                    period_consumption_l=50,
                    period_limit_l=200,
                    period_limit_active=True,
                )
            ])

            history_range = service.resolve_history_range(
                zone_id=1,
                range_mode="monthly",
                year=1900,
                month=1,
            )

            self.assertEqual(history_range.selected_year, 2026)
            self.assertEqual(history_range.selected_month, 3)
            self.assertIsNone(history_range.previous_month)
