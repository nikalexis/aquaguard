from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from .models import AvailableMonth, ZoneDailySnapshot


class SnapshotRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init_schema(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS zone_daily_snapshots (
                  snapshot_date TEXT NOT NULL,
                  snapshot_at TEXT NOT NULL,
                  zone_id INTEGER NOT NULL,
                  zone_name TEXT NOT NULL,
                  meter_consumption_l REAL NOT NULL,
                  period_baseline_l REAL NOT NULL,
                  period_consumption_l REAL NOT NULL,
                  period_limit_l REAL NOT NULL,
                  period_limit_active INTEGER NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (snapshot_date, zone_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_zone_daily_snapshots_zone_date
                ON zone_daily_snapshots (zone_id, snapshot_date)
                """
            )

    def upsert_snapshots(self, snapshots: Iterable[ZoneDailySnapshot]) -> int:
        rows = [
            (
                snapshot.snapshot_date.isoformat(),
                snapshot.snapshot_at.isoformat(),
                snapshot.zone_id,
                snapshot.zone_name,
                snapshot.meter_consumption_l,
                snapshot.period_baseline_l,
                snapshot.period_consumption_l,
                snapshot.period_limit_l,
                1 if snapshot.period_limit_active else 0,
            )
            for snapshot in snapshots
        ]
        if not rows:
            return 0

        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO zone_daily_snapshots (
                  snapshot_date,
                  snapshot_at,
                  zone_id,
                  zone_name,
                  meter_consumption_l,
                  period_baseline_l,
                  period_consumption_l,
                  period_limit_l,
                  period_limit_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_date, zone_id) DO UPDATE SET
                  snapshot_at = excluded.snapshot_at,
                  zone_name = excluded.zone_name,
                  meter_consumption_l = excluded.meter_consumption_l,
                  period_baseline_l = excluded.period_baseline_l,
                  period_consumption_l = excluded.period_consumption_l,
                  period_limit_l = excluded.period_limit_l,
                  period_limit_active = excluded.period_limit_active,
                  updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
        return len(rows)

    def list_zone_snapshots(
        self,
        zone_id: int,
        limit: int = 90,
    ) -> list[ZoneDailySnapshot]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM zone_daily_snapshots
                WHERE zone_id = ?
                ORDER BY snapshot_date DESC
                LIMIT ?
                """,
                (zone_id, limit),
            ).fetchall()

        return [
            self._row_to_snapshot(row)
            for row in reversed(rows)
        ]

    def list_zone_snapshots_between(
        self,
        zone_id: int,
        start_date: date,
        end_date: date,
    ) -> list[ZoneDailySnapshot]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM zone_daily_snapshots
                WHERE zone_id = ?
                  AND snapshot_date >= ?
                  AND snapshot_date <= ?
                ORDER BY snapshot_date ASC
                """,
                (zone_id, start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        return [self._row_to_snapshot(row) for row in rows]

    def list_available_months(self, zone_id: int) -> list[AvailableMonth]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT
                  CAST(strftime('%Y', snapshot_date) AS INTEGER) AS year,
                  CAST(strftime('%m', snapshot_date) AS INTEGER) AS month
                FROM zone_daily_snapshots
                WHERE zone_id = ?
                ORDER BY year DESC, month DESC
                """,
                (zone_id,),
            ).fetchall()
        return [
            AvailableMonth(year=int(row["year"]), month=int(row["month"]))
            for row in rows
        ]

    def list_latest_snapshots(self) -> list[ZoneDailySnapshot]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT snapshots.*
                FROM zone_daily_snapshots snapshots
                JOIN (
                  SELECT zone_id, MAX(snapshot_date) AS snapshot_date
                  FROM zone_daily_snapshots
                  GROUP BY zone_id
                ) latest
                  ON latest.zone_id = snapshots.zone_id
                 AND latest.snapshot_date = snapshots.snapshot_date
                ORDER BY snapshots.zone_id
                """
            ).fetchall()
        return [self._row_to_snapshot(row) for row in rows]

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> ZoneDailySnapshot:
        return ZoneDailySnapshot(
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            snapshot_at=datetime.fromisoformat(row["snapshot_at"]),
            zone_id=int(row["zone_id"]),
            zone_name=str(row["zone_name"]),
            meter_consumption_l=float(row["meter_consumption_l"]),
            period_baseline_l=float(row["period_baseline_l"]),
            period_consumption_l=float(row["period_consumption_l"]),
            period_limit_l=float(row["period_limit_l"]),
            period_limit_active=bool(row["period_limit_active"]),
        )
