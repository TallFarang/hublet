from __future__ import annotations

import sqlite3

import pytest

from app.config import Settings
from app.db import migrate
from app.plugins import coffee


@pytest.fixture
def coffee_settings(settings_env: dict[str, str]) -> Settings:
    settings = Settings.from_env(settings_env)
    migrate(settings.data_dir / coffee.DB_FILENAME, coffee.MIGRATIONS)
    return settings


def test_migration_replaces_legacy_coffee_data(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    database = settings.data_dir / coffee.DB_FILENAME
    migrate(database, coffee.MIGRATIONS[:1])
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO beans (id, name, status, created_at) VALUES ('old', 'Old', 'open', 'now')"
        )
    migrate(database, coffee.MIGRATIONS)

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        bags = connection.execute("SELECT count(*) FROM bags").fetchone()[0]

    assert tables == {"bags", "brews"}
    assert version == 2
    assert bags == 0


def test_bags_are_distinct_purchases_with_exact_identity_matching(
    coffee_settings: Settings,
) -> None:
    first = coffee.add_bag(
        coffee_settings,
        " Moonrise ",
        " Example Roaster ",
        roast_date="2026-08-10",
        roast_level="light",
        origin="Colombia",
        process="washed",
        notes="cocoa",
    )
    second = coffee.add_bag(coffee_settings, "Moonrise", "Example Roaster")
    second = coffee.set_bag_status(coffee_settings, second["id"], "archived")

    assert first["name"] == "Moonrise" and first["roaster"] == "Example Roaster"
    assert coffee.get_bag(coffee_settings, first["id"]) == first
    assert coffee.list_bags(
        coffee_settings, status=None, name="moonrise", roaster="EXAMPLE ROASTER"
    ) == [second, first]
    assert coffee.list_bags(coffee_settings) == [first]


@pytest.mark.parametrize(
    ("method", "targets"),
    [
        ("v60", {"water_g": 250}),
        ("aeropress", {"water_g": 220}),
        ("french_press", {"water_g": 500}),
        ("espresso", {"yield_g": 36}),
    ],
)
def test_all_methods_store_complete_recipe_snapshots(
    coffee_settings: Settings,
    method: str,
    targets: dict[str, int],
) -> None:
    bag = coffee.add_bag(coffee_settings, "Daybreak", "Example Roaster")
    brew = coffee.log_brew(
        coffee_settings,
        bag["id"],
        method,
        18,
        "5.2",
        time_s=180,
        temperature_c=94,
        taste_notes="sweet and balanced",
        **targets,
    )

    assert brew["method"] == method
    assert brew["grinder"] == "Lagom Mini"
    assert brew["bag"]["name"] == "Daybreak"
    assert brew["taste_notes"] == "sweet and balanced"


def test_history_finds_recipes_across_repeat_bags(coffee_settings: Settings) -> None:
    old = coffee.add_bag(coffee_settings, "Moonrise", "Example Roaster", roast_level="Light")
    new = coffee.add_bag(coffee_settings, "moonrise", "example roaster", roast_level="light")
    other = coffee.add_bag(coffee_settings, "Moonrise", "Another Roaster", roast_level="light")
    for bag, grind in ((old, "5.0"), (new, "5.2"), (other, "6.0")):
        coffee.log_brew(
            coffee_settings,
            bag["id"],
            "v60",
            30,
            grind,
            water_g=450,
            bypass_water_g=60,
            rating=4,
            notes="Split; partner over ice, mine topped up warm",
        )

    matches = coffee.history(
        coffee_settings,
        method="V60",
        name="MOONRISE",
        roaster="EXAMPLE ROASTER",
        roast_level="LIGHT",
    )

    assert {brew["bag_id"] for brew in matches} == {old["id"], new["id"]}
    assert all(brew["bypass_water_g"] == 60 for brew in matches)


def test_domain_rejects_incomplete_or_invalid_records(coffee_settings: Settings) -> None:
    with pytest.raises(ValueError, match="roaster"):
        coffee.add_bag(coffee_settings, "Bean", " ")
    with pytest.raises(ValueError, match="roast_date"):
        coffee.add_bag(coffee_settings, "Bean", "Roaster", roast_date="yesterday")
    with pytest.raises(ValueError, match="Bag not found"):
        coffee.log_brew(
            coffee_settings, "missing", "v60", 15, "5", water_g=250, rating=3
        )

    bag = coffee.add_bag(coffee_settings, "Bean", "Roaster")
    with pytest.raises(ValueError, match="rating or taste_notes"):
        coffee.log_brew(coffee_settings, bag["id"], "v60", 15, "5", water_g=250)
    with pytest.raises(ValueError, match="filter methods"):
        coffee.log_brew(
            coffee_settings, bag["id"], "aeropress", 15, "5", yield_g=220, rating=3
        )
    with pytest.raises(ValueError, match="bypass"):
        coffee.log_brew(
            coffee_settings,
            bag["id"],
            "espresso",
            18,
            "1.2",
            yield_g=36,
            bypass_water_g=20,
            rating=3,
        )
