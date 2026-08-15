"""Hublet ASGI application."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings
from app.runtime import PLUGINS, Plugin, migrate_plugins, plugin_health


def create_app(
    settings: Settings | None = None,
    plugins: Sequence[Plugin] | None = None,
) -> FastAPI:
    selected_plugins = tuple(PLUGINS if plugins is None else plugins)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved_settings = Settings.from_env() if settings is None else settings
        migrate_plugins(resolved_settings, selected_plugins)
        application.state.settings = resolved_settings
        application.state.plugins = selected_plugins
        yield

    application = FastAPI(title="Hublet", lifespan=lifespan)

    @application.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "plugins": plugin_health(application.state.settings, application.state.plugins),
        }

    return application


app = create_app()
