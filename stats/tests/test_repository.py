import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from aquaguard_stats.models import ZoneDailySnapshot
from aquaguard_stats.repository import SnapshotRepository


class SnapshotRepositoryTests(unittest.TestCase):
    def test_upsert_snapshots_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SnapshotRepository(Path(temp_dir) / "stats.sqlite3")
            repository.init_schema()

            first = ZoneDailySnapshot(
                snapshot_date=date(2026, 5, 13),
                snapshot_at=datetime(2026, 5, 13, 12),
                zone_id=1,
                zone_name="Zone 1",
                meter_consumption_l=100,
                period_baseline_l=10,
                period_consumption_l=90,
                period_limit_l=200,
                period_limit_active=True,
            )
            second = ZoneDailySnapshot(
                snapshot_date=date(2026, 5, 13),
                snapshot_at=datetime(2026, 5, 13, 12, 1),
                zone_id=1,
                zone_name="Kitchen",
                meter_consumption_l=105,
                period_baseline_l=10,
                period_consumption_l=95,
                period_limit_l=200,
                period_limit_active=True,
            )

            self.assertEqual(repository.upsert_snapshots([first]), 1)
            self.assertEqual(repository.upsert_snapshots([second]), 1)

            snapshots = repository.list_zone_snapshots(zone_id=1)

            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0].zone_name, "Kitchen")
            self.assertEqual(snapshots[0].meter_consumption_l, 105)

    def test_list_zone_snapshots_between_and_available_months(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SnapshotRepository(Path(temp_dir) / "stats.sqlite3")
            repository.init_schema()
            snapshots = [
                ZoneDailySnapshot(date(2026, 4, 30), datetime(2026, 4, 30, 12), 1, "Zone 1", 90, 0, 90, 200, True),
                ZoneDailySnapshot(date(2026, 5, 1), datetime(2026, 5, 1, 12), 1, "Zone 1", 100, 0, 100, 200, True),
                ZoneDailySnapshot(date(2026, 5, 3), datetime(2026, 5, 3, 12), 1, "Zone 1", 125, 0, 125, 200, True),
            ]
            repository.upsert_snapshots(snapshots)

            ranged = repository.list_zone_snapshots_between(
                zone_id=1,
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 31),
            )
            months = repository.list_available_months(zone_id=1)

            self.assertEqual([snapshot.snapshot_date for snapshot in ranged], [
                date(2026, 5, 1),
                date(2026, 5, 3),
            ])
            self.assertEqual([(month.year, month.month) for month in months], [
                (2026, 5),
                (2026, 4),
            ])

    def test_replace_zone_measurements_stores_synthetic_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SnapshotRepository(Path(temp_dir) / "stats.sqlite3")
            repository.init_schema()
            real = ZoneDailySnapshot(
                date(2026, 5, 1),
                datetime(2026, 5, 1, 12),
                1,
                "Zone 1",
                100,
                0,
                100,
                200,
                True,
                daily_consumption_l=None,
                measurement_quality="partial",
            )
            synthetic = ZoneDailySnapshot(
                date(2026, 5, 2),
                None,
                1,
                "Zone 1",
                None,
                None,
                None,
                None,
                None,
                has_device_snapshot=False,
                daily_consumption_l=12.5,
                measurement_quality="estimated",
                estimate_span_days=2,
            )

            repository.upsert_snapshots([real])
            repository.replace_zone_measurements(1, [real, synthetic])

            points = repository.list_zone_daily_points_between(
                zone_id=1,
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 2),
            )
            latest = repository.list_latest_snapshots()

            self.assertEqual([point.measurement_quality for point in points], [
                "partial",
                "estimated",
            ])
            self.assertEqual(points[1].daily_consumption_l, 12.5)
            self.assertEqual(points[1].estimate_span_days, 2)
            self.assertEqual(len(latest), 1)
            self.assertEqual(latest[0].snapshot_date, date(2026, 5, 1))
