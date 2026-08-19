from __future__ import annotations

from app.config import Settings
from app.db import migrate
from app.plugins import goals


def test_connected_hublet_food_sources_report_real_gaps_and_evidence(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    migrate(settings.data_dir / goals.DB_FILENAME, goals.MIGRATIONS)
    sources = [
        {
            "metric": metric,
            "cadence": "weekly",
            "source": "Hublet Food",
            "tracking_status": "connected",
            "role": "supporting_indicator",
        }
        for metric in ("calorie_target_adherence", "recorded_food_summary")
    ]
    goals.create_goal(
        settings,
        "food_evidence",
        "health",
        "Use canonical food evidence",
        title="Food evidence",
        evidence_sources=sources,
    )

    empty = goals.report_snapshot(settings, "2026-08-10", "2026-08-16")
    empty_evidence = empty["domains"][0]["goals"][0]["evidence"]
    assert {item["gap"] for item in empty_evidence} == {"no_observation_in_period"}

    for metric, value in (
        ("calorie_target_adherence", True),
        ("recorded_food_summary", "Seven complete days"),
    ):
        goals.record_evidence(
            settings,
            "food_evidence",
            metric,
            value,
            "Hublet Food",
            f"hublet-food:{metric}:2026-08-10:2026-08-16",
            period_start="2026-08-10",
            period_end="2026-08-16",
        )

    reported = goals.report_snapshot(settings, "2026-08-10", "2026-08-16")
    evidence = reported["domains"][0]["goals"][0]["evidence"]
    assert all(item["gap"] is None and len(item["observations"]) == 1 for item in evidence)
    assert {item["source_definition"]["source"] for item in evidence} == {"Hublet Food"}
