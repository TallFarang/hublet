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
    assert response.text.count('class="launcher-tile') == 4
    assert response.text.count("<svg") >= 4
    assert response.text.index("Goals") < response.text.index("Food")
    assert response.text.index("Food") < response.text.index("Recipes")
    assert response.text.index("Recipes") < response.text.index("Coffee")


def test_pages_share_local_css_and_no_javascript(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings)

    with TestClient(app, base_url=settings.public_origin) as client:
        sign_in(client, settings)
        pages = [client.get(path) for path in ("/", "/coffee", "/goals", "/recipes", "/food")]
        pico = client.get("/static/pico.min.css")
        styles = [client.get(f"/static/{name}.css") for name in ("tokens", "shell", "dashboard", "forms")]

    for page in pages:
        assert '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' in page.text
        assert 'href="/static/pico.min.css"' in page.text
        assert 'href="/static/tokens.css"' in page.text
        assert "<script" not in page.text
        assert "onclick=" not in page.text
        assert "https://" not in page.text
    assert pico.status_code == 200
    assert all(style.status_code == 200 for style in styles)
    assert pico.headers["content-type"].startswith("text/css")


def test_plugin_pages_keep_manual_actions_findable(settings_env: dict[str, str]) -> None:
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

    assert all("<main" in page and "<form" in page for page in pages.values())
    assert "Add beans" in pages["coffee"] and "Log shot" in pages["coffee"]
    assert "Add goal" in pages["goals"]
    assert "Current measurement" not in pages["goals"]
    assert "Link recipe" in pages["recipes"]
    for page in pages.values():
        assert page.index('class="instrument-panel') < page.index('id="manage"')


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
    assert "Food changes are handled through OpenClaw" in response.text
    assert "Nutrition entries" in response.text
    assert "Unresolved" in response.text
    assert response.text.count("<form") == 1  # Shared sign-out form only.
    assert "<script" not in response.text


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
