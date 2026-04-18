# sift-cli

```
┌──────────────────────────────────────────────────────────┐
│ sift-cli                                                 │
│ local, offline, keyboard-first file search               │
└──────────────────────────────────────────────────────────┘

sift-cli indexes user-selected local folders into SQLite, then lets you search them from a
persistent terminal UI.

## How it works

1. You choose the allowed root folders in `~/.config/sift/config.toml`.
2. You also list ignore paths there for directories you do not want indexed.
3. sift-cli walks only those allowed roots, skipping ignored directories.
4. File metadata and extracted text content are stored in SQLite.
5. Search queries hit the last completed index, so the UI stays responsive.
6. A background rebuild can run without blocking searches.
7. Results are ranked, filtered, previewed, and opened from the terminal.

## Search model

- filename search
- content search
- combined search
- filters:
  - `ext:md`
  - `path:notes`
  - `after:2024-01-01`
  - `before:2024-02-01`
  - size comparisons
- autocomplete for likely filenames and paths

## Configuration

- set allowed roots in `~/.config/sift/config.toml`
- set ignored directories in the same file under `ignore_dirs`
- if no config exists, sift-cli falls back to common home folders
- indexing stays scoped to the allowed roots only
- ignored paths are skipped during traversal
- default ignores include `.git`, `node_modules`, `dist`, `build`, `__pycache__`, `.cache`, `.npm`, and `.uv`

## UI model

- Textual-based TUI
- keyboard-driven navigation
- live query updates
- result previews
- index status and refresh controls

## Storage

- SQLite for all data
- FTS5 for text search
- staged rebuilds to keep the active index stable

## Key bindings

- `/` focus search
- `↑` / `↓` move selection
- `Enter` open the selected file
- `Tab` accept autocomplete
- `Esc` dismiss transient UI
- `Ctrl+R` rebuild the index
- `q` quit

## Install

```bash
uv sync
uv run sift-cli
```

## Notes

- local only
- offline only
- no cloud
- no daemon
- no semantic search