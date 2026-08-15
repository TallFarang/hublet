"""Explicit registration for Hublet's deliberately tiny plugin convention."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from fastapi import APIRouter
from mcp.server import MCPServer

from app.config import Settings
from app.db import connect, migrate


@dataclass(frozen=True, slots=True)
class Plugin:
    """The complete convention shared by Hublet's three explicit plugins."""

    name: str
    icon: str
    db_filename: str
    migrations: tuple[str, ...]
    register_mcp: Callable[[MCPServer], None]
    router: APIRouter
    launcher_summary: Callable[[Settings], str]


PLUGINS: tuple[Plugin, ...] = ()


def migrate_plugins(settings: Settings, plugins: Sequence[Plugin] | None = None) -> None:
    for plugin in PLUGINS if plugins is None else plugins:
        migrate(settings.data_dir / plugin.db_filename, plugin.migrations)


def plugin_health(
    settings: Settings, plugins: Sequence[Plugin] | None = None
) -> dict[str, str]:
    health = {}
    for plugin in PLUGINS if plugins is None else plugins:
        with connect(settings.data_dir / plugin.db_filename) as connection:
            connection.execute("SELECT 1").fetchone()
        health[plugin.name] = "ok"
    return health
