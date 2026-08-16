"""Shared Food database row queries and projections."""

from __future__ import annotations

import sqlite3
from typing import Any

from app.plugins.food_validation import clean_number

NUTRITION_FIELDS = (
    "id",
    "restaurant",
    "category",
    "item",
    "calories",
    "calories_min",
    "calories_max",
    "protein_g",
    "carbs_g",
    "fat_g",
    "portion_basis",
    "source",
    "confidence",
    "review_date",
    "evidence_class",
    "evidence_basis",
    "updated_at",
)
RECORD_SELECT = """SELECT records.*,
    nutrition.id AS nutrition_fact_id,
    nutrition.restaurant AS nutrition_restaurant,
    nutrition.category AS nutrition_category,
    nutrition.item AS nutrition_item,
    nutrition.calories AS nutrition_calories,
    nutrition.calories_min AS nutrition_calories_min,
    nutrition.calories_max AS nutrition_calories_max,
    nutrition.protein_g AS nutrition_protein_g,
    nutrition.carbs_g AS nutrition_carbs_g,
    nutrition.fat_g AS nutrition_fat_g,
    nutrition.portion_basis AS nutrition_portion_basis,
    nutrition.source AS nutrition_source,
    nutrition.confidence AS nutrition_confidence,
    nutrition.review_date AS nutrition_review_date,
    nutrition.evidence_class AS nutrition_evidence_class,
    nutrition.evidence_basis AS nutrition_evidence_basis,
    nutrition.updated_at AS nutrition_updated_at
    FROM records LEFT JOIN nutrition ON nutrition.id = records.nutrition_id"""


def joined_record(connection: sqlite3.Connection, record_id: str) -> dict[str, Any]:
    row = connection.execute(RECORD_SELECT + " WHERE records.id = ?", (record_id,)).fetchone()
    if row is None:
        raise ValueError("food record not found")
    return record_from_join(row)


def record_from_join(row: sqlite3.Row) -> dict[str, Any]:
    raw = dict(row)
    nutrition = None
    calculated = None
    if raw["nutrition_id"] is not None:
        nutrition = {
            field: raw.pop("nutrition_fact_id" if field == "id" else f"nutrition_{field}")
            for field in NUTRITION_FIELDS
        }
        calculated = {
            field: clean_number(nutrition[field] * raw["nutrition_multiplier"])
            for field in ("calories", "protein_g", "carbs_g", "fat_g")
        }
    else:
        for field in NUTRITION_FIELDS:
            raw.pop("nutrition_fact_id" if field == "id" else f"nutrition_{field}")
    raw["nutrition"] = nutrition
    raw["calculated_nutrition"] = calculated
    return raw


def receipt_records(
    connection: sqlite3.Connection, order_id: str | None, email_message_id: str | None
) -> list[sqlite3.Row]:
    if order_id is not None:
        rows = connection.execute(
            "SELECT * FROM records WHERE order_id = ? ORDER BY rowid", (order_id,)
        ).fetchall()
        if rows:
            return rows
    if email_message_id is not None:
        return connection.execute(
            "SELECT * FROM records WHERE email_message_id = ? ORDER BY rowid",
            (email_message_id,),
        ).fetchall()
    return []


def unambiguous_nutrition(
    connection: sqlite3.Connection, restaurant: str, item: str, portion_text: str | None
) -> str | None:
    rows = connection.execute(
        """SELECT id, portion_basis FROM nutrition
           WHERE lower(trim(restaurant)) = lower(trim(?))
             AND lower(trim(item)) = lower(trim(?))
           ORDER BY id""",
        (restaurant, item),
    ).fetchall()
    if portion_text is not None:
        matches = [
            row for row in rows if row["portion_basis"].casefold() == portion_text.casefold()
        ]
        if len(matches) == 1:
            return matches[0]["id"]
    return rows[0]["id"] if len(rows) == 1 else None


def require_nutrition(connection: sqlite3.Connection, nutrition_id: str) -> None:
    exists = connection.execute(
        "SELECT 1 FROM nutrition WHERE id = ?", (nutrition_id,)
    ).fetchone()
    if exists is None:
        raise ValueError("nutrition entry not found")
