"""Supported dashboard metrics and their deliberately small display vocabulary."""

from __future__ import annotations


def _metric(
    key: str,
    label: str,
    precision: int,
    view: str,
    presentation: str,
    enabled: bool = True,
) -> dict:
    return {
        "key": key,
        "enabled": enabled,
        "label": label,
        "precision": precision,
        "view": view,
        "presentation": presentation,
    }


DEFAULT_CONFIG = {
    "schema_version": 3,
    "plugins": {
        "health": {
            "metrics": [
                _metric("body_weight_kg", "Body weight", 1, "daily_latest", "line"),
                _metric("body_fat_percentage", "Body fat", 1, "daily_latest", "line"),
                _metric("lean_body_mass_kg", "Lean mass", 1, "daily_latest", "line"),
                _metric("sleep_hours", "Sleep", 1, "daily_total", "line"),
                _metric("resting_heart_rate", "Resting heart rate", 0, "daily_latest", "line"),
                _metric("heart_rate_recovery", "Heart rate recovery", 0, "daily_latest", "line"),
                _metric("workouts_completed", "Workouts", 0, "daily_total", "line"),
                _metric("vo2_max", "VO₂ max", 1, "daily_latest", "line", False),
            ]
        },
        "food": {
            "metrics": [
                _metric("confirmed_calories", "Confirmed calories", 0, "daily_total", "bar"),
                _metric("average_calories", "Daily avg", 0, "period_average", "value"),
                _metric("average_protein", "Protein avg", 1, "period_average", "value"),
                _metric("confirmed_count", "Confirmed", 0, "period_total", "value"),
                _metric("unresolved_count", "Unresolved", 0, "period_total", "value"),
            ]
        },
        "coffee": {
            "metrics": [
                _metric("open_bag_count", "Open bags", 0, "latest", "value"),
                _metric("brew_count", "Brews", 0, "period_total", "value"),
                _metric("average_rating", "Avg rating", 1, "period_average", "value"),
                _metric("latest_rating", "Latest", 0, "latest", "value"),
            ]
        },
        "recipes": {
            "metrics": [
                _metric("recipe_count", "Linked", 0, "latest", "value"),
                _metric("cook_count", "Cooks", 0, "period_total", "value"),
                _metric("average_rating", "Avg rating", 1, "period_average", "value"),
                _metric("latest_rating", "Latest", 0, "latest", "value"),
                _metric("cook_rating", "Cook ratings", 0, "daily_latest", "line"),
            ]
        },
        "goals": {
            "linked_roles": ["supporting_indicator", "supplemental_indicator"],
            "goal_presentations": {},
            "metrics": [
                _metric("body_weight_kg", "Body weight", 1, "daily_latest", "line"),
                _metric("body_fat_percentage", "Body fat", 1, "daily_latest", "line"),
                _metric("lean_body_mass_kg", "Lean mass", 1, "daily_latest", "line"),
                _metric("calorie_target_adherence", "Calories", 0, "daily_with_rolling_7d", "line"),
                _metric("workouts_completed", "Workouts", 0, "daily_total", "line"),
                _metric("resting_heart_rate", "Resting heart rate", 0, "daily_latest", "line"),
                _metric("heart_rate_recovery", "Heart rate recovery", 0, "daily_latest", "line"),
                _metric("sleep_hours", "Sleep", 1, "daily_total", "line"),
                _metric("vo2_max", "VO₂ max", 1, "daily_latest", "line", False),
            ],
        },
    },
}

SERIES_METRICS = {
    "health": {item["key"] for item in DEFAULT_CONFIG["plugins"]["health"]["metrics"]},
    "food": {"confirmed_calories"},
    "coffee": set(),
    "recipes": {"cook_rating"},
    "goals": {item["key"] for item in DEFAULT_CONFIG["plugins"]["goals"]["metrics"]},
}


def _catalogue() -> dict:
    result = {}
    for plugin, values in DEFAULT_CONFIG["plugins"].items():
        result[plugin] = {
            item["key"]: {
                "views": [item["view"]],
                "presentations": ["value", "line", "bar"]
                if item["key"] in SERIES_METRICS[plugin]
                else ["value"],
            }
            for item in values["metrics"]
        }
    result["goals"]["calorie_target_adherence"]["views"] = [
        "daily_total",
        "daily_with_rolling_7d",
    ]
    return result


CATALOGUE = _catalogue()
