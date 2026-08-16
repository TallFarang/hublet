from __future__ import annotations

import pytest

from app.config import Settings
from app.plugins import food
from app.runtime import migrate_plugins


@pytest.fixture
def food_settings(settings_env: dict[str, str]) -> Settings:
    settings = Settings.from_env(settings_env)
    migrate_plugins(settings, (food.PLUGIN,))
    return settings


def add_nutrition(settings: Settings, nutrition_id: str, item: str) -> None:
    food.upsert_nutrition(
        settings,
        nutrition_id,
        "Example Kitchen",
        item,
        100,
        10,
        10,
        2,
        "one serving",
        "menu",
        "exact",
        "official",
    )


def test_nutrition_search_is_stably_paginated(food_settings: Settings) -> None:
    add_nutrition(food_settings, "rice", "Rice")
    add_nutrition(food_settings, "rice-bowl", "Rice bowl")
    add_nutrition(food_settings, "rice-noodles", "Rice noodles")

    first = food.find_nutrition(food_settings, item="Rice", limit=2)
    second = food.find_nutrition(food_settings, item="Rice", limit=2, offset=2)

    assert first["total"] == second["total"] == 3
    assert first["items"][0]["id"] == "rice"
    assert first["next_offset"] == 2
    assert second["next_offset"] is None
    assert {row["id"] for row in [*first["items"], *second["items"]]} == {
        "rice",
        "rice-bowl",
        "rice-noodles",
    }


@pytest.mark.parametrize(
    ("arguments", "message"),
    [({"limit": 0}, "between 1 and 200"), ({"limit": 201}, "between 1 and 200"), ({"offset": -1}, "negative")],
)
def test_nutrition_search_validates_page_bounds(
    food_settings: Settings, arguments: dict[str, int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        food.find_nutrition(food_settings, **arguments)
