from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RUNTIME_DEPENDENCIES = {
    "fastapi==0.141.1",
    "itsdangerous==2.2.0",
    "jinja2==3.1.6",
    "mcp==2.0.0",
    "pydantic==2.13.4",
    "python-multipart==0.0.32",
    "uvicorn==0.52.3",
}
EXPECTED_DEV_DEPENDENCIES = {
    "httpx==0.28.1",
    "pytest==9.1.1",
    "ruff==0.16.3",
}
EXPECTED_RUNTIME_LOCK_PACKAGES = {
    "annotated-doc",
    "annotated-types",
    "anyio",
    "attrs",
    "cffi",
    "click",
    "cryptography",
    "fastapi",
    "h11",
    "httpcore2",
    "httpx2",
    "idna",
    "itsdangerous",
    "jinja2",
    "jsonschema",
    "jsonschema-specifications",
    "markupsafe",
    "mcp",
    "mcp-types",
    "opentelemetry-api",
    "pycparser",
    "pydantic",
    "pydantic-core",
    "pyjwt",
    "python-multipart",
    "referencing",
    "rpds-py",
    "sse-starlette",
    "starlette",
    "truststore",
    "typing-extensions",
    "typing-inspection",
    "uvicorn",
}
EXPECTED_DEV_LOCK_PACKAGES = EXPECTED_RUNTIME_LOCK_PACKAGES | {
    "certifi",
    "httpcore",
    "httpx",
    "iniconfig",
    "packaging",
    "pluggy",
    "pygments",
    "pytest",
    "ruff",
}
REQUIRED_ENV_KEYS = {
    "HUBLET_BACKUP_DIR",
    "HUBLET_DASHBOARD_TOKEN",
    "HUBLET_DATA_DIR",
    "HUBLET_MCP_ALLOWED_HOSTS",
    "HUBLET_MCP_TOKEN",
    "HUBLET_PUBLIC_ORIGIN",
    "HUBLET_SESSION_SECRET",
}
REQUIRED_DOCKERIGNORE_ENTRIES = {
    ".coverage",
    ".coverage.*",
    ".env",
    ".env.*",
    "*.db",
    "*.egg-info/",
    "*.key",
    "*.pem",
    "*.sqlite",
    "*.sqlite3",
    "backups",
    "coverage.xml",
    "data",
    "deploy.env",
    "htmlcov/",
    "secrets",
    "secrets.env",
}
PINNED_REQUIREMENT = re.compile(r"^[A-Za-z0-9_.-]+==[^=\s]+$")


def read_env_example() -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in (REPOSITORY_ROOT / ".env.example").read_text().splitlines()
        if line and not line.startswith("#")
    )


def read_ignore_entries(filename: str) -> set[str]:
    return {
        line.strip()
        for line in (REPOSITORY_ROOT / filename).read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def read_lock(filename: str) -> dict[str, str]:
    lock_path = REPOSITORY_ROOT / filename
    assert lock_path.is_file()
    lines = [
        line.strip()
        for line in lock_path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert lines == sorted(
        lines,
        key=lambda line: line.split("==", 1)[0].casefold().replace("_", "-"),
    )
    assert all(PINNED_REQUIREMENT.fullmatch(line) for line in lines)
    packages = dict(line.split("==", 1) for line in lines)
    assert len(packages) == len(lines)
    return {name.casefold().replace("_", "-"): version for name, version in packages.items()}


def test_application_packages_import() -> None:
    assert importlib.import_module("app")
    assert importlib.import_module("app.plugins")


def test_example_environment_has_required_generic_settings() -> None:
    environment = read_env_example()

    assert set(environment) == REQUIRED_ENV_KEYS
    assert environment["HUBLET_BACKUP_DIR"] == "/backups"
    assert environment["HUBLET_MCP_ALLOWED_HOSTS"] == (
        "hublet.example.test:*,localhost:*,127.0.0.1:*"
    )


def test_dockerignore_excludes_private_and_generated_artifacts() -> None:
    assert REQUIRED_DOCKERIGNORE_ENTRIES <= read_ignore_entries(".dockerignore")


def test_project_metadata_has_only_approved_exact_direct_pins() -> None:
    project = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())["project"]

    assert project["requires-python"] == ">=3.13"
    assert set(project["dependencies"]) == EXPECTED_RUNTIME_DEPENDENCIES
    assert set(project["optional-dependencies"]["dev"]) == EXPECTED_DEV_DEPENDENCIES


def test_resolved_lock_files_are_pinned_and_separated() -> None:
    runtime = read_lock("requirements.lock")
    development = read_lock("requirements-dev.lock")
    runtime_direct = {item.split("==", 1)[0].casefold(): item.split("==", 1)[1] for item in EXPECTED_RUNTIME_DEPENDENCIES}
    dev_direct = {item.split("==", 1)[0].casefold(): item.split("==", 1)[1] for item in EXPECTED_DEV_DEPENDENCIES}

    assert set(runtime) == EXPECTED_RUNTIME_LOCK_PACKAGES
    assert set(development) == EXPECTED_DEV_LOCK_PACKAGES
    assert runtime_direct.items() <= runtime.items()
    assert runtime.items() <= development.items()
    assert dev_direct.items() <= development.items()
    assert dev_direct.keys().isdisjoint(runtime)


def test_readme_installs_from_locks_without_resolving_project_dependencies() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text()

    assert "pip install -r requirements-dev.lock" in readme
    assert "pip install --no-deps -e ." in readme
    assert REQUIRED_ENV_KEYS <= {key for key in REQUIRED_ENV_KEYS if key in readme}


def test_mcp_allowed_host_examples_use_sdk_wildcard_port_syntax() -> None:
    allowed_hosts = "hublet.example.test:*,localhost:*,127.0.0.1:*"

    assert allowed_hosts in (REPOSITORY_ROOT / ".env.example").read_text()
    assert allowed_hosts in (REPOSITORY_ROOT / "README.md").read_text()
    assert allowed_hosts in (REPOSITORY_ROOT / "hublet_spec.md").read_text()


def test_spec_locks_dashboard_session_semantics() -> None:
    specification = (REPOSITORY_ROOT / "hublet_spec.md").read_text()
    required_contract = {
        "Starlette `SessionMiddleware`",
        "`{\"authenticated\": true}`",
        "`max_age` of 90 days",
        "HttpOnly",
        "SameSite=Lax",
        "Path=/",
        "dashboard token rotation alone does not revoke existing sessions",
        "rotating `HUBLET_SESSION_SECRET` revokes all existing sessions",
    }

    assert all(statement in specification for statement in required_contract)
