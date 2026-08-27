"""Minimal read-only projections for the Goals dashboard."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.charts import series_plot
from app.config import Settings
from app.dashboard_config import DEFAULT_CONFIG
from app.dashboard_metrics import axis_dates, display_value, metric_settings
from app.plugins.food_reporting import summary as food_summary
from app.plugins.food_schema import DB_FILENAME as FOOD_DB
from app.plugins.health_report import summary as health_summary
from app.plugins.health_schema import DB_FILENAME as HEALTH_DB

LiveSeries = dict[tuple[str, str], dict[str, Any]]


def goal_dashboard(
    goal: dict[str, Any],
    live: LiveSeries | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one active goal into only the readings its dashboard needs."""

    target = goal.get("target") or {}
    metric = target.get("metric")
    numeric = _numeric_series(goal.get("history", []), metric)
    values = [float(row["value"]) for row in numeric]
    latest = numeric[-1] if numeric else None
    target_value = _number(target.get("value"))
    config = config or DEFAULT_CONFIG["plugins"]["goals"]
    presentation = config.get("goal_presentations", {}).get(goal.get("id"), "line")
    geometry = series_plot(values, presentation, target_value)
    display = metric_settings(config).get(metric or "")
    return {
        **geometry,
        "latest": display_value(latest["value"], display["precision"])
        if latest and display
        else latest["value"]
        if latest
        else None,
        "unit": (latest or {}).get("unit") or target.get("unit") or "",
        "has_series": bool(values),
        "target_line_label": _target_label(target),
        "target_y_percent": round(geometry["target_y"] / 38 * 100, 2)
        if geometry["target_y"] is not None
        else None,
        "start_label": _observation_label(numeric[0], display["precision"] if display else None)
        if numeric
        else None,
        "end_label": _observation_label(numeric[-1], display["precision"] if display else None)
        if numeric
        else None,
        "axis_labels": axis_dates(numeric) if presentation == "bar" else [],
        "tracking": _tracking_charts(goal, live or {}, config),
    }


def live_tracking_series(
    settings: Settings, start: str, end: str, config: dict[str, Any] | None = None
) -> LiveSeries:
    """Read connected Hublet sources without copying or changing their data."""

    result: LiveSeries = {}
    config = config or DEFAULT_CONFIG["plugins"]["goals"]
    configured = metric_settings(config)
    if (settings.data_dir / HEALTH_DB).is_file():
        report = health_summary(settings, start, end)
        for metric, reading in report["metrics"].items():
            points = reading["series"]
            display = configured.get(metric)
            if points and display and display["enabled"]:
                result[(metric, "HealthKit")] = {
                    "label": display["label"],
                    "unit": reading["unit"],
                    "series": points,
                    "precision": display["precision"],
                }
    if (settings.data_dir / FOOD_DB).is_file():
        display = configured.get("calorie_target_adherence")
        if display and display["enabled"]:
            extended = (date.fromisoformat(start) - timedelta(days=6)).isoformat()
            days = food_summary(settings, extended, end, [])["daily_confirmed_totals"]
            daily = [{"date": day["date"], "value": day["calories"]} for day in days]
            rolling = [
                {
                    "date": day["date"],
                    "value": sum(item["value"] for item in daily[index - 6 : index + 1]) / 7,
                }
                for index, day in enumerate(daily)
                if index >= 6
            ]
            daily = [point for point in daily if point["date"] >= start]
            use_rolling = display["view"] == "daily_with_rolling_7d"
            result[("calorie_target_adherence", "Hublet Food")] = {
                "label": display["label"],
                "unit": "kcal",
                "series": rolling if use_rolling else daily,
                "context_series": daily if use_rolling else [],
                "precision": display["precision"],
            }
    return result


def _tracking_charts(
    goal: dict[str, Any], live: LiveSeries, config: dict[str, Any]
) -> list[dict[str, Any]]:
    charts = []
    configured = metric_settings(config)
    for source in goal.get("evidence_sources", []):
        metric = source.get("metric")
        display = configured.get(metric)
        if (
            source.get("role") not in config["linked_roles"]
            or not display
            or not display["enabled"]
        ):
            continue
        provider = source.get("source")
        if not provider:
            continue
        connected = live.get((metric, provider))
        if connected:
            series = connected["series"]
            values = [float(point["value"]) for point in series]
            context = [float(point["value"]) for point in connected.get("context_series", [])]
            unit = connected["unit"]
            start_label = _point_label(series[0], unit, display["precision"])
            end_label = _point_label(series[-1], unit, display["precision"])
            label = connected["label"]
        else:
            series = _numeric_series(goal.get("history", []), metric, provider)
            if not series:
                continue
            values = [float(row["value"]) for row in series]
            context = []
            unit = series[-1].get("unit") or ""
            start_label = _observation_label(series[0], display["precision"])
            end_label = _observation_label(series[-1], display["precision"])
            label = display["label"]
        expectation = source.get("expectation") or {}
        charts.append(
            {
                **series_plot(
                    values,
                    display["presentation"],
                    _number(expectation.get("value")),
                    context,
                ),
                "label": label,
                "latest": display_value(series[-1]["value"], display["precision"]),
                "unit": unit or expectation.get("unit") or "",
                "start_label": start_label,
                "end_label": end_label,
                "axis_labels": axis_dates(series) if display["presentation"] == "bar" else [],
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
    return " ".join(part for part in (displayed, target.get("unit")) if part)


def _observation_label(observation: dict[str, Any], precision: int | None = None) -> dict[str, str]:
    unit = observation.get("unit") or ""
    value = (
        display_value(observation["value"], precision)
        if precision is not None
        else observation["value"]
    )
    return {
        "date": observation.get("observed_at") or observation.get("period_end"),
        "value": f"{value} {unit}".strip(),
    }


def _point_label(point: dict[str, Any], unit: str, precision: int) -> dict[str, str]:
    return {
        "date": point["date"],
        "value": f"{display_value(point['value'], precision)} {unit}".strip(),
    }
