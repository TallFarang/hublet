from __future__ import annotations

import sqlite3
import tomllib
from datetime import date, timedelta
from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch

from app import backup
from app.config import Settings
from app.plugins import PLUGINS

REPOSITORY_ROOT = Path(__file__).parents[1]
SNAPSHOT_MARKER = ".hublet-snapshot"


def test_snapshot_databases_captures_all_live_databases(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    settings.data_dir.mkdir()
    live_connections = []

    try:
        for plugin in PLUGINS:
            connection = sqlite3.connect(settings.data_dir / plugin.db_filename)
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA wal_autocheckpoint = 0")
            connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
            connection.execute("INSERT INTO marker VALUES (?)", (plugin.name,))
            connection.commit()
            live_connections.append(connection)

        snapshot = backup.snapshot_databases(settings, PLUGINS, today=date(2026, 8, 15))

        assert snapshot == settings.backup_dir / "2026-08-15"
        for plugin in PLUGINS:
            with sqlite3.connect(snapshot / plugin.db_filename) as copy:
                assert copy.execute("SELECT value FROM marker").fetchone()[0] == plugin.name
    finally:
        for connection in live_connections:
            connection.close()


def test_snapshot_databases_keeps_thirty_daily_snapshots(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    settings.data_dir.mkdir()
    settings.backup_dir.mkdir()
    today = date(2026, 8, 15)

    for plugin in PLUGINS:
        sqlite3.connect(settings.data_dir / plugin.db_filename).close()
    for age in range(1, 32):
        old_snapshot = settings.backup_dir / (today - timedelta(days=age)).isoformat()
        old_snapshot.mkdir()
        (old_snapshot / SNAPSHOT_MARKER).touch()
    unrelated = settings.backup_dir / "keep-me"
    unrelated.mkdir()
    unrelated_date = settings.backup_dir / (today + timedelta(days=1)).isoformat()
    unrelated_date.mkdir()

    backup.snapshot_databases(settings, PLUGINS, today=today)

    daily_snapshots = sorted(
        path.name
        for path in settings.backup_dir.iterdir()
        if (path / SNAPSHOT_MARKER).is_file()
    )
    assert len(daily_snapshots) == 30
    assert daily_snapshots[0] == (today - timedelta(days=29)).isoformat()
    assert daily_snapshots[-1] == today.isoformat()
    assert unrelated.is_dir()
    assert unrelated_date.is_dir()


def test_snapshot_databases_rejects_a_missing_source(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    settings.data_dir.mkdir()
    for plugin in PLUGINS[:-1]:
        sqlite3.connect(settings.data_dir / plugin.db_filename).close()
    missing = settings.data_dir / PLUGINS[-1].db_filename

    with pytest.raises(FileNotFoundError, match=missing.name):
        backup.snapshot_databases(settings, PLUGINS, today=date(2026, 8, 15))

    assert not missing.exists()
    assert not (settings.backup_dir / "2026-08-15").exists()


def test_failed_backup_does_not_publish_a_partial_snapshot(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    settings.data_dir.mkdir()
    for plugin in PLUGINS:
        source = settings.data_dir / plugin.db_filename
        if plugin is PLUGINS[1]:
            source.write_text("not a database")
        else:
            sqlite3.connect(source).close()

    with pytest.raises(sqlite3.DatabaseError):
        backup.snapshot_databases(settings, PLUGINS, today=date(2026, 8, 15))

    assert not (settings.backup_dir / "2026-08-15").exists()


def test_snapshot_databases_does_not_replace_an_existing_snapshot(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    settings.data_dir.mkdir()
    for plugin in PLUGINS:
        sqlite3.connect(settings.data_dir / plugin.db_filename).close()
    existing = settings.backup_dir / "2026-08-15"
    existing.mkdir(parents=True)
    (existing / SNAPSHOT_MARKER).touch()
    sentinel = existing / "coffee.db"
    sentinel.write_text("original snapshot")

    with pytest.raises(FileExistsError, match="already exists"):
        backup.snapshot_databases(settings, PLUGINS, today=date(2026, 8, 15))

    assert sentinel.read_text() == "original snapshot"


def test_main_snapshots_databases_from_environment(
    settings_env: dict[str, str], monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    settings = Settings.from_env(settings_env)
    settings.data_dir.mkdir()
    for plugin in PLUGINS:
        sqlite3.connect(settings.data_dir / plugin.db_filename).close()
    for key, value in settings_env.items():
        monkeypatch.setenv(key, value)

    backup.main()

    snapshot = Path(capsys.readouterr().out.strip())
    assert date.fromisoformat(snapshot.name).isoformat() == snapshot.name
    assert sorted(path.name for path in snapshot.glob("*.db")) == sorted(
        plugin.db_filename for plugin in PLUGINS
    )
    assert (snapshot / SNAPSHOT_MARKER).is_file()


def test_project_exposes_one_backup_command() -> None:
    project = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    assert project["project"]["scripts"] == {"hublet-backup": "app.backup:main"}
