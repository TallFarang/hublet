"""Read-only live series adapters for the Goals dashboard."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.config import Settings
from app.dashboard_config import DEFAULT_CONFIG
from app.dashboard_metrics import metric_settings
from app.plugins.food_reporting import summary as food_summary
from app.plugins.food_schema import DB_FILENAME as FOOD_DB
from app.plugins.health_report import summary as health_summary
from app.plugins.health_schema import DB_FILENAME as HEALTH_DB

LiveSeries = dict[tuple[str, str], dict[str, Any]]


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
            days = food_summary(settings, extended, end)["daily_confirmed_totals"]
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
