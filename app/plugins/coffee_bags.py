"""Coffee bag records."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.db import connect
from app.plugins.coffee_schema import DB_FILENAME

STATUSES = {"open", "archived"}


def add_bag(
    settings: Settings,
    name: str,
    roaster: str,
    roast_date: str | None = None,
    roast_level: str | None = None,
    origin: str | None = None,
    process: str | None = None,
    notes: str | None = None,
    status: str = "open",
) -> dict[str, Any]:
    name = _required(name, "name")
    roaster = _required(roaster, "roaster")
    _validate_status(status)
    if roast_date:
        try:
            date.fromisoformat(roast_date)
        except ValueError as error:
            raise ValueError("roast_date must use YYYY-MM-DD") from error
    bag_id = str(uuid4())
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            """INSERT INTO bags
               (id, name, roaster, roast_date, roast_level, origin, process,
                status, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bag_id,
                name,
                roaster,
                roast_date,
                _optional(roast_level),
                _optional(origin),
                _optional(process),
                status,
                _optional(notes),
                datetime.now(UTC).isoformat(),
            ),
        )
    return get_bag(settings, bag_id)


def get_bag(settings: Settings, bag_id: str) -> dict[str, Any]:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        row = connection.execute("SELECT * FROM bags WHERE id = ?", (bag_id,)).fetchone()
    if row is None:
        raise ValueError("Bag not found")
    return dict(row)


def list_bags(
    settings: Settings,
    status: str | None = "open",
    *,
    name: str | None = None,
    roaster: str | None = None,
) -> list[dict[str, Any]]:
    if status is not None:
        _validate_status(status)
    clauses: list[str] = []
    parameters: list[str] = []
    if status is not None:
        clauses.append("status = ?")
        parameters.append(status)
    for column, value in (("name", name), ("roaster", roaster)):
        if value is not None:
            clauses.append(f"{column} = ? COLLATE NOCASE")
            parameters.append(_required(value, column))
    query = "SELECT * FROM bags"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC, id DESC"
    with connect(settings.data_dir / DB_FILENAME) as connection:
        return [dict(row) for row in connection.execute(query, parameters)]


def set_bag_status(settings: Settings, bag_id: str, status: str) -> dict[str, Any]:
    _validate_status(status)
    get_bag(settings, bag_id)
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute("UPDATE bags SET status = ? WHERE id = ?", (status, bag_id))
    return get_bag(settings, bag_id)


def _required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    return cleaned


def _optional(value: str | None) -> str | None:
    cleaned = value.strip() if value else None
    return cleaned or None


def _validate_status(status: str) -> None:
    if status not in STATUSES:
        raise ValueError("status must be open or archived")
