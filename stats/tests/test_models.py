import unittest
from datetime import date, datetime

from aquaguard_stats.models import (
    ZoneDailySnapshot,
    ZoneLiveState,
    build_dashboard_summary,
    snapshots_to_daily_points,
)


class ModelTests(unittest.TestCase):
    def test_dashboard_summary_uses_only_active_limits(self):
        zones = [
            ZoneLiveState(1, "One", 100, 0, 80, 100, True, False, True, None, None),
            ZoneLiveState(2, "Two", 50, 0, 20, 500, False, False, True, None, None),
        ]

        summary = build_dashboard_summary(zones, warning_threshold=0.8)

        self.assertEqual(summary.total_period_consumption_l, 100)
        self.assertEqual(summary.total_active_period_limit_l, 100)
        self.assertEqual(summary.utilization_percent, 100)
        self.assertEqual(summary.status_level, "alert")


    def test_dashboard_summary_reports_no_utilization_without_active_limit(self):
        zones = [
            ZoneLiveState(1, "One", 100, 0, 80, 100, False, False, True, None, None),
        ]

        summary = build_dashboard_summary(zones, warning_threshold=0.8)

        self.assertEqual(summary.total_active_period_limit_l, 0)
        self.assertIsNone(summary.utilization_percent)
        self.assertEqual(summary.status_level, "ok")


    def test_daily_points_compute_meter_deltas_and_mark_first_partial(self):
        snapshots = [
            ZoneDailySnapshot(date(2026, 5, 1), datetime(2026, 5, 1, 12), 1, "One", 100, 0, 100, 200, True),
            ZoneDailySnapshot(date(2026, 5, 2), datetime(2026, 5, 2, 12), 1, "One", 115, 0, 115, 200, True),
            ZoneDailySnapshot(date(2026, 5, 3), datetime(2026, 5, 3, 12), 1, "One", 120, 0, 120, 200, True),
        ]

        points = snapshots_to_daily_points(snapshots)

        self.assertIsNone(points[0].daily_consumption_l)
        self.assertIs(points[0].partial, True)
        self.assertEqual(points[1].daily_consumption_l, 15)
        self.assertIs(points[1].partial, False)
        self.assertEqual(points[2].daily_consumption_l, 5)
