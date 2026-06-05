import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from aquaguard_stats.config import Settings
from aquaguard_stats.models import (
    AvailableMonth,
    DailyConsumptionPoint,
    HistoryRange,
    ZoneDailySnapshot,
    ZoneLiveState,
)
from aquaguard_stats.repository import SnapshotRepository
from aquaguard_stats.service import StatsService, _fill_missing_daily_points


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
            meter_reset_threshold_l=1.0,
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

    def test_daily_points_fill_missing_dates_without_persisting_them(self):
        temp_dir, _settings, service = self.make_service()
        with temp_dir:
            history_range = HistoryRange(
                mode="monthly",
                start_date=date(2026, 5, 11),
                end_date=date(2026, 5, 15),
                selected_year=2026,
                selected_month=5,
                available_months=[AvailableMonth(2026, 5)],
                current_year=2026,
                current_month=5,
                first_year=2026,
                first_month=5,
            )

            points = service.get_zone_daily_points_for_range(1, history_range)
            persisted = service.repository.list_zone_daily_points_between(
                zone_id=1,
                start_date=history_range.start_date,
                end_date=history_range.end_date,
            )

            self.assertEqual([point.snapshot_date for point in points], [
                date(2026, 5, 11),
                date(2026, 5, 12),
                date(2026, 5, 13),
                date(2026, 5, 14),
                date(2026, 5, 15),
            ])
            self.assertEqual([point.measurement_quality for point in points], [
                "missing",
                "missing",
                "partial",
                "missing",
                "missing",
            ])
            self.assertEqual(
                [(point.snapshot_date, point.measurement_quality) for point in persisted],
                [(date(2026, 5, 13), "partial")],
            )

    def test_daily_points_mark_today_expected_before_noon(self):
        now = datetime(2026, 6, 4, 11, 30, tzinfo=ZoneInfo("Europe/Athens"))
        points = _fill_missing_daily_points(
            [
                DailyConsumptionPoint(
                    snapshot_date=date(2026, 6, 3),
                    zone_name="Zone 1",
                    meter_consumption_l=100,
                    daily_consumption_l=None,
                    measurement_quality="partial",
                )
            ],
            date(2026, 6, 3),
            date(2026, 6, 4),
            now,
        )

        self.assertEqual([point.measurement_quality for point in points], [
            "partial",
            "expected",
        ])
        self.assertFalse(points[1].missing)

    def test_daily_points_mark_today_missing_after_noon(self):
        now = datetime(2026, 6, 4, 12, 30, tzinfo=ZoneInfo("Europe/Athens"))
        points = _fill_missing_daily_points(
            [
                DailyConsumptionPoint(
                    snapshot_date=date(2026, 6, 3),
                    zone_name="Zone 1",
                    meter_consumption_l=100,
                    daily_consumption_l=None,
                    measurement_quality="partial",
                )
            ],
            date(2026, 6, 3),
            date(2026, 6, 4),
            now,
        )

        self.assertEqual([point.measurement_quality for point in points], [
            "partial",
            "missing",
        ])
        self.assertTrue(points[1].missing)

    def test_daily_points_keep_existing_today_quality(self):
        now = datetime(2026, 6, 4, 11, 30, tzinfo=ZoneInfo("Europe/Athens"))
        points = _fill_missing_daily_points(
            [
                DailyConsumptionPoint(
                    snapshot_date=date(2026, 6, 4),
                    zone_name="Zone 1",
                    meter_consumption_l=120,
                    daily_consumption_l=None,
                    measurement_quality="partial",
                )
            ],
            date(2026, 6, 4),
            date(2026, 6, 4),
            now,
        )

        self.assertEqual([point.measurement_quality for point in points], ["partial"])

    def test_daily_points_add_current_before_noon_from_previous_snapshot(self):
        temp_dir, _settings, service = self.make_service()
        with temp_dir:
            service.repository.upsert_snapshots([
                ZoneDailySnapshot(
                    snapshot_date=date(2026, 6, 3),
                    snapshot_at=datetime(2026, 6, 3, 12),
                    zone_id=1,
                    zone_name="Zone 1",
                    meter_consumption_l=100,
                    period_baseline_l=0,
                    period_consumption_l=100,
                    period_limit_l=200,
                    period_limit_active=True,
                )
            ])
            history_range = _history_range(date(2026, 6, 3), date(2026, 6, 4))
            live_zone = _live_zone(meter_consumption_l=118)

            with _fixed_now(datetime(2026, 6, 4, 11, 30, tzinfo=ZoneInfo("Europe/Athens"))):
                points = service.get_zone_daily_points_for_range(
                    1,
                    history_range,
                    live_zone=live_zone,
                    live_available=True,
                )

            self.assertEqual(points[-1].snapshot_date, date(2026, 6, 4))
            self.assertEqual(points[-1].measurement_quality, "current")
            self.assertEqual(points[-1].daily_consumption_l, 18)
            self.assertEqual(points[-1].meter_consumption_l, 118)

    def test_daily_points_add_tomorrow_current_after_noon_and_keep_today_snapshot(self):
        temp_dir, _settings, service = self.make_service()
        with temp_dir:
            service.repository.upsert_snapshots([
                ZoneDailySnapshot(
                    snapshot_date=date(2026, 6, 3),
                    snapshot_at=datetime(2026, 6, 3, 12),
                    zone_id=1,
                    zone_name="Zone 1",
                    meter_consumption_l=100,
                    period_baseline_l=0,
                    period_consumption_l=100,
                    period_limit_l=200,
                    period_limit_active=True,
                ),
                ZoneDailySnapshot(
                    snapshot_date=date(2026, 6, 4),
                    snapshot_at=datetime(2026, 6, 4, 12),
                    zone_id=1,
                    zone_name="Zone 1",
                    meter_consumption_l=120,
                    period_baseline_l=0,
                    period_consumption_l=120,
                    period_limit_l=200,
                    period_limit_active=True,
                ),
            ])
            service._recalculate_daily_measurements({1})
            history_range = _history_range(date(2026, 6, 3), date(2026, 6, 4))
            live_zone = _live_zone(meter_consumption_l=127)

            with _fixed_now(datetime(2026, 6, 4, 12, 30, tzinfo=ZoneInfo("Europe/Athens"))):
                points = service.get_zone_daily_points_for_range(
                    1,
                    history_range,
                    live_zone=live_zone,
                    live_available=True,
                )

            self.assertEqual([point.snapshot_date for point in points], [
                date(2026, 6, 3),
                date(2026, 6, 4),
                date(2026, 6, 5),
            ])
            self.assertEqual(points[1].measurement_quality, "exact")
            self.assertEqual(points[1].daily_consumption_l, 20)
            self.assertEqual(points[2].measurement_quality, "current")
            self.assertEqual(points[2].daily_consumption_l, 7)

    def test_daily_points_do_not_add_after_noon_current_without_today_baseline(self):
        temp_dir, _settings, service = self.make_service()
        with temp_dir:
            service.repository.upsert_snapshots([
                ZoneDailySnapshot(
                    snapshot_date=date(2026, 6, 3),
                    snapshot_at=datetime(2026, 6, 3, 12),
                    zone_id=1,
                    zone_name="Zone 1",
                    meter_consumption_l=100,
                    period_baseline_l=0,
                    period_consumption_l=100,
                    period_limit_l=200,
                    period_limit_active=True,
                )
            ])
            history_range = _history_range(date(2026, 6, 3), date(2026, 6, 4))
            live_zone = _live_zone(meter_consumption_l=127)

            with _fixed_now(datetime(2026, 6, 4, 12, 30, tzinfo=ZoneInfo("Europe/Athens"))):
                points = service.get_zone_daily_points_for_range(
                    1,
                    history_range,
                    live_zone=live_zone,
                    live_available=True,
                )

            self.assertEqual([point.snapshot_date for point in points], [
                date(2026, 6, 3),
                date(2026, 6, 4),
                date(2026, 6, 5),
            ])
            self.assertEqual(points[1].measurement_quality, "missing")
            self.assertEqual(points[2].measurement_quality, "expected")
            self.assertIsNone(points[2].daily_consumption_l)

    def test_daily_points_add_offline_synthetic_point(self):
        temp_dir, _settings, service = self.make_service()
        with temp_dir:
            service.repository.upsert_snapshots([
                ZoneDailySnapshot(
                    snapshot_date=date(2026, 6, 3),
                    snapshot_at=datetime(2026, 6, 3, 12),
                    zone_id=1,
                    zone_name="Zone 1",
                    meter_consumption_l=100,
                    period_baseline_l=0,
                    period_consumption_l=100,
                    period_limit_l=200,
                    period_limit_active=True,
                )
            ])
            history_range = _history_range(date(2026, 6, 3), date(2026, 6, 4))
            live_zone = _live_zone(meter_consumption_l=118)

            with _fixed_now(datetime(2026, 6, 4, 11, 30, tzinfo=ZoneInfo("Europe/Athens"))):
                points = service.get_zone_daily_points_for_range(
                    1,
                    history_range,
                    live_zone=live_zone,
                    live_available=False,
                )

            self.assertEqual(points[-1].measurement_quality, "offline")
            self.assertIsNone(points[-1].daily_consumption_l)
            self.assertIsNone(points[-1].meter_consumption_l)

    def test_daily_points_use_expected_for_missing_baseline_or_negative_delta(self):
        temp_dir, _settings, service = self.make_service()
        with temp_dir:
            no_baseline_range = _history_range(date(2026, 5, 10), date(2026, 5, 12))

            with _fixed_now(datetime(2026, 5, 12, 11, 30, tzinfo=ZoneInfo("Europe/Athens"))):
                no_baseline = service.get_zone_daily_points_for_range(
                    1,
                    no_baseline_range,
                    live_zone=_live_zone(meter_consumption_l=118),
                    live_available=True,
                )

            negative_delta_range = _history_range(date(2026, 6, 3), date(2026, 6, 4))
            service.repository.upsert_snapshots([
                ZoneDailySnapshot(
                    snapshot_date=date(2026, 6, 3),
                    snapshot_at=datetime(2026, 6, 3, 12),
                    zone_id=1,
                    zone_name="Zone 1",
                    meter_consumption_l=100,
                    period_baseline_l=0,
                    period_consumption_l=100,
                    period_limit_l=200,
                    period_limit_active=True,
                )
            ])
            with _fixed_now(datetime(2026, 6, 4, 11, 30, tzinfo=ZoneInfo("Europe/Athens"))):
                negative_delta = service.get_zone_daily_points_for_range(
                    1,
                    negative_delta_range,
                    live_zone=_live_zone(meter_consumption_l=95),
                    live_available=True,
                )

            self.assertEqual(no_baseline[-1].measurement_quality, "expected")
            self.assertIsNone(no_baseline[-1].daily_consumption_l)
            self.assertEqual(negative_delta[-1].measurement_quality, "expected")
            self.assertIsNone(negative_delta[-1].daily_consumption_l)


def _history_range(start_date: date, end_date: date) -> HistoryRange:
    return HistoryRange(
        mode="last30",
        start_date=start_date,
        end_date=end_date,
        selected_year=end_date.year,
        selected_month=end_date.month,
        available_months=[AvailableMonth(end_date.year, end_date.month)],
        current_year=end_date.year,
        current_month=end_date.month,
        first_year=start_date.year,
        first_month=start_date.month,
    )


def _live_zone(meter_consumption_l: float) -> ZoneLiveState:
    return ZoneLiveState(
        zone_id=1,
        zone_name="Zone 1",
        meter_consumption_l=meter_consumption_l,
        period_baseline_l=0,
        period_consumption_l=meter_consumption_l,
        period_limit_l=200,
        period_limit_active=True,
        effective_stop=False,
        water_allowed=True,
        flow_rate_l_min=None,
        last_pulse_timestamp=None,
    )


def _fixed_now(now: datetime):
    class FixedDateTime:
        @classmethod
        def now(cls, zoneinfo):
            return now

    return patch("aquaguard_stats.service.datetime", FixedDateTime)
