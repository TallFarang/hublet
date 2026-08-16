"""Read-only Food gaps and summary reporting."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.config import Settings
from app.plugins.food_records import query_records
from app.plugins.food_validation import clean_number, iso_date, required_text


def find_gaps(
    settings: Settings,
    start_date: str,
    end_date: str,
    expected_meal_slots: list[str],
) -> dict[str, Any]:
    """Return detailed tracking gaps without writing data."""

    start, end = _required_range(start_date, end_date)
    slots = _meal_slots(expected_meal_slots)
    records = query_records(settings, start_date=start_date, end_date=end_date, limit=500)
    missing_meals = []
    for current in _dates(start, end):
        eaten_slots = {
            record["meal_slot"]
            for record in records
            if record["consumption_date_local"] == current
            and record["status"] == "eaten"
            and record["meal_slot"] is not None
        }
        missing_meals.extend(
            {"date": current, "meal_slot": slot} for slot in slots if slot not in eaten_slots
        )
    uncertain = [record for record in records if record["status"] == "uncertain"]
    missing_nutrition = [
        record for record in records if record["status"] == "eaten" and record["nutrition_id"] is None
    ]
    incomplete = [record for record in records if _incomplete_reasons(record)]
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "expected_meal_slots": slots,
        "missing_expected_meals": missing_meals,
        "uncertain_records": uncertain,
        "missing_nutrition_links": missing_nutrition,
        "structurally_incomplete_records": [
            {"record": record, "reasons": _incomplete_reasons(record)} for record in incomplete
        ],
    }


def summary(
    settings: Settings,
    start_date: str,
    end_date: str,
    expected_meal_slots: list[str],
) -> dict[str, Any]:
    """Return deterministic daily facts with compact embedded uncertainty details."""

    start, end = _required_range(start_date, end_date)
    gaps = find_gaps(settings, start_date, end_date, expected_meal_slots)
    records = query_records(settings, start_date=start_date, end_date=end_date, limit=500)
    all_dates = _dates(start, end)
    daily_totals, evidence_counts, confidence_counts = [], {}, {}
    for current in all_dates:
        eaten = [
            record
            for record in records
            if record["consumption_date_local"] == current and record["status"] == "eaten"
        ]
        totals = {field: 0.0 for field in ("calories", "protein_g", "carbs_g", "fat_g")}
        for record in eaten:
            if record["nutrition_id"] is None:
                continue
            for field in totals:
                totals[field] += record["calculated_nutrition"][field]
            _increment(evidence_counts, record["nutrition"]["evidence_class"])
            _increment(confidence_counts, record["nutrition"]["confidence"])
        daily_totals.append(
            {"date": current, **{field: clean_number(value) for field, value in totals.items()}}
        )
    dates_with_gaps = {gap["date"] for gap in gaps["missing_expected_meals"]}
    dates_with_gaps |= {_record_date(record) for record in gaps["uncertain_records"]}
    dates_with_gaps |= {_record_date(record) for record in gaps["missing_nutrition_links"]}
    dates_with_gaps |= {
        _record_date(entry["record"]) for entry in gaps["structurally_incomplete_records"]
    }
    dates_with_gaps.discard(None)
    complete = [value for value in all_dates if value not in dates_with_gaps]
    complete_totals = [row for row in daily_totals if row["date"] in complete]
    averages = {
        field: clean_number(sum(row[field] for row in complete_totals) / len(complete_totals))
        if complete_totals
        else None
        for field in ("calories", "protein_g", "carbs_g", "fat_g")
    }
    compact_gaps = {
        **gaps,
        "uncertain_records": [_compact_uncertain(record) for record in gaps["uncertain_records"]],
    }
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily_confirmed_totals": daily_totals,
        "averages_over_complete_days": averages,
        "complete_dates": complete,
        "incomplete_dates": [value for value in all_dates if value in dates_with_gaps],
        "evidence_class_counts": dict(sorted(evidence_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "uncertain_count": sum(record["status"] == "uncertain" for record in records),
        "excluded_count": sum(record["status"] == "excluded" for record in records),
        "gaps": compact_gaps,
    }


def _compact_uncertain(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": _record_date(record),
        "restaurant": record["restaurant"],
        "item": record["item"],
        "status": record["status"],
        "record_id": record["id"],
    }


def _incomplete_reasons(record: dict[str, Any]) -> list[str]:
    reasons = []
    if not record["restaurant"]:
        reasons.append("missing_restaurant")
    if not record["item"]:
        reasons.append("missing_item")
    if record["status"] == "eaten":
        if not record["consumption_date_local"]:
            reasons.append("missing_consumption_date")
        if not record["meal_slot"]:
            reasons.append("missing_meal_slot")
    return reasons


def _required_range(start_text: str, end_text: str) -> tuple[date, date]:
    start_value = iso_date(start_text, "start_date", required=True)
    end_value = iso_date(end_text, "end_date", required=True)
    start, end = date.fromisoformat(start_value), date.fromisoformat(end_value)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    if (end - start).days > 366:
        raise ValueError("date range must not exceed 367 days")
    return start, end


def _meal_slots(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise TypeError("expected_meal_slots must be a list")
    slots = [required_text(value, "meal slot") for value in values]
    if len(slots) != len(set(slots)):
        raise ValueError("expected_meal_slots must not contain duplicates")
    return slots


def _dates(start: date, end: date) -> list[str]:
    return [
        (start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)
    ]


def _record_date(record: dict[str, Any]) -> str | None:
    return record["consumption_date_local"] or record["purchase_date_local"]


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1
