# AGENTS.md

## Source of truth
- Treat `spec.md` as authoritative for product scope and acceptance behavior (especially UI focus/precedence, offline-only constraints, and indexing lifecycle).
- Keep V1 boundaries: local/offline only, no daemon watcher, no cloud/vector/semantic features.

## Environment and entrypoints
- Python version is pinned to `3.12` in `.python-version`.
- CLI entrypoint is `sift_cli.main:main` (`pyproject.toml` `[project.scripts]`).
- Repo root `main.py` is a thin wrapper around `sift_cli.main.main()`.
- Runtime paths are resolved in `sift_cli/db.py:resolve_runtime_paths`:
  - config: `~/.config/sift/config.toml` (or platform equivalent)
  - state dir: `~/.local/state/sift/` (or platform equivalent)
  - active DB: `index.db`, staging DB: `index.build.db`

## Commands that actually work here
- Run app from repo: `uv run python -m sift_cli.main`
- Run full tests: `uv run python -m unittest discover -s tests -q`
- Run a single test module: `uv run python -m unittest tests.test_phase5 -q`
- Lint: `uv run ruff check .`
- Typecheck: `uv run ty check .`

## Install behavior (easy to get wrong)
- `uv tool install .` is a snapshot install; code changes will NOT auto-appear in global `sift-cli`.
- For development, use editable install: `uv tool install --editable --reinstall .`.

## Architecture map (high-value files)
- `sift_cli/app.py`: Textual app shell, layout/CSS, keybindings, resize responsiveness, worker orchestration.
- `sift_cli/ui.py`: UI state model (`SearchState`) and controller logic (focus, precedence, status handling).
- `sift_cli/search.py`: parser-to-SQL behavior, FTS + metadata fallback, deterministic ordering.
- `sift_cli/indexer.py`: filesystem traversal, extraction, staging build, publish, single-job lock.
- `sift_cli/db.py`: schema, FTS triggers, runtime path resolution, atomic publish via `os.replace`.
- `sift_cli/messages.py`: worker/UI message contracts.

## UI/rendering constraints to preserve
- Autocomplete must not destabilize layout; it is visibility-toggled and height-bounded in `sift_cli/app.py`.
- Responsive modes are auto-selected from terminal size in `sift_cli/app.py` (`wide` / `stacked` / `compact`); preserve this when editing layout.
- `SearchController.precedence()` in `sift_cli/ui.py` is the interaction priority contract (overlay > autocomplete > results > input).
- Search highlight markers use control delimiters from `sift_cli/search.py` (`\x1f`, `\x1e`) and are rendered by `_styled_text` in `sift_cli/app.py`.

## Indexing/search invariants
- Search always reads active DB; rebuild writes staging DB then publishes.
- Only one indexing job at a time (`IndexingService` lock in `sift_cli/indexer.py`).
- Empty raw query returns help/empty state behavior (search layer returns no corpus dump).

## Testing and validation expectations
- Keep unit + integration coverage in `tests/` passing before handoff.
- If UI keybindings/focus/race behavior changes, update validation artifacts in:
  - `docs/validation/manual-tui-focus-keybindings-checklist.md`
  - `docs/validation/manual-tui-race-handling-checklist.md`
  - `docs/validation/spec-trace-matrix.md` when acceptance evidence changes.
