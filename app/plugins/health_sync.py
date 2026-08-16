"""Atomically replace Health with Agentbridge's current daily snapshot."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.db import connect
from app.plugins.health_goals import update_healthkit_sources
from app.plugins.health_parse import build_snapshot
from app.plugins.health_schema import DB_FILENAME


def sync_agentbridge(settings: Settings, dry_run: bool = False) -> dict[str, Any]:
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run must be a boolean")
    try:
        snapshot = build_snapshot(settings.agentbridge_dir)
        previous_dates, previous_digest = _previous(settings)
        current_dates = {day["export_date"] for day in snapshot["days"]}
        disappeared = sorted(previous_dates - current_dates)
        if disappeared:
            raise ValueError(f"previously imported dates disappeared: {', '.join(disappeared)}")
        result = {
            "dry_run": dry_run,
            "changed": snapshot["dataset_digest"] != previous_digest,
            "days": len(snapshot["days"]),
            "records": len(snapshot["records"]),
            "types": len({row[1] for row in snapshot["types"]}),
            "dataset_digest": snapshot["dataset_digest"],
        }
        if dry_run:
            return result
        if result["changed"]:
            _replace(settings, snapshot)
        else:
            _mark_success(settings)
        from app.plugins.health_query import sync_status

        status = sync_status(settings)
        goals = update_healthkit_sources(
            settings, "connected" if status["freshness"] == "fresh" else "stale"
        )
        return {**result, "status": status, "goals_updated": goals}
    except Exception as error:
        if not dry_run:
            _record_error(settings, str(error))
            update_healthkit_sources(settings, "stale")
        raise


def _previous(settings: Settings) -> tuple[set[str], str | None]:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        dates = {row[0] for row in connection.execute("SELECT export_date FROM days")}
        digest = connection.execute(
            "SELECT dataset_digest FROM sync_state WHERE id = 1"
        ).fetchone()[0]
    return dates, digest


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
        connection.executemany(
            "INSERT INTO types VALUES (?, ?, ?, ?)", snapshot["types"]
        )
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
