from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, create_app
from tests.test_runtime import make_plugin


def test_uvicorn_factory_target_is_available() -> None:
    assert app is create_app


def test_health_reports_registered_plugin(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    app = create_app(settings=settings, plugins=(make_plugin(),))

    with TestClient(app, base_url=settings.public_origin) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "plugins": {"example": "ok"}}
