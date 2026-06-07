from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import load_settings
from .display import format_volume_html, format_volume_text
from .esphome_client import ESPHomeZoneReader
from .i18n import (
    LANGUAGE_COOKIE,
    SUPPORTED_LANGUAGES,
    language_url,
    load_translator,
    localized_url,
    resolve_language,
    status_label_key,
)
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
    templates.env.globals["format_volume"] = format_volume_html
    templates.env.globals["format_volume_text"] = format_volume_text
    translator = load_translator()

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
        language, should_set_language_cookie = resolve_language(request)
        t = translator.for_language(language)
        summary = await service.get_dashboard_summary()
        response = templates.TemplateResponse(
            request,
            "index.html",
            {
                "language": language,
                "languages": SUPPORTED_LANGUAGES,
                "language_url": lambda target_language: language_url(
                    request,
                    target_language,
                ),
                "localized_url": lambda path: localized_url(path, language),
                "summary": summary,
                "status_label_key": status_label_key,
                "t": t,
                "warning_threshold": int(settings.warning_threshold * 100),
            },
        )
        if should_set_language_cookie:
            response.set_cookie(
                LANGUAGE_COOKIE,
                language,
                max_age=60 * 60 * 24 * 365,
                samesite="lax",
            )
        return response

    @app.get("/zones/{zone_id}", response_class=HTMLResponse)
    async def zone_detail(
        request: Request,
        zone_id: int,
        range: str | None = Query(default=None),
        year: int | None = Query(default=None),
        month: int | None = Query(default=None),
    ):
        if zone_id < 1 or zone_id > ZONE_COUNT:
            raise HTTPException(status_code=404, detail="Zone not found")
        language, should_set_language_cookie = resolve_language(request)
        t = translator.for_language(language)
        summary = await service.get_dashboard_summary()
        zone = next(
            (candidate for candidate in summary.zones if candidate.live.zone_id == zone_id),
            None,
        )
        history_range = service.resolve_history_range(
            zone_id=zone_id,
            range_mode=range,
            year=year,
            month=month,
        )
        points = service.get_zone_daily_points_for_range(
            zone_id=zone_id,
            history_range=history_range,
            live_zone=zone.live if zone else None,
            live_available=summary.error is None,
        )
        response = templates.TemplateResponse(
            request,
            "zone.html",
            {
                "language": language,
                "languages": SUPPORTED_LANGUAGES,
                "language_url": lambda target_language: language_url(
                    request,
                    target_language,
                ),
                "localized_url": lambda path: localized_url(path, language),
                "summary": summary,
                "zone": zone,
                "zone_id": zone_id,
                "points": points,
                "history_range": history_range,
                "month_names": translator.month_names(language),
                "status_label_key": status_label_key,
                "t": t,
                "previous_date_iso": lambda snapshot_date: (
                    snapshot_date - timedelta(days=1)
                ).isoformat(),
                "chart_points": [
                    {
                        "date": point.snapshot_date.isoformat(),
                        "value": point.daily_consumption_l,
                        "measurement_quality": point.measurement_quality,
                        "partial": point.partial,
                        "missing": point.missing,
                        "estimate_span_days": point.estimate_span_days,
                    }
                    for point in points
                ],
            },
        )
        if should_set_language_cookie:
            response.set_cookie(
                LANGUAGE_COOKIE,
                language,
                max_age=60 * 60 * 24 * 365,
                samesite="lax",
            )
        return response

    @app.get("/api/dashboard")
    async def api_dashboard():
        return await service.get_dashboard_summary()

    @app.get("/api/zones/{zone_id}/daily")
    async def api_zone_daily(
        zone_id: int,
        range: str | None = Query(default=None),
        year: int | None = Query(default=None),
        month: int | None = Query(default=None),
    ):
        if zone_id < 1 or zone_id > ZONE_COUNT:
            raise HTTPException(status_code=404, detail="Zone not found")
        summary = await service.get_dashboard_summary()
        zone = next(
            (candidate for candidate in summary.zones if candidate.live.zone_id == zone_id),
            None,
        )
        history_range = service.resolve_history_range(
            zone_id=zone_id,
            range_mode=range,
            year=year,
            month=month,
        )
        return service.get_zone_daily_points_for_range(
            zone_id=zone_id,
            history_range=history_range,
            live_zone=zone.live if zone else None,
            live_available=summary.error is None,
        )

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
