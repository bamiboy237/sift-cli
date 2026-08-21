# Manual TUI Focus and Keybinding Checklist

## Scope

Validate focus behavior, keybindings, and interaction precedence in the Textual UI.

## Environment

- Platform: ____________________
- Terminal: ____________________
- Date: ____________________
- Commit/branch: ____________________

## Preconditions

- `uv run python -m sift_cli.main` launches successfully.
- At least one configured root contains test files.
- Run once with no completed index and once with a completed index.

## Checklist

| Step | Action | Expected Behavior | Pass/Fail | Notes |
|---|---|---|---|---|
| 1 | Launch app | Search input is focused on launch |  |  |
| 2 | Press `/` from any state | Focus returns to input; cursor at end |  |  |
| 3 | With autocomplete visible, press `Down`/`Up` | Selection moves in autocomplete first |  |  |
| 4 | With autocomplete visible, press `Tab` | Active suggestion is accepted into active token |  |  |
| 5 | With autocomplete visible, press `Enter` | Active suggestion accepted (not file-open) |  |  |
| 6 | Press `Esc` with status message visible | Transient status is dismissed first |  |  |
| 7 | Press `Esc` with autocomplete visible | Autocomplete closes |  |  |
| 8 | With results visible and input focused, press `Down` | Focus moves to first result |  |  |
| 9 | In results list, press `Down`/`Up` | Selection moves by one row |  |  |
| 10 | In results at first row, press `Up` | Focus returns to input |  |  |
| 11 | In input with query, press `Enter` | Search executes; app remains responsive |  |  |
| 12 | In results, press `Enter` | Selected file opens with platform default app |  |  |
| 13 | Press `Ctrl-R` when idle | Rebuild starts |  |  |
| 14 | Press `Ctrl-R` while indexing | Non-fatal "already running" message appears |  |  |
| 15 | Press `q` with no transient states | App quits |  |  |
| 16 | Press `Ctrl-C` | Immediate quit |  |  |

## State Verification

- No index yet state includes roots and Ctrl-R hint.
- Rebuild with existing index states mention last completed index remains searchable.
- Query error and search error are visibly distinct.

## Sign-off

- Reviewer: ____________________
- Result: ____________________
- Follow-up issues: ____________________
