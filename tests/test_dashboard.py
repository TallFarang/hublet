from __future__ import annotations

from app.dashboard import coffee_dashboard, food_dashboard, goal_dashboard, plot, recipes_dashboard


def goal(values: list[object], *, direction: str = "at_or_above") -> dict[str, object]:
    return {
        "target": {"metric": "books", "value": 10, "unit": "books", "direction": direction},
        "evidence_sources": [],
        "history": [
            {"metric": "books", "value": value, "unit": "books"} for value in reversed(values)
        ],
    }


def test_plot_handles_empty_single_and_target_series() -> None:
    assert plot([]) == {"points": "", "target_y": None, "last": None, "single": False}
    single = plot([4])
    series = plot([2, 4, 8], target=10)

    assert single["points"].startswith("50,")
    assert single["single"] is True
    assert single["last"]["x"] == 50
    assert len(series["points"].split()) == 3
    assert series["target_y"] == 4.0


def test_goal_dashboard_projects_values_without_status_copy() -> None:
    projected = goal_dashboard(goal([8, 10]))

    assert "state" not in projected
    assert projected["latest"] == 10
    assert goal_dashboard(goal(["done"]))["latest"] is None
    assert goal_dashboard(goal([]))["has_series"] is False


def test_coffee_and_recipe_dashboards_use_recent_factual_values() -> None:
    coffee = coffee_dashboard(
        [
            {"dose_g": 18, "yield_g": 36, "time_s": 29, "rating": 5, "created_at": "2026-08-02T00:00:00Z"},
            {"dose_g": 18, "yield_g": 40, "time_s": 31, "rating": 3, "created_at": "2026-08-01T00:00:00Z"},
        ],
        bean_count=2,
    )
    recipes = recipes_dashboard(
        [
            {
                "cook_logs": [
                    {"id": "a", "rating": 3, "created_at": "2026-08-01T00:00:00Z"},
                    {"id": "b", "rating": 5, "created_at": "2026-08-02T00:00:00Z"},
                ]
            }
        ]
    )

    assert coffee["latest_ratio"] == 2.0
    assert coffee["average_rating"] == 4.0
    assert coffee["start_label"] == {"date": "2026-08-01", "value": "2.22×"}
    assert recipes["cook_count"] == 2
    assert recipes["latest_rating"] == 5


def test_food_dashboard_counts_only_confirmed_linked_records() -> None:
    report = {
        "daily_confirmed_totals": [
            {"date": "2026-08-15", "calories": 100, "protein_g": 10},
            {"date": "2026-08-16", "calories": 300, "protein_g": 30},
        ],
        "uncertain_count": 1,
        "excluded_count": 1,
    }
    records = [
        {
            "status": "eaten",
            "nutrition_id": "n1",
            "consumption_date_local": "2026-08-15",
            "meal_slot": "lunch",
            "item": "Rice bowl",
            "restaurant": "Kitchen",
        },
        {
            "status": "eaten",
            "nutrition_id": None,
            "consumption_date_local": "2026-08-15",
            "meal_slot": "dinner",
            "item": "Soup",
            "restaurant": "Kitchen",
        },
        {"status": "uncertain", "nutrition_id": "n1"},
        {"status": "excluded", "nutrition_id": "n1"},
    ]

    dashboard = food_dashboard(report, records)

    assert dashboard["confirmed_count"] == 1
    assert dashboard["unresolved_count"] == 2
    assert dashboard["days"][0]["meal_count"] == 2
    assert dashboard["average_calories"] == 200
    assert dashboard["average_protein"] == 20
    assert dashboard["calorie_chart"]["callout"]["value"] == "300 kcal"
    assert dashboard["calorie_chart"]["axis_labels"] == ["2026-08-15", "2026-08-16"]
