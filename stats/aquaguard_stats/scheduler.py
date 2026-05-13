from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, time, timedelta

from .service import StatsService

LOGGER = logging.getLogger(__name__)


class NoonSnapshotScheduler:
    def __init__(self, service: StatsService) -> None:
        self.service = service
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="noon-snapshot-scheduler")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            delay = seconds_until_next_noon(self.service.settings.zoneinfo)
            await asyncio.sleep(delay)
            try:
                rows = await self.service.record_noon_snapshot()
                LOGGER.info("Recorded %s AquaGuard daily snapshots", rows)
            except Exception:
                LOGGER.exception("Failed to record AquaGuard daily snapshots")


def seconds_until_next_noon(tz) -> float:
    now = datetime.now(tz)
    target = datetime.combine(now.date(), time(hour=12), tzinfo=tz)
    if now >= target:
        target += timedelta(days=1)
    return max((target - now).total_seconds(), 1.0)

