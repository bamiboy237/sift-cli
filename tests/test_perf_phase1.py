"""Phase 1 performance work: prefix search, connection hygiene, fuzzy precompute."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from sift_cli.db import initialize_database
from sift_cli.fuzzy_index import FuzzyIndex
from sift_cli.search import search_files


def seed_file(
    db_path: Path,
    *,
    path: str,
    filename: str,
    ext: str | None,
    content: str | None,
    size: int,
    modified_at: float,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO files(path, filename, ext, content, size, created_at, modified_at, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (path, filename, ext, content, size, None, modified_at, modified_at),
        )
        connection.commit()


class PrefixSearchTests(unittest.TestCase):
    def test_partial_term_matches_as_you_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)
            seed_file(
                db_path,
                path="/docs/document.md",
                filename="document.md",
                ext="md",
                content="zzz",
                size=3,
                modified_at=1.0,
            )

            results = search_files(db_path, "docu")

        self.assertEqual([result.filename for result in results], ["document.md"])
        self.assertTrue(results[0].matched_filename)

    def test_prefix_expansion_does_not_apply_to_phrases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)
            seed_file(
                db_path,
                path="/docs/exact.md",
                filename="exact.md",
                ext="md",
                content="auth bug fixed",
                size=14,
                modified_at=2.0,
            )
            seed_file(
                db_path,
                path="/docs/separate.md",
                filename="separate.md",
                ext="md",
                content="auth login bug",
                size=15,
                modified_at=1.0,
            )

            results = search_files(db_path, '"auth bug"')

        self.assertEqual([result.filename for result in results], ["exact.md"])

    def test_content_snippet_still_highlights_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)
            seed_file(
                db_path,
                path="/docs/notes.md",
                filename="notes.md",
                ext="md",
                content="alpha beta gamma",
                size=16,
                modified_at=1.0,
            )

            results = search_files(db_path, "alpha")

        self.assertEqual(len(results), 1)
        snippet = results[0].snippet
        if snippet is None:
            self.fail("expected snippet for content match")
        self.assertIn("\x1falpha\x1e", snippet.lower())
        self.assertTrue(results[0].matched_content)

    def test_filename_only_match_has_no_content_snippet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)
            seed_file(
                db_path,
                path="/docs/alpha.md",
                filename="alpha.md",
                ext="md",
                content="zzz",
                size=3,
                modified_at=1.0,
            )

            results = search_files(db_path, "alpha")

        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].snippet)
        self.assertTrue(results[0].matched_filename)


class ConnectionHygieneTests(unittest.TestCase):
    def test_search_missing_database_raises_without_creating_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "missing.db"

            with self.assertRaises(FileNotFoundError):
                search_files(db_path, "alpha")

            self.assertFalse(db_path.exists())


class FuzzyPrecomputeTests(unittest.TestCase):
    def test_suggestions_across_strategy_lengths_are_unchanged(self) -> None:
        rows = [
            ("/root/documents/report.md", "report.md"),
            ("/root/notes.txt", "notes.txt"),
            ("/root/deep/nested/dir/thing.py", "thing.py"),
        ]
        fuzzy = FuzzyIndex(rows)

        one_char = [s.basename for s in fuzzy.suggest("r")]
        short = [s.basename for s in fuzzy.suggest("rep")]
        long_query = [s.basename for s in fuzzy.suggest("report")]

        self.assertEqual(fuzzy.strategy_for_query("r"), "prefix")
        self.assertEqual(fuzzy.strategy_for_query("rep"), "subset")
        self.assertEqual(fuzzy.strategy_for_query("report"), "trigram")
        self.assertIn("report.md", one_char)
        # Subset strategy is deliberately loose; basename scoring must still
        # rank the strong match first.
        self.assertEqual(short[0], "report.md")
        self.assertEqual(long_query, ["report.md"])

    def test_update_rows_rebuilds_precomputed_structures(self) -> None:
        fuzzy = FuzzyIndex([("/a/old.txt", "old.txt")])
        fuzzy.update_rows([("/b/new.txt", "new.txt")])

        suggestions = [s.basename for s in fuzzy.suggest("new")]

        self.assertEqual(suggestions, ["new.txt"])


if __name__ == "__main__":
    unittest.main()
