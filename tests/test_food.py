from __future__ import annotations

import asyncio
import sqlite3
from typing import Any

import pytest
from mcp.server import MCPServer

from app.config import Settings
from app.plugins import food
from app.runtime import migrate_plugins


@pytest.fixture
def food_settings(settings_env: dict[str, str]) -> Settings:
    settings = Settings.from_env(settings_env)
    migrate_plugins(settings, (food.PLUGIN,))
    return settings


def nutrition(
    settings: Settings,
    nutrition_id: str = "nutrition-bowl",
    *,
    calories: float = 600,
    portion_basis: str = "one bowl",
) -> dict[str, Any]:
    return food.upsert_nutrition(
        settings,
        nutrition_id,
        "Example Kitchen",
        "Rice bowl",
        calories,
        30,
        75,
        20,
        portion_basis,
        "published menu",
        "high",
        "official",
        category="mains",
        review_date="2026-08-01",
    )


def test_food_migration_has_exactly_two_domain_tables_and_constraints(
    food_settings: Settings,
) -> None:
    database = food_settings.data_dir / food.DB_FILENAME
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO records
                   (id, restaurant, item, quantity, status, nutrition_multiplier,
                    updated_at, update_reason)
                   VALUES ('bad', 'Kitchen', 'Item', 1, 'maybe', 1,
                           '2026-08-01T00:00:00+00:00', 'test')"""
            )

    assert tables == {"nutrition", "records"}


def test_receipt_retries_are_idempotent_and_conflicts_roll_back(
    food_settings: Settings,
) -> None:
    nutrition(food_settings)
    facts = {
        "items": [
            {"item": "Rice bowl", "receipt_line": "1 Rice bowl"},
            {"item": "Unknown side", "receipt_line": "1 Unknown side"},
        ],
        "order_id": "order-1",
        "email_message_id": "message-1",
        "restaurant": "Example Kitchen",
        "purchase_date_local": "2026-08-15",
    }

    created = food.ingest_receipt(food_settings, **facts)
    retried = food.ingest_receipt(food_settings, **facts)

    assert created["created"] is True
    assert retried["created"] is False
    assert [row["id"] for row in created["records"]] == [row["id"] for row in retried["records"]]
    assert created["records"][0]["nutrition_id"] == "nutrition-bowl"
    assert created["records"][1]["nutrition_id"] is None
    assert {row["status"] for row in created["records"]} == {"uncertain"}

    with pytest.raises(ValueError, match="conflicts"):
        food.ingest_receipt(
            food_settings,
            [{"item": "Changed item"}, {"item": "Third item", "record_id": "must-not-exist"}],
            order_id="order-1",
            restaurant="Example Kitchen",
            purchase_date_local="2026-08-15",
        )

    assert len(food.query_records(food_settings)) == 2
    assert not any(row["id"] == "must-not-exist" for row in food.query_records(food_settings))


def test_receipt_auto_link_requires_an_unambiguous_variant(food_settings: Settings) -> None:
    nutrition(food_settings, "small", portion_basis="small bowl")
    nutrition(food_settings, "large", portion_basis="large bowl")

    result = food.ingest_receipt(
        food_settings,
        [{"item": "Rice bowl"}, {"item": "Rice bowl", "portion_text": "large bowl"}],
        order_id="order-variants",
        restaurant="Example Kitchen",
        purchase_date_local="2026-08-15",
    )

    assert result["records"][0]["nutrition_id"] is None
    assert result["records"][1]["nutrition_id"] == "large"


def test_corrections_amend_in_place_and_live_nutrition_changes_history(
    food_settings: Settings,
) -> None:
    nutrition(food_settings)
    record = food.record_consumption(
        food_settings,
        "meal-1",
        "2026-08-15",
        "dinner",
        restaurant="Example Kitchen",
        item="Rice bowl",
        nutrition_id="nutrition-bowl",
        nutrition_multiplier=0.5,
    )
    original_updated_at = record["updated_at"]

    corrected = food.correct_record(
        food_settings,
        "meal-1",
        {"notes": "Shared", "nutrition_multiplier": 0.75},
        "Ate more than first recorded",
    )
    food.upsert_nutrition(
        food_settings,
        "nutrition-bowl",
        "Example Kitchen",
        "Rice bowl",
        800,
        40,
        80,
        24,
        "one bowl",
        "updated menu",
        "high",
        "official",
    )
    current = food.query_records(food_settings, text="shared")[0]

    assert corrected["id"] == "meal-1"
    assert corrected["update_reason"] == "Ate more than first recorded"
    assert corrected["updated_at"] >= original_updated_at
    assert current["calculated_nutrition"]["calories"] == 600
    assert len(food.query_records(food_settings)) == 1

    with pytest.raises(ValueError, match="update_reason"):
        food.correct_record(food_settings, "meal-1", {"notes": "No reason"}, "")


def test_summary_excludes_uncertain_and_excluded_and_reports_explicit_gaps(
    food_settings: Settings,
) -> None:
    nutrition(food_settings)
    food.record_consumption(
        food_settings,
        "breakfast",
        "2026-08-15",
        "breakfast",
        restaurant="Example Kitchen",
        item="Rice bowl",
        nutrition_id="nutrition-bowl",
        nutrition_multiplier=0.5,
    )
    food.ingest_receipt(
        food_settings,
        [{"item": "Unknown lunch"}],
        order_id="lunch-order",
        restaurant="Example Kitchen",
        purchase_date_local="2026-08-15",
    )
    food.record_consumption(
        food_settings,
        "excluded-dinner",
        "2026-08-15",
        "dinner",
        restaurant="Example Kitchen",
        item="Rice bowl",
        nutrition_id="nutrition-bowl",
    )
    food.correct_record(
        food_settings, "excluded-dinner", {"status": "excluded"}, "Did not eat it"
    )

    result = food.summary(
        food_settings, "2026-08-15", "2026-08-16", ["breakfast", "lunch", "dinner"]
    )

    assert result["daily_confirmed_totals"][0]["calories"] == 300
    assert result["daily_confirmed_totals"][1]["calories"] == 0
    assert result["uncertain_count"] == 1
    assert result["excluded_count"] == 1
    assert result["complete_dates"] == []
    assert result["averages_over_complete_days"]["calories"] is None
    assert {gap["meal_slot"] for gap in result["gaps"]["missing_expected_meals"]} >= {
        "lunch",
        "dinner",
    }
    assert result["gaps"]["uncertain_records"] == [
        {
            "date": "2026-08-15",
            "restaurant": "Example Kitchen",
            "item": "Unknown lunch",
            "status": "uncertain",
            "record_id": result["gaps"]["uncertain_records"][0]["record_id"],
        }
    ]
    assert "nutrition" not in result["gaps"]["uncertain_records"][0]
    detailed = food.find_gaps(
        food_settings, "2026-08-15", "2026-08-16", ["breakfast", "lunch", "dinner"]
    )
    assert "nutrition" in detailed["uncertain_records"][0]


def test_dates_ranges_search_and_validation(food_settings: Settings) -> None:
    nutrition(food_settings)
    food.record_consumption(
        food_settings,
        "dated-meal",
        "2026-08-15",
        "lunch",
        consumption_timestamp_utc="2026-08-15T05:00:00Z",
        restaurant="Example Kitchen",
        item="Rice bowl",
        nutrition_id="nutrition-bowl",
    )

    assert len(
        food.query_records(
            food_settings,
            start_date="2026-08-15",
            end_date="2026-08-15",
            meal_slot="lunch",
            restaurant="example kitchen",
        )
    ) == 1
    page = food.find_nutrition(food_settings, restaurant="Example", item="Rice")
    assert page["items"][0]["id"] == "nutrition-bowl"
    assert page["total"] == 1
    assert page["next_offset"] is None

    with pytest.raises(ValueError, match="UTC offset"):
        food.record_consumption(
            food_settings,
            "bad-date",
            "2026-08-15",
            "lunch",
            consumption_timestamp_utc="2026-08-15T05:00:00+07:00",
            restaurant="Example Kitchen",
            item="Rice bowl",
        )
    with pytest.raises(ValueError, match="negative"):
        food.upsert_nutrition(
            food_settings,
            "bad",
            "Kitchen",
            "Item",
            -1,
            0,
            0,
            0,
            "serving",
            "source",
            "low",
            "estimated",
        )


def test_register_mcp_exposes_exact_food_tool_set(food_settings: Settings) -> None:
    class Server:
        def __init__(self) -> None:
            self.names: list[str] = []

        def add_tool(self, function: Any, *, name: str) -> None:
            self.names.append(name)

    server = Server()
    food.register_mcp(server, food_settings)  # type: ignore[arg-type]

    assert server.names == [
        "food_ingest_receipt",
        "food_record_consumption",
        "food_correct_record",
        "food_query_records",
        "food_upsert_nutrition",
        "food_find_nutrition",
        "food_find_gaps",
        "food_summary",
    ]


def test_food_tools_build_valid_mcp_schemas(food_settings: Settings) -> None:
    server = MCPServer("food-test")
    food.register_mcp(server, food_settings)

    tools = asyncio.run(server.list_tools())

    schemas = {tool.name: tool.input_schema for tool in tools}
    assert set(schemas) == {
        "food_ingest_receipt",
        "food_record_consumption",
        "food_correct_record",
        "food_query_records",
        "food_upsert_nutrition",
        "food_find_nutrition",
        "food_find_gaps",
        "food_summary",
    }
    receipt = schemas["food_ingest_receipt"]["$defs"]["ReceiptItem"]
    correction = schemas["food_correct_record"]["$defs"]["RecordCorrection"]
    search = schemas["food_find_nutrition"]["properties"]
    assert receipt["required"] == ["item"]
    assert receipt["additionalProperties"] is False
    assert {"item", "quantity", "status", "nutrition_multiplier"} <= set(receipt["properties"])
    assert {"status", "notes", "nutrition_id", "consumption_date_local"} <= set(
        correction["properties"]
    )
    assert correction["additionalProperties"] is False
    assert search["limit"]["maximum"] == 200
    assert search["offset"]["minimum"] == 0
