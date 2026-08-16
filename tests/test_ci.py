from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_runs_clean_install_lint_and_tests_on_github_hosted_runner() -> None:
    workflow = WORKFLOW.read_text()

    assert "pull_request:" in workflow
    assert "pull_request_target" not in workflow
    assert "self-hosted" not in workflow
    assert workflow.count("runs-on: ubuntu-latest") == 1
    assert "actions/checkout@v6" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "pip install -r requirements-dev.lock" in workflow
    assert "pip install --no-deps -e ." in workflow
    assert "ruff check app tests" in workflow
    assert "pytest -q" in workflow
    assert "packages: write" not in workflow
    assert "docker/" not in workflow
