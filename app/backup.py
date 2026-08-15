"""Daily online snapshots for Hublet's SQLite databases."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from app.config import Settings
from app.plugins import PLUGINS
from app.runtime import Plugin

SNAPSHOT_MARKER = ".hublet-snapshot"


def snapshot_databases(
    settings: Settings,
    plugins: Sequence[Plugin],
    *,
    today: date | None = None,
) -> Path:
    sources = [(plugin, settings.data_dir / plugin.db_filename) for plugin in plugins]
    missing = next((path for _plugin, path in sources if not path.is_file()), None)
    if missing:
        raise FileNotFoundError(f"database not found: {missing}")

    snapshot = settings.backup_dir / (today or datetime.now().astimezone().date()).isoformat()
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    if snapshot.exists():
        if not (snapshot / SNAPSHOT_MARKER).is_file():
            raise FileExistsError(f"backup destination is not a Hublet snapshot: {snapshot}")
        raise FileExistsError(f"snapshot already exists: {snapshot}")

    staging = Path(tempfile.mkdtemp(prefix=".hublet-", dir=settings.backup_dir))
    try:
        for plugin, source_path in sources:
            source_uri = f"{source_path.resolve().as_uri()}?mode=ro"
            with (
                sqlite3.connect(source_uri, uri=True) as source,
                sqlite3.connect(staging / plugin.db_filename) as destination,
            ):
                source.backup(destination)
        (staging / SNAPSHOT_MARKER).touch()

        staging.rename(snapshot)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    daily_snapshots = sorted(
        path
        for path in settings.backup_dir.iterdir()
        if path.is_dir() and (path / SNAPSHOT_MARKER).is_file() and _is_daily_snapshot(path)
    )
    for expired in daily_snapshots[:-30]:
        shutil.rmtree(expired)

    return snapshot


def _is_daily_snapshot(path: Path) -> bool:
    try:
        return date.fromisoformat(path.name).isoformat() == path.name
    except ValueError:
        return False


def main() -> None:
    print(snapshot_databases(Settings.from_env(), PLUGINS))
