from __future__ import annotations

from copy import deepcopy

import pytest

from app.config import Settings
from app.dashboard_config import DEFAULT_CONFIG
from app.dashboard_health import health_dashboard
from app.plugins import health
from app.plugins.health_query import query_records
from app.plugins.health_report import summary
from app.plugins.health_sync import sync_agentbridge
from app.runtime import migrate_plugins
from tests.health_fixtures import export_date, quantity, section, write_export


def prepared(settings_env: dict[str, str]) -> Settings:
    settings = Settings.from_env(settings_env)
    settings.agentbridge_dir.mkdir()
    migrate_plugins(settings, (health.PLUGIN,))
    return settings


def test_empty_source_is_valid_only_after_health_has_history(
    settings_env: dict[str, str],
) -> None:
    settings = prepared(settings_env)
    with pytest.raises(ValueError, match="no Agentbridge exports or stored Health history"):
        sync_agentbridge(settings)

    day = export_date()
    path = write_export(
        settings.agentbridge_dir,
        day,
        [
            section(
                "HKQuantityTypeIdentifierBodyMass", "quantity", [quantity("weight", 93, "kg", day)]
            )
        ],
    )
    sync_agentbridge(settings)
    path.unlink()

    result = sync_agentbridge(settings)
    assert result["changed"] is False and result["source_days"] == 0
    assert result["days"] == 1
    assert query_records(settings, "HKQuantityTypeIdentifierBodyMass", day, day)["total"] == 1


def test_practical_health_catalogue_normalises_without_changing_raw_records(
    settings_env: dict[str, str],
) -> None:
    settings = prepared(settings_env)
    day = export_date()
    sleep = {
        "value": 3,
        "start": f"{day}T00:00:00Z",
        "end": f"{day}T01:00:00Z",
        "source": {"bundleIdentifier": "test.health"},
    }
    write_export(
        settings.agentbridge_dir,
        day,
        [
            section(
                "HKQuantityTypeIdentifierBodyFatPercentage",
                "quantity",
                [quantity("fat", 0.25123, "%", day)],
            ),
            section(
                "HKQuantityTypeIdentifierLeanBodyMass",
                "quantity",
                [quantity("lean", 154.324, "lb", day)],
            ),
            section(
                "HKQuantityTypeIdentifierHeartRateRecoveryOneMinute",
                "quantity",
                [quantity("recovery", 31.86467, "count/min", day)],
            ),
            section(
                "HKCategoryTypeIdentifierSleepAnalysis",
                "category",
                [{"uuid": "sleep-a", **sleep}, {"uuid": "sleep-b", **sleep}],
            ),
            section(
                "HKQuantityTypeIdentifierVO2Max",
                "quantity",
                [quantity("vo2", 38.791234, "ml/(kg*min)", day)],
            ),
        ],
    )
    sync_agentbridge(settings)
    report = summary(settings, day, day)

    assert report["metrics"]["body_fat_percentage"]["latest"]["value"] == 25.123
    assert report["metrics"]["lean_body_mass_kg"]["latest"]["value"] == pytest.approx(70, abs=0.001)
    assert report["metrics"]["sleep_hours"]["latest"]["value"] == 1
    assert (
        query_records(
            settings, "HKQuantityTypeIdentifierBodyFatPercentage", day, day, include_raw=True
        )["records"][0]["raw"]["value"]
        == 0.25123
    )

    dashboard = health_dashboard(report)
    assert "vo2_max" not in {metric["name"] for metric in dashboard["metrics"]}
    config = deepcopy(DEFAULT_CONFIG["plugins"]["health"])
    next(metric for metric in config["metrics"] if metric["key"] == "vo2_max")["enabled"] = True
    vo2 = next(
        metric
        for metric in health_dashboard(report, config)["metrics"]
        if metric["name"] == "vo2_max"
    )
    assert vo2["value"] == "38.8"
