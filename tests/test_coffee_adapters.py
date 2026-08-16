from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from mcp.server import MCPServer

from app.config import Settings
from app.main import create_app
from app.plugins import PLUGINS, coffee
from app.runtime import migrate_plugins


def test_coffee_descriptor_is_explicitly_registered() -> None:
    assert PLUGINS[3] is coffee.PLUGIN
    assert coffee.PLUGIN.name == "coffee"
    assert coffee.PLUGIN.db_filename == "coffee.db"
    assert coffee.PLUGIN.migrations is coffee.MIGRATIONS


def test_mcp_adapter_registers_semantic_tools_and_calls_domain(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    migrate_plugins(settings, (coffee.PLUGIN,))
    server = MCPServer("test")

    coffee.register_mcp(server, settings)
    tools = asyncio.run(server.list_tools())
    asyncio.run(
        server.call_tool(
            "coffee.add_bean",
            {"name": "MCP Bean", "roaster": "Example Roaster"},
        )
    )
    bean = coffee.list_beans(settings)[0]
    asyncio.run(
        server.call_tool(
            "coffee.log_shot",
            {
                "bean_id": bean["id"],
                "dose_g": 18,
                "yield_g": 36,
                "time_s": 29,
                "grind_setting": "13",
                "rating": 4,
            },
        )
    )
    asyncio.run(server.call_tool("coffee.history", {"bean_id": bean["id"]}))

    assert {tool.name for tool in tools} == {
        "coffee.add_bean",
        "coffee.list_beans",
        "coffee.log_shot",
        "coffee.history",
        "coffee.recommend_next",
    }
    assert coffee.history(settings, bean["id"])[0]["rating"] == 4


def test_html_routes_create_log_and_archive_through_domain(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings, plugins=(coffee.PLUGIN,))

    with TestClient(app, base_url=settings.public_origin) as client:
        assert client.get("/coffee", follow_redirects=False).status_code == 303
        login = client.post(
            "/login",
            data={"token": settings.dashboard_token},
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )
        created = client.post(
            "/coffee/beans",
            data={
                "name": "A&B",
                "roaster": "Example Roaster",
                "roast_date": "2026-08-10",
                "origin": "Colombia",
                "process": "washed",
                "notes": "cocoa",
            },
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )
        bean = coffee.list_beans(settings)[0]
        shot = client.post(
            "/coffee/shots",
            data={
                "bean_id": bean["id"],
                "dose_g": "18",
                "yield_g": "36",
                "time_s": "29",
                "grind_setting": "13",
                "rating": "4",
                "taste_tags": "balanced, sweet",
            },
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )
        page = client.get("/coffee")
        edited = client.post(
            f"/coffee/beans/{bean['id']}",
            data={
                "name": "A&B Decaf",
                "roaster": "Another Roaster",
                "roast_date": "2026-08-11",
                "origin": "Peru",
                "process": "natural",
                "notes": "cherry",
            },
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )
        archived = client.post(
            f"/coffee/beans/{bean['id']}/archive",
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )

    assert login.status_code == 303
    assert created.status_code == 303
    assert shot.status_code == 303
    assert edited.status_code == 303
    assert archived.status_code == 303
    assert "A&amp;B" in page.text
    assert coffee.history(settings, bean["id"])[0]["taste_tags"] == ["balanced", "sweet"]
    saved = coffee.get_bean(settings, bean["id"])
    assert (saved["name"], saved["origin"], saved["notes"], saved["status"]) == (
        "A&B Decaf",
        "Peru",
        "cherry",
        "archived",
    )


def test_html_domain_validation_returns_422(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings, plugins=(coffee.PLUGIN,))

    with TestClient(app, base_url=settings.public_origin) as client:
        client.post(
            "/login",
            data={"token": settings.dashboard_token},
            headers={"Origin": settings.public_origin},
        )
        response = client.post(
            "/coffee/beans",
            data={"name": "   "},
            headers={"Origin": settings.public_origin},
        )

    assert response.status_code == 422
    assert "name is required" in response.text
    assert 'role="alert"' in response.text
    assert "history.back()" not in response.text
    assert 'href="/coffee"' in response.text


def test_launcher_summary_counts_open_beans(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    migrate_plugins(settings, (coffee.PLUGIN,))
    coffee.add_bean(settings, "Open")
    coffee.add_bean(settings, "Done", status="archived")

    assert coffee.launcher_summary(settings) == "1 open bean"
