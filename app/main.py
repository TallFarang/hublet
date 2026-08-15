"""Hublet ASGI application."""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from app.auth import BearerAuthMiddleware, DashboardAuthMiddleware, SameOriginMiddleware
from app.config import Settings
from app.runtime import PLUGINS, Plugin, migrate_plugins, plugin_health

SESSION_MAX_AGE = 90 * 24 * 60 * 60
LOGIN_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Sign in · Hublet</title></head>
<body><main><h1>Hublet</h1><form method="post"><label>Token
<input name="token" type="password" required autofocus></label><button>Sign in</button>
</form></main></body></html>"""


def create_app(
    settings: Settings | None = None,
    plugins: Sequence[Plugin] | None = None,
) -> FastAPI:
    resolved_settings = Settings.from_env() if settings is None else settings
    selected_plugins = tuple(PLUGINS if plugins is None else plugins)
    mcp = MCPServer("Hublet")
    for plugin in selected_plugins:
        plugin.register_mcp(mcp)
    mcp_application = mcp.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=list(resolved_settings.mcp_allowed_hosts),
            allowed_origins=[resolved_settings.public_origin],
        ),
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        migrate_plugins(resolved_settings, selected_plugins)
        application.state.settings = resolved_settings
        application.state.plugins = selected_plugins
        async with mcp.session_manager.run():
            yield

    application = FastAPI(title="Hublet", lifespan=lifespan)

    @application.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "plugins": plugin_health(application.state.settings, application.state.plugins),
        }

    @application.get("/login", response_class=HTMLResponse)
    def login_page() -> str:
        return LOGIN_PAGE

    @application.post("/login")
    def login(request: Request, token: Annotated[str, Form()]) -> Response:
        if not hmac.compare_digest(token, resolved_settings.dashboard_token):
            return HTMLResponse(LOGIN_PAGE, status_code=401)
        request.session.clear()
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)

    @application.post("/logout")
    def logout(request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    application.mount(
        "/mcp",
        BearerAuthMiddleware(mcp_application, resolved_settings.mcp_token),
    )
    application.add_middleware(DashboardAuthMiddleware)
    application.add_middleware(SameOriginMiddleware, origin=resolved_settings.public_origin)
    session_options = {
        "secret_key": resolved_settings.session_secret,
        "session_cookie": "hublet_session",
        "max_age": SESSION_MAX_AGE,
        "same_site": "lax",
        "https_only": urlsplit(resolved_settings.public_origin).scheme == "https",
    }
    application.add_middleware(SessionMiddleware, **session_options)

    return application


# Uvicorn target: app.main:app --factory
app = create_app
