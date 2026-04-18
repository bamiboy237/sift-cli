"""Textual app shell for sift-cli."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .indexer import IndexStats, IndexingService
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
        from textual.events import Key
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
            padding: 0 1;
        }

        #top {
            height: 1fr;
            margin: 0 0 1 0;
        }

        #sidebar {
            width: 34;
            margin-right: 1;
            border: round $primary;
            padding: 0 1;
            background: $surface 8%;
        }

        #main {
            width: 1fr;
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
            border: round $accent;
            padding: 0 1;
            background: $surface 6%;
        }

        #results {
            height: 1fr;
        }

        #preview {
            width: 3fr;
            border: round $error;
            padding: 0 1;
            margin-left: 1;
            background: $surface 6%;
        }

        #autocomplete {
            height: auto;
            margin: 0 0 1 0;
            border: round $success;
            padding: 0 1;
            background: $surface 9%;
        }

        #status {
            height: 1;
            color: $text-muted;
            padding: 0 1;
            border-top: solid $surface 30%;
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

        BINDINGS = [("/", "focus_search", "Search"), ("ctrl+r", "refresh_index", "Refresh")]

        _DEBOUNCE_SECONDS = 0.2

        @dataclass(frozen=True, slots=True)
        class _SearchOutcome:
            request_id: int
            query: str
            results: tuple = ()
            query_error: str | None = None
            search_error: str | None = None

        @dataclass(frozen=True, slots=True)
        class _IndexOutcome:
            stats: IndexStats | None = None
            error: str | None = None

        def __init__(self) -> None:
            super().__init__()
            self._indexing_service = IndexingService()
            self._search_debounce_timer = None
            self._pending_query = ""
            self._ui_ready = False
            self._render_pending = False
            self._last_results_render_key: tuple | None = None

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with Vertical(id="content"):
                with Horizontal(id="top"):
                    yield Static("", id="sidebar")
                    with Vertical(id="main"):
                        yield Static("", id="banner")
                        yield Input(placeholder="Search files…", id="search", name="search")
                        yield Static("", id="autocomplete")
                        with Horizontal(id="results-shell"):
                            yield ListView(id="results")
                            yield Static("Preview", id="preview")
                yield Label("Ready", id="status")
            yield Footer()

        def on_mount(self) -> None:
            self.query_one("#search", Input).focus()
            self._ui_ready = True
            self._request_render()

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
            elif controller.state.results:
                controller.focus_results()
            self._request_render()

        def action_cursor_down(self) -> None:
            if controller.precedence() == "autocomplete":
                controller.move_autocomplete_selection(1)
            elif controller.state.focus_mode == "results":
                controller.move_result_selection(1)
            elif controller.state.results:
                controller.focus_results()
            self._request_render()

        def action_submit(self) -> None:
            if controller.precedence() == "autocomplete" and controller.state.autocomplete:
                value = controller.accept_autocomplete()
                self.query_one("#search", Input).value = value
                self._schedule_search(value, immediate=True)
            elif controller.state.focus_mode == "results":
                controller.open_selected_result()
            else:
                self._schedule_search(self.query_one("#search", Input).value, immediate=True)
            self._request_render()

        def action_dismiss(self) -> None:
            if controller.state.autocomplete and not controller.state.autocomplete_hidden:
                controller.dismiss_autocomplete()
            self._request_render()

        def action_quit(self) -> None:
            if controller.state.autocomplete and not controller.state.autocomplete_hidden:
                controller.dismiss_autocomplete()
                self._request_render()
                return
            self.exit()

        def _render_state(self) -> None:
            if not self._ui_ready:
                return
            try:
                search = self.query_one("#search", Input)
                if search.value != controller.state.raw_query:
                    search.value = controller.state.raw_query
                self.query_one("#autocomplete", Static).update(build_autocomplete_text(controller.state))
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
                self.query_one("#preview", Static).update(preview)
                self.query_one("#status", Label).update(
                    build_status_text(controller.state, roots=config.roots, has_index=controller.state.has_index)
                )
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
                            Static(row_text),
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
                results_view.append(ListItem(Static(empty_text)))

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "search":
                self.action_submit()

        def on_input_changed(self, event: Input.Changed) -> None:
            if event.input.id == "search":
                self._schedule_search(event.value, immediate=False)
                self._request_render()

        def on_key(self, event: Key) -> None:
            if event.key == "/":
                self.action_focus_search()
                event.stop()
            elif event.key == "ctrl+r":
                self.action_refresh_index()
                event.stop()
            elif event.key == "escape":
                self.action_dismiss()
                event.stop()
            elif event.key == "tab":
                if controller.state.autocomplete:
                    value = controller.accept_autocomplete()
                    self.query_one("#search", Input).value = value
                    self._schedule_search(value, immediate=True)
                    self._request_render()
                    event.stop()
            elif event.key == "enter":
                self.action_submit()
                event.stop()
            elif event.key == "up":
                self.action_cursor_up()
                event.stop()
            elif event.key == "down":
                self.action_cursor_down()
                event.stop()
            elif event.key == "q":
                self.action_quit()
                event.stop()
            elif event.key == "ctrl+c":
                self.exit()
                event.stop()

        def _schedule_search(self, query: str, *, immediate: bool) -> None:
            controller.update_query(query)
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
            self._pending_query = query
            if self._search_debounce_timer is not None:
                self._search_debounce_timer.stop()
                self._search_debounce_timer = None
            if immediate:
                self._start_search_worker(query, request.request_id)
                return
            self._search_debounce_timer = self.set_timer(
                self._DEBOUNCE_SECONDS,
                lambda: self._start_search_worker(self._pending_query, controller._active_request_id),
            )

        def _start_search_worker(self, query: str, request_id: int) -> None:
            self.run_worker(self._run_search(query, request_id), name=f"search:{request_id}", thread=False)

        async def _run_search(self, query: str, request_id: int) -> None:
            db_path = controller.db_path
            if db_path is None:
                self._apply_search_outcome(
                    self._SearchOutcome(
                        request_id=request_id,
                        query=query,
                        query_error="No index database configured.",
                    )
                )
                return

            def _execute() -> SiftApp._SearchOutcome:
                try:
                    results = search_files(db_path, query)
                except ValueError as exc:
                    return self._SearchOutcome(request_id=request_id, query=query, query_error=str(exc))
                except Exception as exc:
                    return self._SearchOutcome(request_id=request_id, query=query, search_error=str(exc))
                return self._SearchOutcome(request_id=request_id, query=query, results=tuple(results))

            outcome = await asyncio.to_thread(_execute)
            self._apply_search_outcome(outcome)

        def _apply_search_outcome(self, outcome: _SearchOutcome) -> None:
            if outcome.request_id != controller._active_request_id:
                return
            if outcome.query_error is not None:
                controller.set_query_error(outcome.query_error)
            elif outcome.search_error is not None:
                controller.set_search_error(outcome.search_error)
            else:
                controller.complete_search(outcome.request_id, list(outcome.results))
            self._request_render()

        async def _run_index_refresh(self) -> None:
            def _refresh() -> SiftApp._IndexOutcome:
                try:
                    stats = self._indexing_service.refresh(
                        roots=config.roots,
                        active_db_path=config.active_db_path,
                        staging_db_path=config.staging_db_path,
                        ignore_dirs=config.ignore_dirs,
                        max_extracted_file_size=config.max_extracted_file_size,
                    )
                except Exception as exc:
                    return self._IndexOutcome(error=str(exc))
                if stats is None:
                    return self._IndexOutcome(error="An indexing job is already running.")
                return self._IndexOutcome(stats=stats)

            outcome = await asyncio.to_thread(_refresh)
            self._apply_index_outcome(outcome)

        def _apply_index_outcome(self, outcome: _IndexOutcome) -> None:
            if outcome.error is not None:
                controller.set_indexing_error(outcome.error)
            elif outcome.stats is not None:
                controller.refresh_fuzzy_index(config.active_db_path)
                controller.set_indexing_success(files_indexed=outcome.stats.files_indexed)
            else:
                controller.finish_indexing()
            self._request_render()

    SiftApp().run()
