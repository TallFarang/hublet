from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.dashboard import goal_dashboard
from app.main import create_app
from app.plugins import goals
from tests.test_auth import login


def definition(goal_id: str, title: str, status: str, order: int, *, target=True) -> dict:
    return {
        "goal_id": goal_id,
        "domain": "health" if order < 20 else "social",
        "display_order": order,
        "title": title,
        "outcome": f"Complete {title.lower()}",
        "status": status,
        "target": (
            {"metric": "outcome_value", "value": 10, "unit": "points", "direction": "at_or_above"}
            if target
            else None
        ),
        "evidence_sources": [
            {
                "metric": "supporting_value",
                "cadence": "weekly",
                "source": "Example source",
                "tracking_status": "connected",
                "role": "supporting_indicator",
            }
        ],
    }


def test_dashboard_graphs_only_active_goals_and_only_their_primary_metric(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings, plugins=(goals.PLUGIN,))
    with TestClient(app, base_url=settings.public_origin) as client:
        login(client, settings)
        goals.create_goal(settings, **definition("active_primary", "Primary goal", "active", 10))
        goals.create_goal(
            settings,
            **definition(
                "active_without_target", "Tracking context", "active", 20, target=False
            ),
        )
        goals.create_goal(settings, **definition("completed", "Completed goal", "completed", 30))
        goals.create_goal(settings, **definition("archived", "Archived goal", "archived", 40))
        goals.record_evidence(
            settings,
            "active_primary",
            "outcome_value",
            8,
            "Example source",
            "primary-reading",
            unit="points",
            observed_at="2026-08-18T08:00:00Z",
        )
        goals.record_evidence(
            settings,
            "active_primary",
            "supporting_value",
            99,
            "Example source",
            "supporting-reading",
            observed_at="2026-08-18T08:00:00Z",
        )
        response = client.get("/goals")

    instrument, management = response.text.split('id="manage"', 1)
    assert instrument.count('class="goal-readout"') == 2
    assert instrument.count('class="line-chart"') == 1
    assert instrument.index("Primary goal") < instrument.index("Tracking context")
    assert "Completed goal" not in instrument and "Archived goal" not in instrument
    assert "Completed goal" in management and "Archived goal" in management
    assert "99" not in instrument
    assert goals.launcher_summary(settings) == "2 goals"


def test_supporting_evidence_never_becomes_an_implicit_primary_graph() -> None:
    projected = goal_dashboard(
        {
            "target": None,
            "evidence_sources": [{"metric": "supporting_value"}],
            "history": [{"metric": "supporting_value", "value": 12, "unit": "points"}],
        }
    )

    assert projected["metric"] == "No metric"
    assert projected["has_series"] is False
