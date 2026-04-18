from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import tempfile

from sift_cli.db import initialize_database

from sift_cli.fuzzy_index import FuzzyIndex
from sift_cli.models import SearchResult
from sift_cli.ui import (
    SearchController,
    SearchState,
    build_query_banner_text,
    build_autocomplete_text,
    build_results_text,
    build_result_row_text,
    build_sidebar_text,
    build_status_text,
)


def _result(path: str, filename: str, *, snippet: str | None = None) -> SearchResult:
    return SearchResult(
        path=path,
        filename=filename,
        ext=filename.rsplit(".", 1)[-1] if "." in filename else None,
        size=12,
        modified_at=1_714_000_000.0,
        snippet=snippet,
        matched_filename=True,
        matched_content=snippet is not None,
        score=1.0,
    )


class SearchControllerPhase7Tests(unittest.TestCase):
    def test_refresh_keeps_selected_result_when_it_still_exists(self) -> None:
        controller = SearchController()
        first_request = controller.begin_search("alpha")
        first = _result("/tmp/alpha.md", "alpha.md")
        second = _result("/tmp/beta.md", "beta.md")
        controller.complete_search(first_request, [first, second])
        controller.move_result_selection(1)

        self.assertEqual(controller.active_result, second)

        refresh_request = controller.begin_search("alpha")
        controller.complete_search(refresh_request, [second, first])

        self.assertEqual(controller.active_result, second)
        self.assertEqual(controller.state.selected_index, 0)

    def test_accepting_autocomplete_updates_the_raw_query(self) -> None:
        controller = SearchController(fuzzy_index=FuzzyIndex([("/tmp/alpha.md", "alpha.md")]))
        controller.update_query("alp")

        updated = controller.accept_autocomplete()

        self.assertEqual(updated, "alpha.md")
        self.assertEqual(controller.state.raw_query, "alpha.md")

    def test_autocomplete_selection_is_clamped(self) -> None:
        controller = SearchController(fuzzy_index=FuzzyIndex([("/tmp/alpha.md", "alpha.md")]))
        controller.update_query("alp")

        controller.move_autocomplete_selection(10)
        self.assertEqual(controller.state.autocomplete_index, 0)

        controller.move_autocomplete_selection(-10)
        self.assertEqual(controller.state.autocomplete_index, 0)

    def test_has_index_is_false_for_empty_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "index.db"
            initialize_database(db_path)
            controller = SearchController(db_path=db_path)

        self.assertFalse(controller.state.has_index)

    def test_successful_search_clears_previous_status_message(self) -> None:
        controller = SearchController()
        controller.state = replace(controller.state, status_message="old")

        request = controller.begin_search("alpha")
        controller.complete_search(request, [_result("/tmp/a.md", "a.md")])

        self.assertEqual(controller.state.status_message, "")

    def test_query_parse_error_is_distinct_from_search_error(self) -> None:
        controller = SearchController(db_path=Path("/tmp/index.db"))
        with patch("sift_cli.ui.search_files", side_effect=ValueError("invalid date value: nope")):
            controller.search("after:nope")

        self.assertIn("Query error", controller.state.status_message)

    def test_search_execution_error_is_non_fatal(self) -> None:
        controller = SearchController(db_path=Path("/tmp/index.db"))
        with patch("sift_cli.ui.search_files", side_effect=RuntimeError("boom")):
            controller.search("alpha")

        self.assertIn("Search error", controller.state.status_message)

    def test_invalidate_pending_searches_ignores_older_completion(self) -> None:
        controller = SearchController()
        request = controller.begin_search("alpha")
        controller.invalidate_pending_searches()

        controller.complete_search(request, [_result("/tmp/a.md", "a.md")])

        self.assertEqual(controller.state.results, ())

    def test_setters_update_non_fatal_status_messages(self) -> None:
        controller = SearchController()

        controller.set_query_error("bad field")
        self.assertIn("Query error", controller.state.status_message)

        controller.set_search_error("db locked")
        self.assertIn("Search error", controller.state.status_message)

        controller.start_indexing()
        controller.set_indexing_error("permission denied")
        self.assertIn("Indexing failed", controller.state.status_message)
        self.assertFalse(controller.state.indexing)

        controller.start_indexing()
        controller.set_indexing_success(files_indexed=42)
        self.assertIn("Index refreshed: 42 files", controller.state.status_message)
        self.assertFalse(controller.state.indexing)


class ScreenTextTests(unittest.TestCase):
    def test_no_index_state_explains_how_to_start_build(self) -> None:
        state = SearchState()
        text = build_results_text(state, roots=(Path("/projects"), Path("/notes")), has_index=False)

        self.assertIn("No completed index", text)
        self.assertIn("/projects", text)
        self.assertIn("Ctrl-R", text)

    def test_loading_state_mentions_last_completed_index(self) -> None:
        state = SearchState(indexing=True)
        text = build_status_text(state, roots=(Path("/projects"),), has_index=True)

        self.assertIn("Indexing", text)
        self.assertIn("last completed index", text)

    def test_autocomplete_text_marks_the_active_choice(self) -> None:
        state = SearchState(
            autocomplete_index=1,
            autocomplete=(
                __import__("sift_cli.autocomplete", fromlist=["AutocompleteSuggestion"]).AutocompleteSuggestion("alpha.md", "alpha.md"),
                __import__("sift_cli.autocomplete", fromlist=["AutocompleteSuggestion"]).AutocompleteSuggestion("beta.md", "beta.md"),
            ),
        )

        text = build_autocomplete_text(state)

        self.assertIn("> beta.md", text)
        self.assertIn("  alpha.md", text)

    def test_sidebar_text_includes_scope_and_keys(self) -> None:
        state = SearchState(raw_query="alpha", help_text="Searching for: alpha")

        text = build_sidebar_text(state, roots=(Path("/projects"),), has_index=True)

        self.assertIn("SIFT CLI", text)
        self.assertIn("/projects", text)
        self.assertIn("Ctrl-R", text)

    def test_banner_text_summarizes_query_and_index_state(self) -> None:
        state = SearchState(raw_query="alpha", mode="results", results=(_result("/tmp/alpha.md", "alpha.md"),))

        text = build_query_banner_text(state, has_index=True)

        self.assertIn("Query: alpha", text)
        self.assertIn("index ready", text)
        self.assertIn("results for alpha", text)

    def test_result_row_text_shows_selection_and_match_flags(self) -> None:
        result = _result("/tmp/alpha.md", "alpha.md", snippet="alpha beta")

        text = build_result_row_text(result, selected=True, index=0, total=1)

        self.assertIn("> [1/1] alpha.md", text)
        self.assertIn("name", text)
        self.assertIn("content", text)


if __name__ == "__main__":
    unittest.main()
