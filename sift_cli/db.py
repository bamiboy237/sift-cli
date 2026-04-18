"""SQLite schema and storage helpers for sift-cli."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .models import RuntimePaths
from .paths import default_config_path, default_state_dir

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY,
    path         TEXT UNIQUE NOT NULL,
    filename     TEXT NOT NULL,
    ext          TEXT,
    content      TEXT,
    size         INTEGER NOT NULL,
    created_at   REAL,
    modified_at  REAL NOT NULL,
    indexed_at   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_ext ON files(ext);
CREATE INDEX IF NOT EXISTS idx_files_modified_at ON files(modified_at);
CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);
CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    filename,
    content,
    content='files',
    content_rowid='id',
    tokenize='porter unicode61',
    prefix='2 3'
);

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, filename, content)
    VALUES (new.id, new.filename, new.content);
END;

CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, filename, content)
    VALUES ('delete', old.id, old.filename, old.content);
END;

CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, filename, content)
    VALUES ('delete', old.id, old.filename, old.content);
    INSERT INTO files_fts(rowid, filename, content)
    VALUES (new.id, new.filename, new.content);
END;
"""


def resolve_runtime_paths(
    config_path: Path | None = None,
    state_dir: Path | None = None,
) -> RuntimePaths:
    """Resolve config and state locations."""

    resolved_config_path = (
        Path(config_path) if config_path is not None else default_config_path()
    )
    resolved_state_dir = (
        Path(state_dir) if state_dir is not None else default_state_dir()
    )

    resolved_config_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_state_dir.mkdir(parents=True, exist_ok=True)

    return RuntimePaths(
        config_path=resolved_config_path,
        state_dir=resolved_state_dir,
        active_db_path=resolved_state_dir / "index.db",
        staging_db_path=resolved_state_dir / "index.build.db",
    )


def initialize_database(db_path: Path) -> None:
    """Create the schema at the given path."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.commit()


def initialize_active_database(db_path: Path) -> None:
    """Create the active database if missing."""

    if not db_path.exists():
        initialize_database(db_path)


def reset_staging_database(staging_db_path: Path) -> None:
    """Reset the staging database."""

    _remove_database_artifacts(staging_db_path)
    initialize_database(staging_db_path)


def publish_staging_database(active_db_path: Path, staging_db_path: Path) -> None:
    """Publish the staging database."""

    os.replace(staging_db_path, active_db_path)


def cleanup_database_artifacts(db_path: Path) -> None:
    """Remove database files and sidecars."""

    _remove_database_artifacts(db_path)


def _remove_database_artifacts(db_path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        target = Path(f"{db_path}{suffix}")
        try:
            target.unlink()
        except FileNotFoundError:
            continue
