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


def test_dashboard_is_read_only_while_domain_writes_remain_available(
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
        bean = coffee.add_bean(
            settings,
            "A&B",
            roaster="Example Roaster",
            origin="Colombia",
        )
        coffee.log_shot(
            settings,
            bean["id"],
            dose_g=18,
            yield_g=36,
            time_s=29,
            grind_setting="13",
            rating=4,
            taste_tags=["balanced", "sweet"],
        )
        page = client.get("/coffee")
        unavailable = client.post(
            "/coffee/beans",
            data={"name": "Dashboard bean"},
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )

    assert login.status_code == 303
    assert unavailable.status_code in {404, 405}
    assert "A&amp;B" in page.text
    assert coffee.history(settings, bean["id"])[0]["taste_tags"] == ["balanced", "sweet"]
    assert page.text.count("<form") == 1


def test_removed_coffee_post_routes_do_not_validate_dashboard_input(
    settings_env: dict[str, str],
) -> None:
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

    assert response.status_code in {404, 405}


def test_launcher_summary_counts_open_beans(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    migrate_plugins(settings, (coffee.PLUGIN,))
    coffee.add_bean(settings, "Open")
    coffee.add_bean(settings, "Done", status="archived")

    assert coffee.launcher_summary(settings) == "1 open bean"
