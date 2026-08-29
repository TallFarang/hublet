"""Configured Health dashboard projection."""

from __future__ import annotations

from typing import Any

from app.charts import series_plot
from app.dashboard_config import DEFAULT_CONFIG
from app.dashboard_metrics import axis_dates, display_value, enabled_metrics


def health_dashboard(
    report: dict[str, Any], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    config = config or DEFAULT_CONFIG["plugins"]["health"]
    metrics = []
    for settings in enabled_metrics(config):
        name = settings["key"]
        metric = report["metrics"].get(name)
        if metric is None:
            continue
        points = metric["series"]
        if settings["view"] == "daily_latest":
            points = list({point["date"]: point for point in points}.values())
        values = [float(point["value"]) for point in points]
        if name == "workouts_completed":
            running = 0.0
            values = [running := running + value for value in values]
        latest = values[-1] if values else None
        metrics.append(
            {
                **series_plot(
                    values, settings["presentation"], precision=settings["precision"]
                ),
                "name": name,
                "label": settings["label"],
                "value": display_value(latest, settings["precision"])
                if latest is not None
                else None,
                "unit": metric["unit"],
                "latest_date": metric["latest"]["date"] if metric["latest"] else None,
                "has_series": bool(values),
                "start_label": _label(points[0], values[0], metric["unit"], settings["precision"])
                if values
                else None,
                "end_label": _label(points[-1], values[-1], metric["unit"], settings["precision"])
                if values
                else None,
                "axis_labels": axis_dates(points) if settings["presentation"] == "bar" else [],
            }
        )
    return {
        "metrics": metrics,
        "freshness": report["source"]["freshness"],
        "latest_export_date": report["source"]["latest_export_date"],
        "exported_days": len(report["coverage"]["exported_dates"]),
        "missing_days": len(report["source"]["missing_dates"]),
    }


def _label(point: dict[str, Any], value: float, unit: str, precision: int) -> dict[str, str]:
    return {
        "date": point["date"],
        "value": f"{display_value(value, precision)} {unit}".strip(),
    }
