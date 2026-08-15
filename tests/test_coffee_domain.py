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


def test_migration_creates_only_beans_and_shots(coffee_settings: Settings) -> None:
    with sqlite3.connect(coffee_settings.data_dir / coffee.DB_FILENAME) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert tables == {"beans", "shots"}
    assert version == 1


def test_add_list_get_and_update_bean(coffee_settings: Settings) -> None:
    first = coffee.add_bean(
        coffee_settings,
        name="Moonrise",
        roaster="Example Roaster",
        roast_date="2026-08-10",
        origin="Colombia",
        process="washed",
        notes="cocoa",
    )
    coffee.add_bean(coffee_settings, name="Older", status="archived")

    updated = coffee.update_bean(
        coffee_settings,
        first["id"],
        name="Moonrise Decaf",
        status="archived",
        notes="cocoa and cherry",
    )

    assert updated["name"] == "Moonrise Decaf"
    assert updated["status"] == "archived"
    assert coffee.get_bean(coffee_settings, first["id"]) == updated
    assert coffee.list_beans(coffee_settings) == []
    assert {bean["name"] for bean in coffee.list_beans(coffee_settings, status=None)} == {
        "Moonrise Decaf",
        "Older",
    }


def test_log_shot_and_history_round_trip_taste_tags(coffee_settings: Settings) -> None:
    bean = coffee.add_bean(coffee_settings, name="Daybreak")
    first = coffee.log_shot(
        coffee_settings,
        bean["id"],
        dose_g=18,
        yield_g=38,
        time_s=24,
        grind_setting="14",
        grinder="Hand grinder",
        temperature_c=93,
        rating=2,
        taste_tags=["sour", "thin"],
        notes="First try",
    )
    second = coffee.log_shot(
        coffee_settings,
        bean["id"],
        dose_g=18,
        yield_g=36,
        time_s=29,
        grind_setting="13",
        rating=4,
        taste_tags=["balanced"],
    )

    shots = coffee.history(coffee_settings, bean_id=bean["id"])

    assert [shot["id"] for shot in shots] == [second["id"], first["id"]]
    assert shots[1]["taste_tags"] == ["sour", "thin"]
    assert "taste_tags_json" not in shots[1]
    assert shots[0]["bean_name"] == "Daybreak"


def test_domain_rejects_bad_or_missing_records(coffee_settings: Settings) -> None:
    with pytest.raises(ValueError, match="name"):
        coffee.add_bean(coffee_settings, name=" ")
    with pytest.raises(ValueError, match="status"):
        coffee.add_bean(coffee_settings, name="Bean", status="deleted")
    with pytest.raises(ValueError, match="Bean not found"):
        coffee.log_shot(
            coffee_settings,
            "missing",
            dose_g=18,
            yield_g=36,
            time_s=30,
            grind_setting="12",
        )

    bean = coffee.add_bean(coffee_settings, name="Bean")
    with pytest.raises(ValueError, match="rating"):
        coffee.log_shot(
            coffee_settings,
            bean["id"],
            dose_g=18,
            yield_g=36,
            time_s=30,
            grind_setting="12",
            rating=6,
        )


def test_recommendation_uses_high_rated_personal_history(coffee_settings: Settings) -> None:
    bean = coffee.add_bean(coffee_settings, name="Daybreak")
    best = coffee.log_shot(
        coffee_settings,
        bean["id"],
        dose_g=18,
        yield_g=36,
        time_s=29,
        grind_setting="13",
        temperature_c=93,
        rating=5,
        taste_tags=["balanced"],
    )
    coffee.log_shot(
        coffee_settings,
        bean["id"],
        dose_g=18,
        yield_g=40,
        time_s=23,
        grind_setting="14",
        rating=2,
        taste_tags=["sour"],
    )

    result = coffee.recommend_next(coffee_settings, bean["id"])

    assert result["recommendation"] == "Repeat the best-rated shot."
    assert result["change"] is None
    assert result["target"]["grind_setting"] == "13"
    assert result["evidence"] == [{"shot_id": best["id"], "rating": 5}]


def test_recommendation_changes_one_variable_for_fast_sour_shot(
    coffee_settings: Settings,
) -> None:
    bean = coffee.add_bean(coffee_settings, name="Daybreak")
    shot = coffee.log_shot(
        coffee_settings,
        bean["id"],
        dose_g=18,
        yield_g=40,
        time_s=22,
        grind_setting="14",
        rating=2,
        taste_tags=["sour"],
    )

    result = coffee.recommend_next(coffee_settings, bean["id"])

    assert result == {
        "recommendation": "Grind finer; keep every other setting unchanged.",
        "change": {"grind_setting": "finer"},
        "target": None,
        "evidence": [{"shot_id": shot["id"], "time_s": 22.0, "taste_tags": ["sour"]}],
    }


def test_recommendation_waits_for_personal_history(coffee_settings: Settings) -> None:
    bean = coffee.add_bean(coffee_settings, name="Daybreak")

    result = coffee.recommend_next(coffee_settings, bean["id"])

    assert result["change"] is None
    assert result["evidence"] == []
