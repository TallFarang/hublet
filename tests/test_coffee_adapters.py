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


def test_mcp_adapter_registers_only_the_bag_and_brew_tools(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    migrate_plugins(settings, (coffee.PLUGIN,))
    server = MCPServer("test")
    coffee.register_mcp(server, settings)
    tools = asyncio.run(server.list_tools())

    asyncio.run(
        server.call_tool(
            "coffee.add_bag",
            {"name": "MCP Bean", "roaster": "Example Roaster"},
        )
    )
    bag = coffee.list_bags(settings)[0]
    asyncio.run(
        server.call_tool(
            "coffee.log_brew",
            {
                "bag_id": bag["id"],
                "method": "espresso",
                "dose_g": 18,
                "yield_g": 36,
                "time_s": 29,
                "grind_setting": "1.3",
                "rating": 4,
            },
        )
    )
    asyncio.run(server.call_tool("coffee.history", {"bag_id": bag["id"]}))
    asyncio.run(
        server.call_tool(
            "coffee.set_bag_status",
            {"bag_id": bag["id"], "status": "archived"},
        )
    )

    assert {tool.name for tool in tools} == {
        "coffee.add_bag",
        "coffee.list_bags",
        "coffee.set_bag_status",
        "coffee.log_brew",
        "coffee.history",
    }
    assert coffee.history(settings, bag["id"])[0]["rating"] == 4
    assert coffee.get_bag(settings, bag["id"])["status"] == "archived"


def test_dashboard_is_read_only_and_shows_filter_and_espresso_recipes(
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
        bag = coffee.add_bag(settings, "A&B", "Example Roaster", origin="Colombia")
        coffee.log_brew(
            settings,
            bag["id"],
            "v60",
            30,
            "5.2",
            water_g=450,
            bypass_water_g=60,
            rating=4,
            taste_notes="balanced & sweet",
        )
        coffee.log_brew(
            settings,
            bag["id"],
            "espresso",
            18,
            "1.3",
            yield_g=36,
            time_s=29,
            rating=5,
            notes="Latte",
        )
        page = client.get("/coffee")
        unavailable = client.post(
            "/coffee/bags",
            data={"name": "Dashboard bag"},
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )

    assert login.status_code == 303
    assert unavailable.status_code in {404, 405}
    assert "A&amp;B" in page.text
    assert "30g / 450g · grind 5.2 · +60g bypass" in page.text
    assert "18g → 36g · grind 1.3 · 29s" in page.text
    assert "balanced &amp; sweet" in page.text and "Latte" in page.text
    assert page.text.count("<form") == 1


def test_removed_coffee_post_routes_stay_unavailable(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings, plugins=(coffee.PLUGIN,))
    with TestClient(app, base_url=settings.public_origin) as client:
        client.post(
            "/login",
            data={"token": settings.dashboard_token},
            headers={"Origin": settings.public_origin},
        )
        response = client.post(
            "/coffee/bags",
            data={"name": "   "},
            headers={"Origin": settings.public_origin},
        )
    assert response.status_code in {404, 405}


def test_launcher_summary_counts_open_bags(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    migrate_plugins(settings, (coffee.PLUGIN,))
    coffee.add_bag(settings, "Open", "Roaster")
    coffee.add_bag(settings, "Done", "Roaster", status="archived")

    assert coffee.launcher_summary(settings) == "1 open bag"
