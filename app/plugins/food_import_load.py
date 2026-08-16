"""Transactional loading and verification for the Food recovery importer."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db import connect, migrate
from app.plugins.food_import_catalogue import catalogue_values
from app.plugins.food_import_collapse import collapse_corrections
from app.plugins.food_import_csv import number, value
from app.plugins.food_import_records import NUTRIENTS, ledger_values
from app.plugins.food_schema import MIGRATIONS


def load_database(
    database: Path,
    ledger_rows: list[dict[str, str]],
    catalogue_rows: list[dict[str, str]],
) -> dict[str, Any]:
    imported_at = datetime.now(UTC).isoformat()
    canonical_rows, collapse = collapse_corrections(ledger_rows)
    nutrition = catalogue_values(catalogue_rows, imported_at)
    records, legacy = ledger_values(canonical_rows, nutrition, imported_at)
    migrate(database, MIGRATIONS)
    with connect(database) as connection:
        counts = connection.execute(
            "SELECT (SELECT COUNT(*) FROM nutrition), (SELECT COUNT(*) FROM records)"
        ).fetchone()
        if tuple(counts) != (0, 0):
            raise ValueError("food.db must be empty before import")
        for values in [*nutrition, *legacy]:
            _insert_nutrition(connection, values)
        for values in records:
            _insert_record(connection, values)
        _verify(connection, canonical_rows, records)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    statuses = Counter(record["status"] for record in records)
    unresolved = [
        {
            "record_id": record["id"],
            "date": record["consumption_date_local"] or record["purchase_date_local"],
            "restaurant": record["restaurant"],
            "item": record["item"],
        }
        for record in records
        if record["status"] == "uncertain"
    ]
    return {
        **collapse,
        "record_count": len(records),
        "catalogue_count": len(nutrition),
        "legacy_nutrition_count": len(legacy),
        "nutrition_count": len(nutrition) + len(legacy),
        "status_counts": dict(sorted(statuses.items())),
        "unresolved_records": unresolved,
        "confirmed_daily_totals": _source_totals(canonical_rows),
        "integrity": "ok",
    }


def _verify(
    connection: sqlite3.Connection,
    source_rows: list[dict[str, str]],
    records: list[dict[str, Any]],
) -> None:
    imported_ids = {row[0] for row in connection.execute("SELECT id FROM records")}
    expected_ids = {record["id"] for record in records}
    if imported_ids != expected_ids or len(imported_ids) != len(source_rows):
        raise RuntimeError("imported canonical record IDs do not match the ledger")
    expected = _source_totals(source_rows)
    actual: dict[str, dict[str, float]] = defaultdict(_empty_totals)
    rows = connection.execute(
        """SELECT records.consumption_date_local, records.nutrition_multiplier,
                  nutrition.calories, nutrition.protein_g, nutrition.carbs_g, nutrition.fat_g
           FROM records JOIN nutrition ON nutrition.id = records.nutrition_id
           WHERE records.status = 'eaten' AND records.consumption_date_local IS NOT NULL"""
    )
    for row in rows:
        for field in NUTRIENTS:
            actual[row["consumption_date_local"]][field] += row[field] * row["nutrition_multiplier"]
    for current_date, totals in expected.items():
        for field, expected_value in totals.items():
            if abs(actual[current_date][field] - expected_value) > 1e-6:
                raise RuntimeError(f"imported {field} total differs on {current_date}")


def _source_totals(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = defaultdict(_empty_totals)
    for row in rows:
        if (value(row, "status") or "eaten").casefold() != "eaten":
            continue
        consumed = value(row, "consumption_datetime")
        if consumed is None or not any(value(row, field) is not None for field in NUTRIENTS):
            continue
        current_date = datetime.fromisoformat(consumed).date().isoformat()
        for field in NUTRIENTS:
            totals[current_date][field] += number(row, field, 0)
    return {day: dict(values) for day, values in sorted(totals.items())}


def _empty_totals() -> dict[str, float]:
    return {field: 0.0 for field in NUTRIENTS}


def _insert_nutrition(connection: sqlite3.Connection, values: dict[str, Any]) -> None:
    connection.execute(
        """INSERT INTO nutrition
           (id, restaurant, category, item, calories, calories_min, calories_max,
            protein_g, carbs_g, fat_g, portion_basis, source, confidence,
            review_date, evidence_class, evidence_basis, updated_at)
           VALUES (:id, :restaurant, :category, :item, :calories, :calories_min,
                   :calories_max, :protein_g, :carbs_g, :fat_g, :portion_basis,
                   :source, :confidence, :review_date, :evidence_class,
                   :evidence_basis, :updated_at)""",
        values,
    )


def _insert_record(connection: sqlite3.Connection, values: dict[str, Any]) -> None:
    fields = tuple(values)
    placeholders = ", ".join("?" for _ in fields)
    connection.execute(
        f"INSERT INTO records ({', '.join(fields)}) VALUES ({placeholders})",
        [values[field] for field in fields],
    )
