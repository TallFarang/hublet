from __future__ import annotations

import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient
from mcp.server import MCPServer

from app.config import Settings
from app.db import migrate
from app.main import create_app
from app.plugins import PLUGINS, recipes


@pytest.fixture
def recipe_settings(settings_env: dict[str, str]) -> Settings:
    settings = Settings.from_env(settings_env)
    migrate(settings.data_dir / recipes.DB_FILENAME, recipes.MIGRATIONS)
    return settings


def test_recipe_plugin_is_the_third_explicit_registration() -> None:
    assert PLUGINS[2] is recipes.PLUGIN
    assert [plugin.name for plugin in PLUGINS] == ["goals", "food", "recipes", "coffee", "health"]


def test_recipe_schema_keeps_notes_canonical(recipe_settings: Settings) -> None:
    with sqlite3.connect(recipe_settings.data_dir / recipes.DB_FILENAME) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        recipe_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(recipes)")
        }

    assert tables == {"recipes", "cook_logs"}
    assert recipe_columns == {
        "id",
        "name",
        "note_reference",
        "tags_json",
        "created_at",
        "updated_at",
    }
    assert not {"ingredients", "steps", "body"} & recipe_columns


def test_link_search_get_and_edit_recipe(recipe_settings: Settings) -> None:
    linked = recipes.link_recipe(
        recipe_settings,
        "Sunday stew",
        "notes://example/stew",
        tags=["dinner", "slow"],
    )
    recipes.link_recipe(recipe_settings, "Quick noodles", "notes://example/noodles")

    edited = recipes.update_recipe(
        recipe_settings,
        linked["id"],
        name="Better stew",
        note_reference="notes://example/better-stew",
        tags=["dinner", "tested"],
    )

    assert edited["tags"] == ["dinner", "tested"]
    assert "tags_json" not in edited
    assert [item["name"] for item in recipes.search(recipe_settings, "stew")] == [
        "Better stew"
    ]
    assert recipes.search(recipe_settings, "tested")[0]["id"] == linked["id"]
    assert recipes.get_recipe(recipe_settings, linked["id"])["note_reference"].endswith(
        "better-stew"
    )


def test_cook_history_preserves_experiment_and_conclusion(recipe_settings: Settings) -> None:
    recipe = recipes.link_recipe(recipe_settings, "Stew", "notes://example/stew")
    first = recipes.log_cook(
        recipe_settings,
        recipe["id"],
        rating=3,
        changes="Used sirloin; doubled garlic",
        notes="Meat was dry",
        conclusion="Keep the garlic, use chuck",
    )
    second = recipes.log_cook(
        recipe_settings,
        recipe["id"],
        rating=5,
        changes="Used chuck",
        conclusion="This is the version to repeat",
    )

    saved = recipes.get_recipe(recipe_settings, recipe["id"])

    assert [log["id"] for log in saved["cook_logs"]] == [second["id"], first["id"]]
    assert saved["cook_logs"][1]["conclusion"] == "Keep the garlic, use chuck"
    assert recipes.history(recipe_settings, recipe["id"])[0]["recipe_name"] == "Stew"


def test_recipe_domain_rejects_bad_input(recipe_settings: Settings) -> None:
    with pytest.raises(ValueError, match="name"):
        recipes.link_recipe(recipe_settings, " ", "notes://example/x")
    with pytest.raises(ValueError, match="note_reference"):
        recipes.link_recipe(recipe_settings, "Dish", " ")
    with pytest.raises(ValueError, match="Recipe not found"):
        recipes.log_cook(recipe_settings, "missing", rating=3)
    recipe = recipes.link_recipe(recipe_settings, "Dish", "notes://example/dish")
    with pytest.raises(ValueError, match="rating"):
        recipes.log_cook(recipe_settings, recipe["id"], rating=0)


def test_recipe_mcp_tools_use_domain(recipe_settings: Settings) -> None:
    server = MCPServer("test")
    recipes.register_mcp(server, recipe_settings)
    tools = asyncio.run(server.list_tools())
    asyncio.run(
        server.call_tool(
            "recipes.link",
            {
                "name": "MCP curry",
                "note_reference": "notes://example/curry",
                "tags": ["dinner"],
            },
        )
    )
    recipe = recipes.search(recipe_settings, "curry")[0]
    asyncio.run(
        server.call_tool(
            "recipes.log_cook",
            {"recipe_id": recipe["id"], "rating": 4, "conclusion": "Repeat"},
        )
    )
    asyncio.run(server.call_tool("recipes.history", {"recipe_id": recipe["id"]}))

    assert {tool.name for tool in tools} == {
        "recipes.link",
        "recipes.search",
        "recipes.get",
        "recipes.log_cook",
        "recipes.history",
    }
    assert recipes.history(recipe_settings, recipe["id"])[0]["conclusion"] == "Repeat"


def test_recipe_dashboard_is_read_only(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings, plugins=(recipes.PLUGIN,))

    with TestClient(app, base_url=settings.public_origin) as client:
        client.post(
            "/login",
            data={"token": settings.dashboard_token},
            headers={"Origin": settings.public_origin},
        )
        recipe = recipes.link_recipe(settings, "Best pasta", "notes://example/best-pasta")
        recipes.log_cook(settings, recipe["id"], rating=5, conclusion="Keep it")
        unavailable = client.post(
            "/recipes",
            data={"name": "Dashboard recipe", "note_reference": "notes://example"},
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )
        page = client.get("/recipes")

    assert unavailable.status_code in {404, 405}
    assert "Best pasta" in page.text
    assert "Keep it" in page.text
    assert page.text.count("<form") == 1
    assert recipes.get_recipe(settings, recipe["id"])["cook_logs"][0]["rating"] == 5


def test_recipe_launcher_summary_counts_cooks(recipe_settings: Settings) -> None:
    recipe = recipes.link_recipe(recipe_settings, "Stew", "notes://example/stew")
    recipes.log_cook(recipe_settings, recipe["id"], rating=4)
    for _ in range(100):
        recipes.log_cook(recipe_settings, recipe["id"], rating=4)

    assert recipes.launcher_summary(recipe_settings) == "101 cooks"


def test_removed_recipe_post_route_does_not_accept_input(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings, plugins=(recipes.PLUGIN,))

    with TestClient(app, base_url=settings.public_origin) as client:
        client.post(
            "/login",
            data={"token": settings.dashboard_token},
            headers={"Origin": settings.public_origin},
        )
        response = client.post(
            "/recipes",
            data={"name": "Dish", "note_reference": "   "},
            headers={"Origin": settings.public_origin},
        )

    assert response.status_code in {404, 405}
