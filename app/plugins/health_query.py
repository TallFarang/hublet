"""Read the current Health snapshot without interpretation."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings
from app.db import connect
from app.plugins.health_schema import DB_FILENAME


def query_records(
    settings: Settings,
    type_name: str,
    start_date: str,
    end_date: str,
    limit: int = 100,
    offset: int = 0,
    include_raw: bool = False,
) -> dict[str, Any]:
    start, end = _range(start_date, end_date)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if not isinstance(type_name, str) or not type_name.strip():
        raise ValueError("type is required")
    parameters = (type_name.strip(), start.isoformat(), end.isoformat())
    with connect(settings.data_dir / DB_FILENAME) as connection:
        total = connection.execute(
            "SELECT COUNT(*) FROM records WHERE type = ? AND local_date BETWEEN ? AND ?",
            parameters,
        ).fetchone()[0]
        rows = connection.execute(
            """SELECT * FROM records WHERE type = ? AND local_date BETWEEN ? AND ?
               ORDER BY local_date DESC, COALESCE(start_at, end_at) DESC, id DESC
               LIMIT ? OFFSET ?""",
            (*parameters, limit, offset),
        ).fetchall()
    return {
        "records": [_record(dict(row), include_raw) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def list_types(settings: Settings) -> list[dict[str, Any]]:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        rows = connection.execute(
            """SELECT type, kind, MIN(export_date) AS first_date,
                      MAX(export_date) AS latest_date, SUM(COALESCE(record_count, 0)) AS records,
                      SUM(record_count IS NULL) AS missing_sections
               FROM types GROUP BY type, kind ORDER BY type, kind"""
        ).fetchall()
    return [dict(row) for row in rows]


def sync_status(settings: Settings) -> dict[str, Any]:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        state = dict(connection.execute("SELECT * FROM sync_state WHERE id = 1").fetchone())
        days = [dict(row) for row in connection.execute("SELECT * FROM days ORDER BY export_date")]
        missing_sections = [
            {"date": row["export_date"], "type": row["type"]}
            for row in connection.execute(
                "SELECT export_date, type FROM types WHERE record_count IS NULL ORDER BY 1, 2"
            )
        ]
    if not days:
        return {
            **state,
            "freshness": "never_synced" if state["status"] == "never_synced" else "stale",
            "expected_latest_date": None,
            "missing_dates": [],
            "missing_type_sections": missing_sections,
        }
    timezone = days[-1]["timezone"]
    expected = datetime.now(ZoneInfo(timezone)).date() - timedelta(days=1)
    first = date.fromisoformat(days[0]["export_date"])
    present = {date.fromisoformat(day["export_date"]) for day in days}
    missing = []
    current = first
    while current <= expected:
        if current not in present:
            missing.append(current.isoformat())
        current += timedelta(days=1)
    latest = date.fromisoformat(days[-1]["export_date"])
    fresh = latest >= expected and not missing and not missing_sections and state["status"] == "ok"
    return {
        **state,
        "freshness": "fresh" if fresh else "stale",
        "expected_latest_date": expected.isoformat(),
        "missing_dates": missing,
        "missing_type_sections": missing_sections,
    }


def _record(row: dict[str, Any], include_raw: bool) -> dict[str, Any]:
    row["value"] = json.loads(row.pop("value_json")) if row["value_json"] is not None else None
    row["source_dates"] = json.loads(row.pop("source_dates_json"))
    if include_raw:
        row["raw"] = json.loads(row.pop("raw_json"))
    else:
        row.pop("raw_json")
    return row


def _range(start_date: str, end_date: str) -> tuple[date, date]:
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except (TypeError, ValueError) as error:
        raise ValueError("dates must use YYYY-MM-DD") from error
    if start > end:
        raise ValueError("start_date must not be after end_date")
    return start, end
