from __future__ import annotations

from copy import deepcopy

from app.config import Settings
from app.dashboard_config import DEFAULT_CONFIG
from app.goals_dashboard import goal_dashboard
from app.plugins import food
from app.plugins.goals_live import live_tracking_series
from app.runtime import migrate_plugins


def test_goal_primary_chart_uses_its_explicit_live_outcome_source() -> None:
    goal = {
        "target": {"metric": "body_weight_kg", "value": 90, "unit": "kg"},
        "history": [
            {
                "metric": "body_weight_kg",
                "source": "Manual",
                "value": 95,
                "unit": "kg",
                "observed_at": "2026-08-10",
            }
        ],
        "evidence_sources": [
            {"metric": "body_weight_kg", "source": "HealthKit", "role": "outcome"}
        ],
    }
    live = {
        ("body_weight_kg", "HealthKit"): {
            "label": "Body weight",
            "unit": "kg",
            "series": [
                {"date": "2026-08-11", "value": 93.4},
                {"date": "2026-08-16", "value": 92.6},
            ],
            "precision": 1,
        }
    }

    projected = goal_dashboard(goal, live)

    assert projected["latest"] == "92.6" and projected["unit"] == "kg"
    assert projected["has_series"] is True and len(projected["points"].split()) == 2
    assert projected["start_label"] == {"date": "2026-08-11", "value": "93.4 kg"}
    assert projected["end_label"] == {"date": "2026-08-16", "value": "92.6 kg"}

    wrong_source = {**goal, "evidence_sources": [{**goal["evidence_sources"][0], "source": "Other"}]}
    wrong_role = {
        **goal,
        "evidence_sources": [{**goal["evidence_sources"][0], "role": "supporting_indicator"}],
    }
    assert goal_dashboard(wrong_source, live)["latest"] == "95.0"
    assert goal_dashboard(wrong_role, live)["latest"] == "95.0"


def test_goal_calories_show_daily_context_and_trailing_average(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    migrate_plugins(settings, (food.PLUGIN,))
    food.upsert_nutrition(
        settings,
        "meal",
        "Kitchen",
        "Meal",
        700,
        30,
        70,
        20,
        "one meal",
        "menu",
        "high",
        "fact",
    )
    food.record_consumption(
        settings,
        "last-day",
        "2026-08-16",
        "dinner",
        restaurant="Kitchen",
        item="Meal",
        nutrition_id="meal",
    )

    live = live_tracking_series(settings, "2026-08-10", "2026-08-16")
    calories = live[("calorie_target_adherence", "Hublet Food")]
    assert [point["value"] for point in calories["context_series"]] == [0, 0, 0, 0, 0, 0, 700]
    assert calories["series"][-1]["value"] == 100

    projected = goal_dashboard(
        {
            "target": None,
            "history": [],
            "evidence_sources": [
                {
                    "metric": "calorie_target_adherence",
                    "source": "Hublet Food",
                    "role": "supplemental_indicator",
                }
            ],
        },
        live,
    )
    chart = projected["tracking"][0]
    assert chart["label"] == "Calories" and chart["latest"] == "100"
    assert chart["points"] and chart["context_points"]

    config = deepcopy(DEFAULT_CONFIG["plugins"]["goals"])
    calories_config = next(
        metric for metric in config["metrics"] if metric["key"] == "calorie_target_adherence"
    )
    calories_config["view"] = "daily_total"
    daily = live_tracking_series(settings, "2026-08-10", "2026-08-16", config)[
        ("calorie_target_adherence", "Hublet Food")
    ]
    assert daily["series"][-1]["value"] == 700 and daily["context_series"] == []
