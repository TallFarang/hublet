from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any


def export_date(days_ago: int = 1) -> str:
    return (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()


def quantity(uuid: str, value: float, unit: str, day: str) -> dict[str, Any]:
    return {
        "uuid": uuid,
        "value": value,
        "unit": unit,
        "start": f"{day}T08:00:00Z",
        "end": f"{day}T08:00:00Z",
        "source": {"bundleIdentifier": "test.health"},
    }


def section(type_name: str, kind: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": type_name, "kind": kind, "records": records}


def write_export(
    root: Path,
    day: str,
    sections: list[dict[str, Any]],
    *,
    revision: int = 1,
    selection: list[str] | None = None,
    bad_digest: bool = False,
) -> Path:
    parsed = date.fromisoformat(day)
    start = datetime.combine(parsed, time.min, tzinfo=UTC)
    period = {
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": (start + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
    }
    selected = selection if selection is not None else [item["type"] for item in sections]
    payload = {"exports": sections, "period": period, "selection": {"exports": selected}}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    document = {
        "schema": "agentbridge.health.daily",
        "schemaVersion": 1,
        "date": day,
        "revision": revision,
        "generatedAt": f"{day}T23:00:00Z",
        "timeZone": "UTC",
        **payload,
        "contentDigest": "sha256:bad"
        if bad_digest
        else "sha256:" + hashlib.sha256(encoded.encode()).hexdigest(),
    }
    destination = root / day[:4] / f"{day}-r{revision:03d}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, separators=(",", ":")))
    return destination
