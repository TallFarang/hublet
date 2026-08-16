"""Hublet ASGI application."""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from app.auth import BearerAuthMiddleware, DashboardAuthMiddleware, SameOriginMiddleware
from app.config import Settings
from app.plugins import PLUGINS
from app.runtime import Plugin, migrate_plugins, plugin_health
from app.web import STATIC_DIR, render
from app.web import router as web_router

SESSION_MAX_AGE = 90 * 24 * 60 * 60


def create_app(
    settings: Settings | None = None,
    plugins: Sequence[Plugin] | None = None,
) -> FastAPI:
    resolved_settings = Settings.from_env() if settings is None else settings
    selected_plugins = tuple(PLUGINS if plugins is None else plugins)
    mcp = MCPServer("Hublet")
    for plugin in selected_plugins:
        plugin.register_mcp(mcp, resolved_settings)
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
    application.include_router(web_router)
    for plugin in selected_plugins:
        application.include_router(plugin.router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.exception_handler(ValueError)
    def invalid_input(request: Request, error: ValueError) -> Response:
        section = request.url.path.strip("/").partition("/")[0]
        plugins = {plugin.name for plugin in application.state.plugins}
        destination = section.capitalize() if section in plugins else "Hublet"
        back = f"/{section}" if section in plugins else "/"
        response = render(
            request,
            "error.html",
            title="Check that entry",
            message=str(error),
            destination=destination,
            back=back,
        )
        response.status_code = 422
        return response

    @application.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "plugins": plugin_health(application.state.settings, application.state.plugins),
        }

    @application.get("/login")
    def login_page(request: Request) -> Response:
        return render(request, "login.html", error=None)

    @application.post("/login")
    def login(request: Request, token: Annotated[str, Form()]) -> Response:
        if not hmac.compare_digest(token, resolved_settings.dashboard_token):
            response = render(request, "login.html", error="That token did not match.")
            response.status_code = 401
            return response
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
