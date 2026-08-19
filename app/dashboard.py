"""Small presentation projections for Hublet's server-rendered dashboards."""

from __future__ import annotations

from typing import Any


def plot(values: list[float], target: float | None = None) -> dict[str, Any]:
    """Map a numeric series into a compact dependency-free SVG view box."""

    domain = [*values, *([] if target is None else [target])]
    if not domain:
        return {"points": "", "target_y": None, "last": None, "single": False}
    low, high = min(domain), max(domain)
    if low == high:
        low, high = low - 1, high + 1

    def y(value: float) -> float:
        return round(34 - ((value - low) / (high - low) * 30), 2)

    if len(values) == 1:
        points = f"50,{y(values[0])}"
    else:
        points = " ".join(
            f"{round(index * 100 / (len(values) - 1), 2)},{y(value)}"
            for index, value in enumerate(values)
        )
    last = {"x": 50 if len(values) == 1 else 100, "y": y(values[-1])} if values else None
    return {
        "points": points,
        "target_y": y(target) if target is not None else None,
        "last": last,
        "single": len(values) == 1,
    }


def goal_dashboard(goal: dict[str, Any]) -> dict[str, Any]:
    target = goal.get("target") or {}
    metric = target.get("metric")
    history = [row for row in goal.get("history", []) if row["metric"] == metric]
    numeric = [row for row in reversed(history) if _number(row["value"]) is not None]
    values = [float(row["value"]) for row in numeric]
    latest = history[0] if history else None
    target_value = _number(target.get("value"))
    return {
        **plot(values, target_value),
        "metric": str(metric or "No metric").replace("_", " "),
        "latest": latest["value"] if latest else None,
        "unit": (latest or {}).get("unit") or target.get("unit") or "",
        "state": _goal_state(values, target_value, target.get("direction")),
        "has_series": bool(values),
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
    )[:12]
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
    unresolved = [
        record
        for record in records
        if record["status"] == "uncertain"
        or (record["status"] == "eaten" and record["nutrition_id"] is None)
    ]
    return {
        "days": [{**day, "bar": round(day["calories"] / peak * 100, 2)} for day in days],
        "average_calories": round(sum(day["calories"] for day in days) / len(days)) if days else 0,
        "average_protein": round(sum(day["protein_g"] for day in days) / len(days), 1)
        if days
        else 0,
        "confirmed_count": sum(
            record["status"] == "eaten" and record["nutrition_id"] is not None
            for record in records
        ),
        "uncertain_count": summary["uncertain_count"],
        "excluded_count": summary["excluded_count"],
        "unresolved": unresolved,
    }


def health_dashboard(report: dict[str, Any]) -> dict[str, Any]:
    labels = {
        "vo2_max": "VO₂ max",
        "body_weight_kg": "Body weight",
        "resting_heart_rate": "Resting heart rate",
        "workouts_completed": "Workouts · 30d",
    }
    metrics = []
    for name, metric in report["metrics"].items():
        values = [float(point["value"]) for point in metric["series"]]
        latest = sum(values) if name == "workouts_completed" else (values[-1] if values else None)
        metrics.append(
            {
                **plot(values),
                "name": name,
                "label": labels[name],
                "value": round(latest, 1) if latest is not None else None,
                "unit": metric["unit"],
                "latest_date": metric["latest"]["date"] if metric["latest"] else None,
                "has_series": bool(values),
            }
        )
    return {
        "metrics": metrics,
        "freshness": report["source"]["freshness"],
        "latest_export_date": report["source"]["latest_export_date"],
        "exported_days": len(report["coverage"]["exported_dates"]),
        "missing_days": len(report["source"]["missing_dates"]),
    }


def _goal_state(values: list[float], target: float | None, direction: str | None) -> str:
    if not values:
        return "No numeric data"
    if direction == "increasing_trend":
        if len(values) < 2:
            return "One reading"
        return "Trending up" if values[-1] > values[-2] else "Not increasing"
    if target is None:
        return "Tracking"
    latest = values[-1]
    met = {
        "above": latest > target,
        "at_or_above": latest >= target,
        "at_or_below": latest <= target,
        "equals": latest == target,
    }.get(direction or "equals", False)
    return "Target met" if met else "Target not met"


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _shot_label(shot: dict[str, Any]) -> dict[str, str]:
    ratio = round(shot["yield_g"] / shot["dose_g"], 2)
    return {"date": shot["created_at"][:10], "value": f"{ratio}×"}


def _cook_label(log: dict[str, Any]) -> dict[str, str]:
    return {"date": log["created_at"][:10], "value": f"{log['rating']}/5"}
