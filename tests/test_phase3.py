from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sift_cli.db import initialize_database
from sift_cli.parser import is_empty_query, is_filter_only_query, parse_query
from sift_cli.search import search_files


def seed_file(db_path: Path, *, path: str, filename: str, ext: str | None, content: str | None, size: int, modified_at: float) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO files(path, filename, ext, content, size, created_at, modified_at, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (path, filename, ext, content, size, None, modified_at, modified_at),
        )
        connection.commit()


class ParserTests(unittest.TestCase):
    def test_parse_query_separates_scopes_and_filters(self) -> None:
        parsed = parse_query(
            'budget review "quarterly plan" filename:resume content:"auth bug" ext:.md path:notes after:2024-01-01 before:2024-03-31 size>=1kb'
        )

        self.assertEqual(parsed.text_terms, ("budget", "review"))
        self.assertEqual(parsed.phrases, ("quarterly plan",))
        self.assertEqual(parsed.filename_terms, ("resume",))
        self.assertEqual(parsed.content_terms, ("auth bug",))
        self.assertEqual(parsed.exts, ("md",))
        self.assertEqual(parsed.path_terms, ("notes",))
        self.assertEqual(parsed.size_min, 1024)
        self.assertEqual(parsed.size_max, None)
        self.assertTrue(parsed.after is not None)
        self.assertTrue(parsed.before is not None)

    def test_parse_query_supports_simple_date_phrases(self) -> None:
        now = datetime(2024, 4, 17, 15, 30, tzinfo=timezone.utc)

        today = parse_query("today", now=now)
        yesterday = parse_query("yesterday", now=now)
        this_week = parse_query("this week", now=now)
        last_7_days = parse_query("last 7 days", now=now)

        self.assertEqual(today.after, datetime(2024, 4, 17, 0, 0, tzinfo=timezone.utc).timestamp())
        self.assertEqual(today.before, datetime(2024, 4, 18, 0, 0, tzinfo=timezone.utc).timestamp())
        self.assertEqual(yesterday.after, datetime(2024, 4, 16, 0, 0, tzinfo=timezone.utc).timestamp())
        self.assertEqual(yesterday.before, datetime(2024, 4, 17, 0, 0, tzinfo=timezone.utc).timestamp())
        self.assertEqual(this_week.after, datetime(2024, 4, 15, 0, 0, tzinfo=timezone.utc).timestamp())
        self.assertEqual(this_week.before, datetime(2024, 4, 22, 0, 0, tzinfo=timezone.utc).timestamp())
        self.assertEqual(last_7_days.after, datetime(2024, 4, 10, 15, 30, tzinfo=timezone.utc).timestamp())
        self.assertEqual(last_7_days.before, datetime(2024, 4, 17, 15, 30, tzinfo=timezone.utc).timestamp())

    def test_parse_query_treats_unknown_operator_as_free_text(self) -> None:
        parsed = parse_query("foo:bar")

        self.assertEqual(parsed.text_terms, ("foo:bar",))
        self.assertTrue(is_filter_only_query(parse_query("ext:md")))
        self.assertTrue(is_empty_query(parse_query("   ")))

    def test_parse_query_rejects_invalid_size_and_date_values(self) -> None:
        with self.assertRaises(ValueError):
            parse_query("size>=banana")

        with self.assertRaises(ValueError):
            parse_query("after:not-a-date")


class SearchTests(unittest.TestCase):
    def test_metadata_only_search_orders_by_modified_time_then_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)
            seed_file(db_path, path="/docs/c.md", filename="c.md", ext="md", content=None, size=10, modified_at=3.0)
            seed_file(db_path, path="/docs/a.md", filename="a.md", ext="md", content=None, size=10, modified_at=2.0)
            seed_file(db_path, path="/docs/b.md", filename="b.md", ext="md", content=None, size=10, modified_at=2.0)
            seed_file(db_path, path="/docs/x.txt", filename="x.txt", ext="txt", content=None, size=10, modified_at=9.0)

            results = search_files(db_path, "ext:md")

        self.assertEqual([result.filename for result in results], ["c.md", "a.md", "b.md"])

    def test_text_search_prefers_filename_hits_over_content_only_hits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)
            seed_file(db_path, path="/docs/alpha.md", filename="alpha.md", ext="md", content="zzz", size=3, modified_at=2.0)
            seed_file(db_path, path="/docs/notes.md", filename="notes.md", ext="md", content="alpha", size=5, modified_at=1.0)

            results = search_files(db_path, "alpha")

        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0].filename, "alpha.md")
        self.assertTrue(results[0].matched_filename)

    def test_text_search_returns_snippet_for_content_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)
            seed_file(db_path, path="/docs/notes.md", filename="notes.md", ext="md", content="alpha beta gamma", size=16, modified_at=1.0)

            results = search_files(db_path, "alpha")

        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0].snippet)
        self.assertIn("alpha", results[0].snippet.lower())

    def test_text_search_accepts_punctuation_queries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)
            seed_file(db_path, path="/docs/example.py", filename="example.py", ext="py", content="print('hello')", size=14, modified_at=1.0)

            results = search_files(db_path, ".py")

        self.assertEqual([result.filename for result in results], ["example.py"])

    def test_filter_only_search_returns_matches_without_full_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)
            seed_file(db_path, path="/docs/a.md", filename="a.md", ext="md", content="alpha", size=10, modified_at=2.0)
            seed_file(db_path, path="/docs/b.txt", filename="b.txt", ext="txt", content="beta", size=10, modified_at=1.0)

            results = search_files(db_path, "ext:md")

        self.assertEqual([result.filename for result in results], ["a.md"])
        self.assertTrue(all(result.score is None for result in results))


if __name__ == "__main__":
    unittest.main()
