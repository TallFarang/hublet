"""One-time import of a trusted goals YAML registry without a Python YAML dependency."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.config import Settings
from app.db import connect, migrate
from app.plugins import goals

DOMAIN_IDS = ("health", "career", "social")
DURATION_PATTERN = re.compile(r"^(\d+)_consecutive_([a-z][a-z0-9_]*)$")
RUBY_LOADER = """
contents = File.read(ARGV.fetch(0))
begin
  data = YAML.safe_load(contents, permitted_classes: [Date], aliases: false)
rescue ArgumentError
  data = YAML.safe_load(contents, [Date], [], false)
end
print JSON.generate(data)
"""


def load_yaml(path: Path) -> dict[str, Any]:
    ruby = shutil.which("ruby")
    if ruby is None:
        raise RuntimeError("Ruby is required for this one-time YAML import")
    result = subprocess.run(
        [ruby, "-rdate", "-rjson", "-ryaml", "-e", RUBY_LOADER, str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError(f"Could not parse goals YAML: {result.stderr.strip()}")
    loaded = json.loads(result.stdout)
    if not isinstance(loaded, dict):
        raise TypeError("Goals YAML must contain an object")
    return loaded


def normalise_registry(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != 1 or not isinstance(document.get("domains"), dict):
        raise ValueError("Unsupported goals YAML schema")
    domains = []
    definitions = []
    for domain_order, (domain_id, source_domain) in enumerate(document["domains"].items(), 1):
        if not isinstance(source_domain, dict):
            raise TypeError("Each domain must be an object")
        domains.append(
            {
                "id": domain_id,
                "name": domain_id.replace("_", " ").title(),
                "display_order": domain_order * 10,
                "status": source_domain.get("status") or "active",
            }
        )
        for goal_order, source_goal in enumerate(source_domain.get("goals") or [], 1):
            definitions.append(_normalise_goal(domain_id, goal_order * 10, source_goal))
    registry = {"domains": domains, "goals": definitions}
    validate_registry(registry)
    return registry


def validate_registry(registry: dict[str, Any]) -> None:
    domains = registry.get("domains")
    definitions = registry.get("goals")
    if not isinstance(domains, list) or not isinstance(definitions, list):
        raise TypeError("Registry must contain domain and goal lists")
    if tuple(domain.get("id") for domain in domains) != DOMAIN_IDS:
        raise ValueError("Registry domains must be Health, Career and Social in that order")
    goal_ids = [definition.get("id") for definition in definitions]
    if len(set(goal_ids)) != len(goal_ids):
        raise ValueError("Goal IDs must be unique")
    known_ids = set(goal_ids)
    for definition in definitions:
        if any(dependency not in known_ids for dependency in definition["dependencies"]):
            raise ValueError(f"Goal {definition['id']} has an unknown dependency")
        if definition["id"] in definition["dependencies"]:
            raise ValueError(f"Goal {definition['id']} cannot depend on itself")


def import_registry(settings: Settings, registry: dict[str, Any]) -> dict[str, int]:
    validate_registry(registry)
    now = goals._now()
    with connect(settings.data_dir / goals.DB_FILENAME) as connection:
        row_count = connection.execute(
            "SELECT COUNT(*) FROM goals UNION ALL SELECT COUNT(*) FROM observations"
        ).fetchall()
        if sum(row[0] for row in row_count):
            raise ValueError("Goals database must be empty before import")
        for domain in registry["domains"]:
            connection.execute(
                "UPDATE domains SET name = ?, display_order = ?, status = ? WHERE id = ?",
                (
                    domain["name"],
                    domain["display_order"],
                    domain["status"],
                    domain["id"],
                ),
            )
        for definition in registry["goals"]:
            connection.execute(
                """INSERT INTO goals
                   (id, domain_id, display_order, title, outcome, description, horizon, status,
                    target_json, systems_json, dependencies_json, evidence_sources_json,
                    notes_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                goals._definition_values(definition) + (now, now),
            )
    return {"domains": len(registry["domains"]), "goals": len(registry["goals"])}


def _normalise_goal(domain: str, display_order: int, source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise TypeError("Each goal must be an object")
    target = _normalise_target(source.get("outcome_target"))
    evidence = source.get("evidence") or []
    if target is None:
        trend = next(
            (
                item
                for item in evidence
                if isinstance(item, dict) and item.get("target") == "increasing_trend"
            ),
            None,
        )
        if trend is not None:
            target = {"metric": trend["metric"], "direction": "increasing_trend"}
    notes = []
    if source.get("rationale"):
        notes.append(source["rationale"])
    notes.extend(source.get("notes") or [])
    return goals._normalise_definition(
        goal_id=source.get("id"),
        domain=domain,
        display_order=display_order,
        title=source.get("title") or source.get("outcome"),
        outcome=source.get("outcome"),
        description=source.get("description"),
        horizon=source.get("horizon"),
        status=source.get("status") or "active",
        target=target,
        systems=source.get("systems") or [],
        dependencies=source.get("dependencies") or [],
        evidence_sources=[_normalise_source(item) for item in evidence],
        notes=notes,
    )


def _normalise_target(source: Any) -> dict[str, Any] | None:
    if source is None:
        return None
    if not isinstance(source, dict):
        raise TypeError("outcome_target must be an object or null")
    raw_value = source.get("target")
    direction = source.get("direction")
    if direction is None and raw_value in goals.DIRECTIONS:
        direction, raw_value = raw_value, None
    duration = source.get("required_duration")
    if duration is not None:
        match = DURATION_PATTERN.fullmatch(str(duration))
        if match is None:
            raise ValueError("required_duration must look like 3_consecutive_months")
        duration = {"count": int(match[1]), "unit": match[2], "consecutive": True}
    known = {"metric", "target", "unit", "direction", "required_duration"}
    return {
        "metric": source.get("metric"),
        "value": raw_value,
        "unit": source.get("unit"),
        "direction": direction or "equals",
        "required_duration": duration,
        "qualifiers": {key: value for key, value in source.items() if key not in known},
    }


def _normalise_source(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise TypeError("Each evidence source must be an object")
    raw_expectation = source.get("target")
    expectation = None
    if raw_expectation is not None:
        expectation = (
            {"direction": raw_expectation}
            if raw_expectation in goals.DIRECTIONS
            else {"value": raw_expectation, "direction": "equals"}
        )
    known = {
        "metric",
        "cadence",
        "source",
        "tracking_status",
        "role",
        "access",
        "collection_note",
        "target",
    }
    return {
        "metric": source.get("metric"),
        "cadence": source.get("cadence"),
        "source": source.get("source"),
        "tracking_status": source.get("tracking_status") or "unspecified",
        "role": source.get("role"),
        "access_notes": source.get("access"),
        "collection_notes": source.get("collection_note"),
        "expectation": expectation,
        "details": {key: value for key, value in source.items() if key not in known},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a trusted goals YAML registry once")
    parser.add_argument("path", type=Path)
    parser.add_argument("--check", action="store_true", help="validate without writing")
    arguments = parser.parse_args()
    registry = normalise_registry(load_yaml(arguments.path))
    if arguments.check:
        print(f"Valid registry: {len(registry['domains'])} domains, {len(registry['goals'])} goals")
        return
    settings = Settings.from_env()
    migrate(settings.data_dir / goals.DB_FILENAME, goals.MIGRATIONS)
    result = import_registry(settings, registry)
    print(f"Imported {result['domains']} domains and {result['goals']} goals")


if __name__ == "__main__":
    main()
