# Manual TUI Race Handling Checklist

## Scope

Validate query/result race handling and rebuild-search coexistence.

## Environment

- Platform: ____________________
- Terminal: ____________________
- Date: ____________________
- Commit/branch: ____________________

## Preconditions

- Completed index exists with multiple searchable files.
- At least one query returns many results.

## Checklist

| Step | Action | Expected Behavior | Pass/Fail | Notes |
|---|---|---|---|---|
| 1 | Type rapidly: `a` -> `al` -> `alp` -> `alpha` | Final visible results correspond to latest query only |  |  |
| 2 | Pause typing after rapid changes | No stale older-result flash replaces latest results |  |  |
| 3 | Trigger `Ctrl-R` rebuild | Indexing starts; UI remains interactive |  |  |
| 4 | While indexing, run several searches | Results continue from last completed index |  |  |
| 5 | While indexing, press `Ctrl-R` again | Non-fatal "already running" status |  |  |
| 6 | During rebuild, move between input/autocomplete/results | Focus behavior remains deterministic |  |  |
| 7 | Force rebuild failure scenario (unreadable/missing path) | Indexing error is non-fatal; prior index remains usable |  |  |
| 8 | Re-run successful rebuild | Results/suggestions update only after publish |  |  |

## Evidence Capture

- Timestamped notes for each observed race-sensitive behavior.
- Optional terminal recording for rapid-query and rebuild overlap scenarios.

## Sign-off

- Reviewer: ____________________
- Result: ____________________
- Follow-up issues: ____________________
