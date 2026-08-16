"""Food consumption writes and record queries."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.db import connect
from app.plugins.food_rows import (
    RECORD_SELECT,
    joined_record,
    record_from_join,
    require_nutrition,
    unambiguous_nutrition,
)
from app.plugins.food_schema import DB_FILENAME
from app.plugins.food_validation import (
    identifier,
    iso_date,
    now,
    optional_identifier,
    optional_text,
    positive_number,
    required_text,
    utc_timestamp,
)
from app.plugins.food_validation import status as normalise_status


def record_consumption(
    settings: Settings,
    record_id: str,
    consumption_date_local: str,
    meal_slot: str,
    *,
    consumption_timestamp_utc: str | None = None,
    portion_text: str | None = None,
    nutrition_id: str | None = None,
    nutrition_multiplier: float = 1,
    restaurant: str | None = None,
    item: str | None = None,
    quantity: float = 1,
    notes: str | None = None,
) -> dict[str, Any]:
    """Confirm a receipt item or create a caller-ID-supplied standalone record."""

    record_id = identifier(record_id, "record_id")
    consumed = iso_date(consumption_date_local, "consumption_date_local", required=True)
    timestamp = utc_timestamp(consumption_timestamp_utc, "consumption_timestamp_utc")
    meal_slot = required_text(meal_slot, "meal_slot")
    portion_text, notes = optional_text(portion_text), optional_text(notes)
    multiplier = positive_number(nutrition_multiplier, "nutrition_multiplier")
    quantity = positive_number(quantity, "quantity")
    nutrition_id = optional_identifier(nutrition_id, "nutrition_id")
    with connect(settings.data_dir / DB_FILENAME) as connection:
        existing = connection.execute(
            "SELECT * FROM records WHERE id = ?", (record_id,)
        ).fetchone()
        if nutrition_id is not None:
            require_nutrition(connection, nutrition_id)
        if existing is None:
            restaurant = required_text(restaurant, "restaurant")
            item = required_text(item, "item")
            nutrition_id = nutrition_id or unambiguous_nutrition(
                connection, restaurant, item, portion_text
            )
            connection.execute(
                """INSERT INTO records
                   (id, consumption_timestamp_utc, consumption_date_local, meal_slot,
                    restaurant, item, quantity, portion_text, status, nutrition_id,
                    nutrition_multiplier, notes, updated_at, update_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'eaten', ?, ?, ?, ?, ?)""",
                (
                    record_id, timestamp, consumed, meal_slot, restaurant, item, quantity,
                    portion_text, nutrition_id, multiplier, notes, now(), "consumption recorded",
                ),
            )
        else:
            resolved = nutrition_id if nutrition_id is not None else existing["nutrition_id"]
            connection.execute(
                """UPDATE records SET
                   consumption_timestamp_utc=?, consumption_date_local=?, meal_slot=?,
                   portion_text=COALESCE(?, portion_text), status='eaten', nutrition_id=?,
                   nutrition_multiplier=?, notes=COALESCE(?, notes), updated_at=?, update_reason=?
                   WHERE id=?""",
                (
                    timestamp, consumed, meal_slot, portion_text, resolved, multiplier, notes,
                    now(), "consumption recorded", record_id,
                ),
            )
        return joined_record(connection, record_id)


def query_records(
    settings: Settings,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    meal_slot: str | None = None,
    restaurant: str | None = None,
    order_id: str | None = None,
    text: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Query records joined to current nutrition values and provenance."""

    start, end = _date_range(start_date, end_date)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    clauses: list[str] = []
    parameters: list[Any] = []
    effective_date = "COALESCE(records.consumption_date_local, records.purchase_date_local)"
    if start is not None:
        clauses.append(f"{effective_date} >= ?")
        parameters.append(start)
    if end is not None:
        clauses.append(f"{effective_date} <= ?")
        parameters.append(end)
    if status is not None:
        clauses.append("records.status = ?")
        parameters.append(normalise_status(status))
    for field, value in (("meal_slot", meal_slot), ("restaurant", restaurant), ("order_id", order_id)):
        value = optional_text(value)
        if value is not None:
            clauses.append(f"records.{field} = ? COLLATE NOCASE")
            parameters.append(value)
    text = optional_text(text)
    if text is not None:
        clauses.append(
            "(records.restaurant LIKE ? COLLATE NOCASE OR records.item LIKE ? COLLATE NOCASE "
            "OR records.receipt_line LIKE ? COLLATE NOCASE OR records.notes LIKE ? COLLATE NOCASE)"
        )
        parameters.extend([f"%{text}%"] * 4)
    sql = RECORD_SELECT + (" WHERE " + " AND ".join(clauses) if clauses else "")
    sql += (
        " ORDER BY COALESCE(records.consumption_date_local, records.purchase_date_local) DESC, "
        "records.id DESC LIMIT ?"
    )
    with connect(settings.data_dir / DB_FILENAME) as connection:
        return [
            record_from_join(row)
            for row in connection.execute(sql, [*parameters, limit]).fetchall()
        ]


def _date_range(start_date: str | None, end_date: str | None) -> tuple[str | None, str | None]:
    start = iso_date(start_date, "start_date")
    end = iso_date(end_date, "end_date")
    if (start is None) != (end is None):
        raise ValueError("start_date and end_date must be supplied together")
    if start is not None and start > end:
        raise ValueError("start_date must not be after end_date")
    if start is not None:
        from datetime import date

        if (date.fromisoformat(end) - date.fromisoformat(start)).days > 366:
            raise ValueError("date range must not exceed 367 days")
    return start, end
