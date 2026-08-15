from __future__ import annotations

import pytest

from app.config import Settings


def test_settings_load_valid_environment(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)

    assert settings.public_origin == "http://hublet.example.test:8787"
    assert settings.mcp_allowed_hosts == ("hublet.example.test:*", "localhost:*")
    assert settings.data_dir.name == "data"
    assert settings.backup_dir.name == "backups"


def test_settings_require_every_value(settings_env: dict[str, str]) -> None:
    del settings_env["HUBLET_MCP_TOKEN"]

    with pytest.raises(ValueError, match="HUBLET_MCP_TOKEN is required"):
        Settings.from_env(settings_env)


@pytest.mark.parametrize(
    "key",
    ["HUBLET_DASHBOARD_TOKEN", "HUBLET_SESSION_SECRET", "HUBLET_MCP_TOKEN"],
)
def test_settings_reject_short_or_placeholder_secrets(
    settings_env: dict[str, str], key: str
) -> None:
    settings_env[key] = "replace-me"

    with pytest.raises(ValueError, match=key):
        Settings.from_env(settings_env)


@pytest.mark.parametrize(
    "origin",
    [
        "hublet.example.test:8787",
        "ftp://hublet.example.test",
        "http://user@hublet.example.test",
        "http://hublet.example.test/path",
    ],
)
def test_settings_reject_invalid_public_origins(
    settings_env: dict[str, str], origin: str
) -> None:
    settings_env["HUBLET_PUBLIC_ORIGIN"] = origin

    with pytest.raises(ValueError, match="HUBLET_PUBLIC_ORIGIN"):
        Settings.from_env(settings_env)


def test_settings_reject_empty_mcp_host_list(settings_env: dict[str, str]) -> None:
    settings_env["HUBLET_MCP_ALLOWED_HOSTS"] = " , "

    with pytest.raises(ValueError, match="HUBLET_MCP_ALLOWED_HOSTS"):
        Settings.from_env(settings_env)
