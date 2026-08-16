"""Direct canonical Food record corrections."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.db import connect
from app.plugins.food_rows import joined_record, require_nutrition
from app.plugins.food_schema import DB_FILENAME
from app.plugins.food_types import RecordCorrection
from app.plugins.food_validation import identifier, normalise_record, now, required_text

CORRECTABLE_FIELDS = frozenset(RecordCorrection.__optional_keys__)


def correct_record(
    settings: Settings,
    record_id: str,
    updates: RecordCorrection,
    update_reason: str,
) -> dict[str, Any]:
    """Amend the canonical record directly and retain only the latest reason."""

    record_id = identifier(record_id, "record_id")
    update_reason = required_text(update_reason, "update_reason")
    if not isinstance(updates, dict) or not updates:
        raise ValueError("updates must contain at least one allowed field")
    unknown = sorted(set(updates) - CORRECTABLE_FIELDS)
    if unknown:
        raise ValueError(f"unsupported record fields: {', '.join(unknown)}")
    with connect(settings.data_dir / DB_FILENAME) as connection:
        row = connection.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            raise ValueError("food record not found")
        candidate = dict(row)
        candidate.update(updates)
        candidate.update(updated_at=now(), update_reason=update_reason)
        normalise_record(candidate)
        if candidate["nutrition_id"] is not None:
            require_nutrition(connection, candidate["nutrition_id"])
        assignments = ", ".join(f"{field} = ?" for field in updates)
        connection.execute(
            f"UPDATE records SET {assignments}, updated_at = ?, update_reason = ? WHERE id = ?",
            [*[candidate[field] for field in updates], candidate["updated_at"], update_reason, record_id],
        )
        return joined_record(connection, record_id)
