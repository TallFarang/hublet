"""Shared server-rendered web surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
STATIC_DIR = Path(__file__).parents[1] / "static"
router = APIRouter()


def render(request: Request, template: str, **context: Any) -> Response:
    return TEMPLATES.TemplateResponse(request=request, name=template, context=context)


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
