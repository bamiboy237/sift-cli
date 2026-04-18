"""UI controller and state for sift-cli."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from datetime import datetime, timezone
from typing import cast

from .autocomplete import AutocompleteSuggestion, autocomplete_suggestions
from .autocomplete import replace_active_token_with_cursor
from .actions import open_file
from .fuzzy_index import FuzzyIndex, load_fuzzy_index
from .models import ResultViewModel, SearchPreview, SearchResult
from .search import search_files


@dataclass(frozen=True, slots=True)
class SearchState:
    raw_query: str = ""
    results: tuple[SearchResult, ...] = ()
    autocomplete: tuple[AutocompleteSuggestion, ...] = ()
    autocomplete_index: int = 0
    autocomplete_hidden: bool = False
    selected_index: int = 0
    focus_mode: str = "input"
    has_index: bool = False
    indexing: bool = False
    loading: bool = False
    mode: str = "empty"
    help_text: str = "Type a query to search."
    status_message: str = ""


@dataclass(frozen=True, slots=True)
class SearchRequest:
    request_id: int
    query: str


@dataclass(frozen=True, slots=True)
class LaunchConfig:
    db_path: Path
    active_db_path: Path
    staging_db_path: Path
    roots: tuple[Path, ...]
    ignore_dirs: tuple[str, ...] = ()
    max_extracted_file_size: int = 1_048_576
    auto_start_indexing: bool = False


def build_preview_text(*, snippet: str | None, path: str) -> str:
    if snippet:
        if len(snippet) > 240:
            return snippet[:240].rstrip() + "..."
        return snippet
    return f"Preview unavailable for {path}"


def render_result_preview(result: SearchResult) -> str:
    preview = build_preview_text(snippet=result.snippet, path=result.path)
    if result.snippet:
        return preview
    size = f"{result.size} bytes"
    return f"{result.filename}\n{result.path}\n{size}\n{preview}"


def build_query_banner_text(state: SearchState, *, has_index: bool = False) -> str:
    index_ready = has_index or state.has_index
    if state.status_message:
        summary = state.status_message
    elif state.indexing and not index_ready:
        summary = "Building the first index in the background."
    elif state.loading:
        summary = "Searching against the active index..."
    elif state.indexing:
        summary = "Indexing in the background; search stays available."
    elif not state.raw_query.strip():
        summary = "Type a query to search files."
    elif state.results:
        summary = f"{len(state.results)} results for {state.raw_query}"
    else:
        summary = f"No matches for {state.raw_query}"

    index_state = "index ready" if index_ready else "no completed index"
    mode = state.mode.replace("-", " ")
    return f"Query: {state.raw_query or '—'}\nMode: {mode}  •  {index_state}  •  {summary}"


def build_sidebar_text(state: SearchState, *, roots: tuple[Path, ...] = (), has_index: bool = False) -> str:
    root_lines = [f"• {root}" for root in roots] or ["• (no roots configured)"]
    query = state.raw_query.strip() or "(empty)"
    status = state.status_message or ("Indexing" if state.indexing else "Idle")
    index_state = "Ready" if has_index or state.has_index else "Not built yet"
    help_lines = [
        "• / focus search",
        "• Tab accept autocomplete",
        "• Enter open or submit",
        "• Esc dismiss transient UI",
        "• Ctrl-R refresh index",
        "• q quit",
    ]
    lines = [
        "SIFT CLI",
        "Local file search",
        "",
        "Scope",
        *root_lines,
        "",
        "Index",
        f"• {index_state}",
        f"• {status}",
        "",
        "Query",
        f"• {query}",
        f"• {state.help_text}",
        "",
        "Keys",
        *help_lines,
    ]
    return "\n".join(lines)


def build_result_row_text(
    result: SearchResult,
    *,
    selected: bool = False,
    index: int | None = None,
    total: int | None = None,
) -> str:
    view = format_result_view(result)
    marker = ">" if selected else " "
    ordinal = f"[{index + 1}/{total}] " if index is not None and total is not None else ""
    badges: list[str] = []
    if view.matched_filename:
        badges.append("name")
    if view.matched_content:
        badges.append("content")
    if result.ext:
        badges.append(f".{result.ext}")
    badge_text = f"  {' • '.join(badges)}" if badges else ""
    lines = [
        f"{marker} {ordinal}{view.filename}",
        f"  {view.path}",
        f"  {view.modified_label}  {view.size_label or '-'}{badge_text}",
    ]
    if view.snippet:
        lines.append(f"  {view.snippet}")
    return "\n".join(lines)


def build_autocomplete_text(state: SearchState) -> str:
    if state.autocomplete_hidden or not state.autocomplete:
        return ""

    lines = ["Autocomplete"]
    for index, suggestion in enumerate(state.autocomplete):
        prefix = ">" if index == state.autocomplete_index else " "
        lines.append(f"{prefix} {suggestion.display}")
    return "\n".join(lines)


def build_results_text(
    state: SearchState,
    *,
    roots: tuple[Path, ...] = (),
    has_index: bool = False,
) -> str:
    index_ready = has_index or state.has_index

    if state.indexing and not index_ready:
        return "Building the first index... results will appear after the first successful build."

    if state.indexing and index_ready and not state.raw_query.strip() and not state.results:
        return "Indexing... search remains available against the last completed index."

    if state.loading:
        if index_ready:
            return "Indexing... search remains available against the last completed index."
        return "Building the first index... results will appear after the first successful build."

    if not state.raw_query.strip():
        if not index_ready:
            roots_text = "\n".join(f"- {root}" for root in roots) or "- (no roots configured)"
            return (
                "No completed index exists yet.\n"
                f"Roots:\n{roots_text}\n"
                "Press Ctrl-R to start the first build."
            )
        return (
            f"{state.help_text}\n"
            "Examples: alpha, ext:md, path:notes\n"
            "Press Ctrl-R to refresh the index."
        )

    if not state.results:
        return f"No matching files for: {state.raw_query}"

    lines = [f"Results ({len(state.results)})"]
    for index, result in enumerate(state.results):
        view = format_result_view(result)
        marker = ">" if index == state.selected_index else " "
        size = view.size_label or "-"
        lines.append(f"{marker} {view.filename}  {view.modified_label}  {size}")
        lines.append(f"  {view.path}")
        if view.snippet:
            lines.append(f"  {view.snippet}")
    return "\n".join(lines)


def build_status_text(
    state: SearchState,
    *,
    roots: tuple[Path, ...] = (),
    has_index: bool = False,
) -> str:
    if state.status_message:
        return state.status_message
    if state.indexing:
        if has_index or state.has_index:
            return "Indexing in progress. Search continues against the last completed index."
        return "Indexing in progress. The first completed index is not ready yet."
    if state.loading:
        return "Searching..."
    if not state.raw_query.strip():
        if not has_index and not state.has_index:
            return f"Configured roots: {', '.join(str(root) for root in roots) or 'none'}"
        return state.help_text
    if state.results:
        return f"{len(state.results)} results for {state.raw_query}"
    return f"No matching files for {state.raw_query}"


def format_result_view(result: SearchResult) -> ResultViewModel:
    modified = datetime.fromtimestamp(result.modified_at, tz=timezone.utc)
    return ResultViewModel(
        filename=result.filename,
        path=result.path,
        modified_label=modified.strftime("%Y-%m-%d %H:%M"),
        size_label=f"{result.size} B" if result.size is not None else None,
        snippet=result.snippet,
        matched_filename=result.matched_filename,
        matched_content=result.matched_content,
    )


class SearchController:
    def __init__(self, *, fuzzy_index: FuzzyIndex | None = None, db_path: Path | None = None) -> None:
        self._next_request_id = 0
        self._active_request_id = 0
        self._db_path = db_path
        self._fuzzy_index = fuzzy_index or FuzzyIndex([])
        self.state = SearchState(has_index=_has_completed_index(db_path))

    def begin_search(self, query: str) -> SearchRequest:
        self._next_request_id += 1
        self._active_request_id = self._next_request_id
        self.state = replace(self.state, raw_query=query, loading=True, focus_mode="input")
        return SearchRequest(request_id=self._active_request_id, query=query)

    def invalidate_pending_searches(self) -> None:
        self._next_request_id += 1
        self._active_request_id = self._next_request_id

    def complete_search(self, request: SearchRequest | int, results: list[object]) -> None:
        request_id = request.request_id if isinstance(request, SearchRequest) else request
        if request_id != self._active_request_id:
            return
        previous_selected_path = self.active_result.path if self.active_result is not None else None
        typed_results = tuple(cast(list[SearchResult], results))
        selected_index = 0
        if previous_selected_path is not None:
            for index, result in enumerate(typed_results):
                if result.path == previous_selected_path:
                    selected_index = index
                    break
        mode = "no-results" if not results else "results"
        self.state = replace(
            self.state,
            results=typed_results,
            loading=False,
            mode=mode,
            selected_index=selected_index,
            status_message="",
        )

    def update_query(self, query: str, *, cursor: int | None = None) -> None:
        autocomplete = tuple(autocomplete_suggestions(query, self._fuzzy_index, cursor=cursor)) if query.strip() else ()
        mode = "empty" if not query.strip() else ("autocomplete" if autocomplete else "ready")
        help_text = _help_text_for_query(query)
        self.state = replace(
            self.state,
            raw_query=query,
            autocomplete=autocomplete,
            autocomplete_index=0,
            autocomplete_hidden=False,
            mode=mode,
            help_text=help_text,
            focus_mode="input",
            status_message="",
        )

    @property
    def db_path(self) -> Path | None:
        return self._db_path

    def search(self, query: str) -> list[SearchResult]:
        self.update_query(query)
        if not query.strip():
            self.state = replace(self.state, results=(), loading=False, selected_index=0)
            return []
        if self._db_path is None:
            self.state = replace(self.state, loading=False, mode="no-results", status_message="No index database configured.")
            return []

        request = self.begin_search(query)
        try:
            results = search_files(self._db_path, query)
        except ValueError as exc:
            self.state = replace(self.state, loading=False, status_message=f"Query error: {exc}")
            return []
        except Exception as exc:
            self.state = replace(self.state, loading=False, status_message=f"Search error: {exc}")
            return []
        self.complete_search(request, results)
        return results

    def refresh_fuzzy_index(self, db_path: Path) -> None:
        self._db_path = db_path
        self._fuzzy_index = load_fuzzy_index(db_path)
        self.state = replace(self.state, has_index=_has_completed_index(db_path))

    def start_indexing(self) -> None:
        self.state = replace(self.state, indexing=True)

    def finish_indexing(self) -> None:
        self.state = replace(self.state, indexing=False)

    def focus_input(self) -> None:
        self.state = replace(self.state, focus_mode="input")

    def focus_results(self) -> None:
        if self.state.results:
            self.state = replace(self.state, focus_mode="results")

    def dismiss_autocomplete(self) -> None:
        self.state = replace(
            self.state,
            autocomplete=(),
            autocomplete_index=0,
            autocomplete_hidden=True,
            focus_mode="input",
        )

    def move_result_selection(self, delta: int) -> None:
        if not self.state.results:
            return
        next_index = max(0, min(len(self.state.results) - 1, self.state.selected_index + delta))
        self.state = replace(self.state, selected_index=next_index, focus_mode="results")

    def move_autocomplete_selection(self, delta: int) -> None:
        if not self.state.autocomplete:
            return
        next_index = max(0, min(len(self.state.autocomplete) - 1, self.state.autocomplete_index + delta))
        self.state = replace(self.state, autocomplete_index=next_index, focus_mode="autocomplete")

    def accept_autocomplete(self) -> str:
        return self.accept_autocomplete_with_cursor()[0]

    def accept_autocomplete_with_cursor(self, cursor: int | None = None) -> tuple[str, int]:
        if not self.state.autocomplete:
            current_cursor = len(self.state.raw_query) if cursor is None else max(0, min(cursor, len(self.state.raw_query)))
            return self.state.raw_query, current_cursor
        suggestion = self.state.autocomplete[self.state.autocomplete_index]
        query, next_cursor = replace_active_token_with_cursor(
            self.state.raw_query,
            suggestion.insert_text,
            cursor=cursor,
        )
        self.update_query(query)
        return query, next_cursor

    def clear_results(self) -> None:
        self.state = replace(self.state, results=(), selected_index=0)

    def clear_loading(self) -> None:
        self.state = replace(self.state, loading=False)

    def set_query_error(self, message: str) -> None:
        self.state = replace(self.state, loading=False, status_message=f"Query error: {message}")

    def set_search_error(self, message: str) -> None:
        self.state = replace(self.state, loading=False, status_message=f"Search error: {message}")

    def set_indexing_error(self, message: str) -> None:
        self.state = replace(self.state, indexing=False, status_message=f"Indexing failed: {message}")

    def set_indexing_success(self, *, files_indexed: int) -> None:
        self.state = replace(self.state, indexing=False, status_message=f"Index refreshed: {files_indexed} files")

    def precedence(self) -> str:
        if self.state.autocomplete and not self.state.autocomplete_hidden:
            return "autocomplete"
        if self.state.results:
            return "results"
        return "input"

    @property
    def active_result(self) -> SearchResult | None:
        if not self.state.results:
            return None
        index = max(0, min(self.state.selected_index, len(self.state.results) - 1))
        return self.state.results[index]

    def open_selected_result(self) -> None:
        if not self.state.results:
            return
        result = self.active_result
        if result is None:
            return
        try:
            open_file(Path(result.path))
        except FileNotFoundError:
            self.state = replace(self.state, status_message=f"Missing file: {result.path}")
            return
        self.state = replace(self.state, status_message=f"Opened {result.filename}")


def _help_text_for_query(query: str) -> str:
    if not query.strip():
        return "Example queries: alpha, ext:md, path:notes"
    return f"Searching for: {query}"


def _has_completed_index(db_path: Path | None) -> bool:
    if db_path is None or not db_path.exists():
        return False
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute("SELECT 1 FROM files LIMIT 1").fetchone()
    except sqlite3.Error:
        return False
    return row is not None
