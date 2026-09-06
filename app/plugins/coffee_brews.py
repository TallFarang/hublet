"""Method-aware coffee brew records and history retrieval."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.db import connect
from app.plugins.coffee_bags import get_bag
from app.plugins.coffee_schema import DB_FILENAME, DEFAULT_GRINDER, METHODS


def log_brew(
    settings: Settings,
    bag_id: str,
    method: str,
    dose_g: float,
    grind_setting: str,
    *,
    water_g: float | None = None,
    yield_g: float | None = None,
    time_s: float | None = None,
    grinder: str = DEFAULT_GRINDER,
    temperature_c: float | None = None,
    bypass_water_g: float | None = None,
    pressure_bar: float | None = None,
    rating: int | None = None,
    taste_notes: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    get_bag(settings, bag_id)
    method = _method(method)
    grind_setting = _required(grind_setting, "grind_setting")
    grinder = _required(grinder, "grinder")
    taste_notes = _optional(taste_notes)
    notes = _optional(notes)
    _validate_recipe(method, dose_g, water_g, yield_g, bypass_water_g, pressure_bar)
    _positive_optional(time_s, "time_s")
    _positive_optional(temperature_c, "temperature_c")
    if rating is not None and rating not in range(1, 6):
        raise ValueError("rating must be between 1 and 5")
    if rating is None and taste_notes is None:
        raise ValueError("rating or taste_notes is required")

    brew_id = str(uuid4())
    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute(
            """INSERT INTO brews
               (id, bag_id, method, dose_g, water_g, yield_g, time_s,
                grind_setting, grinder, temperature_c, bypass_water_g, pressure_bar,
                rating, taste_notes, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                brew_id, bag_id, method, dose_g, water_g,
                yield_g, time_s, grind_setting, grinder, temperature_c,
                bypass_water_g, pressure_bar, rating, taste_notes, notes,
                datetime.now(UTC).isoformat(),
            ),
        )
    return history(settings, brew_id=brew_id, limit=1)[0]


def history(
    settings: Settings,
    bag_id: str | None = None,
    method: str | None = None,
    limit: int = 20,
    *,
    brew_id: str | None = None,
    name: str | None = None,
    roaster: str | None = None,
    roast_level: str | None = None,
    origin: str | None = None,
    process: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    clauses: list[str] = []
    parameters: list[Any] = []
    if bag_id is not None:
        get_bag(settings, bag_id)
        clauses.append("brews.bag_id = ?")
        parameters.append(bag_id)
    if brew_id is not None:
        clauses.append("brews.id = ?")
        parameters.append(brew_id)
    if method is not None:
        clauses.append("brews.method = ?")
        parameters.append(_method(method))
    for column, value in (
        ("name", name),
        ("roaster", roaster),
        ("roast_level", roast_level),
        ("origin", origin),
        ("process", process),
    ):
        if value is not None:
            clauses.append(f"bags.{column} = ? COLLATE NOCASE")
            parameters.append(_required(value, column))
    if start_date is not None:
        clauses.append("date(brews.created_at) >= ?")
        parameters.append(start_date)
    if end_date is not None:
        clauses.append("date(brews.created_at) <= ?")
        parameters.append(end_date)
    query = _history_query()
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY brews.created_at DESC, brews.id DESC LIMIT ?"
    parameters.append(min(limit, 100))
    with connect(settings.data_dir / DB_FILENAME) as connection:
        return [_brew(row) for row in connection.execute(query, parameters)]


def _history_query() -> str:
    return """SELECT brews.*,
                     bags.name AS bag_name,
                     bags.roaster AS bag_roaster,
                     bags.roast_date AS bag_roast_date,
                     bags.roast_level AS bag_roast_level,
                     bags.origin AS bag_origin,
                     bags.process AS bag_process,
                     bags.status AS bag_status,
                     bags.notes AS bag_notes,
                     bags.created_at AS bag_created_at
              FROM brews JOIN bags ON bags.id = brews.bag_id"""


def _brew(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["bag"] = {
        "id": result["bag_id"],
        "name": result.pop("bag_name"),
        "roaster": result.pop("bag_roaster"),
        "roast_date": result.pop("bag_roast_date"),
        "roast_level": result.pop("bag_roast_level"),
        "origin": result.pop("bag_origin"),
        "process": result.pop("bag_process"),
        "status": result.pop("bag_status"),
        "notes": result.pop("bag_notes"),
        "created_at": result.pop("bag_created_at"),
    }
    return result


def _validate_recipe(
    method: str,
    dose_g: float,
    water_g: float | None,
    yield_g: float | None,
    bypass_water_g: float | None, pressure_bar: float | None,
) -> None:
    _positive(dose_g, "dose_g")
    if method == "espresso":
        if water_g is not None:
            raise ValueError("espresso does not use water_g")
        if bypass_water_g is not None:
            raise ValueError("espresso does not use bypass_water_g")
        _positive_optional(yield_g, "yield_g")
        _positive_optional(pressure_bar, "pressure_bar")
    else:
        if water_g is None or yield_g is not None:
            raise ValueError("filter methods require water_g and do not use yield_g")
        if pressure_bar is not None:
            raise ValueError("filter methods do not use pressure_bar")
        _positive(water_g, "water_g")
        _positive_optional(bypass_water_g, "bypass_water_g")


def _method(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in METHODS:
        raise ValueError(f"method must be one of {', '.join(sorted(METHODS))}")
    return cleaned


def _required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    return cleaned


def _optional(value: str | None) -> str | None:
    cleaned = value.strip() if value else None
    return cleaned or None


def _positive(value: float, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field} must be positive")


def _positive_optional(value: float | None, field: str) -> None:
    if value is not None:
        _positive(value, field)
