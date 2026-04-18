from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sift_cli.autocomplete import autocomplete_suggestions
from sift_cli.fuzzy_index import FuzzyIndex
from sift_cli.ui import SearchController, SearchState, build_preview_text


class SearchControllerTests(unittest.TestCase):
    def test_stale_search_results_do_not_overwrite_newer_query(self) -> None:
        controller = SearchController()
        older = controller.begin_search("alpha")
        newer = controller.begin_search("beta")

        controller.complete_search(older, ["old-result"])
        self.assertEqual(controller.state.results, ())

        controller.complete_search(newer, ["new-result"])
        self.assertEqual(controller.state.results, ("new-result",))

    def test_autocomplete_precedence_is_explicit(self) -> None:
        controller = SearchController(fuzzy_index=FuzzyIndex([("/root/alpha.md", "alpha.md")]))
        controller.update_query("alp")

        self.assertEqual(controller.precedence(), "autocomplete")
        self.assertGreaterEqual(len(controller.state.autocomplete), 1)

    def test_empty_query_exposes_help_state(self) -> None:
        controller = SearchController()

        controller.update_query("")

        self.assertEqual(controller.state.mode, "empty")
        self.assertIn("example", controller.state.help_text.lower())


class PreviewTests(unittest.TestCase):
    def test_preview_text_uses_snippet_when_present(self) -> None:
        self.assertEqual(build_preview_text(snippet="alpha beta", path="/tmp/alpha.txt"), "alpha beta")
        self.assertIn("alpha.txt", build_preview_text(snippet=None, path="/tmp/alpha.txt"))


class AppLaunchTests(unittest.TestCase):
    def test_builds_launch_config_without_textual_dependency(self) -> None:
        from sift_cli.main import build_app_config

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            config = build_app_config(db_path=db_path)

        self.assertEqual(config.db_path, db_path)


if __name__ == "__main__":
    unittest.main()
