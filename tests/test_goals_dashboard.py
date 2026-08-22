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
        "domain": "health" if order < 20 else "career" if order < 30 else "social",
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
        goals.create_goal(settings, **definition("active_social", "Social goal", "active", 30))
        goals.create_goal(settings, **definition("completed", "Completed goal", "completed", 31))
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

    page = response.text
    assert page.count('class="goal-readout"') == 3
    assert page.count('class="instrument-panel goal-domain"') == 3
    assert page.count('class="line-chart"') == 2
    assert page.index("Primary goal") < page.index("Tracking context")
    assert page.index("Health") < page.index("Career") < page.index("Social")
    assert "Completed goal" not in page and "Archived goal" not in page
    assert 'class="dashboard-details"' not in page
    assert "99" in page
    assert "18/08" in page
    assert 'class="chart-target-label"' in page and ">10 points<" in page
    assert "≥ 10 points" not in page
    assert goals.launcher_summary(settings) == "3 goals"


def test_supporting_evidence_never_becomes_an_implicit_primary_graph() -> None:
    projected = goal_dashboard(
        {
            "target": None,
            "evidence_sources": [{"metric": "supporting_value"}],
            "history": [{"metric": "supporting_value", "value": 12, "unit": "points"}],
        }
    )

    assert "metric" not in projected
    assert projected["has_series"] is False


def test_dashboard_projects_every_numeric_supporting_series_without_text() -> None:
    projected = goal_dashboard(
        {
            "target": {
                "metric": "weight",
                "value": 90,
                "unit": "kg",
                "direction": "at_or_below",
            },
            "evidence_sources": [
                {
                    "metric": metric,
                    "source": "Example",
                    "role": "supporting_indicator",
                }
                for metric in ("workouts_completed", "sleep_hours", "on_plan")
            ],
            "history": [
                {"metric": "weight", "source": "Example", "value": 93, "unit": "kg"},
                {
                    "metric": "workouts_completed",
                    "source": "Example",
                    "value": 3,
                    "unit": "workouts",
                },
                {"metric": "sleep_hours", "source": "Example", "value": 7.5, "unit": "h"},
                {"metric": "on_plan", "source": "Example", "value": True, "unit": None},
            ],
        }
    )

    assert projected["target_line_label"] == "90 kg"
    assert projected["target_y_percent"] is not None
    assert [chart["label"] for chart in projected["tracking"]] == [
        "Workouts",
        "Sleep hours",
    ]
    assert all("source" not in chart for chart in projected["tracking"])
