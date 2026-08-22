"""Small presentation projections for Hublet's server-rendered dashboards."""

from __future__ import annotations

from typing import Any

from app.charts import plot


def goal_dashboard(goal: dict[str, Any]) -> dict[str, Any]:
    target = goal.get("target") or {}
    metric = target.get("metric")
    numeric = _numeric_series(goal.get("history", []), metric)
    values = [float(row["value"]) for row in numeric]
    latest = numeric[-1] if numeric else None
    target_value = _number(target.get("value"))
    return {
        **plot(values, target_value),
        "metric": str(metric or "No metric").replace("_", " "),
        "latest": latest["value"] if latest else None,
        "unit": (latest or {}).get("unit") or target.get("unit") or "",
        "has_series": bool(values),
        "start_label": _observation_label(numeric[0]) if numeric else None,
        "end_label": _observation_label(numeric[-1]) if numeric else None,
        "tracking": _tracking_charts(goal),
    }


def coffee_dashboard(shots: list[dict[str, Any]], bean_count: int) -> dict[str, Any]:
    ordered = [shot for shot in reversed(shots) if shot["dose_g"]]
    ratios = [shot["yield_g"] / shot["dose_g"] for shot in ordered]
    ratings = [shot["rating"] for shot in shots if shot["rating"] is not None]
    latest = shots[0] if shots else None
    return {
        **plot(ratios),
        "has_series": bool(ratios),
        "bean_count": bean_count,
        "shot_count": len(shots),
        "latest_ratio": round(latest["yield_g"] / latest["dose_g"], 2)
        if latest and latest["dose_g"]
        else None,
        "latest_time": latest["time_s"] if latest else None,
        "average_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "start_label": _shot_label(ordered[0]) if ordered else None,
        "end_label": _shot_label(ordered[-1]) if ordered else None,
    }


def recipes_dashboard(recipes: list[dict[str, Any]]) -> dict[str, Any]:
    logs = sorted(
        [log for recipe in recipes for log in recipe["cook_logs"]],
        key=lambda log: (log["created_at"], log["id"]),
        reverse=True,
    )
    ordered = list(reversed(logs))
    ratings = [float(log["rating"]) for log in ordered]
    return {
        **plot(ratings),
        "has_series": bool(ratings),
        "recipe_count": len(recipes),
        "cook_count": sum(len(recipe["cook_logs"]) for recipe in recipes),
        "average_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "latest_rating": logs[0]["rating"] if logs else None,
        "start_label": _cook_label(ordered[0]) if ordered else None,
        "end_label": _cook_label(ordered[-1]) if ordered else None,
    }


def food_dashboard(summary: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    days = summary["daily_confirmed_totals"]
    peak = max((day["calories"] for day in days), default=0) or 1
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
                "bar": round(day["calories"] / peak * 100, 2),
                "meals": [{"slot": slot, "items": items} for slot, items in meals.items()],
                "meal_count": len(meals),
            }
        )
    return {
        "days": projected_days,
        "average_calories": round(sum(day["calories"] for day in days) / len(days)) if days else 0,
        "average_protein": round(sum(day["protein_g"] for day in days) / len(days), 1)
        if days
        else 0,
        "confirmed_count": sum(
            record["status"] == "eaten" and record["nutrition_id"] is not None
            for record in records
        ),
        "excluded_count": summary["excluded_count"],
        "unresolved_count": unresolved_count,
    }


def health_dashboard(report: dict[str, Any]) -> dict[str, Any]:
    labels = {
        "vo2_max": "VO₂ max",
        "body_weight_kg": "Body weight",
        "resting_heart_rate": "Resting heart rate",
        "workouts_completed": "Workouts",
    }
    metrics = []
    for name, metric in report["metrics"].items():
        points = metric["series"]
        values = [float(point["value"]) for point in points]
        if name == "workouts_completed":
            running = 0.0
            values = [running := running + value for value in values]
        latest = values[-1] if values else None
        metrics.append(
            {
                **plot(values),
                "name": name,
                "label": labels[name],
                "value": round(latest, 1) if latest is not None else None,
                "unit": metric["unit"],
                "latest_date": metric["latest"]["date"] if metric["latest"] else None,
                "has_series": bool(values),
                "start_label": _health_label(points[0], values[0], metric["unit"])
                if values
                else None,
                "end_label": _health_label(points[-1], values[-1], metric["unit"])
                if values
                else None,
            }
        )
    return {
        "metrics": metrics,
        "freshness": report["source"]["freshness"],
        "latest_export_date": report["source"]["latest_export_date"],
        "exported_days": len(report["coverage"]["exported_dates"]),
        "missing_days": len(report["source"]["missing_dates"]),
    }


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _shot_label(shot: dict[str, Any]) -> dict[str, str]:
    ratio = round(shot["yield_g"] / shot["dose_g"], 2)
    return {"date": shot["created_at"][:10], "value": f"{ratio}×"}


def _cook_label(log: dict[str, Any]) -> dict[str, str]:
    return {"date": log["created_at"][:10], "value": f"{log['rating']}/5"}


def _numeric_series(
    history: list[dict[str, Any]], metric: str | None, source: str | None = None
) -> list[dict[str, Any]]:
    return [
        row
        for row in reversed(history)
        if row["metric"] == metric
        and (source is None or row["source"] == source)
        and _number(row["value"]) is not None
    ]


def _tracking_charts(goal: dict[str, Any]) -> list[dict[str, Any]]:
    charts = []
    for source in goal.get("evidence_sources", []):
        if source.get("role") != "supporting_indicator":
            continue
        series = _numeric_series(goal.get("history", []), source["metric"], source["source"])
        if not series:
            continue
        values = [float(row["value"]) for row in series]
        expectation = source.get("expectation") or {}
        chart = {
            **plot(values, _number(expectation.get("value"))),
            "label": source["metric"].replace("_", " "),
            "source": source["source"],
            "latest": series[-1]["value"],
            "unit": series[-1].get("unit") or expectation.get("unit") or "",
            "start_label": _observation_label(series[0]),
            "end_label": _observation_label(series[-1]),
        }
        charts.append(chart)
    return charts


def _observation_label(observation: dict[str, Any]) -> dict[str, str]:
    return {
        "date": observation.get("observed_at") or observation.get("period_end"),
        "value": f"{observation['value']} {observation.get('unit') or ''}".strip(),
    }


def _health_label(point: dict[str, Any], value: float, unit: str) -> dict[str, str]:
    return {"date": point["date"], "value": f"{round(value, 1)} {unit}".strip()}
