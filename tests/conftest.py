from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def settings_env(tmp_path: Path) -> dict[str, str]:
    secret = "x" * 40
    return {
        "HUBLET_AGENTBRIDGE_DIR": str(tmp_path / "agentbridge"),
        "HUBLET_BACKUP_DIR": str(tmp_path / "backups"),
        "HUBLET_DASHBOARD_TOKEN": secret,
        "HUBLET_DATA_DIR": str(tmp_path / "data"),
        "HUBLET_MCP_ALLOWED_HOSTS": "hublet.example.test:*,localhost:*",
        "HUBLET_MCP_TOKEN": "z" * 40,
        "HUBLET_PUBLIC_ORIGIN": "http://hublet.example.test:8787",
        "HUBLET_SESSION_SECRET": "y" * 40,
    }
