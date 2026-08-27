"""Atomically ingest Agentbridge exports into retained Health history."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.db import connect
from app.plugins.health_parse import build_snapshot
from app.plugins.health_schema import DB_FILENAME


def sync_agentbridge(settings: Settings, dry_run: bool = False) -> dict[str, Any]:
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run must be a boolean")
    try:
        current = build_snapshot(settings.agentbridge_dir)
        snapshot, previous_digest = _merge(settings, current)
        if not snapshot["days"]:
            raise ValueError("no Agentbridge exports or stored Health history found")
        result = {
            "dry_run": dry_run,
            "changed": snapshot["dataset_digest"] != previous_digest,
            "days": len(snapshot["days"]),
            "records": len(snapshot["records"]),
            "types": len({row[1] for row in snapshot["types"]}),
            "dataset_digest": snapshot["dataset_digest"],
            "source_days": len(current["days"]),
        }
        if dry_run:
            return result
        if result["changed"]:
            _replace(settings, snapshot)
        else:
            _mark_success(settings)
        from app.plugins.health_query import sync_status

        return {**result, "status": sync_status(settings)}
    except Exception as error:
        if not dry_run:
            _record_error(settings, str(error))
        raise


def _merge(settings: Settings, current: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    current_dates = {day["export_date"] for day in current["days"]}
    with connect(settings.data_dir / DB_FILENAME) as connection:
        days = {row["export_date"]: dict(row) for row in connection.execute("SELECT * FROM days")}
        types = [
            tuple(row)
            for row in connection.execute("SELECT * FROM types")
            if row["export_date"] not in current_dates
        ]
        records = [dict(row) for row in connection.execute("SELECT * FROM records")]
        digest = connection.execute(
            "SELECT dataset_digest FROM sync_state WHERE id = 1"
        ).fetchone()[0]
    days.update((day["export_date"], day) for day in current["days"])
    merged_records = {}
    for record in records:
        source_dates = set(json.loads(record["source_dates_json"])) - current_dates
        if source_dates:
            record["local_date"] = min(source_dates)
            record["source_dates_json"] = _dump(source_dates)
            merged_records[record["id"]] = record
    for record in current["records"]:
        source_dates = set(json.loads(record["source_dates_json"]))
        existing = merged_records.get(record["id"])
        if existing and existing["raw_json"] != record["raw_json"]:
            raise ValueError(f"conflicting HealthKit UUID: {record['id']}")
        if existing:
            source_dates.update(json.loads(existing["source_dates_json"]))
        record = dict(record)
        record["local_date"] = min(source_dates)
        record["source_dates_json"] = _dump(source_dates)
        merged_records[record["id"]] = record
    ordered_days = [days[day] for day in sorted(days)]
    signature = "\n".join(
        f"{day['export_date']}:r{day['revision']}:{day['content_digest']}" for day in ordered_days
    )
    return (
        {
            "days": ordered_days,
            "types": sorted(types + current["types"]),
            "records": list(merged_records.values()),
            "dataset_digest": "sha256:" + hashlib.sha256(signature.encode()).hexdigest(),
        },
        digest,
    )


def _dump(dates: set[str]) -> str:
    return json.dumps(sorted(dates), separators=(",", ":"))


def _replace(settings: Settings, snapshot: dict[str, Any]) -> None:
    now = datetime.now(UTC).isoformat()
    days = snapshot["days"]
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM records")
        connection.execute("DELETE FROM types")
        connection.execute("DELETE FROM days")
        connection.executemany(
            """INSERT INTO days VALUES
               (:export_date, :revision, :relative_path, :content_digest, :file_digest,
                :generated_at, :timezone, :period_start, :period_end)""",
            days,
        )
        connection.executemany("INSERT INTO types VALUES (?, ?, ?, ?)", snapshot["types"])
        connection.executemany(
            """INSERT INTO records VALUES
               (:id, :uuid, :type, :kind, :local_date, :start_at, :end_at, :value_json,
                :unit, :normalized_value, :normalized_unit, :duration_seconds,
                :activity_type, :raw_json, :source_dates_json)""",
            snapshot["records"],
        )
        connection.execute(
            """UPDATE sync_state SET last_attempt = ?, last_success = ?, status = 'ok',
                      error = NULL, dataset_digest = ?, latest_export_date = ?, timezone = ?
               WHERE id = 1""",
            (
                now,
                now,
                snapshot["dataset_digest"],
                days[-1]["export_date"],
                days[-1]["timezone"],
            ),
        )


def _record_error(settings: Settings, message: str) -> None:
    try:
        with connect(settings.data_dir / DB_FILENAME) as connection:
            connection.execute(
                "UPDATE sync_state SET last_attempt = ?, status = 'error', error = ? WHERE id = 1",
                (datetime.now(UTC).isoformat(), message),
            )
    except sqlite3.OperationalError:
        return


def _mark_success(settings: Settings) -> None:
    now = datetime.now(UTC).isoformat()
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            "UPDATE sync_state SET last_attempt = ?, last_success = ?, status = 'ok', error = NULL",
            (now, now),
        )
