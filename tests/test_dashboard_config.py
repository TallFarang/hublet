from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from mcp.server import MCPServer

from app.config import Settings
from app.dashboard_config import DEFAULT_CONFIG, FILENAME, load_config, register_mcp, replace_config
from app.main import create_app
from app.plugins import coffee
from tests.test_auth import login


def test_defaults_need_no_file_and_mcp_exposes_one_document(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    assert load_config(settings) == DEFAULT_CONFIG
    assert not (settings.data_dir / FILENAME).exists()

    server = MCPServer("test")
    register_mcp(server, settings)
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == {
        "dashboard_config_get",
        "dashboard_config_replace",
    }


def test_replace_is_atomic_and_rejects_unknown_or_invalid_settings(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    configured = deepcopy(DEFAULT_CONFIG)
    configured["plugins"]["health"]["metrics"][0]["label"] = "Weight"
    replace_config(settings, configured)
    before = (settings.data_dir / FILENAME).read_bytes()

    invalid = deepcopy(configured)
    invalid["plugins"]["health"]["metrics"][0]["precision"] = 4
    with pytest.raises(ValueError, match="precision"):
        replace_config(settings, invalid)
    assert (settings.data_dir / FILENAME).read_bytes() == before

    invalid = deepcopy(configured)
    invalid["plugins"]["health"]["metrics"][0]["key"] = "made_up"
    with pytest.raises(ValueError, match="unsupported"):
        replace_config(settings, invalid)

    invalid = deepcopy(configured)
    invalid["plugins"]["health"]["metrics"].pop()
    with pytest.raises(ValueError, match="every supported metric"):
        replace_config(settings, invalid)
    assert load_config(settings) == configured


def test_dashboard_uses_configured_order_labels_and_visibility(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    configured = deepcopy(DEFAULT_CONFIG)
    metrics = configured["plugins"]["coffee"]["metrics"]
    for metric in metrics:
        metric["enabled"] = metric["key"] == "bean_count"
    metrics[0]["label"] = "Beans now"
    replace_config(settings, configured)

    with TestClient(
        create_app(settings=settings, plugins=(coffee.PLUGIN,)),
        base_url=settings.public_origin,
    ) as client:
        login(client, settings)
        coffee.add_bean(settings, "Daybreak")
        page = client.get("/coffee")

    assert "Beans now" in page.text and ">1<" in page.text
    assert "Latest ratio" not in page.text and "Extraction ratio" not in page.text
