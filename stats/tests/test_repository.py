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
