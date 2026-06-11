from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from markupsafe import Markup


Translate = Callable[..., str]


def format_volume_text(liters: float | None) -> str:
    if liters is None:
        return "-"
    rounded_liters = int(round(liters))
    sign = "-" if rounded_liters < 0 else ""
    cubic_meters, remaining_liters = divmod(abs(rounded_liters), 1000)
    if cubic_meters == 0:
        return f"{sign}{remaining_liters} L"
    if remaining_liters == 0:
        return f"{sign}{cubic_meters} m³"
    return f"{sign}{cubic_meters} m³ {remaining_liters} L"


def format_cubic_meters_text(liters: float | None) -> str:
    if liters is None:
        return "-"
    cubic_meters = round(liters / 1000, 1)
    return f"{cubic_meters:.1f} m³"


def format_volume_html(liters: float | None) -> Markup:
    text = format_volume_text(liters)
    if liters is None:
        return Markup(text)
    rounded_liters = int(round(liters))
    sign = "-" if rounded_liters < 0 else ""
    cubic_meters, remaining_liters = divmod(abs(rounded_liters), 1000)
    if cubic_meters == 0:
        return Markup(
            '<span class="volume">'
            f'<span class="volume-major">{sign}{remaining_liters} L</span>'
            "</span>"
        )
    major = f'<span class="volume-major">{sign}{cubic_meters} m³</span>'
    if remaining_liters == 0:
        return Markup(f'<span class="volume">{major}</span>')
    minor = f'<span class="volume-minor">{remaining_liters} L</span>'
    return Markup(f'<span class="volume">{major} {minor}</span>')


def format_last_pulse_relative(
    timestamp: str | None,
    now: datetime,
    timezone: ZoneInfo,
    t: Translate,
) -> str:
    last_pulse_at = _parse_esphome_timestamp(timestamp, timezone)
    if last_pulse_at is None:
        return "-"

    delta_seconds = int((now.astimezone(timezone) - last_pulse_at).total_seconds())
    if delta_seconds < 0:
        return "-"
    if delta_seconds < 5:
        return t("relative_time.just_now")
    if delta_seconds < 60:
        return t("relative_time.seconds_ago", count=delta_seconds)

    delta_minutes = delta_seconds // 60
    if delta_minutes < 60:
        if delta_minutes == 1:
            return t("relative_time.minute_ago")
        return t("relative_time.minutes_ago", count=delta_minutes)

    delta_hours = delta_minutes // 60
    if delta_hours < 24:
        if delta_hours == 1:
            return t("relative_time.hour_ago")
        return t("relative_time.hours_ago", count=delta_hours)

    delta_days = delta_hours // 24
    if delta_days == 1:
        return t("relative_time.day_ago")
    return t("relative_time.days_ago", count=delta_days)


def format_last_pulse_timestamp(
    timestamp: str | None,
    timezone: ZoneInfo,
) -> str:
    last_pulse_at = _parse_esphome_timestamp(timestamp, timezone)
    if last_pulse_at is None:
        return "-"
    return last_pulse_at.strftime("%d/%m/%Y %H:%M:%S")


def is_last_pulse_within(
    timestamp: str | None,
    now: datetime,
    timezone: ZoneInfo,
    seconds: int,
) -> bool:
    last_pulse_at = _parse_esphome_timestamp(timestamp, timezone)
    if last_pulse_at is None:
        return False
    delta_seconds = (now.astimezone(timezone) - last_pulse_at).total_seconds()
    return 0 <= delta_seconds < seconds


def watering_zone_ids(
    zone_states: Iterable[Any],
    live_available: bool,
    now: datetime,
    timezone: ZoneInfo,
    seconds: int = 60,
) -> set[int]:
    if not live_available:
        return set()
    return {
        zone.zone_id
        for zone_state in zone_states
        if is_last_pulse_within(
            (zone := zone_state.live).last_pulse_timestamp,
            now,
            timezone,
            seconds=seconds,
        )
    }


def _parse_esphome_timestamp(
    timestamp: str | None,
    timezone: ZoneInfo,
) -> datetime | None:
    if not timestamp:
        return None
    try:
        parsed = datetime.strptime(timestamp.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone)
