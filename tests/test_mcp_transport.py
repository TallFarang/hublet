from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def auth_header(settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.mcp_token}"}


def test_mcp_requires_bearer_for_every_method(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        responses = [
            client.get("/mcp"),
            client.post("/mcp", json={}),
            client.delete("/mcp"),
        ]

    assert {response.status_code for response in responses} == {401}
    assert all(response.headers["www-authenticate"] == "Bearer" for response in responses)


def test_mcp_rejects_wrong_bearer_query_and_cookie(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        wrong = client.post("/mcp", headers={"Authorization": "Bearer wrong"}, json={})
        query = client.post(f"/mcp?token={settings.mcp_token}", json={})
        client.cookies.set("token", settings.mcp_token)
        cookie = client.post("/mcp", json={})

    assert wrong.status_code == 401
    assert query.status_code == 401
    assert cookie.status_code == 401


def test_dashboard_token_cannot_authenticate_mcp(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        response = client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {settings.dashboard_token}"},
            json={},
        )

    assert response.status_code == 401


def test_authorized_mcp_initializes_with_top_level_lifespan(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "hublet-test", "version": "1"},
        },
    }
    headers = {
        **auth_header(settings),
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        response = client.post("/mcp", headers=headers, json=initialize)

    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "Hublet"


def test_mcp_transport_rejects_unlisted_host(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    with TestClient(
        create_app(settings=settings), base_url="http://unlisted.example.test:8787"
    ) as client:
        response = client.post("/mcp", headers=auth_header(settings), json={})

    assert response.status_code == 421
