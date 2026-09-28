"""Minimal Food totals for dashboards and OpenClaw."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.config import Settings
from app.plugins.food_records import query_records
from app.plugins.food_schema import MACRO_FIELDS
from app.plugins.food_validation import clean_number, iso_date, required_text


def summary(settings: Settings, start_date: str, end_date: str) -> dict[str, Any]:
    """Return confirmed daily nutrition totals for an inclusive date range."""

    start, end = _required_range(start_date, end_date)
    records = query_records(settings, start_date=start_date, end_date=end_date, limit=500)
    daily_totals = []
    for current in _dates(start, end):
        totals: dict[str, float | None] = dict.fromkeys(("calories", *MACRO_FIELDS), 0.0)
        for record in records:
            if (
                record["consumption_date_local"] != current
                or record["status"] != "eaten"
                or record["nutrition_id"] is None
            ):
                continue
            for field, previous in totals.items():
                value = record["calculated_nutrition"][field]
                totals[field] = (
                    previous + value if previous is not None and value is not None else None
                )
        daily_totals.append(
            {
                "date": current,
                "macros_complete": all(totals[field] is not None for field in MACRO_FIELDS),
                **{
                    field: clean_number(value) if value is not None else None
                    for field, value in totals.items()
                },
            }
        )
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily_confirmed_totals": daily_totals,
        "excluded_count": sum(record["status"] == "excluded" for record in records),
    }


def _required_range(start_date: str, end_date: str) -> tuple[date, date]:
    start = iso_date(required_text(start_date, "start_date"), "start_date", required=True)
    end = iso_date(required_text(end_date, "end_date"), "end_date", required=True)
    assert start is not None and end is not None
    parsed_start, parsed_end = date.fromisoformat(start), date.fromisoformat(end)
    if parsed_start > parsed_end:
        raise ValueError("start_date must not be after end_date")
    return parsed_start, parsed_end


def _dates(start: date, end: date) -> list[str]:
    return [
        (start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)
    ]
