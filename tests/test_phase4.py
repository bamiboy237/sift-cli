from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sift_cli.autocomplete import autocomplete_suggestions, replace_active_token
from sift_cli.fuzzy_index import FuzzyIndex, build_trigram_index, extract_trigrams
from sift_cli.indexer import build_index


class FuzzyIndexTests(unittest.TestCase):
    def test_extract_trigrams_pads_edges(self) -> None:
        self.assertEqual(extract_trigrams("ab"), {"  a", " ab", "ab "})

    def test_build_trigram_index_maps_candidate_ids(self) -> None:
        index = build_trigram_index(["alpha", "beta"])

        self.assertIn(" al", index)
        self.assertEqual(index[" al"], {0})
        self.assertEqual(index[" be"], {1})

    def test_strategy_for_query_switches_by_length(self) -> None:
        fuzzy = FuzzyIndex([
            ("/root/alpha.md", "alpha.md"),
        ])

        self.assertEqual(fuzzy.strategy_for_query(""), "empty")
        self.assertEqual(fuzzy.strategy_for_query("a"), "prefix")
        self.assertEqual(fuzzy.strategy_for_query("ab"), "subset")
        self.assertEqual(fuzzy.strategy_for_query("abcd"), "trigram")

    def test_suggest_prefers_basename_over_directory_only_matches(self) -> None:
        fuzzy = FuzzyIndex([
            ("/root/alpha.md", "alpha.md"),
            ("/root/alpha-notes.txt", "alpha-notes.txt"),
            ("/root/projects/alpha/spec.txt", "spec.txt"),
        ])

        results = fuzzy.suggest("alpha", limit=3)

        self.assertEqual([result.path for result in results[:2]], ["/root/alpha.md", "/root/alpha-notes.txt"])
        self.assertEqual(results[-1].path, "/root/projects/alpha/spec.txt")


class AutocompleteTests(unittest.TestCase):
    def test_replace_active_token_updates_only_current_token(self) -> None:
        self.assertEqual(
            replace_active_token("alpha path:do ext:md", "/docs/readme.md", cursor=13),
            "alpha path:/docs/readme.md ext:md",
        )

    def test_autocomplete_uses_basename_for_free_text_and_path_for_path_field(self) -> None:
        fuzzy = FuzzyIndex([
            ("/root/alpha.md", "alpha.md"),
        ])

        free_text = autocomplete_suggestions("alp", fuzzy)
        path_field = autocomplete_suggestions("path:alp", fuzzy)

        self.assertGreaterEqual(len(free_text), 1)
        self.assertEqual(free_text[0].insert_text, "alpha.md")
        self.assertGreaterEqual(len(path_field), 1)
        self.assertEqual(path_field[0].insert_text, "/root/alpha.md")


class RebuildTests(unittest.TestCase):
    def test_build_index_invokes_callback_after_successful_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "docs"
            root.mkdir()
            file_path = root / "alpha.md"
            file_path.write_text("hello alpha", encoding="utf-8")

            active_db_path = Path(temp_dir) / "index.db"
            staging_db_path = Path(temp_dir) / "index.build.db"
            published: list[Path] = []

            build_index(
                roots=(root,),
                active_db_path=active_db_path,
                staging_db_path=staging_db_path,
                ignore_dirs=(),
                max_extracted_file_size=1024,
                on_published=published.append,
            )

        self.assertEqual(published, [active_db_path])


if __name__ == "__main__":
    unittest.main()
