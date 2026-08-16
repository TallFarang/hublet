"""Food input normalization shared by live writes and recovery imports."""

from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.plugins.food_schema import CONFIDENCES, STATUSES

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


def normalise_nutrition(**values: Any) -> dict[str, Any]:
    evidence = required_text(values["evidence_class"], "evidence_class")
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9 ._-]{0,99}", evidence) is None:
        raise ValueError("evidence_class contains unsupported characters")
    result = {
        "id": identifier(values["nutrition_id"], "nutrition_id"),
        "restaurant": required_text(values["restaurant"], "restaurant"),
        "category": optional_text(values["category"]),
        "item": required_text(values["item"], "item"),
        "calories": non_negative(values["calories"], "calories"),
        "calories_min": optional_non_negative(values["calories_min"], "calories_min"),
        "calories_max": optional_non_negative(values["calories_max"], "calories_max"),
        "protein_g": non_negative(values["protein_g"], "protein_g"),
        "carbs_g": non_negative(values["carbs_g"], "carbs_g"),
        "fat_g": non_negative(values["fat_g"], "fat_g"),
        "portion_basis": required_text(values["portion_basis"], "portion_basis"),
        "source": required_text(values["source"], "source"),
        "confidence": required_text(values["confidence"], "confidence").casefold(),
        "review_date": iso_date(values["review_date"], "review_date"),
        "evidence_class": evidence,
        "evidence_basis": optional_text(values["evidence_basis"]),
        "updated_at": utc_timestamp(values["updated_at"], "updated_at", required=True),
    }
    if result["confidence"] not in CONFIDENCES:
        raise ValueError("confidence must be exact, high, medium, low or unknown")
    low, high = result["calories_min"], result["calories_max"]
    if (low is None) != (high is None):
        raise ValueError("calories_min and calories_max must be supplied together")
    if low is not None and not low <= result["calories"] <= high:
        raise ValueError("calories must fall within calories_min and calories_max")
    return result


def normalise_record(values: dict[str, Any]) -> dict[str, Any]:
    for field in ("receipt_id", "order_id", "email_message_id", "receipt_line"):
        values[field] = optional_text(values.get(field))
    for prefix in ("purchase", "consumption"):
        timestamp = f"{prefix}_timestamp_utc"
        local_date = f"{prefix}_date_local"
        values[timestamp] = utc_timestamp(values.get(timestamp), timestamp)
        values[local_date] = iso_date(values.get(local_date), local_date)
        if values[timestamp] and not values[local_date]:
            raise ValueError(f"{local_date} is required with {timestamp}")
    values["meal_slot"] = optional_text(values.get("meal_slot"))
    values["restaurant"] = required_text(values.get("restaurant"), "restaurant")
    values["item"] = required_text(values.get("item"), "item")
    values["quantity"] = positive_number(values.get("quantity"), "quantity")
    values["portion_text"] = optional_text(values.get("portion_text"))
    values["status"] = status(values.get("status"))
    values["nutrition_id"] = optional_identifier(values.get("nutrition_id"), "nutrition_id")
    values["nutrition_multiplier"] = positive_number(
        values.get("nutrition_multiplier"), "nutrition_multiplier"
    )
    for field in ("notes", "apple_health_reference", "apple_health_sample_uuid"):
        values[field] = optional_text(values.get(field))
    values["apple_health_synced_at"] = utc_timestamp(
        values.get("apple_health_synced_at"), "apple_health_synced_at"
    )
    values["updated_at"] = utc_timestamp(values.get("updated_at"), "updated_at", required=True)
    values["update_reason"] = required_text(values.get("update_reason"), "update_reason")
    return values


def identifier(value: Any, field: str) -> str:
    result = required_text(value, field)
    if len(result) > 200 or ID_PATTERN.fullmatch(result) is None:
        raise ValueError(f"{field} contains unsupported characters")
    return result


def optional_identifier(value: Any, field: str) -> str | None:
    result = optional_text(value)
    return None if result is None else identifier(result, field)


def required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("text values must be strings")
    return value.strip() or None


def status(value: Any) -> str:
    result = required_text(value, "status").casefold()
    if result not in STATUSES:
        raise ValueError("status must be eaten, uncertain or excluded")
    return result


def number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a number") from error
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def non_negative(value: Any, field: str) -> float:
    result = number(value, field)
    if result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def optional_non_negative(value: Any, field: str) -> float | None:
    return None if value is None else non_negative(value, field)


def positive_number(value: Any, field: str) -> float:
    result = number(value, field)
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def iso_date(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None or value == "":
        if required:
            raise ValueError(f"{field} is required")
        return None
    try:
        return date.fromisoformat(required_text(value, field)).isoformat()
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error


def utc_timestamp(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None or value == "":
        if required:
            raise ValueError(f"{field} is required")
        return None
    try:
        parsed = datetime.fromisoformat(required_text(value, field))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must include a UTC offset")
    return parsed.astimezone(UTC).isoformat()


def now() -> str:
    return datetime.now(UTC).isoformat()


def clean_number(value: float) -> int | float:
    rounded = round(value, 6)
    return int(rounded) if rounded.is_integer() else rounded
