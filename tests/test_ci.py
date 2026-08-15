from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci-deploy.yml"


def test_ci_tests_changes_and_publishes_green_main_images() -> None:
    workflow = WORKFLOW.read_text()

    assert "pull_request:" in workflow
    assert "pull_request_target" not in workflow
    assert "self-hosted" not in workflow
    assert workflow.count("runs-on: ubuntu-latest") == 2
    assert "actions/checkout@v6" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "pip install -r requirements-dev.lock" in workflow
    assert "pip install --no-deps -e ." in workflow
    assert "ruff check app tests" in workflow
    assert "pytest -q" in workflow
    assert "needs: test" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "packages: write" in workflow
    assert "docker/login-action@v4" in workflow
    assert "docker/setup-qemu-action@v4" in workflow
    assert "docker/setup-buildx-action@v4" in workflow
    assert "docker/build-push-action@v7" in workflow
    assert "platforms: linux/amd64,linux/arm64" in workflow
    assert "ghcr.io/tallfarang/hublet:latest" in workflow
    assert "ghcr.io/tallfarang/hublet:${{ github.sha }}" in workflow
