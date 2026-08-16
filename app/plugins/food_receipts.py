"""Atomic and idempotent Food receipt ingestion."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.config import Settings
from app.db import connect
from app.plugins.food_rows import (
    joined_record,
    receipt_records,
    require_nutrition,
    unambiguous_nutrition,
)
from app.plugins.food_schema import DB_FILENAME
from app.plugins.food_types import ReceiptItem
from app.plugins.food_validation import (
    identifier,
    iso_date,
    now,
    optional_identifier,
    optional_text,
    positive_number,
    required_text,
    status,
    utc_timestamp,
)


def ingest_receipt(
    settings: Settings,
    items: list[ReceiptItem],
    *,
    order_id: str | None = None,
    email_message_id: str | None = None,
    receipt_id: str | None = None,
    restaurant: str | None = None,
    purchase_timestamp_utc: str | None = None,
    purchase_date_local: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Atomically ingest parsed receipt facts with order-then-message idempotency."""

    if not isinstance(items, list) or not items:
        raise ValueError("items must contain at least one receipt item")
    order_id, email_message_id = optional_text(order_id), optional_text(email_message_id)
    receipt_id, restaurant, notes = map(optional_text, (receipt_id, restaurant, notes))
    if order_id is None and email_message_id is None:
        raise ValueError("order_id or email_message_id is required")
    purchase_timestamp_utc = utc_timestamp(purchase_timestamp_utc, "purchase_timestamp_utc")
    purchase_date_local = iso_date(purchase_date_local, "purchase_date_local")
    if purchase_timestamp_utc is not None and purchase_date_local is None:
        raise ValueError("purchase_date_local is required with purchase_timestamp_utc")
    canonical = [_normalise_item(item, restaurant) for item in items]
    facts = {
        "receipt_id": receipt_id,
        "order_id": order_id,
        "email_message_id": email_message_id,
        "restaurant": restaurant,
        "purchase_timestamp_utc": purchase_timestamp_utc,
        "purchase_date_local": purchase_date_local,
        "notes": notes,
        "items": canonical,
    }
    fingerprint = hashlib.sha256(_json(facts).encode()).hexdigest()
    seed = order_id or email_message_id
    if seed is None:
        raise ValueError("order_id or email_message_id is required")

    with connect(settings.data_dir / DB_FILENAME) as connection:
        existing = receipt_records(connection, order_id, email_message_id)
        if existing:
            if any(row["ingest_fingerprint"] != fingerprint for row in existing):
                raise ValueError("receipt conflicts with an existing order or email message")
            return {
                "created": False,
                "records": [joined_record(connection, row["id"]) for row in existing],
            }
        inserted = []
        for position, item in enumerate(canonical, start=1):
            record_id = item["record_id"] or _record_id(seed, position)
            nutrition_id = item["nutrition_id"]
            if nutrition_id is not None:
                require_nutrition(connection, nutrition_id)
            else:
                nutrition_id = unambiguous_nutrition(
                    connection, item["restaurant"], item["item"], item["portion_text"]
                )
            connection.execute(
                """INSERT INTO records
                   (id, receipt_id, order_id, email_message_id, receipt_line,
                    purchase_timestamp_utc, purchase_date_local, restaurant, item,
                    quantity, portion_text, status, nutrition_id, nutrition_multiplier,
                    notes, updated_at, update_reason, ingest_fingerprint)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record_id, receipt_id, order_id, email_message_id, item["receipt_line"],
                    purchase_timestamp_utc, purchase_date_local, item["restaurant"],
                    item["item"], item["quantity"], item["portion_text"], item["status"],
                    nutrition_id, item["nutrition_multiplier"], _join_notes(notes, item["notes"]),
                    now(), "receipt ingestion", fingerprint,
                ),
            )
            inserted.append(record_id)
        return {
            "created": True,
            "records": [joined_record(connection, record_id) for record_id in inserted],
        }


def _normalise_item(item: Any, receipt_restaurant: str | None) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise TypeError("every receipt item must be an object")
    restaurant = optional_text(item.get("restaurant")) or receipt_restaurant
    return {
        "record_id": optional_identifier(item.get("record_id"), "record_id"),
        "receipt_line": optional_text(item.get("receipt_line")),
        "restaurant": required_text(restaurant, "restaurant"),
        "item": required_text(item.get("item"), "item"),
        "quantity": positive_number(item.get("quantity", 1), "quantity"),
        "portion_text": optional_text(item.get("portion_text")),
        "status": status(item.get("status", "uncertain")),
        "nutrition_id": optional_identifier(item.get("nutrition_id"), "nutrition_id"),
        "nutrition_multiplier": positive_number(
            item.get("nutrition_multiplier", 1), "nutrition_multiplier"
        ),
        "notes": optional_text(item.get("notes")),
    }


def _record_id(seed: str, position: int) -> str:
    digest = hashlib.sha256(f"{seed}\0{position}".encode()).hexdigest()[:24]
    return identifier(f"receipt-{digest}", "record_id")


def _join_notes(parent: str | None, child: str | None) -> str | None:
    return "\n".join(value for value in (parent, child) if value) or None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
