"""Shared server-rendered web surface."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
STATIC_DIR = Path(__file__).parents[1] / "static"
router = APIRouter()
PERIOD_DAYS = {"week": 7, "month": 30}


def render(request: Request, template: str, **context: Any) -> Response:
    return TEMPLATES.TemplateResponse(request=request, name=template, context=context)


def dashboard_period(value: str, end: date | None = None) -> dict[str, Any]:
    """Resolve the shared dashboard range without exposing storage dates to templates."""

    key = value if value in PERIOD_DAYS else "week"
    resolved_end = end or datetime.now().astimezone().date()
    days = PERIOD_DAYS[key]
    return {
        "key": key,
        "days": days,
        "start": (resolved_end - timedelta(days=days - 1)).isoformat(),
        "end": resolved_end.isoformat(),
    }


def uk_date(value: Any, compact: bool = False) -> str:
    """Format an ISO date or timestamp for the read-only UK dashboard."""

    if value in {None, ""}:
        return "—"
    parsed = date.fromisoformat(str(value)[:10])
    return parsed.strftime("%d/%m" if compact else "%d/%m/%Y")


TEMPLATES.env.filters["uk_date"] = uk_date


@router.get("/")
def launcher(request: Request) -> Response:
    settings = request.app.state.settings
    plugins = [
        {
            "name": plugin.name,
            "icon": plugin.icon,
            "summary": plugin.launcher_summary(settings),
            "url": f"/{plugin.name}",
        }
        for plugin in request.app.state.plugins
    ]
    return render(request, "launcher.html", title="Hublet", plugins=plugins)
