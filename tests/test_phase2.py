from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sift_cli.config import DEFAULT_IGNORE_DIRS, DEFAULT_MAX_EXTRACTED_FILE_SIZE
from sift_cli.db import initialize_database
from sift_cli.indexer import IndexingService, build_index


def read_files(db_path: Path) -> list[tuple[str, str, str | None, str | None, int]]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT path, filename, ext, content, size FROM files ORDER BY path"
        ).fetchall()


class IndexingTests(unittest.TestCase):
    def test_build_index_skips_hidden_directories_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            (root / ".hidden").mkdir()
            (root / ".hidden" / "secret.md").write_text("secret", encoding="utf-8")
            (root / "notes.md").write_text("public", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )

            rows = read_files(active_db)

        self.assertEqual([row[1] for row in rows], ["notes.md"])

    def test_build_index_can_include_hidden_directories_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            (root / ".hidden").mkdir()
            (root / ".hidden" / "secret.md").write_text("secret", encoding="utf-8")
            (root / "notes.md").write_text("public", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
                include_hidden_dirs=True,
            )

            rows = read_files(active_db)

        self.assertEqual({row[1] for row in rows}, {"notes.md", "secret.md"})

    def test_build_index_stores_metadata_and_text_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            (root / "docs").mkdir()
            (root / "docs" / "notes.md").write_text("hello world\n", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "ignored.md").write_text("ignore me", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            stats = build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )

            rows = read_files(active_db)

        self.assertEqual(stats.files_seen, 1)
        self.assertEqual(stats.files_indexed, 1)
        self.assertEqual(rows, [(f"{root / 'docs' / 'notes.md'}", "notes.md", "md", "hello world\n", len("hello world\n"))])
        self.assertFalse(staging_db.exists())

    def test_build_index_keeps_oversized_unsupported_and_binary_files_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()

            (root / "big.md").write_text("x" * 2048, encoding="utf-8")
            (root / "binary.bin").write_bytes(b"abc\x00def")
            (root / "script.exe").write_text("not supported", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=16,
            )

            rows = read_files(active_db)

        self.assertEqual({row[1] for row in rows}, {"big.md", "binary.bin", "script.exe"})
        self.assertTrue(all(row[3] is None for row in rows))

    def test_build_index_continues_when_extraction_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            (root / "good.md").write_text("good", encoding="utf-8")
            (root / "bad.md").write_text("bad", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            def fake_extract(path: Path, ext: str | None, max_size: int) -> str:
                if path.name == "bad.md":
                    raise OSError("read failed")
                return "good"

            stats = build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
                extractor=fake_extract,
            )

            rows = read_files(active_db)

        self.assertEqual(stats.extraction_failures, 1)
        self.assertEqual(stats.files_skipped, 0)
        self.assertEqual({row[1] for row in rows}, {"bad.md", "good.md"})
        self.assertEqual(dict((row[1], row[3]) for row in rows), {"good.md": "good", "bad.md": None})

    def test_build_index_sets_indexed_at_to_job_timestamp_not_file_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            file_path = root / "notes.md"
            file_path.write_text("alpha", encoding="utf-8")

            old_mtime = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
            Path(file_path).touch()
            import os

            os.utime(file_path, (old_mtime, old_mtime))

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
                modified_at, indexed_at = connection.execute(
                    "SELECT modified_at, indexed_at FROM files WHERE filename = 'notes.md'"
                ).fetchone()

        self.assertEqual(modified_at, old_mtime)
        self.assertNotEqual(indexed_at, modified_at)

    def test_build_index_skips_file_when_stat_fails_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            good_path = root / "good.md"
            bad_path = root / "bad.md"
            good_path.write_text("good", encoding="utf-8")
            bad_path.write_text("bad", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            def flaky_extract(path: Path, ext: str | None, max_size: int) -> str | None:
                if path.name == "bad.md":
                    raise FileNotFoundError("disappeared")
                return "good"

            stats = build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
                extractor=flaky_extract,
            )

            rows = read_files(active_db)

        self.assertEqual(stats.files_seen, 2)
        self.assertEqual(stats.files_indexed, 1)
        self.assertEqual(stats.files_skipped, 1)
        self.assertEqual([row[1] for row in rows], ["good.md"])

    def test_failed_refresh_does_not_replace_last_completed_active_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            keep = root / "keep.md"
            keep.write_text("keep", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )
            baseline_rows = read_files(active_db)

            with patch("sift_cli.indexer.publish_staging_database", side_effect=RuntimeError("publish failed")):
                with self.assertRaises(RuntimeError):
                    build_index(
                        roots=(root,),
                        active_db_path=active_db,
                        staging_db_path=staging_db,
                        ignore_dirs=DEFAULT_IGNORE_DIRS,
                        max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
                    )

            rows_after_failure = read_files(active_db)

        self.assertEqual(rows_after_failure, baseline_rows)

    def test_build_index_resets_preexisting_staging_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            (root / "live.md").write_text("live", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            initialize_database(staging_db)
            with sqlite3.connect(staging_db) as connection:
                connection.execute(
                    "INSERT INTO files(path, filename, ext, content, size, created_at, modified_at, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("/stale.md", "stale.md", "md", "stale", 5, None, 1.0, 1.0),
                )
                connection.commit()

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )

            rows = read_files(active_db)

        self.assertEqual([row[1] for row in rows], ["live.md"])

    def test_build_index_dedupes_overlapping_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            nested = root / "nested"
            nested.mkdir(parents=True)
            (nested / "one.md").write_text("one", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            stats = build_index(
                roots=(root, nested),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )

            rows = read_files(active_db)

        self.assertEqual([row[1] for row in rows], ["one.md"])
        self.assertEqual(stats.files_indexed, 1)
        self.assertEqual(stats.files_skipped, 1)

    def test_successful_rebuild_removes_deleted_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            file_a = root / "a.md"
            file_b = root / "b.md"
            file_a.write_text("a", encoding="utf-8")
            file_b.write_text("b", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )

            file_a.unlink()

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )

            rows = read_files(active_db)

        self.assertEqual([row[1] for row in rows], ["b.md"])

    def test_indexing_service_rejects_overlapping_builds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            (root / "slow.md").write_text("slow", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"
            service = IndexingService()
            started = threading.Event()
            release = threading.Event()

            def slow_extract(path: Path, ext: str | None, max_size: int) -> str:
                started.set()
                release.wait(timeout=2)
                return "slow"

            result_holder: list[object] = []

            def run_first_build() -> None:
                result_holder.append(
                    service.refresh(
                        roots=(root,),
                        active_db_path=active_db,
                        staging_db_path=staging_db,
                        ignore_dirs=DEFAULT_IGNORE_DIRS,
                        max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
                        extractor=slow_extract,
                    )
                )

            thread = threading.Thread(target=run_first_build)
            thread.start()
            self.assertTrue(started.wait(timeout=2))

            second_result = service.refresh(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
                extractor=slow_extract,
            )

            release.set()
            thread.join(timeout=2)

        self.assertIsNone(second_result)
        self.assertEqual(len(result_holder), 1)
        self.assertIsNotNone(result_holder[0])


if __name__ == "__main__":
    unittest.main()
