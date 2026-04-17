from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sift_cli.config import DEFAULT_IGNORE_DIRS, DEFAULT_MAX_EXTRACTED_FILE_SIZE, default_config, load_config
from sift_cli.db import initialize_database, publish_staging_database, resolve_runtime_paths
from sift_cli.paths import default_config_path, default_index_roots, default_state_dir, normalize_path


class PathTests(unittest.TestCase):
    def test_normalize_path_returns_absolute_forward_slash_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "alpha" / ".." / "beta"
            self.assertEqual(normalize_path(target), (Path(temp_dir) / "beta").as_posix())

    def test_default_locations_follow_user_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            with patch("sift_cli.paths.Path.home", return_value=home):
                self.assertEqual(default_config_path(), home / ".config" / "sift" / "config.toml")
                self.assertEqual(default_state_dir(), home / ".local" / "state" / "sift")
                self.assertEqual(default_index_roots(), tuple(home / name for name in ("Documents", "Desktop", "Downloads", "Projects")))


class ConfigTests(unittest.TestCase):
    def test_default_config_uses_spec_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            with patch("sift_cli.paths.Path.home", return_value=home):
                config = default_config()

        self.assertEqual(config.ignore_dirs, DEFAULT_IGNORE_DIRS)
        self.assertEqual(config.max_extracted_file_size, DEFAULT_MAX_EXTRACTED_FILE_SIZE)
        self.assertEqual(config.roots, tuple(home / name for name in ("Documents", "Desktop", "Downloads", "Projects")))

    def test_load_config_parses_and_normalizes_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            home = temp_path / "home"
            home.mkdir()
            config_file = temp_path / "config.toml"
            config_file.write_text(
                "\n".join(
                    [
                        'roots = ["~/notes", "' + (temp_path / "workspace" / ".." / "docs").as_posix() + '"]',
                        'ignore_dirs = ["cache", "tmp"]',
                        "max_extracted_file_size = 2048",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"HOME": str(home)}, clear=False):
                config = load_config(config_file)

        self.assertEqual(config.roots, (home / "notes", temp_path / "docs"))
        self.assertEqual(config.ignore_dirs, ("cache", "tmp"))
        self.assertEqual(config.max_extracted_file_size, 2048)


class StorageTests(unittest.TestCase):
    def test_resolve_runtime_paths_creates_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config" / "sift" / "config.toml"
            state_dir = temp_path / "state" / "sift"

            runtime_paths = resolve_runtime_paths(config_path=config_path, state_dir=state_dir)

            self.assertTrue(runtime_paths.config_path.parent.exists())
            self.assertTrue(runtime_paths.state_dir.exists())
            self.assertEqual(runtime_paths.active_db_path, state_dir / "index.db")
            self.assertEqual(runtime_paths.staging_db_path, state_dir / "index.build.db")

    def test_initialize_database_creates_schema_and_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)

            with sqlite3.connect(db_path) as connection:
                rows = connection.execute("SELECT type, name, sql FROM sqlite_master").fetchall()

        names = {name for _, name, _ in rows}
        self.assertIn("files", names)
        self.assertIn("files_fts", names)
        self.assertIn("files_ai", names)
        self.assertIn("files_ad", names)
        self.assertIn("files_au", names)

    def test_publish_staging_database_replaces_active_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            initialize_database(active_db)
            with sqlite3.connect(active_db) as connection:
                connection.execute(
                    "INSERT INTO files(path, filename, ext, content, size, created_at, modified_at, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("/active.txt", "active.txt", "txt", "active", 1, None, 1.0, 1.0),
                )
                connection.commit()

            initialize_database(staging_db)
            with sqlite3.connect(staging_db) as connection:
                connection.execute(
                    "INSERT INTO files(path, filename, ext, content, size, created_at, modified_at, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("/staging.txt", "staging.txt", "txt", "staging", 2, None, 2.0, 2.0),
                )
                connection.commit()

            publish_staging_database(active_db, staging_db)

            self.assertFalse(staging_db.exists())
            with sqlite3.connect(active_db) as connection:
                result = connection.execute("SELECT path, content FROM files").fetchall()

            self.assertEqual(result, [("/staging.txt", "staging")])


if __name__ == "__main__":
    unittest.main()
