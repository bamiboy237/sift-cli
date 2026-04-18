from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_accept_autocomplete_with_cursor_updates_query_and_cursor_position(self) -> None:
        controller = SearchController(fuzzy_index=FuzzyIndex([("/root/alpha.md", "alpha.md")]))
        controller.update_query("hello alp world", cursor=8)

        query, cursor = controller.accept_autocomplete_with_cursor(cursor=8)

        self.assertEqual(query, "hello alpha.md world")
        self.assertEqual(cursor, len("hello alpha.md"))

    def test_search_completion_during_indexing_keeps_indexing_state(self) -> None:
        controller = SearchController()
        controller.start_indexing()

        request = controller.begin_search("alpha")
        controller.complete_search(request, ["alpha-result"])

        self.assertTrue(controller.state.indexing)
        self.assertEqual(controller.state.results, ("alpha-result",))


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

    def test_bootstrap_app_initializes_controller_and_non_blocking_launch_config(self) -> None:
        from sift_cli.main import bootstrap_app
        from sift_cli.models import AppConfig, RuntimePaths

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            runtime_paths = RuntimePaths(
                config_path=temp_path / "config.toml",
                state_dir=temp_path,
                active_db_path=temp_path / "index.db",
                staging_db_path=temp_path / "index.build.db",
            )
            app_config = AppConfig(
                roots=(temp_path / "root",),
                ignore_dirs=(".git",),
                max_extracted_file_size=1234,
            )

            with patch("sift_cli.main.resolve_runtime_paths", return_value=runtime_paths), patch(
                "sift_cli.main.load_config", return_value=app_config
            ):
                launch_config, controller, loaded_config = bootstrap_app()

        self.assertEqual(loaded_config, app_config)
        self.assertEqual(launch_config.db_path, runtime_paths.active_db_path)
        self.assertTrue(launch_config.auto_start_indexing)
        self.assertEqual(controller.db_path, runtime_paths.active_db_path)


if __name__ == "__main__":
    unittest.main()
