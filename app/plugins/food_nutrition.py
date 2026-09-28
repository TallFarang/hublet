"""Food nutrition catalogue operations."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.db import connect
from app.plugins.food_rows import nutrition_from_row
from app.plugins.food_schema import DB_FILENAME
from app.plugins.food_types import SearchLimit, SearchOffset
from app.plugins.food_validation import identifier, normalise_nutrition, now, optional_text


def upsert_nutrition(
    settings: Settings,
    nutrition_id: str,
    restaurant: str,
    item: str,
    calories: float,
    protein_g: float | None,
    carbs_g: float | None,
    fat_g: float | None,
    portion_basis: str,
    source: str,
    confidence: str,
    evidence_class: str,
    *,
    category: str | None = None,
    calories_min: float | None = None,
    calories_max: float | None = None,
    review_date: str | None = None,
    evidence_basis: str | None = None,
    updated_at: str | None = None,
    macros_complete: bool | None = None,
) -> dict[str, Any]:
    """Replace nutrition values, preserving completeness unless explicitly supplied."""

    with connect(settings.data_dir / DB_FILENAME) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if macros_complete is None:
            existing = connection.execute(
                "SELECT macros_complete FROM nutrition WHERE id = ?",
                (identifier(nutrition_id, "nutrition_id"),),
            ).fetchone()
            macros_complete = bool(existing[0]) if existing is not None else True
        values = normalise_nutrition(
            nutrition_id=nutrition_id,
            macros_complete=macros_complete,
            restaurant=restaurant,
            category=category,
            item=item,
            calories=calories,
            calories_min=calories_min,
            calories_max=calories_max,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
            portion_basis=portion_basis,
            source=source,
            confidence=confidence,
            review_date=review_date,
            evidence_class=evidence_class,
            evidence_basis=evidence_basis,
            updated_at=updated_at or now(),
        )
        connection.execute(
            """INSERT INTO nutrition
               (id, restaurant, category, item, calories, calories_min, calories_max,
                protein_g, carbs_g, fat_g, portion_basis, source, confidence,
                review_date, evidence_class, evidence_basis, updated_at, macros_complete)
               VALUES (:id, :restaurant, :category, :item, :calories, :calories_min,
                       :calories_max, :protein_g, :carbs_g, :fat_g, :portion_basis,
                       :source, :confidence, :review_date, :evidence_class,
                       :evidence_basis, :updated_at, :macros_complete)
               ON CONFLICT(id) DO UPDATE SET
                   restaurant=excluded.restaurant, category=excluded.category,
                   item=excluded.item, calories=excluded.calories,
                   calories_min=excluded.calories_min, calories_max=excluded.calories_max,
                   protein_g=excluded.protein_g, carbs_g=excluded.carbs_g,
                   fat_g=excluded.fat_g, macros_complete=excluded.macros_complete,
                   portion_basis=excluded.portion_basis,
                   source=excluded.source, confidence=excluded.confidence,
                   review_date=excluded.review_date, evidence_class=excluded.evidence_class,
                   evidence_basis=excluded.evidence_basis, updated_at=excluded.updated_at""",
            values,
        )
        row = connection.execute("SELECT * FROM nutrition WHERE id = ?", (values["id"],)).fetchone()
        return nutrition_from_row(row)


def get_nutrition(settings: Settings, nutrition_id: str) -> dict[str, Any]:
    with connect(settings.data_dir / DB_FILENAME) as connection:
        row = connection.execute(
            "SELECT * FROM nutrition WHERE id = ?", (identifier(nutrition_id, "nutrition_id"),)
        ).fetchone()
    if row is None:
        raise ValueError("nutrition entry not found")
    return nutrition_from_row(row)


def find_nutrition(
    settings: Settings,
    *,
    restaurant: str | None = None,
    item: str | None = None,
    category: str | None = None,
    evidence_class: str | None = None,
    limit: SearchLimit = 50,
    offset: SearchOffset = 0,
) -> dict[str, Any]:
    """Find a deterministic page of exact-then-partial nutrition matches."""

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must not be negative")
    filters = {
        "restaurant": optional_text(restaurant),
        "item": optional_text(item),
        "category": optional_text(category),
        "evidence_class": optional_text(evidence_class),
    }
    clauses, where_values, ranks, rank_values = [], [], [], []
    for field, value in filters.items():
        if value is None:
            continue
        clauses.append(f"{field} LIKE ? COLLATE NOCASE")
        where_values.append(f"%{value}%")
        ranks.append(f"CASE WHEN lower({field}) = lower(?) THEN 0 ELSE 1 END")
        rank_values.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    order = ", ".join([*ranks, "restaurant", "item", "portion_basis", "id"])
    with connect(settings.data_dir / DB_FILENAME) as connection:
        total = connection.execute(
            "SELECT COUNT(*) FROM nutrition" + where, where_values
        ).fetchone()[0]
        rows = connection.execute(
            f"SELECT * FROM nutrition{where} ORDER BY {order} LIMIT ? OFFSET ?",
            [*where_values, *rank_values, limit, offset],
        ).fetchall()
    next_offset = offset + len(rows)
    return {
        "items": [nutrition_from_row(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset if next_offset < total else None,
    }
