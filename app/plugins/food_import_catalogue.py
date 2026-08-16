"""Convert the strict legacy nutrition catalogue to Food rows."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.plugins.food_import_csv import (
    deterministic_id,
    number,
    optional_number,
    required,
    semantic_key,
    value,
)
from app.plugins.food_validation import normalise_nutrition


def catalogue_values(rows: list[dict[str, str]], imported_at: str) -> list[dict[str, Any]]:
    values = []
    occurrences: Counter[str] = Counter()
    for row in rows:
        restaurant, item = required(row, "restaurant"), required(row, "item")
        portion = value(row, "portion_basis") or "one serving"
        low, high = optional_number(row, "calories_low"), optional_number(row, "calories_high")
        calories = optional_number(row, "calories")
        if calories is None and low is not None and high is not None:
            calories = (low + high) / 2
        if calories is None:
            raise ValueError("CSV number is required: calories")
        semantic = semantic_key(
            restaurant, item, portion, str(calories), str(low), str(high),
            str(number(row, "protein_g", 0)), str(number(row, "carbs_g", 0)),
            str(number(row, "fat_g", 0)),
        )
        occurrences[semantic] += 1
        values.append(
            normalise_nutrition(
                nutrition_id=deterministic_id(
                    "nutrition-catalogue", semantic, str(occurrences[semantic])
                ),
                restaurant=restaurant,
                category=value(row, "category"),
                item=item,
                calories=calories,
                calories_min=low,
                calories_max=high,
                protein_g=number(row, "protein_g", 0),
                carbs_g=number(row, "carbs_g", 0),
                fat_g=number(row, "fat_g", 0),
                portion_basis=portion,
                source=value(row, "source") or "legacy catalogue import",
                confidence=(value(row, "confidence") or "unknown").casefold(),
                review_date=value(row, "last_reviewed"),
                evidence_class=value(row, "evidence_class") or "legacy",
                evidence_basis=value(row, "evidence_basis"),
                updated_at=imported_at,
            )
        )
    return values
