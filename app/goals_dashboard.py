"""Minimal read-only projections for the Goals dashboard."""

from __future__ import annotations

from typing import Any

from app.charts import plot
from app.config import Settings
from app.plugins.food_reporting import summary as food_summary
from app.plugins.food_schema import DB_FILENAME as FOOD_DB
from app.plugins.health_report import summary as health_summary
from app.plugins.health_schema import DB_FILENAME as HEALTH_DB

LiveSeries = dict[tuple[str, str], dict[str, Any]]
LABELS = {
    "calorie_target_adherence": "Calories",
    "workouts_completed": "Workouts",
    "resting_heart_rate": "Resting heart rate",
    "vo2_max": "VO₂ max",
}
TARGET_SYMBOLS = {
    "above": ">",
    "at_or_above": "≥",
    "at_or_below": "≤",
    "equals": "=",
}


def goal_dashboard(goal: dict[str, Any], live: LiveSeries | None = None) -> dict[str, Any]:
    """Project one active goal into only the readings its dashboard needs."""

    target = goal.get("target") or {}
    metric = target.get("metric")
    numeric = _numeric_series(goal.get("history", []), metric)
    values = [float(row["value"]) for row in numeric]
    latest = numeric[-1] if numeric else None
    target_value = _number(target.get("value"))
    return {
        **plot(values, target_value),
        "latest": latest["value"] if latest else None,
        "unit": (latest or {}).get("unit") or target.get("unit") or "",
        "has_series": bool(values),
        "target_label": _target_label(target),
        "start_label": _observation_label(numeric[0]) if numeric else None,
        "end_label": _observation_label(numeric[-1]) if numeric else None,
        "tracking": _tracking_charts(goal, live or {}),
    }


def live_tracking_series(settings: Settings, start: str, end: str) -> LiveSeries:
    """Read connected Hublet sources without copying or changing their data."""

    result: LiveSeries = {}
    if (settings.data_dir / HEALTH_DB).is_file():
        report = health_summary(settings, start, end)
        for metric, reading in report["metrics"].items():
            points = reading["series"]
            if points:
                result[(metric, "HealthKit")] = {
                    "label": LABELS.get(metric, _label(metric)),
                    "unit": reading["unit"],
                    "series": points,
                }
    if (settings.data_dir / FOOD_DB).is_file():
        days = food_summary(settings, start, end, [])["daily_confirmed_totals"]
        points = [
            {"date": day["date"], "value": day["calories"]}
            for day in days
            if _number(day["calories"]) and day["calories"] > 0
        ]
        if points:
            result[("calorie_target_adherence", "Hublet Food")] = {
                "label": "Calories",
                "unit": "kcal",
                "series": points,
            }
    return result


def _tracking_charts(goal: dict[str, Any], live: LiveSeries) -> list[dict[str, Any]]:
    charts = []
    for source in goal.get("evidence_sources", []):
        if source.get("role") != "supporting_indicator":
            continue
        metric, provider = source["metric"], source["source"]
        connected = live.get((metric, provider))
        if connected:
            series = connected["series"]
            values = [float(point["value"]) for point in series]
            unit = connected["unit"]
            start_label = _point_label(series[0], unit)
            end_label = _point_label(series[-1], unit)
            label = connected["label"]
        else:
            series = _numeric_series(goal.get("history", []), metric, provider)
            if not series:
                continue
            values = [float(row["value"]) for row in series]
            unit = series[-1].get("unit") or ""
            start_label = _observation_label(series[0])
            end_label = _observation_label(series[-1])
            label = LABELS.get(metric, _label(metric))
        expectation = source.get("expectation") or {}
        charts.append(
            {
                **plot(values, _number(expectation.get("value"))),
                "label": label,
                "latest": series[-1]["value"],
                "unit": unit or expectation.get("unit") or "",
                "start_label": start_label,
                "end_label": end_label,
            }
        )
    return charts


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


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


def _target_label(target: dict[str, Any]) -> str | None:
    value = target.get("value")
    if value is None:
        return None
    displayed = f"{value:g}" if _number(value) is not None else str(value)
    symbol = TARGET_SYMBOLS.get(target.get("direction"), "")
    return " ".join(part for part in (symbol, displayed, target.get("unit")) if part)


def _label(metric: str) -> str:
    return metric.replace("_", " ").capitalize()


def _observation_label(observation: dict[str, Any]) -> dict[str, str]:
    unit = observation.get("unit") or ""
    return {
        "date": observation.get("observed_at") or observation.get("period_end"),
        "value": f"{observation['value']} {unit}".strip(),
    }


def _point_label(point: dict[str, Any], unit: str) -> dict[str, str]:
    return {"date": point["date"], "value": f"{point['value']} {unit}".strip()}
