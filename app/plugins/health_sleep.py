"""Sleep duration projection for the supported Health catalogue."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def sleep_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    asleep_states = {1, 3, 4, 5}
    intervals: dict[str, set[tuple[str, str, int]]] = {}
    for row in rows:
        raw = json.loads(row["raw_json"])
        value, start, end = raw.get("value"), row["start_at"], row["end_at"]
        if value in asleep_states and start and end:
            intervals.setdefault(row["local_date"], set()).add((start, end, value))
    return [
        {
            "date": day,
            "value": round(
                sum(
                    (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
                    for start, end, _value in values
                )
                / 3600,
                8,
            ),
        }
        for day, values in sorted(intervals.items())
    ]


def sleep_evidence(metric: str, unit: str, point: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": point["value"],
        "unit": unit,
        "source": "HealthKit",
        "reference": "Agentbridge via Hublet Health",
        "observed_at": f"{point['date']}T12:00:00Z",
        "idempotency_key": f"healthkit:{metric}:{point['date']}",
    }
