"""Standalone recovery importer for the two legacy Food CSV archives."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from app.config import Settings
from app.plugins.food_import_csv import (
    CATALOGUE_HEADERS,
    LEDGER_HEADERS,
    checksum,
    read_csv,
)
from app.plugins.food_import_load import load_database
from app.plugins.food_schema import DB_FILENAME


def import_csvs(
    settings: Settings,
    ledger_path: Path,
    catalogue_path: Path,
    *,
    check: bool = False,
    database: Path | None = None,
) -> dict[str, Any]:
    """Validate or import the unchanged archives into an empty database."""

    ledger_path, catalogue_path = ledger_path.resolve(), catalogue_path.resolve()
    before = {"ledger": checksum(ledger_path), "catalogue": checksum(catalogue_path)}
    ledger_rows = read_csv(ledger_path, LEDGER_HEADERS)
    catalogue_rows = read_csv(catalogue_path, CATALOGUE_HEADERS)
    if not ledger_rows:
        raise ValueError("ledger CSV contains no records")
    if not catalogue_rows:
        raise ValueError("catalogue CSV contains no nutrition entries")
    if check:
        with tempfile.TemporaryDirectory(prefix="hublet-food-check-") as directory:
            result = load_database(Path(directory) / DB_FILENAME, ledger_rows, catalogue_rows)
    else:
        target = database.resolve() if database else settings.data_dir / DB_FILENAME
        result = load_database(target, ledger_rows, catalogue_rows)
    after = {"ledger": checksum(ledger_path), "catalogue": checksum(catalogue_path)}
    if after != before:
        raise RuntimeError("a source CSV changed during import")
    return {**result, "check_only": check, "checksums": before}


def main() -> None:
    parser = argparse.ArgumentParser(description="Recover Food from its legacy CSV archives")
    parser.add_argument("ledger", type=Path)
    parser.add_argument("catalogue", type=Path)
    parser.add_argument("--check", action="store_true", help="validate in a temporary database")
    parser.add_argument("--database", type=Path, help="write to this empty database path")
    arguments = parser.parse_args()
    result = import_csvs(
        Settings.from_env(),
        arguments.ledger,
        arguments.catalogue,
        check=arguments.check,
        database=arguments.database,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
