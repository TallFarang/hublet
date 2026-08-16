"""Small public-safe CSV fixtures for Food importer tests."""

from __future__ import annotations

import csv
from pathlib import Path


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def catalogue_row(**overrides: str) -> dict[str, str]:
    row = {
        "Restaurant": "Example Kitchen",
        "Category": "Mains",
        "Item": "Rice bowl",
        "Calories": "600",
        "Carbs (g)": "75",
        "Protein (g)": "30",
        "Fat (g)": "20",
        "Calories Low": "550",
        "Calories High": "650",
        "Portion Basis": "one bowl",
        "Source": "published menu",
        "Confidence": "exact",
        "Last Reviewed": "2026-08-01",
        "Evidence Class": "official",
        "Evidence Basis": "menu",
    }
    row.update(overrides)
    return row


def ledger_row(record_id: str, **overrides: str) -> dict[str, str]:
    row = {
        "record_id": record_id,
        "order_id": "order-1",
        "purchase_datetime": "2026-08-09T11:00:00+07:00",
        "consumption_datetime": "2026-08-09T12:00:00+07:00",
        "meal_slot": "lunch",
        "restaurant": "Example Kitchen",
        "item": "Rice bowl",
        "quantity_ordered": "1",
        "portion_consumed": "one bowl",
        "status": "eaten",
        "calories": "600",
        "calories_low": "550",
        "calories_high": "650",
        "protein_g": "30",
        "carbs_g": "75",
        "fat_g": "20",
        "confidence": "exact",
        "nutrition_source": "published menu",
        "notes": "",
        "updated_at": "2026-08-09T13:00:00+07:00",
        "apple_health_export_id": "",
        "apple_health_exported_at": "",
        "nutrition_evidence": "official",
    }
    row.update(overrides)
    return row
