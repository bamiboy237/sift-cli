"""Textual app shell for sift-cli."""

from __future__ import annotations

import asyncio
from typing import Literal

from rich.text import Text

from .indexer import IndexingService
from .messages import IndexBuildAlreadyRunning, IndexBuildFailed, IndexBuildSucceeded, SearchCompletedWithResults, SearchFailed, SearchQueryFailed
from .search import search_files
from .ui import (
    LaunchConfig,
    SearchController,
    build_query_banner_text,
    build_autocomplete_text,
    build_result_row_text,
    build_results_text,
    build_sidebar_text,
    build_status_text,
    render_result_preview,
)


def launch_app(config: LaunchConfig, controller: SearchController | None = None) -> None:
    controller = controller or SearchController(db_path=config.db_path)
    try:
        from textual.app import App, ComposeResult
        from textual.events import Resize
        from textual.containers import Horizontal, Vertical
        from textual.widget import MountError
        from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static
    except ModuleNotFoundError as exc:
        raise RuntimeError("textual is required to run the UI") from exc

    class SiftApp(App):
        CSS = """
        Screen {
            layout: vertical;
            background: $background;
        }

        #content {
            height: 1fr;
            min-height: 0;
            padding: 0 1;
            overflow: hidden;
        }

        #top {
            height: 1fr;
            min-height: 0;
            margin: 0 0 1 0;
            overflow: hidden;
        }

        #sidebar {
            width: 34;
            min-width: 24;
            margin-right: 1;
            border: round $primary;
            padding: 0 1;
            background: $surface 8%;
            overflow-y: auto;
            overflow-x: hidden;
        }

        #main {
            width: 1fr;
            min-height: 0;
            overflow: hidden;
        }

        #banner {
            border: round $secondary;
            padding: 0 1;
            margin: 0 0 1 0;
            background: $surface 9%;
        }

        #search {
            margin: 0 0 1 0;
            border: round $warning;
            padding: 0 1;
            background: $surface 10%;
        }

        #results-shell {
            height: 1fr;
            min-height: 0;
            border: round $accent;
            padding: 0 1;
            background: $surface 6%;
            overflow: hidden;
        }

        #results {
            height: 1fr;
            width: 3fr;
            min-height: 0;
        }

        #preview {
            width: 2fr;
            height: 1fr;
            min-height: 0;
            min-width: 32;
            border: round $error;
            padding: 0 1;
            margin-left: 1;
            background: $surface 6%;
            overflow-y: auto;
            overflow-x: hidden;
        }

        #autocomplete {
            height: auto;
            max-height: 8;
            margin: 0 0 1 0;
            border: round $success;
            padding: 0 1;
            background: $surface 9%;
            overflow-y: auto;
            overflow-x: hidden;
        }

        #autocomplete.-hidden {
            display: none;
        }

        #autocomplete.-visible {
            display: block;
        }

        #status {
            height: 1;
            color: $text-muted;
            padding: 0 1;
            border-top: solid $surface 30%;
        }

        #spinner {
            width: 3;
            margin-right: 1;
        }

        #status-line {
            height: 1;
            min-height: 1;
        }

        Screen.-mode-stacked #results-shell {
            layout: vertical;
        }

        Screen.-mode-stacked #results {
            width: 1fr;
            height: 1fr;
        }

        Screen.-mode-stacked #preview {
            width: 1fr;
            height: 12;
            min-width: 0;
            margin-left: 0;
            margin-top: 1;
        }

        Screen.-mode-compact #top {
            layout: vertical;
        }

        Screen.-mode-compact #sidebar {
            width: 1fr;
            min-width: 0;
            height: 8;
            margin-right: 0;
            margin-bottom: 1;
        }

        Screen.-mode-compact #results-shell {
            layout: vertical;
        }

        Screen.-mode-compact #results {
            width: 1fr;
            height: 1fr;
        }

        Screen.-mode-compact #preview {
            width: 1fr;
            height: 8;
            min-width: 0;
            margin-left: 0;
            margin-top: 1;
        }

        ListView {
            background: transparent;
        }

        ListItem {
            margin: 0 0 1 0;
            border: round $surface 30%;
            padding: 0 1;
            background: $surface 8%;
        }

        ListItem.selected {
            background: $surface 18%;
            border: round $primary;
        }

        Static {
            color: $text;
        }

        Input {
            background: transparent;
        }

        .muted {
            color: $text-muted;
        }

        .title {
            text-style: bold;
        }
        """

        BINDINGS = [
            ("/", "focus_search", "Search"),
            ("up", "cursor_up", "Up"),
            ("down", "cursor_down", "Down"),
            ("enter", "submit", "Enter"),
            ("tab", "accept_autocomplete", "Tab Accept"),
            ("escape", "dismiss", "Esc Dismiss"),
            ("ctrl+r", "refresh_index", "Refresh"),
            ("q", "request_quit", "Quit"),
            ("ctrl+c", "force_quit", "Force Quit"),
        ]

        _DEBOUNCE_SECONDS = 0.2

        def __init__(self) -> None:
            super().__init__()
            self._indexing_service = IndexingService()
            self._search_debounce_timer = None
            self._ui_ready = False
            self._render_pending = False
            self._last_results_render_key: tuple | None = None
            self._layout_mode: LayoutMode | None = None
            self._autocomplete_visible = False

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with Vertical(id="content"):
                with Horizontal(id="top"):
                    yield Static("", id="sidebar")
                    with Vertical(id="main"):
                        yield Static("", id="banner")
                        yield Input(placeholder="Search files…", id="search", name="search")
                        yield Static("", id="autocomplete", classes="-hidden")
                        with Horizontal(id="results-shell"):
                            yield ListView(id="results")
                            yield Static("Preview", id="preview")
                with Horizontal(id="status-line"):
                    yield Label("", id="spinner")
                    yield Label("Ready", id="status")
            yield Footer()

        def on_mount(self) -> None:
            self.query_one("#search", Input).focus()
            self._apply_layout_mode(self.size.width, self.size.height)
            self._ui_ready = True
            self._request_render()
            if config.auto_start_indexing:
                self.call_after_refresh(self.action_refresh_index)

        def on_resize(self, event: Resize) -> None:
            self._apply_layout_mode(event.size.width, event.size.height)
            self._last_results_render_key = None
            self._request_render()

        def _apply_layout_mode(self, width: int, height: int) -> None:
            mode = _layout_mode_for_size(width, height)
            if mode == self._layout_mode:
                return
            if self._layout_mode is not None:
                self.remove_class(f"-mode-{self._layout_mode}")
            self.add_class(f"-mode-{mode}")
            self._layout_mode = mode
            self._last_results_render_key = None

        def _request_render(self) -> None:
            if not self._ui_ready or self._render_pending:
                return
            self._render_pending = True

            def _run() -> None:
                self._render_pending = False
                self._render_state()

            self.call_after_refresh(_run)

        def action_focus_search(self) -> None:
            search = self.query_one("#search", Input)
            search.focus()
            search.cursor_position = len(search.value)
            controller.focus_input()

        def action_refresh_index(self) -> None:
            if controller.state.indexing:
                controller.set_indexing_already_running()
                self._request_render()
                return
            controller.start_indexing()
            self.run_worker(self._run_index_refresh(), name="index-refresh", thread=False)
            self._request_render()

        def action_open_selected(self) -> None:
            controller.open_selected_result()
            self._request_render()

        def action_cursor_up(self) -> None:
            if controller.precedence() == "autocomplete":
                controller.move_autocomplete_selection(-1)
            elif controller.state.focus_mode == "results":
                if controller.state.selected_index == 0:
                    controller.focus_input()
                    self.query_one("#search", Input).focus()
                    self._request_render()
                    return
                controller.move_result_selection(-1)
            self._request_render()

        def action_cursor_down(self) -> None:
            if controller.precedence() == "autocomplete":
                controller.move_autocomplete_selection(1)
            elif controller.state.focus_mode == "results":
                controller.move_result_selection(1)
            elif controller.state.results:
                controller.focus_results_first()
            self._request_render()

        def action_submit(self) -> None:
            if controller.precedence() == "autocomplete" and controller.state.autocomplete:
                search_input = self.query_one("#search", Input)
                value, cursor = controller.accept_autocomplete_with_cursor(search_input.cursor_position)
                self.query_one("#search", Input).value = value
                self.query_one("#search", Input).cursor_position = cursor
                self._schedule_search(value, immediate=True)
            elif controller.state.focus_mode == "results":
                controller.open_selected_result()
            else:
                self._schedule_search(self.query_one("#search", Input).value, immediate=True)
            self._request_render()

        def action_dismiss(self) -> None:
            if controller.dismiss_transient():
                self._request_render()
                return
            if controller.state.autocomplete and not controller.state.autocomplete_hidden:
                controller.dismiss_autocomplete()
            self._request_render()

        def action_request_quit(self) -> None:
            if controller.state.autocomplete and not controller.state.autocomplete_hidden:
                controller.dismiss_autocomplete()
                self._request_render()
                return
            self.exit()

        def action_force_quit(self) -> None:
            self.exit()

        def action_accept_autocomplete(self) -> None:
            if not controller.state.autocomplete:
                return
            search_input = self.query_one("#search", Input)
            value, cursor = controller.accept_autocomplete_with_cursor(search_input.cursor_position)
            self.query_one("#search", Input).value = value
            self.query_one("#search", Input).cursor_position = cursor
            self._schedule_search(value, immediate=True)
            self._request_render()

        def _render_state(self) -> None:
            if not self._ui_ready:
                return
            try:
                search = self.query_one("#search", Input)
                if search.value != controller.state.raw_query:
                    search.value = controller.state.raw_query
                autocomplete_widget = self.query_one("#autocomplete", Static)
                autocomplete_text = build_autocomplete_text(controller.state)
                autocomplete_widget.update(_styled_text(autocomplete_text) if autocomplete_text else "")
                autocomplete_visible = bool(autocomplete_text)
                if autocomplete_visible != self._autocomplete_visible:
                    self._last_results_render_key = None
                    self._autocomplete_visible = autocomplete_visible
                if autocomplete_visible:
                    autocomplete_widget.remove_class("-hidden")
                    autocomplete_widget.add_class("-visible")
                else:
                    autocomplete_widget.remove_class("-visible")
                    autocomplete_widget.add_class("-hidden")
                self.query_one("#sidebar", Static).update(
                    build_sidebar_text(controller.state, roots=config.roots, has_index=controller.state.has_index)
                )
                self.query_one("#banner", Static).update(
                    build_query_banner_text(controller.state, has_index=controller.state.has_index)
                )
                self._render_results_list()
                preview = (
                    render_result_preview(controller.active_result)
                    if controller.active_result is not None
                    else "Preview\nNo result selected."
                )
                self.query_one("#preview", Static).update(_styled_text(preview))
                self.query_one("#status", Label).update(
                    build_status_text(controller.state, roots=config.roots, has_index=controller.state.has_index)
                )
                spinner = self.query_one("#spinner", Label)
                spinner.update("[*]" if controller.state.indexing or controller.state.loading else "")
            except MountError:
                self._request_render()

        def _render_results_list(self) -> None:
            results_view = self.query_one("#results", ListView)
            state = controller.state
            if state.results:
                render_key = ("results", state.results, state.selected_index)
            else:
                render_key = (
                    "empty",
                    state.raw_query,
                    state.loading,
                    state.mode,
                    state.has_index,
                )

            if render_key == self._last_results_render_key:
                return

            self._last_results_render_key = render_key
            results_view.clear()
            if state.results:
                total = len(state.results)
                for index, result in enumerate(state.results):
                    row_text = build_result_row_text(
                        result,
                        selected=index == state.selected_index,
                        index=index,
                        total=total,
                    )
                    results_view.append(
                        ListItem(
                            Static(_styled_text(row_text)),
                            classes="selected" if index == state.selected_index else None,
                        )
                    )
                results_view.index = state.selected_index
            else:
                empty_text = build_results_text(
                    state,
                    roots=config.roots,
                    has_index=state.has_index,
                )
                results_view.append(ListItem(Static(_styled_text(empty_text))))

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "search":
                self.action_submit()

        def on_input_changed(self, event: Input.Changed) -> None:
            if event.input.id == "search":
                self._schedule_search(event.value, immediate=False)
                self._request_render()

        def _schedule_search(self, query: str, *, immediate: bool) -> None:
            cursor = self.query_one("#search", Input).cursor_position
            controller.update_query(query, cursor=cursor)
            if not query.strip():
                controller.invalidate_pending_searches()
                controller.clear_results()
                controller.clear_loading()
                if self._search_debounce_timer is not None:
                    self._search_debounce_timer.stop()
                    self._search_debounce_timer = None
                self._last_results_render_key = None
                return

            request = controller.begin_search(query)
            if self._search_debounce_timer is not None:
                self._search_debounce_timer.stop()
                self._search_debounce_timer = None
            if immediate:
                self._start_search_worker(query, request.request_id)
                return
            self._search_debounce_timer = self.set_timer(
                self._DEBOUNCE_SECONDS,
                lambda q=query, request_id=request.request_id: self._start_search_worker(q, request_id),
            )

        def _start_search_worker(self, query: str, request_id: int) -> None:
            self.run_worker(self._run_search(query, request_id), name=f"search:{request_id}", thread=False)

        async def _run_search(self, query: str, request_id: int) -> None:
            db_path = controller.db_path
            if db_path is None:
                self._apply_search_outcome(
                    SearchQueryFailed(request_id=request_id, query=query, error="No index database configured.")
                )
                return

            def _execute() -> SearchCompletedWithResults | SearchQueryFailed | SearchFailed:
                try:
                    results = search_files(db_path, query)
                except ValueError as exc:
                    return SearchQueryFailed(request_id=request_id, query=query, error=str(exc))
                except Exception as exc:
                    return SearchFailed(request_id=request_id, error=str(exc))
                return SearchCompletedWithResults(request_id=request_id, query=query, results=tuple(results))

            outcome = await asyncio.to_thread(_execute)
            self._apply_search_outcome(outcome)

        def _apply_search_outcome(self, outcome: SearchCompletedWithResults | SearchQueryFailed | SearchFailed) -> None:
            if not controller.is_active_request(outcome.request_id):
                return
            if isinstance(outcome, SearchQueryFailed):
                controller.set_query_error(outcome.error)
            elif isinstance(outcome, SearchFailed):
                controller.set_search_error(outcome.error)
            else:
                controller.complete_search(outcome.request_id, outcome.results)
            self._request_render()

        async def _run_index_refresh(self) -> None:
            def _refresh() -> IndexBuildSucceeded | IndexBuildFailed | IndexBuildAlreadyRunning:
                try:
                    stats = self._indexing_service.refresh(
                        roots=config.roots,
                        active_db_path=config.active_db_path,
                        staging_db_path=config.staging_db_path,
                        ignore_dirs=config.ignore_dirs,
                        max_extracted_file_size=config.max_extracted_file_size,
                        include_hidden_dirs=config.include_hidden_dirs,
                    )
                except Exception as exc:
                    return IndexBuildFailed(error=str(exc))
                if stats is None:
                    return IndexBuildAlreadyRunning()
                return IndexBuildSucceeded(
                    active_db_path=config.active_db_path,
                    files_indexed=stats.files_indexed,
                    files_skipped=stats.files_skipped,
                )

            outcome = await asyncio.to_thread(_refresh)
            self._apply_index_outcome(outcome)

        def _apply_index_outcome(self, outcome: IndexBuildSucceeded | IndexBuildFailed | IndexBuildAlreadyRunning) -> None:
            if isinstance(outcome, IndexBuildAlreadyRunning):
                controller.set_indexing_already_running()
                self._request_render()
                return
            if isinstance(outcome, IndexBuildFailed):
                controller.set_indexing_error(outcome.error)
            elif isinstance(outcome, IndexBuildSucceeded):
                controller.refresh_fuzzy_index(config.active_db_path)
                controller.set_indexing_success(
                    files_indexed=outcome.files_indexed,
                    files_skipped=outcome.files_skipped,
                )
            else:
                controller.finish_indexing()
            self._request_render()

    SiftApp().run()


def _styled_text(text: str) -> Text:
    rendered = Text()
    i = 0
    while i < len(text):
        start = text.find("\x1f", i)
        if start == -1:
            rendered.append(text[i:])
            break
        rendered.append(text[i:start])
        end = text.find("\x1e", start + 1)
        if end == -1:
            rendered.append(text[start:])
            break
        rendered.append(text[start + 1 : end], style="bold yellow")
        i = end + 1
    return rendered


LayoutMode = Literal["wide", "stacked", "compact"]


def _layout_mode_for_size(width: int, height: int) -> LayoutMode:
    if width >= 140 and height >= 38:
        return "wide"
    if width >= 105 and height >= 30:
        return "stacked"
    return "compact"
