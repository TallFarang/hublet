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
from app.dashboard_catalogue import CATALOGUE, DEFAULT_CONFIG

FILENAME = "dashboard.json"
METRIC_FIELDS = {"key", "enabled", "label", "precision", "view", "presentation"}
LINKED_ROLES = {"supporting_indicator", "supplemental_indicator"}


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
    document = _upgrade_v1(deepcopy(document))
    if document["schema_version"] != 2 or not isinstance(document["plugins"], dict):
        raise ValueError("unsupported dashboard configuration")
    if set(document["plugins"]) != set(CATALOGUE):
        raise ValueError("dashboard configuration must contain every known plugin")
    for plugin, values in document["plugins"].items():
        expected = (
            {"metrics", "linked_roles", "goal_presentations"} if plugin == "goals" else {"metrics"}
        )
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
    _validate_goal_presentations(document["plugins"]["goals"]["goal_presentations"])
    return deepcopy(document)


def _upgrade_v1(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != 1:
        return document
    plugins = document.get("plugins")
    if not isinstance(plugins, dict):
        return document
    defaults = {
        plugin: {metric["key"]: metric["presentation"] for metric in values["metrics"]}
        for plugin, values in DEFAULT_CONFIG["plugins"].items()
    }
    for plugin, values in plugins.items():
        if not isinstance(values, dict) or not isinstance(values.get("metrics"), list):
            continue
        for metric in values["metrics"]:
            if isinstance(metric, dict) and metric.get("key") in defaults.get(plugin, {}):
                metric.setdefault("presentation", defaults[plugin][metric["key"]])
    goals = plugins.get("goals")
    if isinstance(goals, dict):
        goals.setdefault("goal_presentations", {})
    document["schema_version"] = 2
    return document


def _validate_metrics(plugin: str, metrics: Any) -> None:
    if not isinstance(metrics, list):
        raise TypeError(f"{plugin} metrics must be a list")
    keys = []
    for metric in metrics:
        if not isinstance(metric, dict) or set(metric) != METRIC_FIELDS:
            raise ValueError(f"invalid {plugin} metric settings")
        key, label = metric["key"], metric["label"]
        precision, view = metric["precision"], metric["view"]
        presentation = metric["presentation"]
        supported = CATALOGUE[plugin].get(key)
        if not supported or view not in supported["views"]:
            raise ValueError(f"unsupported {plugin} metric or view: {key}")
        if presentation not in supported["presentations"]:
            raise ValueError(f"unsupported presentation for {plugin}.{key}")
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


def _validate_goal_presentations(presentations: Any) -> None:
    if not isinstance(presentations, dict):
        raise TypeError("Goals goal_presentations must be an object")
    if any(
        not isinstance(goal_id, str)
        or not goal_id.strip()
        or len(goal_id) > 100
        or not isinstance(presentation, str)
        or presentation not in {"value", "line", "bar"}
        for goal_id, presentation in presentations.items()
    ):
        raise ValueError("invalid Goals goal presentation")


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
        """Return dashboard configuration and supported metric views and presentations."""
        return {"config": load_config(settings), "catalogue": CATALOGUE}

    def replace_tool(config: dict[str, Any]) -> dict[str, Any]:
        """Validate and atomically replace the complete dashboard configuration."""
        return replace_config(settings, config)

    server.add_tool(get_tool, name="dashboard_config_get")
    server.add_tool(replace_tool, name="dashboard_config_replace")
