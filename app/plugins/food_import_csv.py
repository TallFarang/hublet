"""Strict CSV parsing primitives for the Food recovery importer."""

from __future__ import annotations

import csv
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

HEADER_PATTERN = re.compile(r"[^a-z0-9]+")
NUMBER_PATTERN = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")

LEDGER_HEADERS = (
    "record_id", "order_id", "purchase_datetime", "consumption_datetime", "meal_slot",
    "restaurant", "item", "quantity_ordered", "portion_consumed", "status", "calories",
    "calories_low", "calories_high", "protein_g", "carbs_g", "fat_g", "confidence",
    "nutrition_source", "notes", "updated_at", "apple_health_export_id",
    "apple_health_exported_at", "nutrition_evidence",
)
CATALOGUE_HEADERS = (
    "restaurant", "category", "item", "calories", "carbs_g", "protein_g", "fat_g",
    "calories_low", "calories_high", "portion_basis", "source", "confidence",
    "last_reviewed", "evidence_class", "evidence_basis",
)


def read_csv(path: Path, expected_headers: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        actual = tuple(normal_header(value) for value in (reader.fieldnames or ()))
        if actual != expected_headers:
            raise ValueError(
                f"unexpected {path.name} headers: expected {expected_headers}, got {actual}"
            )
        rows = []
        for source_row in reader:
            row = {normal_header(key): (value or "").strip() for key, value in source_row.items()}
            if any(row.values()):
                rows.append(row)
        return rows


def required(row: dict[str, str], field: str) -> str:
    result = value(row, field)
    if result is None:
        raise ValueError(f"CSV field is required: {field}")
    return result


def value(row: dict[str, str], field: str) -> str | None:
    result = row.get(field, "").strip()
    return result or None


def number(row: dict[str, str], field: str, default: float | None = None) -> float:
    text = value(row, field)
    if text is None:
        if default is None:
            raise ValueError(f"CSV number is required: {field}")
        return default
    try:
        return float(text.replace(",", ""))
    except ValueError as error:
        raise ValueError(f"invalid CSV number for {field}: {text}") from error


def optional_number(row: dict[str, str], field: str) -> float | None:
    return None if value(row, field) is None else number(row, field)


def quantity(row: dict[str, str]) -> float:
    text = value(row, "quantity_ordered")
    if text is None:
        return 1
    match = NUMBER_PATTERN.search(text)
    if match is None:
        raise ValueError(f"invalid CSV number for quantity_ordered: {text}")
    return float(match.group().replace(",", ""))


def source_datetime(row: dict[str, str], field: str) -> tuple[str | None, str | None]:
    text = value(row, field)
    if text is None:
        return None, None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed.astimezone(UTC).isoformat(), parsed.date().isoformat()


def timestamp(row: dict[str, str], field: str) -> str | None:
    return source_datetime(row, field)[0]


def normal_header(text: str | None) -> str:
    return HEADER_PATTERN.sub("_", (text or "").strip().casefold()).strip("_")


def normal(text: str) -> str:
    return " ".join(HEADER_PATTERN.sub(" ", text.casefold()).split())


def semantic_key(*values: str) -> str:
    return "\0".join(normal(value) for value in values)


def deterministic_id(prefix: str, *values: str) -> str:
    digest = hashlib.sha256("\0".join(values).encode()).hexdigest()[:24]
    return f"{prefix}-{digest}"


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
