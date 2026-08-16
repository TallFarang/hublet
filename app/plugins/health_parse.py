"""Read Agentbridge's daily JSON into one canonical snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-r(\d{3})\.json$")


def build_snapshot(configured_root: Path) -> dict[str, Any]:
    root = configured_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("HUBLET_AGENTBRIDGE_DIR must be a directory")
    selected: dict[str, tuple[int, Path]] = {}
    for candidate in root.rglob("*.json"):
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f"Agentbridge file escapes configured directory: {candidate.name}")
        match = FILENAME.fullmatch(candidate.name)
        if match and int(match[2]) > selected.get(match[1], (-1, candidate))[0]:
            selected[match[1]] = (int(match[2]), candidate)
    if not selected:
        raise ValueError("no Agentbridge daily exports found")

    days, type_rows, records = [], [], {}
    for export_date, (revision, path) in sorted(selected.items()):
        day, exports, selected_types = _read_day(root, path, export_date, revision)
        days.append(day)
        by_type = {}
        for section in exports:
            type_name = _text(section.get("type"), "export type")
            if type_name in by_type:
                raise ValueError(f"duplicate export type in {path.name}: {type_name}")
            kind = _text(section.get("kind"), "record kind")
            rows = section.get("records")
            if not isinstance(rows, list):
                raise TypeError(f"records must be an array in {path.name}")
            by_type[type_name] = (kind, rows)
        for type_name in sorted(selected_types | set(by_type)):
            kind, rows = by_type.get(type_name, (None, None))
            type_rows.append((export_date, type_name, kind, None if rows is None else len(rows)))
            for record in rows or []:
                normalized = _record(type_name, kind, export_date, record)
                existing = records.get(normalized["id"])
                if existing and existing["raw_json"] != normalized["raw_json"]:
                    raise ValueError(f"conflicting HealthKit UUID: {normalized['id']}")
                if existing:
                    existing["source_dates"].add(export_date)
                else:
                    records[normalized["id"]] = normalized
    record_rows = []
    for row in records.values():
        row["source_dates_json"] = _dump(sorted(row.pop("source_dates")))
        record_rows.append(row)
    signature = "\n".join(
        f"{row['export_date']}:r{row['revision']}:{row['content_digest']}" for row in days
    )
    return {
        "days": days,
        "types": type_rows,
        "records": record_rows,
        "dataset_digest": "sha256:" + hashlib.sha256(signature.encode()).hexdigest(),
    }


def _read_day(
    root: Path, path: Path, export_date: str, revision: int
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path.name}") from error
    if document.get("schema") != "agentbridge.health.daily" or document.get("schemaVersion") != 1:
        raise ValueError(f"unsupported Agentbridge schema in {path.name}")
    if document.get("date") != export_date or document.get("revision") != revision:
        raise ValueError(f"filename metadata mismatch in {path.name}")
    date.fromisoformat(export_date)
    generated = _timestamp(document.get("generatedAt"), "generatedAt")
    timezone = _text(document.get("timeZone"), "timeZone")
    ZoneInfo(timezone)
    period = document.get("period")
    selection = document.get("selection")
    exports = document.get("exports")
    if not isinstance(period, dict) or not isinstance(selection, dict) or not isinstance(exports, list):
        raise TypeError(f"invalid Agentbridge envelope in {path.name}")
    period_start = _timestamp(period.get("start"), "period.start")
    period_end = _timestamp(period.get("end"), "period.end")
    selected = selection.get("exports")
    if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected):
        raise ValueError(f"selection.exports must be a string array in {path.name}")
    digest_payload = {"exports": exports, "period": period, "selection": selection}
    expected = "sha256:" + hashlib.sha256(_dump(digest_payload).encode()).hexdigest()
    if document.get("contentDigest") != expected:
        raise ValueError(f"content digest mismatch in {path.name}")
    return (
        {
            "export_date": export_date,
            "revision": revision,
            "relative_path": path.relative_to(root).as_posix(),
            "content_digest": expected,
            "file_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "generated_at": generated,
            "timezone": timezone,
            "period_start": period_start,
            "period_end": period_end,
        },
        exports,
        set(selected),
    )


def _record(type_name: str, kind: str, export_date: str, record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise TypeError(f"{type_name} records must be objects")
    raw = _dump(record)
    uuid = record.get("uuid")
    if uuid is not None and (not isinstance(uuid, str) or not uuid.strip()):
        raise ValueError("HealthKit UUID must be a non-empty string")
    identity = uuid or hashlib.sha256(f"{type_name}\0{export_date}\0{raw}".encode()).hexdigest()
    value = record.get("value")
    normalized, normalized_unit = _quantity(type_name, kind, value, record.get("unit"))
    if kind in {"activitySummary", "stateOfMind"} and value is None:
        value = record
    return {
        "id": identity,
        "uuid": uuid,
        "type": type_name,
        "kind": kind,
        "local_date": export_date,
        "start_at": record.get("start"),
        "end_at": record.get("end"),
        "value_json": None if value is None else _dump(value),
        "unit": record.get("unit"),
        "normalized_value": normalized,
        "normalized_unit": normalized_unit,
        "duration_seconds": record.get("durationSeconds") if kind == "workout" else None,
        "activity_type": (
            str(record["activityType"])
            if kind == "workout" and record.get("activityType") is not None
            else None
        ),
        "raw_json": raw,
        "source_dates": {export_date},
    }


def _quantity(type_name: str, kind: str, value: Any, unit: Any) -> tuple[float | None, str | None]:
    if kind != "quantity" or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, None
    if type_name != "HKQuantityTypeIdentifierBodyMass":
        return float(value), unit if isinstance(unit, str) else None
    factors = {"kg": 1.0, "g": 0.001, "lb": 0.45359237, "lbs": 0.45359237}
    if unit not in factors:
        return None, None
    return round(float(value) * factors[unit], 8), "kg"


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _timestamp(value: Any, field: str) -> str:
    value = _text(value, field)
    datetime.fromisoformat(value)
    return value
