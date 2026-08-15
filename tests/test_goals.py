from __future__ import annotations

import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient
from mcp.server import MCPServer

from app.config import Settings
from app.db import migrate
from app.main import create_app
from app.plugins import PLUGINS, goals


@pytest.fixture
def goal_settings(settings_env: dict[str, str]) -> Settings:
    settings = Settings.from_env(settings_env)
    migrate(settings.data_dir / goals.DB_FILENAME, goals.MIGRATIONS)
    return settings


def test_goal_plugin_adds_one_explicit_registration() -> None:
    assert PLUGINS[1] is goals.PLUGIN


def test_goal_schema_is_only_goals_and_entries(goal_settings: Settings) -> None:
    with sqlite3.connect(goal_settings.data_dir / goals.DB_FILENAME) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    assert tables == {"goals", "entries"}


def test_latest_progress_is_absolute_not_a_sum(goal_settings: Settings) -> None:
    goal = goals.create_goal(
        goal_settings,
        "Run comfortably",
        description="Build distance",
        target_value=10,
        unit="km",
        target_date="2026-12-01",
    )
    goals.log_progress(goal_settings, goal["id"], 5, "First check")
    latest = goals.log_progress(goal_settings, goal["id"], 7, "Second check")

    saved = goals.get_goal(goal_settings, goal["id"])

    assert saved["current_value"] == 7.0
    assert saved["current_entry_at"] == latest["created_at"]
    assert [entry["value"] for entry in saved["entries"]] == [7.0, 5.0]
    assert goals.list_goals(goal_settings)[0]["current_value"] == 7.0


def test_goal_update_and_non_destructive_status(goal_settings: Settings) -> None:
    goal = goals.create_goal(goal_settings, "Draft")

    updated = goals.update_goal(
        goal_settings,
        goal["id"],
        title="Ship it",
        description="Small and useful",
        target_value=1,
        unit="release",
        target_date="2026-09-01",
    )
    completed = goals.set_status(goal_settings, goal["id"], "completed")
    cleared = goals.update_goal(goal_settings, goal["id"], clear_target=True)

    assert updated["title"] == "Ship it"
    assert completed["status"] == "completed"
    assert cleared["target_value"] is None
    assert goals.list_goals(goal_settings) == []
    assert goals.list_goals(goal_settings, status=None)[0]["id"] == goal["id"]


def test_goal_domain_rejects_invalid_input(goal_settings: Settings) -> None:
    with pytest.raises(ValueError, match="title"):
        goals.create_goal(goal_settings, " ")
    with pytest.raises(ValueError, match="Goal not found"):
        goals.log_progress(goal_settings, "missing", 2)
    goal = goals.create_goal(goal_settings, "Valid")
    with pytest.raises(ValueError, match="status"):
        goals.set_status(goal_settings, goal["id"], "deleted")


def test_goal_mcp_tools_use_domain(goal_settings: Settings) -> None:
    server = MCPServer("test")
    goals.register_mcp(server, goal_settings)

    tools = asyncio.run(server.list_tools())
    asyncio.run(
        server.call_tool(
            "goals.create",
            {"title": "MCP goal", "target_value": 12, "unit": "books"},
        )
    )
    goal = goals.list_goals(goal_settings)[0]
    asyncio.run(
        server.call_tool(
            "goals.log_progress",
            {"goal_id": goal["id"], "value": 3, "note": "Started"},
        )
    )
    asyncio.run(server.call_tool("goals.get", {"goal_id": goal["id"]}))

    assert {tool.name for tool in tools} == {
        "goals.create",
        "goals.list",
        "goals.get",
        "goals.log_progress",
        "goals.update",
        "goals.status",
    }
    assert goals.get_goal(goal_settings, goal["id"])["current_value"] == 3


def test_goal_html_forms_create_edit_progress_and_complete(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings, plugins=(goals.PLUGIN,))

    with TestClient(app, base_url=settings.public_origin) as client:
        client.post(
            "/login",
            data={"token": settings.dashboard_token},
            headers={"Origin": settings.public_origin},
        )
        created = client.post(
            "/goals",
            data={"title": "Read more", "target_value": "12", "unit": "books"},
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )
        goal = goals.list_goals(settings)[0]
        edited = client.post(
            f"/goals/{goal['id']}/edit",
            data={"title": "Read thoughtfully", "description": "Take notes"},
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )
        progress = client.post(
            f"/goals/{goal['id']}/progress",
            data={"value": "4", "note": "August"},
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )
        completed = client.post(
            f"/goals/{goal['id']}/status",
            data={"status": "completed"},
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )

    assert {created.status_code, edited.status_code, progress.status_code, completed.status_code} == {
        303
    }
    saved = goals.get_goal(settings, goal["id"])
    assert (saved["title"], saved["current_value"], saved["status"]) == (
        "Read thoughtfully",
        4.0,
        "completed",
    )
    assert saved["target_value"] is None


def test_goal_invalid_html_returns_422(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings, plugins=(goals.PLUGIN,))

    with TestClient(app, base_url=settings.public_origin) as client:
        client.post(
            "/login",
            data={"token": settings.dashboard_token},
            headers={"Origin": settings.public_origin},
        )
        response = client.post(
            "/goals",
            data={"title": "   "},
            headers={"Origin": settings.public_origin},
        )

    assert response.status_code == 422
    assert "title is required" in response.text
    assert 'role="alert"' in response.text


def test_goal_launcher_summary_counts_active(goal_settings: Settings) -> None:
    goals.create_goal(goal_settings, "One")
    done = goals.create_goal(goal_settings, "Two")
    goals.set_status(goal_settings, done["id"], "completed")

    assert goals.launcher_summary(goal_settings) == "1 active goal"
