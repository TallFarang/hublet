from __future__ import annotations

from copy import deepcopy

from app.config import Settings
from app.dashboard_config import DEFAULT_CONFIG
from app.goals_dashboard import goal_dashboard, live_tracking_series
from app.plugins import food
from app.runtime import migrate_plugins


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
