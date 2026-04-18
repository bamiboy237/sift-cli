# sift-cli

```
┌──────────────────────────────────────────────┐
│ sift-cli                                     │
│ local, offline, keyboard-first file search   │
└──────────────────────────────────────────────┘
```

` s i f t - c l i` indexes user-selected local folders into SQLite, then searches them in a
persistent terminal UI.

## Flow

1. Choose allowed root folders in `~/.config/sift/config.toml`.
2. Add ignored directories in the same file under `ignore_dirs`.
3. The indexer walks only allowed roots and skips ignored paths.
4. File metadata and extracted text content land in SQLite.
5. Search reads the last completed index, so the UI stays responsive.
6. Rebuilds run in the background without blocking search.
7. Results are ranked, filtered, previewed, and opened from the terminal.

## Search

- filename
- content
- both
- filters:
  - `ext:md`
  - `path:notes`
  - `after:2024-01-01`
  - `before:2024-02-01`
  - size comparisons
- autocomplete for filenames and paths

## Config

- defaults live in `~/.config/sift/config.toml`
- `roots` sets the allowed index scope
- `ignore_dirs` excludes traversal targets
- if no config exists, sift-cli falls back to common home folders
- default ignores: `.git`, `node_modules`, `dist`, `build`, `__pycache__`, `.cache`, `.npm`, `.uv`

## UI

- Textual TUI
- keyboard-first navigation
- live query updates
- result previews
- index status and refresh controls

## Storage

- SQLite for persistence
- FTS5 for text search
- staged rebuilds keep the active index stable

## Keys

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

## Constraints

- local only
- offline only
- no cloud
- no daemon
- no semantic search