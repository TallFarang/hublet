from __future__ import annotations

import base64
import json
from dataclasses import replace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SESSION_MAX_AGE = 90 * 24 * 60 * 60


def make_client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings=settings), base_url=settings.public_origin)


def login(client: TestClient, settings: Settings, token: str | None = None):
    return client.post(
        "/login",
        data={"token": settings.dashboard_token if token is None else token},
        headers={"Origin": settings.public_origin},
        follow_redirects=False,
    )


def test_public_routes_do_not_require_dashboard_session(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with make_client(settings) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/health", follow_redirects=False).status_code == 303
        assert client.get("/login").status_code == 200


def test_dashboard_route_redirects_to_login(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with make_client(settings) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_every_html_post_requires_same_origin(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with make_client(settings) as client:
        missing = client.post("/login", data={"token": settings.dashboard_token})
        wrong = client.post(
            "/login",
            data={"token": settings.dashboard_token},
            headers={"Origin": "http://elsewhere.example.test"},
        )
        referer = client.post(
            "/login",
            data={"token": settings.dashboard_token},
            headers={"Referer": f"{settings.public_origin}/login"},
            follow_redirects=False,
        )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert referer.status_code == 303


def test_mcp_like_dashboard_path_still_requires_same_origin(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)

    with make_client(settings) as client:
        response = client.post("/mcp-settings")

    assert response.status_code == 403


def test_login_rejects_wrong_token_without_cookie(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with make_client(settings) as client:
        response = login(client, settings, token="wrong-token")

    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_login_sets_minimal_long_lived_session(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with make_client(settings) as client:
        response = login(client, settings)
        cookie = response.headers["set-cookie"]
        cookie_options = cookie.casefold()
        cookie_value = client.cookies["hublet_session"]
        payload = json.loads(base64.b64decode(cookie_value.split(".", 1)[0]))
        authenticated = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert payload == {"authenticated": True}
    assert settings.dashboard_token not in cookie
    assert f"Max-Age={SESSION_MAX_AGE}" in cookie
    assert "httponly" in cookie_options
    assert "samesite=lax" in cookie_options
    assert "path=/" in cookie_options
    assert "secure" not in cookie_options
    assert authenticated.status_code == 200
    assert "Hublet plugins" in authenticated.text


def test_https_origin_sets_secure_cookie(settings_env: dict[str, str]) -> None:
    settings_env["HUBLET_PUBLIC_ORIGIN"] = "https://hublet.example.test"
    settings = Settings.from_env(settings_env)

    with make_client(settings) as client:
        response = login(client, settings)

    assert "secure" in response.headers["set-cookie"].casefold()


def test_tampered_expired_or_rotated_session_is_rejected(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with make_client(settings) as client:
        login(client, settings)
        valid_cookie = client.cookies["hublet_session"]
        client.cookies.set("hublet_session", f"{valid_cookie}tampered")
        assert client.get("/", follow_redirects=False).status_code == 303

    with make_client(settings) as client, patch("itsdangerous.timed.time.time", return_value=0):
        login(client, settings)
        expired_cookie = client.cookies["hublet_session"]
    with make_client(settings) as client:
        client.cookies.set("hublet_session", expired_cookie)
        assert client.get("/", follow_redirects=False).status_code == 303

    with make_client(settings) as client:
        login(client, settings)
        old_cookie = client.cookies["hublet_session"]
    rotated = replace(settings, session_secret="z" * 40)
    with make_client(rotated) as client:
        client.cookies.set("hublet_session", old_cookie)
        assert client.get("/", follow_redirects=False).status_code == 303


def test_dashboard_token_rotation_does_not_revoke_session(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    with make_client(settings) as client:
        login(client, settings)
        cookie = client.cookies["hublet_session"]

    rotated = replace(settings, dashboard_token="w" * 40)
    with make_client(rotated) as client:
        client.cookies.set("hublet_session", cookie)
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 200


def test_mcp_token_cannot_log_in_to_dashboard(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with make_client(settings) as client:
        response = login(client, settings, settings.mcp_token)

    assert response.status_code == 401


def test_logout_clears_session_and_requires_origin(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with make_client(settings) as client:
        login(client, settings)
        blocked = client.post("/logout")
        response = client.post(
            "/logout",
            headers={"Origin": settings.public_origin},
            follow_redirects=False,
        )
        dashboard = client.get("/", follow_redirects=False)

    assert blocked.status_code == 403
    assert response.status_code == 303
    assert dashboard.status_code == 303
