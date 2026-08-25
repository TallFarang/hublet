"""One validated presentation document for every Hublet dashboard."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from app.config import Settings

FILENAME = "dashboard.json"
METRIC_FIELDS = {"key", "enabled", "label", "precision", "view"}
LINKED_ROLES = {"supporting_indicator", "supplemental_indicator"}


def _metric(key: str, label: str, precision: int, view: str, enabled: bool = True) -> dict:
    return {"key": key, "enabled": enabled, "label": label, "precision": precision, "view": view}


DEFAULT_CONFIG = {
    "schema_version": 1,
    "plugins": {
        "health": {
            "metrics": [
                _metric("body_weight_kg", "Body weight", 1, "daily_latest"),
                _metric("body_fat_percentage", "Body fat", 1, "daily_latest"),
                _metric("lean_body_mass_kg", "Lean mass", 1, "daily_latest"),
                _metric("sleep_hours", "Sleep", 1, "daily_total"),
                _metric("resting_heart_rate", "Resting heart rate", 0, "daily_latest"),
                _metric("heart_rate_recovery", "Heart rate recovery", 0, "daily_latest"),
                _metric("workouts_completed", "Workouts", 0, "daily_total"),
                _metric("vo2_max", "VO₂ max", 1, "daily_latest", False),
            ]
        },
        "food": {
            "metrics": [
                _metric("confirmed_calories", "Confirmed calories", 0, "daily_total"),
                _metric("average_calories", "Daily avg", 0, "period_average"),
                _metric("average_protein", "Protein avg", 1, "period_average"),
                _metric("confirmed_count", "Confirmed", 0, "period_total"),
                _metric("unresolved_count", "Unresolved", 0, "period_total"),
            ]
        },
        "coffee": {
            "metrics": [
                _metric("bean_count", "Open beans", 0, "latest"),
                _metric("latest_ratio", "Latest ratio", 2, "latest"),
                _metric("latest_time", "Latest time", 1, "latest"),
                _metric("average_rating", "Avg rating", 1, "period_average"),
                _metric("extraction_ratio", "Extraction ratio", 2, "daily_latest"),
            ]
        },
        "recipes": {
            "metrics": [
                _metric("recipe_count", "Linked", 0, "latest"),
                _metric("cook_count", "Cooks", 0, "period_total"),
                _metric("average_rating", "Avg rating", 1, "period_average"),
                _metric("latest_rating", "Latest", 0, "latest"),
                _metric("cook_rating", "Cook ratings", 0, "daily_latest"),
            ]
        },
        "goals": {
            "linked_roles": ["supporting_indicator", "supplemental_indicator"],
            "metrics": [
                _metric("body_weight_kg", "Body weight", 1, "daily_latest"),
                _metric("body_fat_percentage", "Body fat", 1, "daily_latest"),
                _metric("lean_body_mass_kg", "Lean mass", 1, "daily_latest"),
                _metric("calorie_target_adherence", "Calories", 0, "daily_with_rolling_7d"),
                _metric("workouts_completed", "Workouts", 0, "daily_total"),
                _metric("resting_heart_rate", "Resting heart rate", 0, "daily_latest"),
                _metric("heart_rate_recovery", "Heart rate recovery", 0, "daily_latest"),
                _metric("sleep_hours", "Sleep", 1, "daily_total"),
                _metric("vo2_max", "VO₂ max", 1, "daily_latest", False),
            ],
        },
    },
}

CATALOGUE = {
    "health": {
        item["key"]: [item["view"]] for item in DEFAULT_CONFIG["plugins"]["health"]["metrics"]
    },
    "food": {item["key"]: [item["view"]] for item in DEFAULT_CONFIG["plugins"]["food"]["metrics"]},
    "coffee": {
        item["key"]: [item["view"]] for item in DEFAULT_CONFIG["plugins"]["coffee"]["metrics"]
    },
    "recipes": {
        item["key"]: [item["view"]] for item in DEFAULT_CONFIG["plugins"]["recipes"]["metrics"]
    },
    "goals": {
        item["key"]: [item["view"]] for item in DEFAULT_CONFIG["plugins"]["goals"]["metrics"]
    },
}
CATALOGUE["goals"]["calorie_target_adherence"] = [
    "daily_total",
    "daily_with_rolling_7d",
]


def load_config(settings: Settings) -> dict[str, Any]:
    path = settings.data_dir / FILENAME
    if not path.is_file():
        return deepcopy(DEFAULT_CONFIG)
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError("dashboard.json is not valid JSON") from error
    return validate_config(document)


def validate_config(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != {"schema_version", "plugins"}:
        raise ValueError("dashboard configuration must contain schema_version and plugins")
    if document["schema_version"] != 1 or not isinstance(document["plugins"], dict):
        raise ValueError("unsupported dashboard configuration")
    if set(document["plugins"]) != set(CATALOGUE):
        raise ValueError("dashboard configuration must contain every known plugin")
    for plugin, values in document["plugins"].items():
        expected = {"metrics", "linked_roles"} if plugin == "goals" else {"metrics"}
        if not isinstance(values, dict) or set(values) != expected:
            raise ValueError(f"invalid {plugin} dashboard settings")
        _validate_metrics(plugin, values["metrics"])
    roles = document["plugins"]["goals"]["linked_roles"]
    if (
        not isinstance(roles, list)
        or len(roles) != len(set(roles))
        or not set(roles) <= LINKED_ROLES
    ):
        raise ValueError("invalid Goals linked roles")
    return deepcopy(document)


def _validate_metrics(plugin: str, metrics: Any) -> None:
    if not isinstance(metrics, list):
        raise TypeError(f"{plugin} metrics must be a list")
    keys = []
    for metric in metrics:
        if not isinstance(metric, dict) or set(metric) != METRIC_FIELDS:
            raise ValueError(f"invalid {plugin} metric settings")
        key, label = metric["key"], metric["label"]
        precision, view = metric["precision"], metric["view"]
        if key not in CATALOGUE[plugin] or view not in CATALOGUE[plugin][key]:
            raise ValueError(f"unsupported {plugin} metric or view: {key}")
        if (
            not isinstance(metric["enabled"], bool)
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > 80
        ):
            raise ValueError(f"invalid {plugin} metric display")
        if isinstance(precision, bool) or not isinstance(precision, int) or not 0 <= precision <= 3:
            raise ValueError(f"invalid precision for {plugin}.{key}")
        keys.append(key)
    if len(keys) != len(set(keys)):
        raise ValueError(f"duplicate {plugin} metric")
    if set(keys) != set(CATALOGUE[plugin]):
        raise ValueError(f"{plugin} configuration must contain every supported metric")


def replace_config(settings: Settings, document: Any) -> dict[str, Any]:
    validated = validate_config(document)
    path = settings.data_dir / FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{FILENAME}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(validated, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return validated


def register_mcp(server: MCPServer, settings: Settings) -> None:
    def get_tool() -> dict[str, Any]:
        """Return the active dashboard configuration and supported metric views."""
        return {"config": load_config(settings), "catalogue": CATALOGUE}

    def replace_tool(config: dict[str, Any]) -> dict[str, Any]:
        """Validate and atomically replace the complete dashboard configuration."""
        return replace_config(settings, config)

    server.add_tool(get_tool, name="dashboard_config_get")
    server.add_tool(replace_tool, name="dashboard_config_replace")
