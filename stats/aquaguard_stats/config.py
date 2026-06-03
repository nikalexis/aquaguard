from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    esphome_host: str
    esphome_port: int
    api_encryption_key: str | None
    db_path: Path
    timezone: str
    warning_threshold: float
    meter_reset_threshold_l: float
    refresh_timeout_s: float
    host: str
    port: int

    @property
    def zoneinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_settings() -> Settings:
    threshold = float(os.getenv("AQUAGUARD_WARNING_THRESHOLD", "0.8"))
    if threshold <= 0:
        threshold = 0.8
    reset_threshold = float(os.getenv("AQUAGUARD_METER_RESET_THRESHOLD_L", "1.0"))
    if reset_threshold < 0:
        reset_threshold = 1.0

    return Settings(
        esphome_host=os.getenv("AQUAGUARD_ESPHOME_HOST", "aquaguard.local"),
        esphome_port=int(os.getenv("AQUAGUARD_ESPHOME_PORT", "6053")),
        api_encryption_key=_optional_env("AQUAGUARD_API_ENCRYPTION_KEY"),
        db_path=Path(os.getenv("AQUAGUARD_DB_PATH", "data/aquaguard-stats.sqlite3")),
        timezone=os.getenv("AQUAGUARD_TIMEZONE", "Europe/Athens"),
        warning_threshold=threshold,
        meter_reset_threshold_l=reset_threshold,
        refresh_timeout_s=float(os.getenv("AQUAGUARD_REFRESH_TIMEOUT_S", "8")),
        host=os.getenv("AQUAGUARD_HTTP_HOST", "0.0.0.0"),
        port=int(os.getenv("AQUAGUARD_HTTP_PORT", "8080")),
    )
