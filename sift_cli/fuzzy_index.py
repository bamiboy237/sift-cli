"""In-memory fuzzy filename/path indexing for autocomplete."""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .db import connect_read_database
from .paths import casefold_path, normalize_path


def extract_trigrams(text: str) -> set[str]:
    padded = f"  {text} "
    return {padded[index : index + 3] for index in range(len(padded) - 2)}


def build_trigram_index(values: list[str]) -> dict[str, set[int]]:
    index: dict[str, set[int]] = defaultdict(set)
    for item_index, value in enumerate(values):
        for trigram in extract_trigrams(value.casefold()):
            index[trigram].add(item_index)
    return index


@dataclass(frozen=True, slots=True)
class FuzzySuggestion:
    path: str
    basename: str
    score: tuple[int, int, int, int, int, int, str]


class FuzzyIndex:
    def __init__(self, rows: list[tuple[str, str]] | None = None) -> None:
        self._rows: list[tuple[str, str]] = []
        self._normalized_paths: list[str] = []
        self._basenames: list[str] = []
        self._index: dict[str, set[int]] = {}
        # Precomputed per-row lookup structures so suggest() never allocates
        # per candidate on the UI thread.
        self._char_sets: list[frozenset[str]] = []
        self._folded_basenames: list[str] = []
        self._sort_keys: list[str] = []
        if rows is not None:
            self.update_rows(rows)

    def update_rows(self, rows: list[tuple[str, str]]) -> None:
        self._rows = rows
        self._normalized_paths = [casefold_path(path) for path, _ in rows]
        self._basenames = [basename for _, basename in rows]
        self._index = build_trigram_index(self._normalized_paths)
        self._char_sets = [frozenset(path) for path in self._normalized_paths]
        self._folded_basenames = [basename.casefold() for basename in self._basenames]
        self._sort_keys = [normalize_path(path) for path, _ in rows]

    def strategy_for_query(self, query: str) -> str:
        query = query.casefold().strip()
        if not query:
            return "empty"
        if len(query) == 1:
            return "prefix"
        if len(query) <= 3:
            return "subset"
        return "trigram"

    def suggest(self, query: str, limit: int = 10) -> list[FuzzySuggestion]:
        normalized_query = query.casefold().strip()
        if not normalized_query:
            return []

        candidate_ids = self._candidate_ids(normalized_query)
        suggestions: list[FuzzySuggestion] = []
        for candidate_id in candidate_ids:
            path, basename = self._rows[candidate_id]
            suggestions.append(
                FuzzySuggestion(
                    path=path,
                    basename=basename,
                    score=self._score(candidate_id, normalized_query),
                )
            )
        suggestions.sort(key=lambda suggestion: suggestion.score)
        return suggestions[:limit]

    def _candidate_ids(self, query: str) -> list[int]:
        if len(query) == 1:
            return [
                index
                for index, path in enumerate(self._normalized_paths)
                if query in path
            ]
        if len(query) <= 3:
            query_chars = set(query)
            return [
                index
                for index, char_set in enumerate(self._char_sets)
                if query_chars.issubset(char_set)
            ]

        query_trigrams = extract_trigrams(query)
        overlap_counts: Counter[int] = Counter()
        for trigram in query_trigrams:
            overlap_counts.update(self._index.get(trigram, set()))
        minimum_overlap = max(1, len(query_trigrams) // 3)
        return [
            index for index, count in overlap_counts.items() if count >= minimum_overlap
        ]

    def _score(
        self, candidate_id: int, query: str
    ) -> tuple[int, int, int, int, int, int, str]:
        normalized_path = self._normalized_paths[candidate_id]
        normalized_basename = self._folded_basenames[candidate_id]
        basename_match = 0 if normalized_basename == query else 1
        basename_prefix = 0 if normalized_basename.startswith(query) else 1
        basename_length = len(normalized_basename)
        basename_overlap = -len(
            extract_trigrams(normalized_basename) & extract_trigrams(query)
        )
        boundary_match = (
            0
            if f"/{query}" in normalized_path or normalized_path.startswith(query)
            else 1
        )
        deep_match = normalized_path.count("/")
        return (
            basename_match,
            basename_prefix,
            basename_length,
            basename_overlap,
            boundary_match,
            deep_match,
            self._sort_keys[candidate_id],
        )


def load_fuzzy_index(db_path: Path) -> FuzzyIndex:
    with closing(connect_read_database(db_path)) as connection:
        rows = connection.execute(
            "SELECT path, filename FROM files ORDER BY path ASC"
        ).fetchall()
    fuzzy = FuzzyIndex()
    fuzzy.update_rows([(row[0], row[1]) for row in rows])
    return fuzzy
