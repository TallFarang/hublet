from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.db import migrate
from app.plugins import goals
from app.plugins.goals_import import import_registry, load_yaml, normalise_registry

EXAMPLE_YAML = """
schema_version: 1
owner: Example Person
reporting:
  cadence: weekly
  channel: Example channel
domains:
  health:
    status: active
    goals:
      - id: durable_target
        title: Durable target
        outcome: Reach a durable target
        horizon: medium_term
        outcome_target:
          metric: monthly_value
          target: 100000
          unit: credits
          direction: at_or_above
          income_basis: personal_income
          required_duration: 3_consecutive_months
        status: active
        systems:
          - Follow the useful system.
        evidence:
          - metric: monthly_value
            cadence: monthly
            source: Automatic source
            tracking_status: not_connected
            access: Read only
            collection_note: One-time setup is required.
            current_reference_target: 90000
        notes:
          - The threshold is deliberate.
      - id: trend_target
        outcome: Increase a supporting metric
        horizon: short_term
        outcome_target: null
        status: awaiting_automatic_data
        dependencies:
          - durable_target
        systems: []
        evidence:
          - metric: weekly_count
            cadence: weekly
            source: Automatic source
            target: increasing_trend
            tracking_status: connected
  career:
    status: active
    goals: []
  social:
    status: tbc
    goals: []
change_log:
  - date: 2026-08-11
    change: Example change that belongs outside Hublet.
"""


@pytest.fixture
def goal_settings(settings_env: dict[str, str]) -> Settings:
    settings = Settings.from_env(settings_env)
    migrate(settings.data_dir / goals.DB_FILENAME, goals.MIGRATIONS)
    return settings


def test_dependency_free_yaml_loader_reads_trusted_file(tmp_path: Path) -> None:
    source = tmp_path / "registry.yaml"
    source.write_text(EXAMPLE_YAML)

    loaded = load_yaml(source)

    assert loaded["schema_version"] == 1
    assert str(loaded["change_log"][0]["date"]) == "2026-08-11"


def test_yaml_mapping_preserves_goal_semantics_and_excludes_reporting(tmp_path: Path) -> None:
    mapped = normalise_registry(load_yaml_text(EXAMPLE_YAML, tmp_path))
    durable, trend = mapped["goals"]

    assert [domain["id"] for domain in mapped["domains"]] == ["health", "career", "social"]
    assert durable["id"] == "durable_target"
    assert durable["title"] == "Durable target"
    assert durable["target"]["required_duration"] == {
        "count": 3,
        "unit": "months",
        "consecutive": True,
    }
    assert durable["target"]["qualifiers"] == {"income_basis": "personal_income"}
    assert durable["evidence_sources"][0]["access_notes"] == "Read only"
    assert durable["evidence_sources"][0]["details"] == {
        "current_reference_target": 90000
    }
    assert trend["target"]["direction"] == "increasing_trend"
    assert trend["dependencies"] == ["durable_target"]
    assert "reporting" not in mapped
    assert "change_log" not in mapped


def test_import_is_atomic_round_trips_ids_and_leaves_source_untouched(
    goal_settings: Settings, tmp_path: Path
) -> None:
    source = tmp_path / "registry.yaml"
    source.write_text(EXAMPLE_YAML)
    before = source.read_bytes()
    registry = normalise_registry(load_yaml(source))

    result = import_registry(goal_settings, registry)
    saved = goals.get_registry(goal_settings)

    assert result == {"domains": 3, "goals": 2}
    assert source.read_bytes() == before
    assert [goal["id"] for goal in saved["domains"][0]["goals"]] == [
        "durable_target",
        "trend_target",
    ]
    assert saved["domains"][0]["goals"][0]["title"] == "Durable target"
    assert saved["domains"][2]["status"] == "tbc"
    with pytest.raises(ValueError, match="empty"):
        import_registry(goal_settings, registry)


def test_import_validation_rejects_missing_dependencies(tmp_path: Path) -> None:
    registry = normalise_registry(load_yaml_text(EXAMPLE_YAML, tmp_path))
    registry["goals"][1]["dependencies"] = ["missing"]

    with pytest.raises(ValueError, match="dependency"):
        import_registry_shape(registry)


def load_yaml_text(contents: str, tmp_path: Path) -> dict:
    source = tmp_path / "registry.yaml"
    source.write_text(contents)
    return load_yaml(source)


def import_registry_shape(registry: dict) -> None:
    """Exercise validation without needing a database write."""
    from app.plugins.goals_import import validate_registry

    validate_registry(registry)
