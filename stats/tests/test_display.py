import unittest
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from aquaguard_stats.display import (
    format_cubic_meters_text,
    format_last_pulse_relative,
    format_last_pulse_timestamp,
    format_volume_html,
    format_volume_text,
    is_last_pulse_within,
    watering_zone_ids,
)


class DisplayFormatterTests(unittest.TestCase):
    def test_format_volume_text_splits_cubic_meters_and_liters(self):
        self.assertEqual(format_volume_text(678), "678 L")
        self.assertEqual(format_volume_text(1000), "1 m³")
        self.assertEqual(format_volume_text(15678), "15 m³ 678 L")
        self.assertEqual(format_volume_text(0), "0 L")

    def test_format_volume_text_handles_missing_values(self):
        self.assertEqual(format_volume_text(None), "-")

    def test_format_cubic_meters_text_uses_meters_only(self):
        self.assertEqual(format_cubic_meters_text(0), "0.0 m³")
        self.assertEqual(format_cubic_meters_text(678), "0.7 m³")
        self.assertEqual(format_cubic_meters_text(1000), "1.0 m³")
        self.assertEqual(format_cubic_meters_text(15678), "15.7 m³")
        self.assertEqual(format_cubic_meters_text(None), "-")

    def test_format_volume_html_marks_major_and_minor_units(self):
        html = str(format_volume_html(15678))

        self.assertIn('<span class="volume-major">15 m³</span>', html)
        self.assertIn('<span class="volume-minor">678 L</span>', html)

    def test_format_last_pulse_relative_uses_translated_units(self):
        timezone = ZoneInfo("Europe/Athens")
        now = datetime(2026, 6, 11, 14, 30, 0, tzinfo=timezone)
        t = _translator(
            {
                "relative_time.just_now": "Just now",
                "relative_time.seconds_ago": "{count} seconds ago",
                "relative_time.minutes_ago": "{count} minutes ago",
                "relative_time.hours_ago": "{count} hours ago",
                "relative_time.days_ago": "{count} days ago",
            }
        )

        self.assertEqual(
            format_last_pulse_relative("2026-06-11 14:29:56", now, timezone, t),
            "Just now",
        )
        self.assertEqual(
            format_last_pulse_relative("2026-06-11 14:29:30", now, timezone, t),
            "30 seconds ago",
        )
        self.assertEqual(
            format_last_pulse_relative("2026-06-11 14:28:00", now, timezone, t),
            "2 minutes ago",
        )
        self.assertEqual(
            format_last_pulse_relative("2026-06-11 12:30:00", now, timezone, t),
            "2 hours ago",
        )
        self.assertEqual(
            format_last_pulse_relative("2026-06-09 14:30:00", now, timezone, t),
            "2 days ago",
        )

    def test_format_last_pulse_relative_supports_greek(self):
        timezone = ZoneInfo("Europe/Athens")
        now = datetime(2026, 6, 11, 14, 30, 0, tzinfo=timezone)
        t = _translator({"relative_time.hour_ago": "πριν από 1 ώρα"})

        self.assertEqual(
            format_last_pulse_relative("2026-06-11 13:30:00", now, timezone, t),
            "πριν από 1 ώρα",
        )

    def test_format_last_pulse_timestamp_uses_readable_24_hour_format(self):
        timezone = ZoneInfo("Europe/Athens")

        self.assertEqual(
            format_last_pulse_timestamp("2026-06-11 14:30:05", timezone),
            "11/06/2026 14:30:05",
        )

    def test_format_last_pulse_handles_missing_invalid_and_future_values(self):
        timezone = ZoneInfo("Europe/Athens")
        now = datetime(2026, 6, 11, 14, 30, 0, tzinfo=timezone)
        t = _translator({})

        self.assertEqual(format_last_pulse_relative(None, now, timezone, t), "-")
        self.assertEqual(format_last_pulse_relative("not a date", now, timezone, t), "-")
        self.assertEqual(
            format_last_pulse_relative("2026-06-11 14:30:01", now, timezone, t),
            "-",
        )
        self.assertEqual(format_last_pulse_timestamp(None, timezone), "-")
        self.assertEqual(format_last_pulse_timestamp("not a date", timezone), "-")

    def test_is_last_pulse_within_checks_recent_valid_timestamp(self):
        timezone = ZoneInfo("Europe/Athens")
        now = datetime(2026, 6, 11, 14, 30, 0, tzinfo=timezone)

        self.assertTrue(
            is_last_pulse_within("2026-06-11 14:29:01", now, timezone, seconds=60)
        )
        self.assertFalse(
            is_last_pulse_within("2026-06-11 14:29:00", now, timezone, seconds=60)
        )
        self.assertFalse(
            is_last_pulse_within("2026-06-11 14:30:01", now, timezone, seconds=60)
        )
        self.assertFalse(is_last_pulse_within(None, now, timezone, seconds=60))

    def test_watering_zone_ids_returns_only_recent_live_zones(self):
        timezone = ZoneInfo("Europe/Athens")
        now = datetime(2026, 6, 11, 14, 30, 0, tzinfo=timezone)
        zone_states = [
            _zone_state(1, "2026-06-11 14:29:01"),
            _zone_state(2, "2026-06-11 14:29:00"),
            _zone_state(3, "2026-06-11 14:30:01"),
            _zone_state(4, None),
            _zone_state(5, "not a date"),
        ]

        self.assertEqual(
            watering_zone_ids(zone_states, True, now, timezone, seconds=60),
            {1},
        )

    def test_watering_zone_ids_returns_empty_when_live_state_is_unavailable(self):
        timezone = ZoneInfo("Europe/Athens")
        now = datetime(2026, 6, 11, 14, 30, 0, tzinfo=timezone)

        self.assertEqual(
            watering_zone_ids(
                [_zone_state(1, "2026-06-11 14:29:01")],
                False,
                now,
                timezone,
                seconds=60,
            ),
            set(),
        )


def _zone_state(zone_id, last_pulse_timestamp):
    return SimpleNamespace(
        live=SimpleNamespace(
            zone_id=zone_id,
            last_pulse_timestamp=last_pulse_timestamp,
        )
    )


def _translator(translations):
    def translate(key, **params):
        value = translations[key]
        if params:
            return value.format(**params)
        return value

    return translate
