"""Shared formatting for configured dashboard readings."""

from __future__ import annotations

from typing import Any


def metric_settings(plugin_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {metric["key"]: metric for metric in plugin_config["metrics"]}


def enabled_metrics(plugin_config: dict[str, Any]) -> list[dict[str, Any]]:
    return [metric for metric in plugin_config["metrics"] if metric["enabled"]]


def configured_readings(
    plugin_config: dict[str, Any], values: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    readings = []
    for metric in enabled_metrics(plugin_config):
        value = values.get(metric["key"])
        if value is None:
            continue
        readings.append(
            {
                "key": metric["key"],
                "label": metric["label"],
                "display": display_value(
                    value.get("value"),
                    metric["precision"],
                    value.get("prefix", ""),
                    value.get("suffix", ""),
                ),
            }
        )
    return readings


def display_value(value: Any, precision: int, prefix: str = "", suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        rounded = round(float(value), precision)
        rendered = str(int(rounded)) if precision == 0 else str(rounded)
    else:
        rendered = str(value)
    return f"{prefix}{rendered}{suffix}"
