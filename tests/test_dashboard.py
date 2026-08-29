from __future__ import annotations

from copy import deepcopy

from app.charts import bar_plot, plot, series_plot
from app.dashboard import coffee_dashboard, food_dashboard, goal_dashboard, recipes_dashboard
from app.dashboard_config import DEFAULT_CONFIG


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

    bars = bar_plot([-2, 0, 4], precision=0)
    assert bars["baseline_y"] < 34
    assert bars["bars"][1]["height"] == 0
    assert [bar["label"] for bar in bars["bars"]] == ["-2", "0", "4"]
    assert bar_plot([1.234], precision=2)["bars"][0]["label"] == "1.23"


def test_weekly_bar_labels_are_shared_but_never_crowded() -> None:
    from app.web import TEMPLATES

    chart = TEMPLATES.env.get_template("charts.html").module.series_chart
    weekly = str(chart(series_plot(list(range(7)), "bar", precision=0), "Weekly", True))
    dense = str(chart(series_plot(list(range(8)), "bar", precision=0), "Dense", True))
    monthly = str(chart(series_plot(list(range(7)), "bar", precision=0), "Monthly", False))
    empty = str(chart(series_plot([], "bar", precision=0), "Empty", True))

    assert weekly.count('class="chart-bar-value"') == 7
    assert "Values, oldest to newest: 0, 1, 2, 3, 4, 5, 6" in weekly
    assert 'class="chart-bar-values"' not in dense
    assert 'class="chart-bar-values"' not in monthly
    assert 'class="chart-bar-values"' not in empty


def test_goal_dashboard_projects_values_without_status_copy() -> None:
    projected = goal_dashboard(goal([8, 10]))

    assert "state" not in projected
    assert projected["latest"] == 10
    assert goal_dashboard(goal(["done"]))["latest"] is None
    assert goal_dashboard(goal([]))["has_series"] is False


def test_coffee_and_recipe_dashboards_use_recent_factual_values() -> None:
    coffee = coffee_dashboard(
        [
            {
                "dose_g": 18,
                "yield_g": 36,
                "time_s": 29,
                "rating": 5,
                "created_at": "2026-08-02T00:00:00Z",
            },
            {
                "dose_g": 18,
                "yield_g": 40,
                "time_s": 31,
                "rating": 3,
                "created_at": "2026-08-01T00:00:00Z",
            },
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
    assert coffee["presentation"] == "line" and coffee["current_display"] == "2.0×"
    assert coffee["average_rating"] == 4.0
    assert coffee["start_label"] == {"date": "2026-08-01", "value": "2.22×"}
    assert recipes["cook_count"] == 2
    assert recipes["latest_rating"] == 5
    assert recipes["presentation"] == "line" and recipes["current_display"] == "5/5"


def test_food_dashboard_counts_only_confirmed_linked_records() -> None:
    report = {
        "daily_confirmed_totals": [
            {"date": "2026-08-15", "calories": 100, "protein_g": 10},
            {"date": "2026-08-16", "calories": 300, "protein_g": 30},
        ],
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
    assert dashboard["calorie_chart"]["presentation"] == "bar"
    assert len(dashboard["calorie_chart"]["bars"]) == 2
    assert dashboard["calorie_chart"]["callout"] is None
    assert dashboard["calorie_chart"]["axis_labels"] == ["2026-08-15", "2026-08-16"]

    config = deepcopy(DEFAULT_CONFIG["plugins"]["food"])
    next(metric for metric in config["metrics"] if metric["key"] == "confirmed_calories")[
        "presentation"
    ] = "line"
    line = food_dashboard(report, records, config)["calorie_chart"]
    assert line["presentation"] == "line" and line["callout"]["value"] == "300 kcal"
