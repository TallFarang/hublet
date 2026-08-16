"""Registration of the eight public Food MCP tools."""

from __future__ import annotations

from functools import partial
from typing import Any

from mcp.server import MCPServer

from app.config import Settings
from app.plugins.food_corrections import correct_record
from app.plugins.food_nutrition import find_nutrition, upsert_nutrition
from app.plugins.food_receipts import ingest_receipt
from app.plugins.food_records import query_records, record_consumption
from app.plugins.food_reporting import find_gaps, summary


def register_mcp(server: MCPServer, settings: Settings) -> None:
    """Expose Food domain functions without duplicating their input contracts."""

    tools = (
        ("food_ingest_receipt", partial(ingest_receipt, settings)),
        ("food_record_consumption", partial(record_consumption, settings)),
        ("food_correct_record", partial(correct_record, settings)),
        ("food_query_records", partial(query_records, settings)),
        ("food_upsert_nutrition", partial(_upsert_nutrition, settings)),
        ("food_find_nutrition", partial(find_nutrition, settings)),
        ("food_find_gaps", partial(find_gaps, settings)),
        ("food_summary", partial(summary, settings)),
    )
    for name, function in tools:
        function.__name__ = name
        server.add_tool(function, name=name)


def _upsert_nutrition(
    settings: Settings,
    nutrition_id: str,
    restaurant: str,
    item: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    portion_basis: str,
    source: str,
    confidence: str,
    evidence_class: str,
    category: str | None = None,
    calories_min: float | None = None,
    calories_max: float | None = None,
    review_date: str | None = None,
    evidence_basis: str | None = None,
) -> dict[str, Any]:
    """Create or fully replace a stable nutrition variant."""

    return upsert_nutrition(
        settings,
        nutrition_id,
        restaurant,
        item,
        calories,
        protein_g,
        carbs_g,
        fat_g,
        portion_basis,
        source,
        confidence,
        evidence_class,
        category=category,
        calories_min=calories_min,
        calories_max=calories_max,
        review_date=review_date,
        evidence_basis=evidence_basis,
    )
