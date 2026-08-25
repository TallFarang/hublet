from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from app.config import Settings
from app.plugins import health
from app.plugins.health_parse import build_snapshot
from app.plugins.health_query import list_types, query_records
from app.plugins.health_sync import sync_agentbridge
from app.runtime import migrate_plugins
from tests.health_fixtures import export_date, quantity, section, write_export


@pytest.fixture
def health_settings(settings_env: dict[str, str]) -> Settings:
    settings = Settings.from_env(settings_env)
    settings.agentbridge_dir.mkdir()
    migrate_plugins(settings, (health.PLUGIN,))
    return settings


def test_sync_normalizes_known_kinds_and_keeps_unknown_json(health_settings: Settings) -> None:
    day = export_date()
    sections = [
        section(
            "HKQuantityTypeIdentifierBodyMass",
            "quantity",
            [quantity("weight-1", 200, "lb", day)],
        ),
        section(
            "UnknownFruitType",
            "newKind",
            [{"uuid": "fruit-1", "banana": 7, "futureField": {"kept": True}}],
        ),
        section("HKCategoryTypeIdentifierSleepAnalysis", "category", [{"uuid": "sleep-1", "value": 1}]),
        section("HKActivitySummaryTypeIdentifier", "activitySummary", [{"activeEnergy": 500}]),
        section(
            "HKWorkoutTypeIdentifier",
            "workout",
            [{"uuid": "workout-1", "durationSeconds": 600, "activityType": 9}],
        ),
    ]
    write_export(health_settings.agentbridge_dir, day, sections, selection=[*[row["type"] for row in sections], "SelectedButMissing"])

    dry_run = sync_agentbridge(health_settings, dry_run=True)
    first = sync_agentbridge(health_settings)
    before = query_records(health_settings, "UnknownFruitType", day, day, include_raw=True)
    second = sync_agentbridge(health_settings)
    weight = query_records(health_settings, "HKQuantityTypeIdentifierBodyMass", day, day)

    assert dry_run["records"] == 5 and dry_run["changed"] is True
    assert first["changed"] is True and second["changed"] is False
    assert weight["records"][0]["normalized_value"] == pytest.approx(90.718474)
    assert before["records"][0]["raw"]["futureField"] == {"kept": True}
    assert {row["type"] for row in list_types(health_settings)} >= {
        "UnknownFruitType",
        "SelectedButMissing",
    }


def test_duplicate_uuid_collapses_and_conflicts_abort(health_settings: Settings) -> None:
    first_day, second_day = export_date(2), export_date(1)
    record = quantity("repeat", 55, "count/min", first_day)
    type_name = "HKQuantityTypeIdentifierRestingHeartRate"
    write_export(health_settings.agentbridge_dir, first_day, [section(type_name, "quantity", [record])])
    write_export(health_settings.agentbridge_dir, second_day, [section(type_name, "quantity", [record])])
    sync_agentbridge(health_settings)

    collapsed = query_records(health_settings, type_name, first_day, second_day)
    assert collapsed["total"] == 1
    assert collapsed["records"][0]["source_dates"] == [first_day, second_day]

    write_export(
        health_settings.agentbridge_dir,
        second_day,
        [section(type_name, "quantity", [quantity("repeat", 60, "count/min", second_day)])],
        revision=2,
    )
    with pytest.raises(ValueError, match="conflicting HealthKit UUID"):
        sync_agentbridge(health_settings)
    assert query_records(health_settings, type_name, first_day, second_day)["records"][0]["normalized_value"] == 55


def test_revision_replaces_snapshot_and_invalid_revision_rolls_back(health_settings: Settings) -> None:
    day = export_date()
    type_name = "HKQuantityTypeIdentifierVO2Max"
    write_export(health_settings.agentbridge_dir, day, [section(type_name, "quantity", [quantity("vo2", 38, "ml/(kg*min)", day)])])
    sync_agentbridge(health_settings)
    write_export(
        health_settings.agentbridge_dir,
        day,
        [section(type_name, "quantity", [quantity("vo2", 40, "ml/(kg*min)", day)])],
        revision=2,
    )
    sync_agentbridge(health_settings)
    assert query_records(health_settings, type_name, day, day)["records"][0]["normalized_value"] == 40

    write_export(
        health_settings.agentbridge_dir,
        day,
        [section(type_name, "quantity", [])],
        revision=3,
        bad_digest=True,
    )
    with pytest.raises(ValueError, match="content digest"):
        sync_agentbridge(health_settings)
    assert query_records(health_settings, type_name, day, day)["total"] == 1


def test_database_failure_preserves_snapshot(health_settings: Settings) -> None:
    day = export_date()
    write_export(health_settings.agentbridge_dir, day, [section("Unknown", "new", [{"uuid": "one"}])])
    sync_agentbridge(health_settings)
    snapshot = build_snapshot(health_settings.agentbridge_dir)
    snapshot["dataset_digest"] = "sha256:changed"
    snapshot["records"].append(dict(snapshot["records"][0]))
    with (
        patch("app.plugins.health_sync._merge", return_value=(snapshot, "sha256:old")),
        pytest.raises(sqlite3.IntegrityError),
    ):
        sync_agentbridge(health_settings)
    assert query_records(health_settings, "Unknown", day, day)["total"] == 1


def test_rolling_window_retains_history_and_replaces_current_dates(
    health_settings: Settings,
) -> None:
    old_day, current_day, new_day = export_date(3), export_date(2), export_date(1)
    type_name = "HKQuantityTypeIdentifierVO2Max"
    old_path = write_export(
        health_settings.agentbridge_dir,
        old_day,
        [section(type_name, "quantity", [quantity("old", 31, "ml/(kg*min)", old_day)])],
    )
    write_export(
        health_settings.agentbridge_dir,
        current_day,
        [section(type_name, "quantity", [quantity("current", 32, "ml/(kg*min)", current_day)])],
    )
    sync_agentbridge(health_settings)

    old_path.unlink()
    write_export(
        health_settings.agentbridge_dir,
        current_day,
        [section(type_name, "quantity", [quantity("current", 42, "ml/(kg*min)", current_day)])],
        revision=2,
    )
    write_export(
        health_settings.agentbridge_dir,
        new_day,
        [section(type_name, "quantity", [quantity("new", 33, "ml/(kg*min)", new_day)])],
    )

    dry_run = sync_agentbridge(health_settings, dry_run=True)
    assert dry_run["changed"] is True and dry_run["days"] == 3
    assert query_records(health_settings, type_name, old_day, new_day)["total"] == 2

    result = sync_agentbridge(health_settings)
    rows = query_records(health_settings, type_name, old_day, new_day)["records"]
    type_summary = next(row for row in list_types(health_settings) if row["type"] == type_name)
    assert result["days"] == 3 and result["records"] == 3
    assert [row["normalized_value"] for row in rows] == [33, 42, 31]
    assert (type_summary["first_date"], type_summary["latest_date"]) == (old_day, new_day)
    assert sync_agentbridge(health_settings)["changed"] is False


def test_uuid_conflict_with_retained_history_aborts(health_settings: Settings) -> None:
    old_day, new_day = export_date(2), export_date(1)
    type_name = "HKQuantityTypeIdentifierRestingHeartRate"
    old_path = write_export(
        health_settings.agentbridge_dir,
        old_day,
        [section(type_name, "quantity", [quantity("repeat", 55, "count/min", old_day)])],
    )
    sync_agentbridge(health_settings)
    old_path.unlink()
    write_export(
        health_settings.agentbridge_dir,
        new_day,
        [section(type_name, "quantity", [quantity("repeat", 60, "count/min", new_day)])],
    )

    with pytest.raises(ValueError, match="conflicting HealthKit UUID"):
        sync_agentbridge(health_settings)
    rows = query_records(health_settings, type_name, old_day, new_day)["records"]
    assert len(rows) == 1 and rows[0]["normalized_value"] == 55


def test_symlink_cannot_escape_configured_directory(health_settings: Settings, tmp_path) -> None:
    day = export_date()
    outside = tmp_path / f"{day}-r001.json"
    outside.write_text("{}")
    (health_settings.agentbridge_dir / outside.name).symlink_to(outside)

    with pytest.raises(ValueError, match="escapes configured directory"):
        sync_agentbridge(health_settings, dry_run=True)
