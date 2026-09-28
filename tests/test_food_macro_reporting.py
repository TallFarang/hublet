from __future__ import annotations

from app.config import Settings
from app.dashboard import food_dashboard
from app.plugins import food
from app.plugins.goals_live import live_tracking_series
from tests.food_fixtures import nutrition_values


def test_calorie_only_records_remain_unknown_through_receipts_and_corrections(
    food_settings: Settings,
) -> None:
    food.upsert_nutrition(food_settings, **nutrition_values())
    receipt = food.ingest_receipt(
        food_settings,
        [{"item": "Calorie-only bowl"}],
        order_id="order",
        restaurant="Grain",
        purchase_date_local="2026-09-01",
    )
    ingested = receipt["records"][0]
    assert ingested["nutrition_id"] == "meal"
    consumed = food.record_consumption(
        food_settings,
        ingested["id"],
        "2026-09-01",
        "lunch",
        nutrition_multiplier=0.5,
    )
    corrected = food.correct_record(
        food_settings,
        ingested["id"],
        {"nutrition_multiplier": 0.75},
        "Ate more",
    )
    queried = food.query_records(food_settings)[0]
    for record, calories in ((ingested, 600), (consumed, 300), (corrected, 450), (queried, 450)):
        assert record["nutrition"]["macros_complete"] is False
        assert record["calculated_nutrition"] == {
            "calories": calories,
            "protein_g": None,
            "carbs_g": None,
            "fat_g": None,
            "macros_complete": False,
        }


def test_mixed_days_keep_calories_but_invalidate_macros_and_period_average(
    food_settings: Settings,
) -> None:
    food.upsert_nutrition(food_settings, **nutrition_values())
    food.upsert_nutrition(
        food_settings,
        **nutrition_values(
            nutrition_id="complete",
            protein_g=30,
            carbs_g=70,
            fat_g=20,
            macros_complete=True,
        ),
    )
    for record_id, nutrition_id, day, multiplier in (
        ("a-known", "complete", "2026-09-01", 1),
        ("b-unknown", "meal", "2026-09-01", 0.5),
        ("c-known", "complete", "2026-09-01", 1),
        ("d-next-day", "complete", "2026-09-02", 1),
    ):
        food.record_consumption(
            food_settings,
            record_id,
            day,
            "lunch",
            restaurant="Grain",
            item="Bowl",
            nutrition_id=nutrition_id,
            nutrition_multiplier=multiplier,
        )
    report = food.summary(food_settings, "2026-09-01", "2026-09-03")
    mixed, complete, empty = report["daily_confirmed_totals"]
    assert mixed == {
        "date": "2026-09-01",
        "calories": 1500,
        "macros_complete": False,
        "protein_g": None,
        "carbs_g": None,
        "fat_g": None,
    }
    assert complete["protein_g"] == 30 and complete["macros_complete"] is True
    assert empty["protein_g"] == empty["calories"] == 0 and empty["macros_complete"] is True
    dashboard = food_dashboard(report, food.query_records(food_settings))
    assert dashboard["average_protein"] is None
    protein = next(row for row in dashboard["readings"] if row["key"] == "average_protein")
    assert protein["display"] == "Incomplete"
    assert dashboard["average_calories"] == 700
    assert dashboard["confirmed_count"] == 4 and dashboard["unresolved_count"] == 0
    assert dashboard["calorie_chart"]["hover_regions"][0]["value"] == "1500 kcal"
    series = live_tracking_series(food_settings, "2026-09-01", "2026-09-01")
    calories = series[("calorie_target_adherence", "Hublet Food")]
    assert calories["context_series"] == [{"date": "2026-09-01", "value": 1500}]
    assert calories["series"] == [{"date": "2026-09-01", "value": 1500 / 7}]


def test_excluded_uncertain_and_unlinked_records_do_not_invalidate_confirmed_macros(
    food_settings: Settings,
) -> None:
    food.upsert_nutrition(food_settings, **nutrition_values())
    for record_id, status, nutrition_id in (
        ("excluded", "excluded", "meal"),
        ("uncertain", "uncertain", "meal"),
        ("unlinked", "eaten", None),
    ):
        food.record_consumption(
            food_settings,
            record_id,
            "2026-09-01",
            "lunch",
            restaurant="Grain",
            item="Bowl",
            nutrition_id=nutrition_id,
        )
        food.correct_record(food_settings, record_id, {"status": status}, "Fixture status")
    report = food.summary(food_settings, "2026-09-01", "2026-09-01")
    totals = report["daily_confirmed_totals"][0]
    assert totals["macros_complete"] is True
    assert totals["calories"] == totals["protein_g"] == totals["carbs_g"] == totals["fat_g"] == 0
    assert report["excluded_count"] == 1


def test_completing_nutrition_updates_historical_totals(food_settings: Settings) -> None:
    food.upsert_nutrition(food_settings, **nutrition_values())
    food.record_consumption(
        food_settings,
        "eaten",
        "2026-09-01",
        "lunch",
        restaurant="Grain",
        item="Bowl",
        nutrition_id="meal",
    )
    assert (
        food.summary(food_settings, "2026-09-01", "2026-09-01")["daily_confirmed_totals"][0][
            "protein_g"
        ]
        is None
    )
    food.upsert_nutrition(
        food_settings,
        **nutrition_values(
            protein_g=0,
            carbs_g=0,
            fat_g=0,
            macros_complete=True,
        ),
    )
    totals = food.summary(food_settings, "2026-09-01", "2026-09-01")["daily_confirmed_totals"][0]
    assert totals["macros_complete"] is True
    assert totals["protein_g"] == 0 and totals["calories"] == 600
