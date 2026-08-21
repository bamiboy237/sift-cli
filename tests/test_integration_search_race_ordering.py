from __future__ import annotations

import unittest

from sift_cli.models import SearchResult
from sift_cli.ui import SearchController


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


class SearchRaceOrderingIntegrationTests(unittest.TestCase):
    def test_out_of_order_completions_only_show_latest_results(self) -> None:
        controller = SearchController()

        first = controller.begin_search("alpha")
        second = controller.begin_search("beta")
        third = controller.begin_search("gamma")

        beta = _result("/tmp/beta.md", "beta.md")
        controller.complete_search(second, [beta])
        self.assertEqual(controller.state.results, ())

        alpha = _result("/tmp/alpha.md", "alpha.md")
        controller.complete_search(first, [alpha])
        self.assertEqual(controller.state.results, ())

        gamma = _result("/tmp/gamma.md", "gamma.md")
        controller.complete_search(third, [gamma])
        self.assertEqual(controller.state.results, (gamma,))

    def test_invalidate_pending_searches_rejects_all_prior_completions(self) -> None:
        controller = SearchController()

        first = controller.begin_search("alpha")
        second = controller.begin_search("beta")
        controller.invalidate_pending_searches()

        controller.complete_search(first, [_result("/tmp/alpha.md", "alpha.md")])
        controller.complete_search(second, [_result("/tmp/beta.md", "beta.md")])

        self.assertEqual(controller.state.results, ())


if __name__ == "__main__":
    unittest.main()
