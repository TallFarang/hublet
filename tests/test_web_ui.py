from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.plugins import coffee, food, goals, recipes


def sign_in(client: TestClient, settings: Settings) -> None:
    response = client.post(
        "/login",
        data={"token": settings.dashboard_token},
        headers={"Origin": settings.public_origin},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_launcher_is_compact_factual_and_ordered(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings)

    with TestClient(app, base_url=settings.public_origin) as client:
        sign_in(client, settings)
        coffee.add_bean(settings, "Daybreak")
        goals.create_goal(settings, "read", "health", "Read")
        recipe = recipes.link_recipe(settings, "Stew", "notes://example/stew")
        recipes.log_cook(settings, recipe["id"], rating=4)
        response = client.get("/")

    assert response.status_code == 200
    assert "Personal" not in response.text
    assert "1 open bean" in response.text
    assert "1 goal" in response.text
    assert "1 cook" in response.text
    assert "0 food records" in response.text
    assert "Four useful places" not in response.text
    assert "Local by design" not in response.text
    assert response.text.count('class="launcher-tile') == 5
    assert response.text.count("<svg") >= 5
    assert response.text.index("Goals") < response.text.index("Food")
    assert response.text.index("Food") < response.text.index("Recipes")
    assert response.text.index("Recipes") < response.text.index("Coffee")
    assert response.text.index("Coffee") < response.text.index("Health")


def test_pages_share_local_css_and_no_javascript(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings)

    with TestClient(app, base_url=settings.public_origin) as client:
        sign_in(client, settings)
        pages = [
            client.get(path)
            for path in ("/", "/coffee", "/goals", "/recipes", "/food", "/health")
        ]
        pico = client.get("/static/pico.min.css")
        styles = [client.get(f"/static/{name}.css") for name in ("tokens", "shell", "dashboard", "forms")]

    for page in pages:
        assert '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' in page.text
        assert 'href="/static/pico.min.css?v=' in page.text
        assert 'href="/static/tokens.css?v=' in page.text
        assert 'href="/static/dashboard.css?v=' in page.text
        assert "<script" not in page.text
        assert "onclick=" not in page.text
        assert "https://" not in page.text
    assert pico.status_code == 200
    assert all(style.status_code == 200 for style in styles)
    assert pico.headers["content-type"].startswith("text/css")


def test_plugin_pages_are_read_only_dashboards(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings)

    with TestClient(app, base_url=settings.public_origin) as client:
        sign_in(client, settings)
        goals.create_goal(settings, "make_progress", "health", "Make progress")
        pages = {
            "coffee": client.get("/coffee").text,
            "goals": client.get("/goals").text,
            "recipes": client.get("/recipes").text,
        }

    assert all("<main" in page and page.count("<form") == 1 for page in pages.values())
    assert "Add beans" not in pages["coffee"] and "Log shot" not in pages["coffee"]
    assert "Add goal" not in pages["goals"]
    assert "Current progress" not in pages["goals"]
    assert "Link recipe" not in pages["recipes"]
    for page in pages.values():
        assert ">Home<" not in page
        assert 'class="period-toggle"' in page


def test_login_page_is_small_and_accessible(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        response = client.get("/login")

    assert response.status_code == 200
    assert '<label for="token">' in response.text
    assert 'id="token"' in response.text
    assert 'autocomplete="current-password"' in response.text
    assert '<meta name="viewport"' in response.text


def test_food_page_is_read_only_and_reports_unresolved_counts(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)

    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        sign_in(client, settings)
        response = client.get("/food")

    assert response.status_code == 200
    assert "Food changes are handled through OpenClaw" not in response.text
    assert "Tracking issues" not in response.text
    assert "Food database" in response.text
    assert "Unresolved" in response.text
    assert response.text.count("<form") == 2  # Sign out and read-only catalogue filters.
    assert "<script" not in response.text


def test_food_catalogue_filters_sorts_and_caps_results(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        sign_in(client, settings)
        for index in range(12):
            food.upsert_nutrition(
                settings,
                f"rice-{index}",
                "Grain",
                f"Rice bowl {index}",
                600 - index,
                20 + index,
                70,
                15,
                "one bowl",
                "menu",
                "high",
                "official",
                category="rice bowls",
            )
        response = client.get(
            "/food?period=month&q=Rice&restaurant=Grain&sort=protein_desc"
        )

    assert response.status_code == 200
    assert response.text.count('class="catalogue-result"') == 10
    assert response.text.index("Rice bowl 11") < response.text.index("Rice bowl 10")
    assert 'name="period" value="month"' in response.text


def test_food_meal_disclosure_changes_with_period(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    today = datetime.now().astimezone().date()
    yesterday = today - timedelta(days=1)
    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        sign_in(client, settings)
        food.upsert_nutrition(
            settings,
            "meal",
            "Kitchen",
            "Meal",
            500,
            30,
            50,
            15,
            "one meal",
            "menu",
            "high",
            "official",
        )
        for record_id, consumed, slot, item in (
            ("today-lunch", today, "lunch", "Rice"),
            ("today-dinner", today, "dinner", "Soup"),
            ("yesterday-lunch", yesterday, "lunch", "Salad"),
        ):
            food.record_consumption(
                settings,
                record_id,
                consumed.isoformat(),
                slot,
                restaurant="Kitchen",
                item=item,
                nutrition_id="meal",
            )
        week = client.get("/food?period=week")
        month = client.get("/food?period=month")

    assert "Meals" in week.text and all(item in week.text for item in ("Rice", "Soup", "Salad"))
    monthly_meals = month.text.split('class="meal-days"', 1)[1].split("</ol>", 1)[0]
    assert "Days under two meals" in month.text
    assert yesterday.strftime("%d/%m/%Y") in monthly_meals and "1 meal" in monthly_meals
    assert today.strftime("%d/%m/%Y") not in monthly_meals


def test_shared_navigation_uses_accessible_icon_only_sign_out(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        sign_in(client, settings)
        response = client.get("/")

    assert 'class="sign-out"' in response.text
    assert 'aria-label="Sign out"' in response.text
    assert ">Sign out<" not in response.text
    assert 'class="lucide lucide-log-out"' in response.text
