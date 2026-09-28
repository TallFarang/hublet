from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.plugins import food
from tests.food_fixtures import nutrition_values
from tests.test_auth import login


@pytest.mark.parametrize("period", ["week", "month"])
def test_dashboard_displays_incomplete_average_and_unknown_catalogue_macros(
    settings_env: dict[str, str],
    period: str,
) -> None:
    settings = Settings.from_env(settings_env)
    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        login(client, settings)
        food.upsert_nutrition(settings, **nutrition_values())
        food.record_consumption(
            settings,
            "eaten",
            datetime.now().astimezone().date().isoformat(),
            "lunch",
            restaurant="Grain",
            item="Bowl",
            nutrition_id="meal",
        )
        response = client.get(f"/food?period={period}")
    assert response.status_code == 200
    assert "Incomplete" in response.text and "Macros unknown" in response.text
    assert "Noneg" not in response.text and "0.0g protein" not in response.text
    assert "600 kcal" in response.text


@pytest.mark.parametrize("sort", ["protein_asc", "protein_desc"])
def test_protein_sort_places_unknown_after_known_zeroes(
    settings_env: dict[str, str],
    sort: str,
) -> None:
    settings = Settings.from_env(settings_env)
    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        login(client, settings)
        food.upsert_nutrition(settings, **nutrition_values(item="Unknown", protein_g=999))
        food.upsert_nutrition(
            settings,
            **nutrition_values(
                nutrition_id="known",
                item="Known zero",
                protein_g=0,
                carbs_g=0,
                fat_g=0,
                macros_complete=True,
            ),
        )
        response = client.get(f"/food?sort={sort}")
    assert response.status_code == 200
    assert response.text.index("Known zero") < response.text.index(">Unknown<")
    assert "0.0g protein" in response.text
    assert "999" not in response.text


def test_calorie_sort_still_includes_incomplete_entries(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        login(client, settings)
        food.upsert_nutrition(settings, **nutrition_values(item="Unknown", calories=100))
        food.upsert_nutrition(
            settings,
            **nutrition_values(
                nutrition_id="known",
                item="Known",
                protein_g=10,
                carbs_g=20,
                fat_g=5,
                macros_complete=True,
            ),
        )
        ascending = client.get("/food?sort=calories_asc").text
        descending = client.get("/food?sort=calories_desc").text
    assert ascending.index(">Unknown<") < ascending.index(">Known<")
    assert descending.index(">Known<") < descending.index(">Unknown<")
