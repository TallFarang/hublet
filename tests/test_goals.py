from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime

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


def example_definition(**changes):
    definition = {
        "goal_id": "reach_example",
        "domain": "health",
        "display_order": 20,
        "title": "Example target",
        "outcome": "Reach the example target",
        "description": "A complete structured goal.",
        "horizon": "short_term",
        "status": "active",
        "target": {
            "metric": "example_metric",
            "value": 90,
            "unit": "kg",
            "direction": "at_or_below",
            "required_duration": {"count": 3, "unit": "months", "consecutive": True},
            "qualifiers": {"basis": "rolling_average"},
        },
        "systems": ["Use the automatic source."],
        "dependencies": ["prepare_example"],
        "evidence_sources": [
            {
                "metric": "example_metric",
                "cadence": "weekly",
                "source": "Example source",
                "tracking_status": "connected",
                "role": "outcome",
                "access_notes": "Read only",
            }
        ],
        "notes": ["This is a note."],
    }
    definition.update(changes)
    return definition


def test_goal_plugin_adds_one_explicit_registration() -> None:
    assert PLUGINS[0] is goals.PLUGIN


def test_goal_schema_is_three_tables_with_fixed_domain_order(goal_settings: Settings) -> None:
    with sqlite3.connect(goal_settings.data_dir / goals.DB_FILENAME) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    assert tables == {"domains", "goals", "observations"}
    assert [(item["id"], item["display_order"]) for item in goals.list_domains(goal_settings)] == [
        ("health", 10),
        ("career", 20),
        ("social", 30),
    ]


def test_schema_replacement_refuses_nonempty_legacy_database(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    database = settings.data_dir / goals.DB_FILENAME
    migrate(database, goals.MIGRATIONS[:1])
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO goals
               (id, title, status, created_at, updated_at)
               VALUES ('legacy', 'Keep me', 'active', 'now', 'now')"""
        )

    with pytest.raises(sqlite3.IntegrityError):
        migrate(database, goals.MIGRATIONS)


def test_title_migration_backfills_existing_outcomes(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    database = settings.data_dir / goals.DB_FILENAME
    migrate(database, goals.MIGRATIONS[:2])
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO goals
               (id, domain_id, display_order, outcome, status, created_at, updated_at)
               VALUES ('existing', 'health', 10, 'Existing outcome', 'active', 'now', 'now')"""
        )

    migrate(database, goals.MIGRATIONS)

    assert goals.get_goal(settings, "existing")["title"] == "Existing outcome"


def test_create_get_list_and_registry_round_trip(goal_settings: Settings) -> None:
    goals.create_goal(goal_settings, **example_definition(goal_id="prepare_example", display_order=10))
    created = goals.create_goal(goal_settings, **example_definition())

    fetched = goals.get_goal(goal_settings, created["id"])
    listed = goals.list_goals(goal_settings, domain="health", status="active")
    registry = goals.get_registry(goal_settings)

    assert fetched["id"] == "reach_example"
    assert fetched["title"] == "Example target"
    assert fetched["target"]["required_duration"] == {
        "count": 3,
        "unit": "months",
        "consecutive": True,
    }
    assert fetched["systems"] == ["Use the automatic source."]
    assert fetched["evidence_sources"][0]["tracking_status"] == "connected"
    assert [item["id"] for item in listed] == ["prepare_example", "reach_example"]
    assert [domain["id"] for domain in registry["domains"]] == ["health", "career", "social"]
    assert [item["id"] for item in registry["domains"][0]["goals"]] == [
        "prepare_example",
        "reach_example",
    ]


def test_targets_support_numeric_categorical_trend_and_duration(goal_settings: Settings) -> None:
    targets = {
        "numeric": {"metric": "weight", "value": 90, "direction": "at_or_below"},
        "categorical": {"metric": "employment", "value": "self_employed"},
        "trend": {"metric": "outbound", "direction": "increasing_trend"},
        "duration": {
            "metric": "income",
            "value": 100000,
            "unit": "THB/month",
            "direction": "at_or_above",
            "required_duration": {"count": 3, "unit": "months", "consecutive": True},
        },
    }
    for order, (goal_id, target) in enumerate(targets.items()):
        goals.create_goal(
            goal_settings,
            **example_definition(goal_id=goal_id, display_order=order, target=target),
        )

    saved = {item["id"]: item["target"] for item in goals.list_goals(goal_settings)}

    assert saved["numeric"]["value"] == 90
    assert saved["categorical"]["direction"] == "equals"
    assert saved["trend"] == {
        "metric": "outbound",
        "value": None,
        "unit": None,
        "direction": "increasing_trend",
        "required_duration": None,
        "qualifiers": {},
    }
    assert saved["duration"]["required_duration"]["consecutive"] is True


def test_goal_update_status_and_validation(goal_settings: Settings) -> None:
    goals.create_goal(goal_settings, **example_definition(dependencies=[]))
    updated = goals.update_goal(
        goal_settings,
        "reach_example",
        **{
            key: value
            for key, value in example_definition(
                domain="career",
                title="Updated title",
                outcome="Updated outcome",
                status="awaiting_automatic_data",
                systems=[],
                dependencies=[],
            ).items()
            if key != "goal_id"
        },
    )
    completed = goals.set_status(goal_settings, "reach_example", "completed")

    assert updated["domain"] == "career"
    assert updated["title"] == "Updated title"
    assert updated["outcome"] == "Updated outcome"
    assert completed["status"] == "completed"
    with pytest.raises(ValueError, match="domain"):
        goals.create_goal(goal_settings, **example_definition(goal_id="bad", domain="unknown"))
    with pytest.raises(ValueError, match="outcome"):
        goals.create_goal(goal_settings, **example_definition(goal_id="blank", outcome=" "))
    with pytest.raises(ValueError, match="direction"):
        goals.create_goal(
            goal_settings,
            **example_definition(goal_id="bad_target", target={"metric": "x", "direction": "up"}),
        )


@pytest.mark.parametrize("value", [42.5, "steady", True])
def test_evidence_values_are_typed_absolute_and_idempotent(
    goal_settings: Settings, value: float | str | bool
) -> None:
    goals.create_goal(goal_settings, **example_definition(dependencies=[]))
    arguments = {
        "goal_id": "reach_example",
        "metric": "example_metric",
        "value": value,
        "unit": "score",
        "source": "Example source",
        "reference": "record:123",
        "observed_at": "2026-08-14T09:00:00+07:00",
        "note": "Absolute reading",
        "idempotency_key": f"reading-{type(value).__name__}",
    }

    first = goals.record_evidence(goal_settings, **arguments)
    repeated = goals.record_evidence(goal_settings, **arguments)

    assert first["created"] is True
    assert repeated["created"] is False
    assert repeated["observation"]["id"] == first["observation"]["id"]
    assert repeated["observation"]["value"] == value
    assert repeated["observation"]["observed_at"] == "2026-08-14T02:00:00+00:00"
    assert len(goals.query_evidence(goal_settings, goal_id="reach_example")) == 1


def test_idempotency_conflicts_and_observation_mutation_are_rejected(
    goal_settings: Settings,
) -> None:
    goals.create_goal(goal_settings, **example_definition(dependencies=[]))
    result = goals.record_evidence(
        goal_settings,
        goal_id="reach_example",
        metric="example_metric",
        value=1,
        source="Example source",
        observed_at="2026-08-14T00:00:00Z",
        idempotency_key="one-reading",
    )

    with pytest.raises(ValueError, match="different observation"):
        goals.record_evidence(
            goal_settings,
            goal_id="reach_example",
            metric="example_metric",
            value=2,
            source="Example source",
            observed_at=datetime.now(UTC).isoformat(),
            idempotency_key="one-reading",
        )
    with pytest.raises(ValueError, match="different observation"):
        goals.record_evidence(
            goal_settings,
            goal_id="reach_example",
            metric="example_metric",
            value=True,
            source="Example source",
            observed_at="2026-08-14T00:00:00Z",
            idempotency_key="one-reading",
        )
    with sqlite3.connect(goal_settings.data_dir / goals.DB_FILENAME) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE observations SET note = 'changed' WHERE id = ?",
                (result["observation"]["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM observations WHERE id = ?", (result["observation"]["id"],)
            )


def test_latest_observations_are_not_truncated_with_history(
    goal_settings: Settings,
) -> None:
    goals.create_goal(goal_settings, **example_definition(dependencies=[]))
    for source, observed_at, key in (
        ("Quiet source", "2026-08-01T00:00:00Z", "quiet"),
        ("Busy source", "2026-08-02T00:00:00Z", "busy-1"),
        ("Busy source", "2026-08-03T00:00:00Z", "busy-2"),
    ):
        goals.record_evidence(
            goal_settings,
            goal_id="reach_example",
            metric="example_metric",
            value=1,
            source=source,
            observed_at=observed_at,
            idempotency_key=key,
        )

    saved = goals.get_goal(goal_settings, "reach_example", history_limit=1)

    assert len(saved["history"]) == 1
    assert {item["source"] for item in saved["latest_observations"]} == {
        "Busy source",
        "Quiet source",
    }


def test_evidence_query_supports_periods_filters_and_history(goal_settings: Settings) -> None:
    goals.create_goal(goal_settings, **example_definition(dependencies=[]))
    goals.record_evidence(
        goal_settings,
        goal_id="reach_example",
        metric="example_metric",
        value="earlier",
        source="Example source",
        observed_at="2026-08-09T23:00:00Z",
        idempotency_key="earlier",
    )
    goals.record_evidence(
        goal_settings,
        goal_id="reach_example",
        metric="example_metric",
        value="weekly",
        source="Example source",
        period_start="2026-08-10",
        period_end="2026-08-16",
        idempotency_key="weekly",
    )
    goals.record_evidence(
        goal_settings,
        goal_id="reach_example",
        metric="supporting",
        value=False,
        source="Other source",
        observed_at="2026-08-12T12:00:00Z",
        idempotency_key="supporting",
    )

    queried = goals.query_evidence(
        goal_settings,
        goal_id="reach_example",
        metric="example_metric",
        source="Example source",
        start_date="2026-08-10",
        end_date="2026-08-16",
    )
    fetched = goals.get_goal(goal_settings, "reach_example", history_limit=2)

    assert [item["value"] for item in queried] == ["weekly"]
    assert len(fetched["history"]) == 2
    assert {(item["metric"], item["source"]) for item in fetched["latest_observations"]} == {
        ("example_metric", "Example source"),
        ("supporting", "Other source"),
    }
    with pytest.raises(ValueError, match="timing"):
        goals.record_evidence(
            goal_settings,
            goal_id="reach_example",
            metric="example_metric",
            value=1,
            source="Example source",
            idempotency_key="missing-time",
        )


def test_report_snapshot_returns_prior_values_and_factual_gaps(goal_settings: Settings) -> None:
    sources = [
        {
            "metric": "connected_metric",
            "cadence": "weekly",
            "source": "Connected source",
            "tracking_status": "connected",
            "role": "outcome",
        },
        {
            "metric": "offline_metric",
            "cadence": "monthly",
            "source": "Offline source",
            "tracking_status": "not_connected",
            "role": "supporting_indicator",
        },
    ]
    goals.create_goal(
        goal_settings,
        **example_definition(
            dependencies=[],
            target={"metric": "connected_metric", "direction": "increasing_trend"},
            evidence_sources=sources,
        ),
    )
    goals.record_evidence(
        goal_settings,
        goal_id="reach_example",
        metric="connected_metric",
        value=7,
        source="Connected source",
        observed_at="2026-08-09T12:00:00Z",
        idempotency_key="prior",
    )

    snapshot = goals.report_snapshot(goal_settings, "2026-08-10", "2026-08-16")
    evidence = snapshot["domains"][0]["goals"][0]["evidence"]

    assert evidence[0]["observations"] == []
    assert evidence[0]["latest_before_period"]["value"] == 7
    assert evidence[0]["gap"] == "no_observation_in_period"
    assert evidence[1]["latest_before_period"] is None
    assert evidence[1]["gap"] == "source_unavailable"
    assert "progress" not in snapshot["domains"][0]["goals"][0]


def test_mcp_exposes_only_the_new_goal_contract(goal_settings: Settings) -> None:
    server = MCPServer("test")
    goals.register_mcp(server, goal_settings)

    tools = asyncio.run(server.list_tools())
    schemas = {tool.name: tool.input_schema for tool in tools}

    assert {tool.name for tool in tools} == {
        "goals_registry_get",
        "goals_get",
        "goals_list",
        "goals_create",
        "goals_update",
        "goals_set_status",
        "goals_record_evidence",
        "goals_query_evidence",
        "goals_report_snapshot",
    }
    assert "title" in schemas["goals_create"]["properties"]
    assert "title" in schemas["goals_update"]["required"]


def test_goal_dashboard_groups_definitions_and_shows_evidence_states(
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
        goals.create_goal(
            settings,
            **example_definition(
                dependencies=[],
                evidence_sources=[
                    {
                        "metric": "example_metric",
                        "cadence": "weekly",
                        "source": "Connected source",
                        "tracking_status": "connected",
                        "role": "outcome",
                    },
                    {
                        "metric": "supporting_metric",
                        "cadence": "monthly",
                        "source": "Offline source",
                        "tracking_status": "not_connected",
                        "role": "supporting_indicator",
                    },
                ],
            ),
        )
        goals.record_evidence(
            settings,
            goal_id="reach_example",
            metric="example_metric",
            value=88,
            unit="kg",
            source="Connected source",
            observed_at=datetime.now(UTC).isoformat(),
            idempotency_key="dashboard-reading",
        )

        response = client.get("/goals")

    assert response.status_code == 200
    instrument, definitions = response.text.split('class="dashboard-details"', 1)
    assert "Example target" in instrument
    assert "Reach the example target" not in instrument
    assert all(
        text in definitions
        for text in ["Health", "Career", "Social", "Reach the example target", "88 kg"]
    )
    assert "Source unavailable" not in response.text
    assert "Observation history" not in response.text
    assert "Record evidence" not in response.text
    assert 'action="/goals/reach_example/evidence"' not in response.text


def test_goal_dashboard_post_routes_are_removed(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings, plugins=(goals.PLUGIN,))
    headers = {"Origin": settings.public_origin}
    with TestClient(app, base_url=settings.public_origin) as client:
        client.post("/login", data={"token": settings.dashboard_token}, headers=headers)
        responses = [client.post(
            "/goals",
            data={"domain": "career", "title": "Read", "outcome": "Read more"},
            headers=headers,
            follow_redirects=False,
        )]

    assert all(response.status_code in {404, 405} for response in responses)
    assert goals.list_goals(settings) == []
