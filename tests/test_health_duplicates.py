from __future__ import annotations

from app.config import Settings
from app.plugins import health
from app.plugins.health_query import query_records
from app.plugins.health_report import summary
from app.plugins.health_sync import sync_agentbridge
from app.runtime import migrate_plugins
from tests.health_fixtures import export_date, quantity, section, write_export


def prepared(settings_env: dict[str, str], sections: list[dict]) -> tuple[Settings, str]:
    settings = Settings.from_env(settings_env)
    settings.agentbridge_dir.mkdir()
    migrate_plugins(settings, (health.PLUGIN,))
    day = export_date()
    write_export(settings.agentbridge_dir, day, sections)
    sync_agentbridge(settings)
    return settings, day


def test_semantic_quantity_duplicates_remain_raw_but_report_once(
    settings_env: dict[str, str],
) -> None:
    day = export_date()
    type_name = "HKQuantityTypeIdentifierBodyMass"
    settings, day = prepared(
        settings_env,
        [
            section(
                type_name,
                "quantity",
                [quantity("weight-b", 92.5, "kg", day), quantity("weight-a", 92.5, "kg", day)],
            )
        ],
    )

    raw = query_records(settings, type_name, day, day)
    report = summary(settings, day, day)
    metric = report["metrics"]["body_weight_kg"]

    assert raw["total"] == 2
    assert len(metric["samples"]) == 1
    assert len([row for row in report["evidence"] if row["metric"] == "body_weight_kg"]) == 1
    assert report["record_counts"] == {"raw": 2, "reported": 1, "duplicates_suppressed": 1}
    assert metric["samples"][0]["uuid"] == "weight-a"


def test_semantic_matching_respects_time_value_and_source(
    settings_env: dict[str, str],
) -> None:
    day = export_date()
    type_name = "HKQuantityTypeIdentifierVO2Max"
    baseline = quantity("base", 41.0, "ml/(kg*min)", day)
    later = {**quantity("later", 41.0, "ml/(kg*min)", day), "start": f"{day}T09:00:00Z"}
    changed = quantity("changed", 42.0, "ml/(kg*min)", day)
    other_source = quantity("source", 41.0, "ml/(kg*min)", day)
    other_source["source"] = {"bundleIdentifier": "other.health"}
    settings, day = prepared(
        settings_env,
        [section(type_name, "quantity", [baseline, later, changed, other_source])],
    )

    report = summary(settings, day, day)

    assert len(report["metrics"]["vo2_max"]["samples"]) == 4
    assert report["record_counts"]["duplicates_suppressed"] == 0


def test_semantic_workout_duplicates_count_once(settings_env: dict[str, str]) -> None:
    day = export_date()
    workout = {
        "durationSeconds": 1200,
        "activityType": 9,
        "start": f"{day}T08:00:00Z",
        "end": f"{day}T08:20:00Z",
        "source": {"bundleIdentifier": "test.health"},
    }
    settings, day = prepared(
        settings_env,
        [
            section(
                "HKWorkoutTypeIdentifier",
                "workout",
                [{**workout, "uuid": "workout-b"}, {**workout, "uuid": "workout-a"}],
            )
        ],
    )

    report = summary(settings, day, day)

    assert report["metrics"]["workouts_completed"]["latest"]["value"] == 1
    assert report["record_counts"]["duplicates_suppressed"] == 1
