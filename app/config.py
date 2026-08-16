"""Environment-backed Hublet configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

REQUIRED_SETTINGS = (
    "HUBLET_AGENTBRIDGE_DIR",
    "HUBLET_BACKUP_DIR",
    "HUBLET_DASHBOARD_TOKEN",
    "HUBLET_DATA_DIR",
    "HUBLET_MCP_ALLOWED_HOSTS",
    "HUBLET_MCP_TOKEN",
    "HUBLET_PUBLIC_ORIGIN",
    "HUBLET_SESSION_SECRET",
)
SECRET_SETTINGS = (
    "HUBLET_DASHBOARD_TOKEN",
    "HUBLET_MCP_TOKEN",
    "HUBLET_SESSION_SECRET",
)
PLACEHOLDER_PREFIXES = ("change-me", "example", "placeholder", "replace-me")


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated settings needed by the single Hublet process."""

    data_dir: Path
    backup_dir: Path
    agentbridge_dir: Path
    public_origin: str
    mcp_allowed_hosts: tuple[str, ...]
    dashboard_token: str
    session_secret: str
    mcp_token: str

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if environment is None else environment
        missing = next((key for key in REQUIRED_SETTINGS if not values.get(key, "").strip()), None)
        if missing:
            raise ValueError(f"{missing} is required")

        for key in SECRET_SETTINGS:
            value = values[key]
            if len(value) < 32 or value.casefold().startswith(PLACEHOLDER_PREFIXES):
                raise ValueError(f"{key} must be a random value of at least 32 characters")

        public_origin = _validate_origin(values["HUBLET_PUBLIC_ORIGIN"].strip())
        allowed_hosts = tuple(
            host.strip()
            for host in values["HUBLET_MCP_ALLOWED_HOSTS"].split(",")
            if host.strip()
        )
        if not allowed_hosts or any(
            "://" in host or "/" in host or any(character.isspace() for character in host)
            for host in allowed_hosts
        ):
            raise ValueError("HUBLET_MCP_ALLOWED_HOSTS must be a comma-separated host list")

        return cls(
            data_dir=Path(values["HUBLET_DATA_DIR"]),
            backup_dir=Path(values["HUBLET_BACKUP_DIR"]),
            agentbridge_dir=Path(values["HUBLET_AGENTBRIDGE_DIR"]),
            public_origin=public_origin,
            mcp_allowed_hosts=allowed_hosts,
            dashboard_token=values["HUBLET_DASHBOARD_TOKEN"],
            session_secret=values["HUBLET_SESSION_SECRET"],
            mcp_token=values["HUBLET_MCP_TOKEN"],
        )


def _validate_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as error:
        raise ValueError("HUBLET_PUBLIC_ORIGIN must be a valid HTTP(S) origin") from error

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("HUBLET_PUBLIC_ORIGIN must be a valid HTTP(S) origin")
    return value
