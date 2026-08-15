from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db import connect, migrate


def test_connect_enables_foreign_keys_and_commits(tmp_path: Path) -> None:
    database = tmp_path / "test.db"

    with connect(database) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        connection.execute("CREATE TABLE example (value TEXT NOT NULL)")
        connection.execute("INSERT INTO example VALUES ('saved')")

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM example").fetchone()[0] == "saved"


def test_connect_rolls_back_failed_transaction(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    with connect(database) as connection:
        connection.execute("CREATE TABLE example (value TEXT NOT NULL)")

    with pytest.raises(RuntimeError, match="stop"), connect(database) as connection:
        connection.execute("INSERT INTO example VALUES ('discarded')")
        raise RuntimeError("stop")

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM example").fetchone()[0] == 0


def test_migrate_applies_each_version_once(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    migrations = (
        "CREATE TABLE example (value TEXT NOT NULL);",
        "ALTER TABLE example ADD COLUMN note TEXT;",
    )

    migrate(database, migrations)
    migrate(database, migrations)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        columns = connection.execute("PRAGMA table_info(example)").fetchall()
        assert [column[1] for column in columns] == ["value", "note"]


def test_migrate_rolls_back_failed_version(tmp_path: Path) -> None:
    database = tmp_path / "test.db"

    with pytest.raises(sqlite3.OperationalError):
        migrate(
            database,
            (
                "CREATE TABLE example (value TEXT NOT NULL);",
                "CREATE TABLE broken (id TEXT); INVALID SQL;",
            ),
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert names == {"example"}


def test_migrate_rejects_database_from_newer_app(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 3")

    with pytest.raises(RuntimeError, match="newer schema version 3"):
        migrate(database, ("CREATE TABLE example (value TEXT);",))
