"""Minimal read-only projections for the Goals dashboard."""

from __future__ import annotations

from typing import Any

from app.charts import series_plot
from app.dashboard_config import DEFAULT_CONFIG
from app.dashboard_metrics import axis_dates, display_value, metric_settings

LiveSeries = dict[tuple[str, str], dict[str, Any]]


def goal_dashboard(
    goal: dict[str, Any],
    live: LiveSeries | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one active goal into only the readings its dashboard needs."""

    live = live or {}
    target = goal.get("target") or {}
    metric = target.get("metric")
    numeric, series_unit = _primary_series(goal, metric, live)
    values = [float(row["value"]) for row in numeric]
    latest = numeric[-1] if numeric else None
    target_value = _number(target.get("value"))
    config = config or DEFAULT_CONFIG["plugins"]["goals"]
    presentation = config.get("goal_presentations", {}).get(goal.get("id"), "line")
    display = metric_settings(config).get(metric or "")
    geometry = series_plot(
        values,
        presentation,
        target_value,
        precision=display["precision"] if display else None,
    )
    return {
        **geometry,
        "latest": display_value(latest["value"], display["precision"])
        if latest and display
        else latest["value"]
        if latest
        else None,
        "unit": series_unit or (latest or {}).get("unit") or target.get("unit") or "",
        "has_series": bool(values),
        "target_line_label": _target_label(target),
        "target_y_percent": round(geometry["target_y"] / 38 * 100, 2)
        if geometry["target_y"] is not None
        else None,
        "start_label": _observation_label(
            numeric[0], display["precision"] if display else None, series_unit
        )
        if numeric
        else None,
        "end_label": _observation_label(
            numeric[-1], display["precision"] if display else None, series_unit
        )
        if numeric
        else None,
        "axis_labels": axis_dates(numeric) if presentation == "bar" else [],
        "tracking": _tracking_charts(goal, live, config),
    }


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
            start_label = _observation_label(series[0], display["precision"], unit)
            end_label = _observation_label(series[-1], display["precision"], unit)
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
                    precision=display["precision"],
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


def _primary_series(
    goal: dict[str, Any], metric: str | None, live: LiveSeries
) -> tuple[list[dict[str, Any]], str]:
    for source in goal.get("evidence_sources", []):
        if source.get("role") != "outcome" or source.get("metric") != metric:
            continue
        connected = live.get((metric, source.get("source")))
        if connected and connected["series"]:
            return connected["series"], connected.get("unit") or ""
    return _numeric_series(goal.get("history", []), metric), ""


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


def _observation_label(
    observation: dict[str, Any], precision: int | None = None, fallback_unit: str = ""
) -> dict[str, str]:
    unit = observation.get("unit") or fallback_unit
    value = (
        display_value(observation["value"], precision)
        if precision is not None
        else observation["value"]
    )
    return {
        "date": observation.get("date")
        or observation.get("observed_at")
        or observation.get("period_end"),
        "value": f"{value} {unit}".strip(),
    }
