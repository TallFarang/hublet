"""Convert canonical legacy ledger rows into Food records and nutrition variants."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.plugins.food_import_csv import (
    deterministic_id,
    normal,
    number,
    optional_number,
    quantity,
    required,
    semantic_key,
    source_datetime,
    timestamp,
    value,
)
from app.plugins.food_validation import identifier, normalise_nutrition, normalise_record

NUTRIENTS = ("calories", "protein_g", "carbs_g", "fat_g")


def ledger_values(
    rows: list[dict[str, str]], catalogue: list[dict[str, Any]], imported_at: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matches: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in catalogue:
        matches[(normal(entry["restaurant"]), normal(entry["item"]))].append(entry)
    legacy: dict[str, dict[str, Any]] = {}
    records = []
    for row in rows:
        restaurant, item = required(row, "restaurant"), required(row, "item")
        portion = value(row, "portion_consumed")
        selected = _select_variant(matches.get((normal(restaurant), normal(item)), []), portion)
        ledger_nutrition = _ledger_nutrition(row)
        if ledger_nutrition is not None and (
            selected is None
            or any(abs(selected[field] - ledger_nutrition[field]) > 1e-6 for field in NUTRIENTS)
        ):
            selected = _legacy_variant(row, restaurant, item, portion, imported_at)
            legacy.setdefault(selected["id"], selected)
        purchase_timestamp, purchase_date = source_datetime(row, "purchase_datetime")
        consumption_timestamp, consumption_date = source_datetime(row, "consumption_datetime")
        record = {
            "id": identifier(required(row, "record_id"), "record_id"),
            "receipt_id": None,
            "order_id": value(row, "order_id"),
            "email_message_id": None,
            "receipt_line": None,
            "purchase_timestamp_utc": purchase_timestamp,
            "purchase_date_local": purchase_date,
            "consumption_timestamp_utc": consumption_timestamp,
            "consumption_date_local": consumption_date,
            "meal_slot": value(row, "meal_slot"),
            "restaurant": restaurant,
            "item": item,
            "quantity": quantity(row),
            "portion_text": portion,
            "status": (value(row, "status") or "eaten").casefold(),
            "nutrition_id": selected["id"] if selected else None,
            "nutrition_multiplier": 1,
            "notes": value(row, "notes"),
            "apple_health_reference": value(row, "apple_health_export_id"),
            "apple_health_sample_uuid": None,
            "apple_health_synced_at": timestamp(row, "apple_health_exported_at"),
            "updated_at": timestamp(row, "updated_at") or imported_at,
            "update_reason": value(row, "update_reason") or "legacy CSV import",
            "ingest_fingerprint": None,
        }
        records.append(normalise_record(record))
    return records, list(legacy.values())


def _select_variant(
    candidates: list[dict[str, Any]], portion: str | None
) -> dict[str, Any] | None:
    if portion:
        exact = [candidate for candidate in candidates if normal(candidate["portion_basis"]) == normal(portion)]
        if len(exact) == 1:
            return exact[0]
    return candidates[0] if len(candidates) == 1 else None


def _ledger_nutrition(row: dict[str, str]) -> dict[str, float] | None:
    if not any(value(row, field) is not None for field in NUTRIENTS):
        return None
    return {field: number(row, field, 0) for field in NUTRIENTS}


def _legacy_variant(
    row: dict[str, str], restaurant: str, item: str, portion: str | None, imported_at: str
) -> dict[str, Any]:
    facts = _ledger_nutrition(row)
    if facts is None:
        raise ValueError("legacy nutrition facts are required")
    basis = portion or "legacy ledger portion"
    key = semantic_key(restaurant, item, basis, *(str(facts[field]) for field in NUTRIENTS))
    return normalise_nutrition(
        nutrition_id=deterministic_id("nutrition-legacy", key),
        restaurant=restaurant,
        category=None,
        item=item,
        calories=facts["calories"],
        calories_min=optional_number(row, "calories_low"),
        calories_max=optional_number(row, "calories_high"),
        protein_g=facts["protein_g"],
        carbs_g=facts["carbs_g"],
        fat_g=facts["fat_g"],
        portion_basis=basis,
        source=value(row, "nutrition_source") or "legacy ledger import",
        confidence=(value(row, "confidence") or "unknown").casefold(),
        review_date=None,
        evidence_class=value(row, "nutrition_evidence") or "legacy",
        evidence_basis="Legacy variant preserving source ledger totals",
        updated_at=timestamp(row, "updated_at") or imported_at,
    )
