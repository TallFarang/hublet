from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import migrate
from app.main import create_app
from app.plugins import food


def seed_v1(database: Path) -> None:
    migrate(database, food.MIGRATIONS[:1])
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO nutrition
               (id, restaurant, item, calories, protein_g, carbs_g, fat_g,
                portion_basis, source, confidence, evidence_class, updated_at)
               VALUES ('original', 'Kitchen', 'Meal', 600, 30, 70, 20,
                       'bowl', 'menu', 'high', 'fact', '2026-09-01T00:00:00Z')"""
        )
        connection.execute(
            """INSERT INTO records
               (id, restaurant, item, status, nutrition_id, consumption_date_local,
                updated_at, update_reason)
               VALUES ('eaten', 'Kitchen', 'Meal', 'eaten', 'original', '2026-09-01',
                       '2026-09-01T00:00:00Z', 'fixture')"""
        )


def database_rows(database: Path) -> tuple[list[tuple], list[tuple]]:
    with sqlite3.connect(database) as connection:
        return (
            connection.execute("SELECT * FROM nutrition ORDER BY id").fetchall(),
            connection.execute("SELECT * FROM records ORDER BY id").fetchall(),
        )


def test_fresh_food_schema_v2_and_constraints(tmp_path: Path) -> None:
    database = tmp_path / "food.db"
    migrate(database, food.MIGRATIONS)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(nutrition)")}
        assert columns["macros_complete"][3:5] == (1, "1")
        assert all(columns[field][3] == 1 for field in ("protein_g", "carbs_g", "fat_g"))


def test_v1_migration_preserves_rows_and_defaults_to_complete(tmp_path: Path) -> None:
    database = tmp_path / "food.db"
    seed_v1(database)
    nutrition, records = database_rows(database)
    migrate(database, food.MIGRATIONS)
    migrate(database, food.MIGRATIONS)
    migrated, current_records = database_rows(database)
    assert migrated == [(*row, 1) for row in nutrition]
    assert current_records == records
    for assignment in ("macros_complete=2", "macros_complete=NULL", "protein_g=NULL"):
        with sqlite3.connect(database) as connection, pytest.raises(sqlite3.IntegrityError):
            connection.execute(f"UPDATE nutrition SET {assignment}")


def test_existing_v2_startup_keeps_167_unknown_entries_unchanged(
    settings_env: dict[str, str],
) -> None:
    settings = Settings.from_env(settings_env)
    database = settings.data_dir / food.DB_FILENAME
    seed_v1(database)
    # Construct the already-deployed v2 independently of the new migration.
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """ALTER TABLE nutrition ADD COLUMN macros_complete INTEGER NOT NULL DEFAULT 1
               CHECK (macros_complete IN (0, 1));
               PRAGMA user_version = 2;"""
        )
        connection.executemany(
            """INSERT INTO nutrition
               (id, restaurant, item, calories, protein_g, carbs_g, fat_g, portion_basis,
                source, confidence, evidence_class, updated_at, macros_complete)
               VALUES (?, 'Kitchen', 'Unknown', 500, 0, 12, 0, 'bowl',
                       'menu', 'high', 'fact', '2026-09-01T00:00:00Z', 0)""",
            [(f"unknown-{index}",) for index in range(167)],
        )
    before = database_rows(database)
    with TestClient(create_app(settings=settings), base_url=settings.public_origin) as client:
        assert client.get("/healthz").json()["plugins"]["food"] == "ok"
        assert food.get_nutrition(settings, "unknown-0")["carbs_g"] is None
        assert (
            food.summary(settings, "2026-09-01", "2026-09-01")["daily_confirmed_totals"][0][
                "calories"
            ]
            == 600
        )
    assert database_rows(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert (
            connection.execute("SELECT COUNT(*) FROM nutrition WHERE macros_complete=0").fetchone()[
                0
            ]
            == 167
        )


def test_food_startup_still_rejects_future_schema(settings_env: dict[str, str]) -> None:
    settings = Settings.from_env(settings_env)
    database = settings.data_dir / food.DB_FILENAME
    seed_v1(database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=3")
    with (
        pytest.raises(RuntimeError, match="newer schema version 3"),
        TestClient(create_app(settings=settings)),
    ):
        pass
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
