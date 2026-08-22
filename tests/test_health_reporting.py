from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from mcp.server import MCPServer

from app.config import Settings
from app.main import create_app
from app.plugins import goals, health
from app.plugins.health_goals import update_healthkit_sources
from app.plugins.health_query import sync_status
from app.plugins.health_report import summary
from app.plugins.health_sync import sync_agentbridge
from app.runtime import migrate_plugins
from tests.health_fixtures import export_date, quantity, section, write_export
from tests.test_auth import login


def mapped_sections(day: str) -> list[dict]:
    return [
        section(
            "HKQuantityTypeIdentifierVO2Max",
            "quantity",
            [quantity(f"vo2-{day}", 41.2, "ml/(kg*min)", day)],
        ),
        section("HKQuantityTypeIdentifierBodyMass", "quantity", []),
        section(
            "HKQuantityTypeIdentifierRestingHeartRate",
            "quantity",
            [quantity(f"heart-{day}", 58, "count/min", day)],
        ),
        section(
            "HKWorkoutTypeIdentifier",
            "workout",
            [{"uuid": f"workout-{day}", "durationSeconds": 1200, "activityType": 9}],
        ),
    ]


def prepared_settings(settings_env: dict[str, str]) -> tuple[Settings, str]:
    settings = Settings.from_env(settings_env)
    settings.agentbridge_dir.mkdir()
    migrate_plugins(settings, (goals.PLUGIN, health.PLUGIN))
    day = export_date()
    write_export(settings.agentbridge_dir, day, mapped_sections(day))
    return settings, day


def test_summary_separates_no_measurement_and_missing_export(settings_env: dict[str, str]) -> None:
    settings, latest = prepared_settings(settings_env)
    earlier = export_date(3)
    write_export(settings.agentbridge_dir, earlier, mapped_sections(earlier))
    sync_agentbridge(settings)

    report = summary(settings, earlier, latest)
    status = sync_status(settings)

    assert report["coverage"]["missing_dates"] == [export_date(2)]
    assert report["metrics"]["body_weight_kg"]["no_measurement_dates"] == [earlier, latest]
    assert report["metrics"]["vo2_max"]["latest"]["value"] == 41.2
    assert report["metrics"]["workouts_completed"]["latest"]["value"] == 1
    assert status["freshness"] == "stale"
    assert status["missing_dates"] == [export_date(2)]
    assert not any(item["metric"] == "workouts_completed" for item in report["evidence"])


def test_health_updates_goal_source_and_supplies_idempotent_evidence(
    settings_env: dict[str, str],
) -> None:
    settings, day = prepared_settings(settings_env)
    goals.create_goal(
        settings,
        "fitness",
        "health",
        "Improve fitness",
        status="awaiting_automated_data",
        target={"metric": "vo2_max", "value": 45, "unit": "ml/(kg*min)"},
        evidence_sources=[
            {
                "metric": "vo2_max",
                "cadence": "weekly",
                "source": "HealthKit",
                "tracking_status": "unspecified",
                "role": "outcome",
            }
        ],
    )
    sync_agentbridge(settings)
    definition = goals.get_goal(settings, "fitness")
    report = summary(settings, day, day)
    evidence = next(item for item in report["evidence"] if item["metric"] == "vo2_max")

    assert definition["status"] == "active"
    assert definition["evidence_sources"][0]["tracking_status"] == "connected"
    assert definition["evidence_sources"][0]["details"]["transport"] == (
        "Agentbridge via Hublet Health"
    )
    first = goals.record_evidence(settings, "fitness", **evidence)
    second = goals.record_evidence(settings, "fitness", **evidence)
    assert first["created"] is True and second["created"] is False
    assert goals.report_snapshot(settings, day, day)["domains"][0]["goals"][0]["evidence"][0]["gap"] is None

    update_healthkit_sources(settings, "stale")
    empty = goals.create_goal(
        settings,
        "fitness_gap",
        "health",
        "Track fitness",
        evidence_sources=[
            {
                "metric": "vo2_max",
                "cadence": "weekly",
                "source": "HealthKit",
                "tracking_status": "stale",
            }
        ],
    )
    assert empty["id"] == "fitness_gap"
    snapshot = goals.report_snapshot(settings, day, day)
    gap_goal = next(item for item in snapshot["domains"][0]["goals"] if item["definition"]["id"] == "fitness_gap")
    assert gap_goal["evidence"][0]["gap"] == "source_stale"


def test_health_mcp_contract_and_private_dashboard(settings_env: dict[str, str]) -> None:
    settings, _day = prepared_settings(settings_env)
    server = MCPServer("test")
    health.register_mcp(server, settings)
    tools = asyncio.run(server.list_tools())
    schemas = {tool.name: tool.input_schema for tool in tools}

    assert set(schemas) == {
        "health_sync_agentbridge",
        "health_query_records",
        "health_summary",
        "health_sync_status",
        "health_list_types",
    }
    query = schemas["health_query_records"]["properties"]
    assert query["limit"]["maximum"] == 200
    assert "path" not in query and "directory" not in query

    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/health", follow_redirects=False).status_code == 303
        login(client, settings)
        page = client.get("/health")
    assert page.status_code == 200
    assert "HealthKit" not in page.text and "Agentbridge" not in page.text
    assert 'class="period-toggle"' in page.text
    assert page.text.count("<form") == 1 and "<script" not in page.text
