from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import subprocess
from unittest.mock import patch

from sift_cli.actions import open_file
from sift_cli.models import SearchResult
from sift_cli.ui import SearchController, build_preview_text, render_result_preview


class ActionTests(unittest.TestCase):
    def test_open_file_uses_platform_default_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "alpha.md"
            file_path.write_text("alpha", encoding="utf-8")

            with patch("sift_cli.actions.sys.platform", "darwin"), patch("sift_cli.actions.subprocess.Popen") as popen:
                open_file(file_path)

        popen.assert_called_once()
        args, kwargs = popen.call_args
        self.assertEqual(args[0][:2], ["open", str(file_path)])
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)

    def test_open_file_raises_for_missing_path(self) -> None:
        with self.assertRaises(FileNotFoundError):
            open_file(Path("/tmp/does-not-exist.txt"))


class PreviewTests(unittest.TestCase):
    def test_build_preview_text_truncates_long_snippets(self) -> None:
        text = build_preview_text(snippet="x" * 300, path="/tmp/alpha.md")

        self.assertLessEqual(len(text), 243)
        self.assertTrue(text.endswith("..."))

    def test_render_result_preview_includes_metadata_when_no_snippet(self) -> None:
        result = SearchResult(
            path="/tmp/alpha.md",
            filename="alpha.md",
            ext="md",
            size=12,
            modified_at=1_714_000_000.0,
            snippet=None,
            matched_filename=True,
            matched_content=False,
            score=1.0,
        )

        preview = render_result_preview(result)

        self.assertIn("alpha.md", preview)
        self.assertIn("/tmp/alpha.md", preview)
        self.assertIn("12 bytes", preview)


class ControllerActionTests(unittest.TestCase):
    def test_open_selected_result_updates_status_without_clearing_state(self) -> None:
        result = SearchResult(
            path="/tmp/alpha.md",
            filename="alpha.md",
            ext="md",
            size=12,
            modified_at=1_714_000_000.0,
            snippet="alpha beta",
            matched_filename=True,
            matched_content=True,
            score=1.0,
        )
        controller = SearchController()
        request = controller.begin_search("alpha")
        controller.complete_search(request, [result])

        with patch("sift_cli.ui.open_file") as open_mock:
            controller.open_selected_result()

        open_mock.assert_called_once_with(Path("/tmp/alpha.md"))
        self.assertIn("Opened", controller.state.status_message)
        self.assertEqual(controller.state.results[0], result)

    def test_open_selected_result_reports_missing_file_non_fatally(self) -> None:
        result = SearchResult(
            path="/tmp/missing.md",
            filename="missing.md",
            ext="md",
            size=12,
            modified_at=1_714_000_000.0,
            snippet=None,
            matched_filename=True,
            matched_content=False,
            score=1.0,
        )
        controller = SearchController()
        request = controller.begin_search("alpha")
        controller.complete_search(request, [result])

        with patch("sift_cli.ui.open_file", side_effect=FileNotFoundError("missing")):
            controller.open_selected_result()

        self.assertIn("Missing file", controller.state.status_message)
        self.assertEqual(controller.state.results[0], result)


if __name__ == "__main__":
    unittest.main()
