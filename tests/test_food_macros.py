from __future__ import annotations

import asyncio
import sqlite3

import pytest
from mcp.server import MCPServer

from app.config import Settings
from app.plugins import food
from tests.food_fixtures import nutrition_values


def test_unknown_macros_are_masked_in_all_nutrition_reads(food_settings: Settings) -> None:
    entry = food.upsert_nutrition(food_settings, **nutrition_values(carbs_g=12))
    for result in (
        entry,
        food.get_nutrition(food_settings, "meal"),
        food.find_nutrition(food_settings)["items"][0],
    ):
        assert result["macros_complete"] is False
        assert result["calories"] == 600
        assert all(result[field] is None for field in ("protein_g", "carbs_g", "fat_g"))
    with sqlite3.connect(food_settings.data_dir / food.DB_FILENAME) as connection:
        assert connection.execute(
            "SELECT protein_g, carbs_g, fat_g, macros_complete FROM nutrition"
        ).fetchone() == (0, 12, 0, 0)


def test_upserts_preserve_flag_until_explicit_completion(food_settings: Settings) -> None:
    food.upsert_nutrition(food_settings, **nutrition_values())
    values = nutrition_values(protein_g=0, carbs_g=20, fat_g=0, calories=650)
    del values["macros_complete"]
    assert food.upsert_nutrition(food_settings, **values)["macros_complete"] is False
    complete = food.upsert_nutrition(food_settings, **values, macros_complete=True)
    assert complete["macros_complete"] is True
    assert complete["protein_g"] == complete["fat_g"] == 0
    assert complete["carbs_g"] == 20
    assert food.upsert_nutrition(food_settings, **values)["macros_complete"] is True


def test_new_entries_default_to_complete_and_reject_missing_macros(food_settings: Settings) -> None:
    values = nutrition_values()
    del values["macros_complete"]
    with pytest.raises(ValueError, match="protein_g"):
        food.upsert_nutrition(food_settings, **values)
    values.update(protein_g=0, carbs_g=0, fat_g=0)
    assert food.upsert_nutrition(food_settings, **values)["macros_complete"] is True


@pytest.mark.parametrize("field", ["protein_g", "carbs_g", "fat_g"])
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True])
def test_incomplete_macros_still_validate_supplied_numbers(
    food_settings: Settings,
    field: str,
    value: float,
) -> None:
    with pytest.raises((ValueError, TypeError)):
        food.upsert_nutrition(food_settings, **nutrition_values(**{field: value}))
    assert food.find_nutrition(food_settings)["total"] == 0


@pytest.mark.parametrize("flag", [2, -1, "false", 0.5])
def test_completeness_flag_is_validated(food_settings: Settings, flag: object) -> None:
    with pytest.raises(ValueError, match="macros_complete"):
        food.upsert_nutrition(food_settings, **nutrition_values(macros_complete=flag))


def test_failed_completion_does_not_change_existing_entry(food_settings: Settings) -> None:
    original = food.upsert_nutrition(food_settings, **nutrition_values())
    with pytest.raises(ValueError, match="protein_g"):
        food.upsert_nutrition(food_settings, **nutrition_values(macros_complete=True, calories=1))
    assert food.get_nutrition(food_settings, "meal") == original


def test_mcp_accepts_omitted_macros_for_calorie_only_entries(food_settings: Settings) -> None:
    server = MCPServer("food-test")
    food.register_mcp(server, food_settings)

    async def exercise() -> None:
        schemas = {tool.name: tool.input_schema for tool in await server.list_tools()}
        schema = schemas["food_upsert_nutrition"]
        assert not {"protein_g", "carbs_g", "fat_g", "macros_complete"} & set(schema["required"])
        values = nutrition_values()
        for field in ("protein_g", "carbs_g", "fat_g"):
            del values[field]
        result = await server.call_tool("food_upsert_nutrition", values)
        assert not result.is_error

    asyncio.run(exercise())
    assert food.get_nutrition(food_settings, "meal")["macros_complete"] is False
