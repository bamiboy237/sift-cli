"""Autocomplete helpers for fuzzy filename/path suggestions."""

from __future__ import annotations

from dataclasses import dataclass

from .fuzzy_index import FuzzyIndex


@dataclass(frozen=True, slots=True)
class AutocompleteSuggestion:
    display: str
    insert_text: str


def autocomplete_suggestions(
    query: str,
    fuzzy_index: FuzzyIndex,
    limit: int = 10,
    cursor: int | None = None,
) -> list[AutocompleteSuggestion]:
    token = _active_token(query, cursor=cursor)
    if token is None:
        return []

    field, value = token
    suggestions = fuzzy_index.suggest(value, limit=limit)
    if field == "path":
        return [AutocompleteSuggestion(display=suggestion.path, insert_text=suggestion.path) for suggestion in suggestions]
    return [AutocompleteSuggestion(display=suggestion.basename, insert_text=suggestion.basename) for suggestion in suggestions]


def replace_active_token(query: str, replacement: str, cursor: int | None = None) -> str:
    token = _active_token(query, cursor=cursor)
    if token is None:
        return query
    field, value = token
    start, end = _token_bounds(query, cursor=cursor)
    if field is None:
        return f"{query[:start]}{replacement}{query[end:]}"
    return f"{query[:start]}{field}:{replacement}{query[end:]}"


def _active_token(query: str, cursor: int | None = None) -> tuple[str | None, str] | None:
    start, end = _token_bounds(query, cursor=cursor)
    if start == end:
        return None
    token = query[start:end]
    if ":" in token:
        field, value = token.split(":", 1)
        if not value:
            return None
        if field.casefold() in {"path", "filename", "content", "ext"}:
            return field.casefold(), value
    return (None, token)


def _token_bounds(query: str, cursor: int | None = None) -> tuple[int, int]:
    if cursor is None:
        cursor = len(query)
    cursor = max(0, min(cursor, len(query)))
    start = cursor
    while start > 0 and not query[start - 1].isspace():
        start -= 1
    end = cursor
    while end < len(query) and not query[end].isspace():
        end += 1
    return start, end
