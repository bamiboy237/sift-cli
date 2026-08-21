"""Textual app shell."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from rich.text import Text

from .fuzzy_index import load_fuzzy_index
from .indexer import IndexingService
from .messages import (
    IndexBuildAlreadyRunning,
    IndexBuildFailed,
    IndexBuildSucceeded,
    SearchCompletedWithResults,
    SearchFailed,
    SearchQueryFailed,
)
from .search import search_files
from .ui import (
    LaunchConfig,
    SearchController,
    build_autocomplete_text,
    build_query_banner_text,
    build_result_row_text,
    build_results_text,
    build_sidebar_text,
    build_status_text,
    render_result_preview,
)


def launch_app(
    config: LaunchConfig, controller: SearchController | None = None
) -> None:
    controller = controller or SearchController(db_path=config.db_path)
    app_cls = build_sift_app(config, controller)
    app = app_cls()
    app.run()


def build_sift_app(config: LaunchConfig, controller: SearchController):
    """Construct the Textual app class. Separated from launch_app so tests
    can drive the real app headlessly."""

    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.events import Resize
        from textual.widget import MountError
        from textual.widgets import (
            Footer,
            Header,
            Input,
            Label,
            ListItem,
            ListView,
            Static,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError("textual is required to run the UI") from exc

    class SiftApp(App):
        CSS = """
        Screen {
            layout: vertical;
            background: #090a0f;
            color: #f0f4fc;
        }

        #content {
            height: 1fr;
            min-height: 0;
            padding: 0 1;
            overflow: hidden;
            background: #090a0f;
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
            border: solid #1c2030;
            padding: 0 1;
            background: #0d0e16;
            color: #8b95a5;
            overflow-y: auto;
            overflow-x: hidden;
        }

        #main {
            width: 1fr;
            min-height: 0;
            overflow: hidden;
        }

        #banner {
            border: solid #1c2030;
            padding: 0 1;
            margin: 0 0 1 0;
            background: #0d0e16;
            color: #8b95a5;
        }

        #search {
            margin: 0 0 1 0;
            border: solid #262d42;
            padding: 0 1;
            background: #10121c;
            color: #ffffff;
        }

        #search:focus {
            border: solid #3875f6;
        }

        #results-shell {
            height: 1fr;
            min-height: 0;
            border: solid #1c2030;
            padding: 0 1;
            background: #090a0f;
            overflow: hidden;
        }

        #results {
            height: 1fr;
            width: 3fr;
            min-height: 0;
            background: transparent;
        }

        #preview {
            width: 2fr;
            height: 1fr;
            min-height: 0;
            min-width: 32;
            border: solid #1c2030;
            padding: 0 1;
            margin-left: 1;
            background: #0c0d14;
            color: #b4bccb;
            overflow-y: auto;
            overflow-x: hidden;
        }

        #autocomplete {
            height: auto;
            max-height: 8;
            margin: 0 0 1 0;
            border: solid #3875f6;
            padding: 0 1;
            background: #121522;
            color: #f0f4fc;
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
            color: #8b95a5;
            padding: 0 1;
            background: #0d0e16;
        }

        #spinner {
            width: 3;
            margin-right: 1;
            color: #7aa2f7;
        }

        #status-line {
            height: 1;
            min-height: 1;
            background: #0d0e16;
            border-top: solid #181b26;
            padding: 0 1;
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
            border: solid #181b26;
            padding: 0 1;
            background: #0d0f18;
        }

        ListItem:hover {
            background: #101322;
        }

        ListItem.selected {
            background: #141724;
            border: solid #2a334c;
            border-left: tall #3875f6;
        }

        Static {
            color: #c0c6d4;
        }

        Input {
            background: transparent;
        }

        .muted {
            color: #5b6477;
        }

        .title {
            text-style: bold;
            color: #ffffff;
        }

        Header {
            background: #0d0e16;
            color: #ffffff;
        }

        Footer {
            background: #0d0e16;
            color: #8b95a5;
        }

        Footer > .footer--key {
            background: #181c2c;
            color: #7aa2f7;
        }

        Footer > .footer--highlight {
            background: #3875f6;
            color: #ffffff;
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

        _DEBOUNCE_SECONDS = 0.08

        def __init__(self) -> None:
            super().__init__()
            self._indexing_service = IndexingService()
            self._search_debounce_timer = None
            self._search_workers: dict[int, Any] = {}
            self._ui_ready = False
            self._render_pending = False
            self._last_results_render_key: tuple | None = None
            self._layout_mode: LayoutMode | None = None
            self._autocomplete_visible = False
            self._result_items: list = []
            self._rendered_selected_index: int | None = None
            self._fuzzy_load_seq = 0

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with Vertical(id="content"):
                with Horizontal(id="top"):
                    yield Static("", id="sidebar")
                    with Vertical(id="main"):
                        yield Static("", id="banner")
                        yield Input(
                            placeholder="Search files…", id="search", name="search"
                        )
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
            self._load_fuzzy_index_async(config.active_db_path)
            if config.auto_start_indexing:
                self.call_after_refresh(self.action_refresh_index)

        def _load_fuzzy_index_async(self, db_path: Path) -> None:
            """Build the trigram index in a worker; install it when done."""

            self._fuzzy_load_seq += 1
            load_seq = self._fuzzy_load_seq

            async def _run():
                index = await asyncio.to_thread(load_fuzzy_index, db_path)
                if load_seq == self._fuzzy_load_seq:
                    controller.install_fuzzy_index(index, db_path)
                    # If the user already typed while the index was building,
                    # refresh suggestions for the in-progress query.
                    search_input = self.query_one("#search", Input)
                    if search_input.value.strip():
                        controller.update_query(
                            search_input.value,
                            cursor=search_input.cursor_position,
                        )
                    self._request_render()

            self.run_worker(_run(), name="fuzzy-index-load", thread=False)

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
            self.run_worker(
                self._run_index_refresh(), name="index-refresh", thread=False
            )
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
            if (
                controller.precedence() == "autocomplete"
                and controller.state.autocomplete
                and not controller.state.autocomplete_hidden
            ):
                search_input = self.query_one("#search", Input)
                value, cursor = controller.accept_autocomplete_with_cursor(
                    search_input.cursor_position
                )
                self.query_one("#search", Input).value = value
                self.query_one("#search", Input).cursor_position = cursor
                self._schedule_search(value, immediate=True)
            elif controller.state.results:
                controller.open_selected_result()
            else:
                self._schedule_search(
                    self.query_one("#search", Input).value, immediate=True
                )
            self._request_render()

        def action_dismiss(self) -> None:
            if controller.dismiss_transient():
                self._request_render()
                return
            if (
                controller.state.autocomplete
                and not controller.state.autocomplete_hidden
            ):
                controller.dismiss_autocomplete()
            self._request_render()

        def action_request_quit(self) -> None:
            if (
                controller.state.autocomplete
                and not controller.state.autocomplete_hidden
            ):
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
            value, cursor = controller.accept_autocomplete_with_cursor(
                search_input.cursor_position
            )
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
                autocomplete_widget.update(
                    _styled_text(autocomplete_text) if autocomplete_text else ""
                )
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
                    build_sidebar_text(
                        controller.state,
                        roots=config.roots,
                        has_index=controller.state.has_index,
                    )
                )
                self.query_one("#banner", Static).update(
                    build_query_banner_text(
                        controller.state, has_index=controller.state.has_index
                    )
                )
                self._render_results_list()
                preview = (
                    render_result_preview(controller.active_result)
                    if controller.active_result is not None
                    else "Preview\nNo result selected."
                )
                self.query_one("#preview", Static).update(_styled_text(preview))
                self.query_one("#status", Label).update(
                    build_status_text(
                        controller.state,
                        roots=config.roots,
                        has_index=controller.state.has_index,
                    )
                )
                spinner = self.query_one("#spinner", Label)
                spinner.update(
                    "[*]"
                    if controller.state.indexing or controller.state.loading
                    else ""
                )
            except MountError:
                self._request_render()

        def _render_results_list(self) -> None:
            results_view = self.query_one("#results", ListView)
            state = controller.state
            if state.results:
                # Selection is intentionally excluded: moving it only rewrites
                # the two affected rows instead of rebuilding every ListItem.
                render_key = ("results", state.results)
            else:
                render_key = (
                    "empty",
                    state.raw_query,
                    state.loading,
                    state.mode,
                    state.has_index,
                )

            if render_key != self._last_results_render_key:
                self._last_results_render_key = render_key
                results_view.clear()
                self._result_items = []
                if state.results:
                    total = len(state.results)
                    for index, result in enumerate(state.results):
                        row_text = build_result_row_text(
                            result,
                            selected=index == state.selected_index,
                            index=index,
                            total=total,
                        )
                        item = ListItem(
                            Static(_styled_text(row_text)),
                            classes="selected"
                            if index == state.selected_index
                            else None,
                        )
                        self._result_items.append(item)
                        results_view.append(item)
                    results_view.index = state.selected_index
                else:
                    empty_text = build_results_text(
                        state,
                        roots=config.roots,
                        has_index=state.has_index,
                    )
                    results_view.append(ListItem(Static(_styled_text(empty_text))))
                self._rendered_selected_index = (
                    state.selected_index if state.results else None
                )
                return

            if state.results and self._rendered_selected_index != state.selected_index:
                self._sync_result_selection(state)

        def _sync_result_selection(self, state) -> None:
            """Rewrite only the previously and newly selected rows."""

            total = len(state.results)
            old_index = self._rendered_selected_index
            new_index = max(0, min(state.selected_index, total - 1))
            for changed in {old_index, new_index}:
                if changed is None or changed < 0 or changed >= total:
                    continue
                item = self._result_items[changed]
                item.set_classes(
                    "selected" if changed == new_index else ""
                )
                item.query_one(Static).update(
                    _styled_text(
                        build_result_row_text(
                            state.results[changed],
                            selected=changed == new_index,
                            index=changed,
                            total=total,
                        )
                    )
                )
            self._rendered_selected_index = new_index
            results_view = self.query_one("#results", ListView)
            results_view.index = new_index

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "search":
                self.action_submit()

        def on_input_changed(self, event: Input.Changed) -> None:
            if event.input.id == "search":
                self._schedule_search(event.value, immediate=False)
                self._request_render()

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            controller.open_selected_result()
            self._request_render()

        def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
            if event.item and event.list_view.index is not None:
                if controller.state.results and 0 <= event.list_view.index < len(controller.state.results):
                    if controller.state.selected_index != event.list_view.index:
                        controller.move_result_selection(event.list_view.index - controller.state.selected_index)
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
                lambda q=query, request_id=request.request_id: (
                    self._start_search_worker(q, request_id)
                ),
            )

        def _start_search_worker(self, query: str, request_id: int) -> None:
            # Cancel superseded searches instead of letting them run to
            # completion; request-id gating already discards their results.
            for worker_id in list(self._search_workers):
                worker = self._search_workers.pop(worker_id)
                worker.cancel()
            worker = self.run_worker(
                self._run_search(query, request_id),
                name=f"search:{request_id}",
                thread=False,
            )
            self._search_workers[request_id] = worker

        async def _run_search(self, query: str, request_id: int) -> None:
            db_path = controller.db_path
            if db_path is None:
                self._apply_search_outcome(
                    SearchQueryFailed(
                        request_id=request_id,
                        query=query,
                        error="No index database configured.",
                    )
                )
                return

            def _execute() -> (
                SearchCompletedWithResults | SearchQueryFailed | SearchFailed
            ):
                try:
                    results = search_files(db_path, query)
                except ValueError as exc:
                    return SearchQueryFailed(
                        request_id=request_id, query=query, error=str(exc)
                    )
                except Exception as exc:
                    return SearchFailed(request_id=request_id, error=str(exc))
                return SearchCompletedWithResults(
                    request_id=request_id, query=query, results=tuple(results)
                )

            outcome = await asyncio.to_thread(_execute)
            self._apply_search_outcome(outcome)

        def _apply_search_outcome(
            self, outcome: SearchCompletedWithResults | SearchQueryFailed | SearchFailed
        ) -> None:
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
            def _refresh() -> (
                IndexBuildSucceeded | IndexBuildFailed | IndexBuildAlreadyRunning
            ):
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

        def _apply_index_outcome(
            self,
            outcome: IndexBuildSucceeded | IndexBuildFailed | IndexBuildAlreadyRunning,
        ) -> None:
            if isinstance(outcome, IndexBuildAlreadyRunning):
                controller.set_indexing_already_running()
                self._request_render()
                return
            if isinstance(outcome, IndexBuildFailed):
                controller.set_indexing_error(outcome.error)
            elif isinstance(outcome, IndexBuildSucceeded):
                self._load_fuzzy_index_async(config.active_db_path)
                controller.set_indexing_success(
                    files_indexed=outcome.files_indexed,
                    files_skipped=outcome.files_skipped,
                )
            else:
                controller.finish_indexing()
            self._request_render()

    return SiftApp


def _append_delimited(rendered: Text, text: str, default_style: str = "") -> None:
    i = 0
    while i < len(text):
        start = text.find("\x1f", i)
        if start == -1:
            rendered.append(text[i:], style=default_style or None)
            break
        if start > i:
            rendered.append(text[i:start], style=default_style or None)
        end = text.find("\x1e", start + 1)
        if end == -1:
            rendered.append(text[start:], style=default_style or None)
            break
        rendered.append(text[start + 1 : end], style="bold #ffb454 on #2b2010")
        i = end + 1


def _styled_text(text: str) -> Text:
    rendered = Text()
    lines = text.split("\n")
    for line_idx, line in enumerate(lines):
        if line_idx > 0:
            rendered.append("\n")

        if line.startswith("SIFT CLI"):
            rendered.append("◆ ", style="bold #7aa2f7")
            rendered.append("SIFT CLI", style="bold #ffffff")
        elif line in ("Scope", "Index", "Query", "Keys", "Autocomplete"):
            rendered.append(f"• {line}", style="bold #7aa2f7")
        elif line.startswith("Query:"):
            rendered.append("Query: ", style="bold #7aa2f7")
            _append_delimited(rendered, line[len("Query:") :], default_style="#ffffff")
        elif line.startswith("> "):
            rendered.append("▶ ", style="bold #3875f6")
            _append_delimited(rendered, line[2:], default_style="bold #ffffff")
        elif line.startswith("  ") and (line.strip().startswith("~/") or line.strip().startswith("/")):
            rendered.append("  ", style="")
            rendered.append(line.strip(), style="#6e7991")
        elif line.startswith("─"):
            rendered.append(line, style="#262d42")
        elif "│" in line and len(line) >= 4 and line[:4].strip().isdigit():
            parts = line.split("│", 1)
            rendered.append(parts[0] + "│", style="#4e566d")
            _append_delimited(rendered, parts[1], default_style="#d8dee9")
        elif line.startswith("[Binary File") or line.startswith("[Cached Index"):
            rendered.append(line, style="bold #7aa2f7")
        else:
            _append_delimited(rendered, line)

    return rendered


LayoutMode = Literal["wide", "stacked", "compact"]


def _layout_mode_for_size(width: int, height: int) -> LayoutMode:
    if width >= 140 and height >= 38:
        return "wide"
    if width >= 105 and height >= 30:
        return "stacked"
    return "compact"
