from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.plugins import coffee, goals, recipes


def sign_in(client: TestClient, settings: Settings) -> None:
    response = client.post(
        "/login",
        data={"token": settings.dashboard_token},
        headers={"Origin": settings.public_origin},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_launcher_renders_three_useful_local_cards(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings)

    with TestClient(app, base_url=settings.public_origin) as client:
        sign_in(client, settings)
        coffee.add_bean(settings, "Daybreak")
        goals.create_goal(settings, "Read")
        recipe = recipes.link_recipe(settings, "Stew", "notes://example/stew")
        recipes.log_cook(settings, recipe["id"], rating=4)
        response = client.get("/")

    assert response.status_code == 200
    assert "Personal" in response.text
    assert "1 open bean" in response.text
    assert "1 active goal" in response.text
    assert "1 cook" in response.text
    assert response.text.count('class="launcher-card') == 3
    assert response.text.count("<svg") >= 3


def test_pages_share_local_css_and_no_javascript(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings)

    with TestClient(app, base_url=settings.public_origin) as client:
        sign_in(client, settings)
        pages = [client.get(path) for path in ("/", "/coffee", "/goals", "/recipes")]
        pico = client.get("/static/pico.min.css")
        custom = client.get("/static/app.css")

    for page in pages:
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in page.text
        assert 'href="/static/pico.min.css"' in page.text
        assert 'href="/static/app.css"' in page.text
        assert "<script" not in page.text
        assert "https://" not in page.text
    assert pico.status_code == 200
    assert custom.status_code == 200
    assert pico.headers["content-type"].startswith("text/css")


def test_plugin_pages_keep_manual_actions_findable(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings)

    with TestClient(app, base_url=settings.public_origin) as client:
        sign_in(client, settings)
        goals.create_goal(settings, "Make progress")
        pages = {
            "coffee": client.get("/coffee").text,
            "goals": client.get("/goals").text,
            "recipes": client.get("/recipes").text,
        }

    assert all("<main" in page and "<form" in page for page in pages.values())
    assert "Add beans" in pages["coffee"] and "Log a shot" in pages["coffee"]
    assert "Add a goal" in pages["goals"] and "Current measurement" in pages["goals"]
    assert "Link a recipe" in pages["recipes"] and "Recipe content stays in Apple Notes" in pages[
        "recipes"
    ]


def test_login_page_is_small_and_accessible(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        response = client.get("/login")

    assert response.status_code == 200
    assert '<label for="token">' in response.text
    assert 'id="token"' in response.text
    assert 'autocomplete="current-password"' in response.text
    assert '<meta name="viewport"' in response.text
