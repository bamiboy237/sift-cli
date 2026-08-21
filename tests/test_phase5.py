from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sift_cli.app import _layout_mode_for_size
from sift_cli.fuzzy_index import FuzzyIndex
from sift_cli.models import SearchResult
from sift_cli.ui import (
    SearchController,
    SearchState,
    build_autocomplete_text,
    build_preview_text,
)


def _result(path: str, filename: str) -> SearchResult:
    return SearchResult(
        path=path,
        filename=filename,
        ext=filename.rsplit(".", 1)[-1] if "." in filename else None,
        size=12,
        modified_at=1_714_000_000.0,
        snippet=None,
        matched_filename=True,
        matched_content=False,
        score=1.0,
    )


class SearchControllerTests(unittest.TestCase):
    def test_stale_search_results_do_not_overwrite_newer_query(self) -> None:
        controller = SearchController()
        older = controller.begin_search("alpha")
        newer = controller.begin_search("beta")

        controller.complete_search(older, [_result("/tmp/old.md", "old.md")])
        self.assertEqual(controller.state.results, ())

        new_result = _result("/tmp/new.md", "new.md")
        controller.complete_search(newer, [new_result])
        self.assertEqual(controller.state.results, (new_result,))

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
        alpha_result = _result("/tmp/alpha.md", "alpha.md")
        controller.complete_search(request, [alpha_result])

        self.assertTrue(controller.state.indexing)
        self.assertEqual(controller.state.results, (alpha_result,))


class PreviewTests(unittest.TestCase):
    def test_preview_text_uses_snippet_when_present(self) -> None:
        self.assertEqual(build_preview_text(snippet="alpha beta", path="/tmp/alpha.txt"), "alpha beta")
        self.assertIn("alpha.txt", build_preview_text(snippet=None, path="/tmp/alpha.txt"))


class LayoutModeTests(unittest.TestCase):
    def test_layout_mode_for_size_uses_wide_threshold(self) -> None:
        self.assertEqual(_layout_mode_for_size(140, 38), "wide")
        self.assertEqual(_layout_mode_for_size(180, 50), "wide")

    def test_layout_mode_for_size_uses_stacked_threshold(self) -> None:
        self.assertEqual(_layout_mode_for_size(105, 30), "stacked")
        self.assertEqual(_layout_mode_for_size(130, 35), "stacked")

    def test_layout_mode_for_size_uses_compact_below_thresholds(self) -> None:
        self.assertEqual(_layout_mode_for_size(104, 30), "compact")
        self.assertEqual(_layout_mode_for_size(120, 29), "compact")

    def test_autocomplete_text_hidden_and_empty_states_render_blank(self) -> None:
        self.assertEqual(build_autocomplete_text(SearchState()), "")
        state = SearchState(
            autocomplete=(
                __import__("sift_cli.autocomplete", fromlist=["AutocompleteSuggestion"]).AutocompleteSuggestion(
                    "alpha.md", "alpha.md"
                ),
            ),
            autocomplete_hidden=True,
        )
        self.assertEqual(build_autocomplete_text(state), "")


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
                include_hidden_dirs=False,
            )

            with patch("sift_cli.main.resolve_runtime_paths", return_value=runtime_paths), patch(
                "sift_cli.main.load_config", return_value=app_config
            ):
                launch_config, controller, loaded_config = bootstrap_app()

        self.assertEqual(loaded_config, app_config)
        self.assertEqual(launch_config.db_path, runtime_paths.active_db_path)
        self.assertTrue(launch_config.auto_start_indexing)
        self.assertEqual(controller.db_path, runtime_paths.active_db_path)

    def test_launch_app_instantiates_and_runs_app(self) -> None:
        from unittest.mock import MagicMock
        from sift_cli.app import launch_app
        from sift_cli.ui import LaunchConfig

        config = LaunchConfig(
            db_path=Path("/tmp/index.db"),
            active_db_path=Path("/tmp/index.db"),
            staging_db_path=Path("/tmp/index.build.db"),
            roots=(),
        )
        mock_instance = MagicMock()
        mock_cls = MagicMock(return_value=mock_instance)

        with patch("sift_cli.app.build_sift_app", return_value=mock_cls):
            launch_app(config)

        mock_cls.assert_called_once()
        mock_instance.run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
