from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sift_cli.config import DEFAULT_IGNORE_DIRS, DEFAULT_MAX_EXTRACTED_FILE_SIZE
from sift_cli.indexer import build_index
from sift_cli.search import search_files


class ActiveStagingLifecycleIntegrationTests(unittest.TestCase):
    def test_failed_rebuild_keeps_last_completed_active_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            file_path = root / "alpha.md"
            file_path.write_text("alpha", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )

            baseline = [result.filename for result in search_files(active_db, "alpha")]
            self.assertEqual(baseline, ["alpha.md"])

            file_path.write_text("beta", encoding="utf-8")
            with patch("sift_cli.indexer.publish_staging_database", side_effect=RuntimeError("publish failed")):
                with self.assertRaises(RuntimeError):
                    build_index(
                        roots=(root,),
                        active_db_path=active_db,
                        staging_db_path=staging_db,
                        ignore_dirs=DEFAULT_IGNORE_DIRS,
                        max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
                    )

            after_failure = [result.filename for result in search_files(active_db, "alpha")]
            self.assertEqual(after_failure, ["alpha.md"])
            self.assertFalse(staging_db.exists())

    def test_successful_publish_switches_active_index_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            file_path = root / "alpha.md"
            file_path.write_text("alpha", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )
            self.assertEqual([result.filename for result in search_files(active_db, "alpha")], ["alpha.md"])

            file_path.unlink()
            new_file = root / "beta.md"
            new_file.write_text("beta", encoding="utf-8")

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )

            self.assertEqual([result.filename for result in search_files(active_db, "beta")], ["beta.md"])
            self.assertEqual(search_files(active_db, "alpha"), [])

    def test_indexed_rows_share_job_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            (root / "a.md").write_text("a", encoding="utf-8")
            (root / "b.md").write_text("b", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )

            with sqlite3.connect(active_db) as connection:
                timestamps = [row[0] for row in connection.execute("SELECT DISTINCT indexed_at FROM files ORDER BY indexed_at").fetchall()]

            self.assertEqual(len(timestamps), 1)


if __name__ == "__main__":
    unittest.main()
