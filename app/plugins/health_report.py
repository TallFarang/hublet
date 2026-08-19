"""Compact semantic summaries over Health's current records table."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from app.config import Settings
from app.db import connect
from app.plugins.health_query import _range, sync_status
from app.plugins.health_schema import DB_FILENAME, MAPPINGS


def summary(settings: Settings, start_date: str, end_date: str) -> dict[str, Any]:
    start, end = _range(start_date, end_date)
    if (end - start).days >= 367:
        raise ValueError("summary range must not exceed 367 days")
    requested = []
    current = start
    while current <= end:
        requested.append(current.isoformat())
        current += timedelta(days=1)
    with connect(settings.data_dir / DB_FILENAME) as connection:
        exported = {
            row[0]
            for row in connection.execute(
                "SELECT export_date FROM days WHERE export_date BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            )
        }
        sections = {
            (row["export_date"], row["type"]): row["record_count"]
            for row in connection.execute(
                "SELECT * FROM types WHERE export_date BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            )
        }
        rows = [
            dict(row)
            for row in connection.execute(
                """SELECT id, uuid, type, kind, local_date, start_at, end_at, unit,
                          normalized_value, normalized_unit, duration_seconds,
                          activity_type, raw_json
                   FROM records WHERE local_date BETWEEN ? AND ?
                   AND type IN (?, ?, ?, ?) ORDER BY local_date, COALESCE(start_at, end_at), id""",
                (start.isoformat(), end.isoformat(), *MAPPINGS),
            )
        ]
    raw_record_count = len(rows)
    rows = _semantic_records(rows)
    metrics, evidence = {}, []
    for type_name, (metric, expected_unit) in MAPPINGS.items():
        typed = [row for row in rows if row["type"] == type_name]
        empty = [day for day in requested if sections.get((day, type_name)) == 0]
        missing = [day for day in requested if day in exported and (day, type_name) not in sections]
        if metric == "workouts_completed":
            series = [{"date": day, "value": sum(row["local_date"] == day for row in typed)} for day in requested if day in exported]
            metrics[metric] = _metric(metric, expected_unit, series, empty, missing)
            if len(exported) == len(requested) and not missing:
                evidence.append(
                    {
                        "metric": metric,
                        "value": len(typed),
                        "unit": expected_unit,
                        "source": "HealthKit",
                        "reference": "Agentbridge via Hublet Health",
                        "period_start": start.isoformat(),
                        "period_end": end.isoformat(),
                        "idempotency_key": f"healthkit:workouts:{start}:{end}",
                    }
                )
            continue
        samples = [
            {
                "record_id": row["id"],
                "uuid": row["uuid"],
                "date": row["local_date"],
                "observed_at": row["start_at"] or row["end_at"],
                "value": row["normalized_value"],
                "unit": row["normalized_unit"] or row["unit"],
            }
            for row in typed
            if row["normalized_value"] is not None
            and (row["normalized_unit"] or row["unit"]) == expected_unit
        ]
        series = [{"date": item["date"], "value": item["value"]} for item in samples]
        metrics[metric] = {**_metric(metric, expected_unit, series, empty, missing), "samples": samples}
        evidence.extend(_point_evidence(metric, sample) for sample in samples)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "source": sync_status(settings),
        "coverage": {
            "exported_dates": sorted(exported),
            "missing_dates": [day for day in requested if day not in exported],
        },
        "record_counts": {
            "raw": raw_record_count,
            "reported": len(rows),
            "duplicates_suppressed": raw_record_count - len(rows),
        },
        "metrics": metrics,
        "evidence": evidence,
    }


def _semantic_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one deterministic representative of each reported measurement."""

    unique = {}
    for row in rows:
        raw = json.loads(row["raw_json"])
        key = (
            row["type"],
            row["kind"],
            row["local_date"],
            row["start_at"],
            row["end_at"],
            row["normalized_value"],
            row["normalized_unit"] or row["unit"],
            row["duration_seconds"],
            row["activity_type"],
            json.dumps(raw.get("source"), sort_keys=True, separators=(",", ":")),
        )
        unique.setdefault(key, row)
    return list(unique.values())


def _metric(
    metric: str,
    unit: str,
    series: list[dict[str, Any]],
    empty: list[str],
    missing: list[str],
) -> dict[str, Any]:
    return {
        "metric": metric,
        "unit": unit,
        "latest": series[-1] if series else None,
        "series": series,
        "no_measurement_dates": empty,
        "missing_type_dates": missing,
    }


def _point_evidence(metric: str, sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": sample["value"],
        "unit": sample["unit"],
        "source": "HealthKit",
        "reference": f"Agentbridge via Hublet Health: {sample['record_id']}",
        "observed_at": sample["observed_at"],
        "idempotency_key": f"healthkit:{sample['uuid'] or sample['record_id']}",
    }
