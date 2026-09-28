from __future__ import annotations

from typing import Any


def nutrition_values(**overrides: Any) -> dict[str, Any]:
    return {
        "nutrition_id": "meal",
        "restaurant": "Grain",
        "item": "Calorie-only bowl",
        "calories": 600,
        "protein_g": None,
        "carbs_g": None,
        "fat_g": None,
        "portion_basis": "one bowl",
        "source": "menu",
        "confidence": "high",
        "evidence_class": "fact",
        "macros_complete": False,
        **overrides,
    }
