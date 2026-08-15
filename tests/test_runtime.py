from __future__ import annotations

from fastapi import APIRouter
from mcp.server import MCPServer

from app.config import Settings
from app.runtime import Plugin, migrate_plugins, plugin_health


def make_plugin() -> Plugin:
    return Plugin(
        name="example",
        icon="circle",
        db_filename="example.db",
        migrations=("CREATE TABLE example (value TEXT NOT NULL);",),
        register_mcp=lambda server, settings: None,
        router=APIRouter(),
        launcher_summary=lambda settings: "0 examples",
    )


def test_plugin_runtime_migrates_and_checks_health(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    plugin = make_plugin()

    migrate_plugins(settings, (plugin,))

    assert (settings.data_dir / "example.db").is_file()
    assert plugin_health(settings, (plugin,)) == {"example": "ok"}


def test_plugin_descriptor_accepts_mcp_registration(settings_env: dict[str, str]) -> None:
    registered: list[tuple[MCPServer, Settings]] = []
    plugin = make_plugin()
    server = MCPServer("test")
    plugin = Plugin(
        name=plugin.name,
        icon=plugin.icon,
        db_filename=plugin.db_filename,
        migrations=plugin.migrations,
        register_mcp=lambda server, settings: registered.append((server, settings)),
        router=plugin.router,
        launcher_summary=plugin.launcher_summary,
    )

    settings = Settings.from_env(settings_env)
    plugin.register_mcp(server, settings)

    assert registered == [(server, settings)]
