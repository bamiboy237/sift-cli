from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from sift_cli.config import DEFAULT_IGNORE_DIRS, DEFAULT_MAX_EXTRACTED_FILE_SIZE
from sift_cli.indexer import IndexingService, build_index
from sift_cli.search import search_files
from sift_cli.ui import SearchController


class RebuildSearchAvailabilityIntegrationTests(unittest.TestCase):
    def test_search_uses_last_completed_index_while_rebuild_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "root"
            root.mkdir()
            file_path = root / "alpha.md"
            file_path.write_text("alpha", encoding="utf-8")

            active_db = temp_path / "index.db"
            staging_db = temp_path / "index.build.db"

            build_index(
                roots=(root,),
                active_db_path=active_db,
                staging_db_path=staging_db,
                ignore_dirs=DEFAULT_IGNORE_DIRS,
                max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
            )

            service = IndexingService()
            started = threading.Event()
            release = threading.Event()

            def slow_extract(path: Path, ext: str | None, max_size: int) -> str:
                if path.name == "alpha.md":
                    started.set()
                    release.wait(timeout=2)
                return path.read_text(encoding="utf-8")

            result_holder: list[object] = []

            def run_rebuild() -> None:
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

            thread = threading.Thread(target=run_rebuild)
            thread.start()
            self.assertTrue(started.wait(timeout=2))

            live_results = [result.filename for result in search_files(active_db, "alpha")]
            self.assertEqual(live_results, ["alpha.md"])

            release.set()
            thread.join(timeout=2)
            self.assertEqual(len(result_holder), 1)
            self.assertIsNotNone(result_holder[0])

    def test_controller_reports_refresh_already_running_without_resetting_state(self) -> None:
        controller = SearchController()
        controller.state = controller.state
        controller.start_indexing()
        controller.set_indexing_already_running()

        self.assertTrue(controller.state.indexing)
        self.assertIn("already running", controller.state.status_message)


if __name__ == "__main__":
    unittest.main()
