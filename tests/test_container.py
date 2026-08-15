from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]


def test_dockerfile_runs_one_unprivileged_process_from_runtime_lock() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text()

    assert dockerfile.startswith("FROM python:3.13-slim\n")
    assert "pip install --no-cache-dir -r requirements.lock" in dockerfile
    assert "requirements-dev.lock" not in dockerfile
    assert "USER nobody" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "http://127.0.0.1:8000/health" in dockerfile
    assert (
        'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", '
        '"--workers", "1"]'
    ) in dockerfile


def test_compose_uses_generic_host_paths_and_restart_policy() -> None:
    compose = (REPOSITORY_ROOT / "compose.yml").read_text()

    assert "ghcr.io/tallfarang/hublet:latest" in compose
    assert "build: ." in compose
    assert "restart: unless-stopped" in compose
    assert '- "8787:8000"' in compose
    assert "HUBLET_HOST_DATA_DIR" in compose
    assert "HUBLET_HOST_BACKUP_DIR" in compose
    assert "HUBLET_ENV_FILE" in compose
    assert "/data" in compose
    assert "/backups" in compose
