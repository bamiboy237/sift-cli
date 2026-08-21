"""Headless UI smoke tests for Phase 1 responsiveness work.

These drive the real Textual app with a Pilot so the live-app paths
(selection sync, worker cancellation, async fuzzy-index install) are covered.
"""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

try:
    from textual.widgets import Input, ListItem, ListView
except ModuleNotFoundError:  # pragma: no cover - textual is a hard dependency
    raise unittest.SkipTest("textual not installed")

from sift_cli.app import build_sift_app
from sift_cli.db import initialize_database
from sift_cli.ui import LaunchConfig, SearchController


def _seed_db(db_path: Path) -> None:
    initialize_database(db_path)
    modified = datetime.now(UTC).timestamp()
    rows = [
        ("/docs/document.md", "document.md", "md", "alpha content here"),
        ("/docs/docker.md", "docker.md", "md", "alpha again"),
        ("/docs/dog.txt", "dog.txt", "txt", "alpha again"),
        ("/docs/notes/unrelated.md", "unrelated.md", "md", None),
    ]
    with sqlite3.connect(db_path) as connection:
        for path, filename, ext, content in rows:
            connection.execute(
                "INSERT INTO files(path, filename, ext, content, size, created_at, modified_at, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    path,
                    filename,
                    ext,
                    content,
                    32,
                    None,
                    modified,
                    modified,
                ),
            )
        connection.commit()


async def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


class HeadlessAppSmokeTests(unittest.TestCase):
    def run(self, result=None):
        return super().run(result)

    def _make_app(self, temp_path: Path):
        db_path = temp_path / "index.db"
        _seed_db(db_path)
        config = LaunchConfig(
            db_path=db_path,
            active_db_path=db_path,
            staging_db_path=temp_path / "index.build.db",
            roots=(temp_path / "docs",),
            ignore_dirs=(".git",),
            max_extracted_file_size=1_048_576,
            include_hidden_dirs=False,
            auto_start_indexing=False,
        )
        controller = SearchController(db_path=db_path)
        app_class = build_sift_app(config, controller)
        return app_class(), controller

    def test_type_search_select_and_autocomplete_flow(self) -> None:
        asyncio.run(self._drive_app())

    async def _drive_app(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app, controller = self._make_app(Path(temp_dir))
            async with app.run_test(size=(140, 40)) as pilot:
                search_input = app.query_one("#search", Input)

                # Boot state: input focused.
                self.assertTrue(search_input.has_focus)

                # Type a partial query; prefix search must find document.md.
                # Each keystroke outlives the debounce here, so wait for the
                # final "doc" result set rather than the first non-empty one.
                for char in "doc":
                    await pilot.press(char)
                expected = {"docker.md", "document.md"}
                self.assertTrue(
                    await _wait_until(
                        lambda: {r.filename for r in controller.state.results}
                        == expected
                    ),
                    f"expected {expected}, got "
                    f"{[r.filename for r in controller.state.results]}",
                )
                self.assertEqual(
                    controller.state.results[0].filename, "docker.md"
                )
                results_view = app.query_one("#results", ListView)
                item_count = len(results_view.children)
                self.assertGreaterEqual(item_count, 2)

                # Fuzzy index installs asynchronously; suggestions must appear
                # for the already-typed query without further keystrokes.
                self.assertTrue(
                    await _wait_until(
                        lambda: bool(controller.state.autocomplete),
                        timeout=5.0,
                    ),
                    "expected async fuzzy index to populate autocomplete",
                )

                # Per the precedence contract arrows move suggestions first,
                # so dismiss autocomplete before navigating results.
                await pilot.press("escape")
                self.assertFalse(
                    controller.state.autocomplete
                    and not controller.state.autocomplete_hidden
                )

                # Arrow navigation must move selection without rebuilding
                # every row (Phase 1 selection-sync path).
                await pilot.press("down")
                await pilot.press("down")
                self.assertEqual(controller.state.selected_index, 1)
                self.assertEqual(len(results_view.children), item_count)
                selected_items = [
                    child
                    for child in results_view.children
                    if isinstance(child, ListItem) and "selected" in child.classes
                ]
                self.assertEqual(len(selected_items), 1)

                # Up returns to the first result per the focus contract.
                await pilot.press("up")
                self.assertEqual(controller.state.selected_index, 0)

                # Rapid extra typing exercises worker cancellation path.
                for char in "xyz":
                    await pilot.press(char)
                await pilot.pause(0.3)


if __name__ == "__main__":
    unittest.main()
