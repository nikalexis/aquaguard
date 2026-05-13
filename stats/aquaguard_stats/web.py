from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import load_settings
from .esphome_client import ESPHomeZoneReader
from .models import ZONE_COUNT
from .repository import SnapshotRepository
from .scheduler import NoonSnapshotScheduler
from .service import StatsService

LOGGER = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    repository = SnapshotRepository(settings.db_path)
    repository.init_schema()
    service = StatsService(settings, repository, ESPHomeZoneReader(settings))
    scheduler = NoonSnapshotScheduler(service)
    templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = service
        app.state.settings = settings
        scheduler.start()
        LOGGER.info("AquaGuard stats dashboard started")
        try:
            yield
        finally:
            await scheduler.stop()

    app = FastAPI(title="AquaGuard Stats", lifespan=lifespan)
    app.mount(
        "/static",
        StaticFiles(directory=str(PACKAGE_DIR / "static")),
        name="static",
    )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        summary = await service.get_dashboard_summary()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "summary": summary,
                "warning_threshold": int(settings.warning_threshold * 100),
            },
        )

    @app.get("/zones/{zone_id}", response_class=HTMLResponse)
    async def zone_detail(request: Request, zone_id: int):
        if zone_id < 1 or zone_id > ZONE_COUNT:
            raise HTTPException(status_code=404, detail="Zone not found")
        summary = await service.get_dashboard_summary()
        zone = next(
            (candidate for candidate in summary.zones if candidate.zone_id == zone_id),
            None,
        )
        points = service.get_zone_daily_points(zone_id=zone_id)
        return templates.TemplateResponse(
            request,
            "zone.html",
            {
                "summary": summary,
                "zone": zone,
                "zone_id": zone_id,
                "points": points,
                "chart_points": [
                    {
                        "date": point.snapshot_date.isoformat(),
                        "value": point.daily_consumption_l,
                        "partial": point.partial,
                    }
                    for point in points
                ],
            },
        )

    @app.get("/api/dashboard")
    async def api_dashboard():
        return await service.get_dashboard_summary()

    @app.get("/api/zones/{zone_id}/daily")
    async def api_zone_daily(zone_id: int):
        if zone_id < 1 or zone_id > ZONE_COUNT:
            raise HTTPException(status_code=404, detail="Zone not found")
        return service.get_zone_daily_points(zone_id=zone_id)

    @app.post("/api/snapshots/noon")
    async def api_record_snapshot():
        rows = await service.record_noon_snapshot()
        return {"rows": rows}

    return app


app = create_app()


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "aquaguard_stats.web:app",
        host=settings.host,
        port=settings.port,
        factory=False,
    )


if __name__ == "__main__":
    main()
