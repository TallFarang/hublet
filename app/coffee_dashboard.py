"""Coffee dashboard projection focused on repeatable recipes."""

from __future__ import annotations

from typing import Any

from app.dashboard_catalogue import DEFAULT_CONFIG
from app.dashboard_metrics import configured_readings


def coffee_dashboard(
    brews: list[dict[str, Any]], bag_count: int, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    config = config or DEFAULT_CONFIG["plugins"]["coffee"]
    ratings = [brew["rating"] for brew in brews if brew["rating"] is not None]
    latest_rating = brews[0]["rating"] if brews else None
    average_rating = sum(ratings) / len(ratings) if ratings else None
    result = {
        "bag_count": bag_count,
        "brew_count": len(brews),
        "average_rating": round(average_rating, 1) if average_rating is not None else None,
        "latest_rating": latest_rating,
        "brews": [_brew(brew) for brew in brews[:8]],
    }
    result["readings"] = configured_readings(
        config,
        {
            "open_bag_count": {"value": bag_count},
            "brew_count": {"value": len(brews)},
            "average_rating": {"value": average_rating, "suffix": "/5"},
            "latest_rating": {"value": latest_rating, "suffix": "/5"},
        },
    )
    return result


def _brew(brew: dict[str, Any]) -> dict[str, Any]:
    method = {
        "v60": "V60",
        "aeropress": "AeroPress",
        "french_press": "French press",
        "espresso": "Espresso",
    }[brew["method"]]
    target = brew["yield_g"] if brew["method"] == "espresso" else brew["water_g"]
    separator = "→" if brew["method"] == "espresso" else "/"
    recipe = [
        f"{_number(brew['dose_g'])}g {separator} {_number(target)}g",
        f"grind {brew['grind_setting']}",
    ]
    for value, suffix in (
        (brew["time_s"], "s"),
        (brew["temperature_c"], "°C"),
        (brew["bypass_water_g"], "g bypass"),
    ):
        if value is not None:
            prefix = "+" if suffix == "g bypass" else ""
            recipe.append(f"{prefix}{_number(value)}{suffix}")
    outcome = ([f"{brew['rating']}/5"] if brew["rating"] is not None else []) + (
        [brew["taste_notes"]] if brew["taste_notes"] else []
    )
    return {
        "method": method,
        "bag_name": brew["bag"]["name"],
        "roaster": brew["bag"]["roaster"],
        "created_at": brew["created_at"],
        "recipe": " · ".join(recipe),
        "outcome": " · ".join(outcome),
        "notes": brew["notes"],
    }


def _number(value: float) -> str:
    return f"{value:g}"
