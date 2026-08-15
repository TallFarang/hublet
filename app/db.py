"""Small SQLite connection and migration helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect(database: Path) -> Iterator[sqlite3.Connection]:
    """Open a short-lived SQLite connection with safe local defaults."""

    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def migrate(database: Path, migrations: Sequence[str]) -> None:
    """Apply ordered SQL migrations tracked by ``PRAGMA user_version``."""

    with connect(database) as connection:
        current_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if current_version > len(migrations):
            raise RuntimeError(
                f"{database.name} has newer schema version {current_version}; "
                f"this app supports {len(migrations)}"
            )

        for version, sql in enumerate(migrations[current_version:], start=current_version + 1):
            connection.executescript(
                f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;"
            )
