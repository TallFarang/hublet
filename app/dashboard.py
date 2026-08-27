"""Small presentation projections for Hublet's server-rendered dashboards."""

from __future__ import annotations

from typing import Any

from app.charts import series_plot
from app.dashboard_config import DEFAULT_CONFIG
from app.dashboard_metrics import axis_dates, configured_readings, display_value, metric_settings


def goal_dashboard(
    goal: dict[str, Any],
    live: dict[tuple[str, str], dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep the established projection import without loading plugin adapters eagerly."""

    from app.goals_dashboard import goal_dashboard as project_goal

    return project_goal(goal, live, config)


def coffee_dashboard(
    shots: list[dict[str, Any]], bean_count: int, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    config = config or DEFAULT_CONFIG["plugins"]["coffee"]
    ordered = [shot for shot in reversed(shots) if shot["dose_g"]]
    ratios = [shot["yield_g"] / shot["dose_g"] for shot in ordered]
    ratings = [shot["rating"] for shot in shots if shot["rating"] is not None]
    latest = shots[0] if shots else None
    latest_ratio = latest["yield_g"] / latest["dose_g"] if latest and latest["dose_g"] else None
    average_rating = sum(ratings) / len(ratings) if ratings else None
    chart = metric_settings(config)["extraction_ratio"]
    result = {
        **series_plot(ratios, chart["presentation"]),
        "has_series": bool(ratios),
        "bean_count": bean_count,
        "shot_count": len(shots),
        "latest_ratio": round(latest_ratio, 2) if latest_ratio is not None else None,
        "latest_time": latest["time_s"] if latest else None,
        "average_rating": round(average_rating, 1) if average_rating is not None else None,
        "start_label": _shot_label(ordered[0], chart["precision"]) if ordered else None,
        "end_label": _shot_label(ordered[-1], chart["precision"]) if ordered else None,
        "axis_labels": axis_dates([{"date": shot["created_at"][:10]} for shot in ordered])
        if chart["presentation"] == "bar"
        else [],
        "current_display": display_value(latest_ratio, chart["precision"], suffix="×"),
    }
    result["readings"] = configured_readings(
        config,
        {
            "bean_count": {"value": bean_count},
            "latest_ratio": {"value": latest_ratio, "prefix": "1:"},
            "latest_time": {"value": result["latest_time"], "suffix": "s"},
            "average_rating": {"value": average_rating, "suffix": "/5"},
        },
    )
    result["has_series"] = result["has_series"] and chart["enabled"]
    result["chart_label"] = chart["label"]
    return result


def recipes_dashboard(
    recipes: list[dict[str, Any]], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    config = config or DEFAULT_CONFIG["plugins"]["recipes"]
    logs = sorted(
        [log for recipe in recipes for log in recipe["cook_logs"]],
        key=lambda log: (log["created_at"], log["id"]),
        reverse=True,
    )
    ordered = list(reversed(logs))
    ratings = [float(log["rating"]) for log in ordered]
    average_rating = sum(ratings) / len(ratings) if ratings else None
    chart = metric_settings(config)["cook_rating"]
    result = {
        **series_plot(ratings, chart["presentation"]),
        "has_series": bool(ratings),
        "recipe_count": len(recipes),
        "cook_count": sum(len(recipe["cook_logs"]) for recipe in recipes),
        "average_rating": round(average_rating, 1) if average_rating is not None else None,
        "latest_rating": logs[0]["rating"] if logs else None,
        "start_label": _cook_label(ordered[0], chart["precision"]) if ordered else None,
        "end_label": _cook_label(ordered[-1], chart["precision"]) if ordered else None,
        "axis_labels": axis_dates([{"date": log["created_at"][:10]} for log in ordered])
        if chart["presentation"] == "bar"
        else [],
        "current_display": display_value(
            logs[0]["rating"] if logs else None, chart["precision"], suffix="/5"
        ),
    }
    result["readings"] = configured_readings(
        config,
        {
            "recipe_count": {"value": result["recipe_count"]},
            "cook_count": {"value": result["cook_count"]},
            "average_rating": {"value": average_rating, "suffix": "/5"},
            "latest_rating": {"value": result["latest_rating"], "suffix": "/5"},
        },
    )
    result["has_series"] = result["has_series"] and chart["enabled"]
    result["chart_label"] = chart["label"]
    return result


def food_dashboard(
    summary: dict[str, Any],
    records: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or DEFAULT_CONFIG["plugins"]["food"]
    days = summary["daily_confirmed_totals"]
    chart = metric_settings(config)["confirmed_calories"]
    calorie_chart = series_plot([float(day["calories"]) for day in days], chart["presentation"])
    if days:
        calorie_chart.update(
            {
                "axis_labels": axis_dates(days),
                "callout": {
                    "value": f"{round(days[-1]['calories'])} kcal",
                    "y": round(calorie_chart["last"]["y"] / 38 * 100, 2),
                }
                if chart["presentation"] == "line"
                else None,
            }
        )
    unresolved_count = sum(
        record["status"] == "uncertain"
        or (record["status"] == "eaten" and record["nutrition_id"] is None)
        for record in records
    )
    records_by_date: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record["status"] == "eaten" and record["consumption_date_local"]:
            records_by_date.setdefault(record["consumption_date_local"], []).append(record)
    projected_days = []
    average_calories = sum(day["calories"] for day in days) / len(days) if days else 0
    average_protein = sum(day["protein_g"] for day in days) / len(days) if days else 0
    for day in days:
        meals: dict[str, list[dict[str, str]]] = {}
        for record in records_by_date.get(day["date"], []):
            slot = record["meal_slot"] or "Meal"
            meals.setdefault(slot, []).append(
                {"item": record["item"], "restaurant": record["restaurant"]}
            )
        projected_days.append(
            {
                **day,
                "meals": [{"slot": slot, "items": items} for slot, items in meals.items()],
                "meal_count": len(meals),
            }
        )
    result = {
        "days": projected_days,
        "calorie_chart": calorie_chart,
        "average_calories": round(average_calories),
        "average_protein": round(average_protein, 1),
        "confirmed_count": sum(
            record["status"] == "eaten" and record["nutrition_id"] is not None for record in records
        ),
        "excluded_count": summary["excluded_count"],
        "unresolved_count": unresolved_count,
        "current_calories": display_value(
            days[-1]["calories"] if days else None, chart["precision"], suffix=" kcal"
        ),
    }
    result["readings"] = configured_readings(
        config,
        {
            "average_calories": {"value": average_calories, "suffix": " kcal"},
            "average_protein": {"value": average_protein, "suffix": "g"},
            "confirmed_count": {"value": result["confirmed_count"]},
            "unresolved_count": {"value": result["unresolved_count"]},
        },
    )
    result["calorie_chart_enabled"] = chart["enabled"]
    result["calorie_chart_label"] = chart["label"]
    return result


def _shot_label(shot: dict[str, Any], precision: int) -> dict[str, str]:
    ratio = shot["yield_g"] / shot["dose_g"]
    return {
        "date": shot["created_at"][:10],
        "value": f"{display_value(ratio, precision)}×",
    }


def _cook_label(log: dict[str, Any], precision: int) -> dict[str, str]:
    return {
        "date": log["created_at"][:10],
        "value": f"{display_value(log['rating'], precision)}/5",
    }
