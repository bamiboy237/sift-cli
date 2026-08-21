# Spec Trace Matrix (Phase 2-6)

## Phase 2 - Indexing

| Acceptance Criterion | Evidence |
|---|---|
| supported text files indexed with content | `tests/test_phase2.py::test_build_index_stores_metadata_and_text_content` |
| oversized/binary/unsupported metadata-only | `tests/test_phase2.py::test_build_index_keeps_oversized_unsupported_and_binary_files_metadata_only` |
| unreadable files do not crash | `tests/test_phase2.py::test_build_index_continues_when_extraction_fails` |
| deleted files absent after refresh | `tests/test_phase2.py::test_successful_rebuild_removes_deleted_files` |
| one indexing job at a time | `tests/test_phase2.py::test_indexing_service_rejects_overlapping_builds` |
| UI usable during indexing | `tests/test_phase5.py::test_search_completion_during_indexing_keeps_indexing_state`, manual checklist |

## Phase 3 - Parser and Search

| Acceptance Criterion | Evidence |
|---|---|
| free/scoped/mixed/filter-only parse correctly | `tests/test_phase3.py::ParserTests` |
| repeated `ext:` is OR | `tests/test_phase3.py::test_filter_only_search_returns_matches_without_full_text` |
| repeated date/size/path are AND | `tests/test_phase3.py::test_parse_query_separates_scopes_and_filters` |
| empty raw query -> help state | `tests/test_phase5.py::test_empty_query_exposes_help_state` |
| metadata-only query works without FTS | `tests/test_phase3.py::test_filter_only_search_returns_matches_without_full_text` |
| deterministic ranking | `tests/test_phase3.py::test_text_search_order_is_deterministic_on_unchanged_data` |

## Phase 4 - Fuzzy and Autocomplete

| Acceptance Criterion | Evidence |
|---|---|
| 1/2-3/4+ strategy paths | `tests/test_phase4.py::test_strategy_for_query_switches_by_length` |
| basename outranks deep matches | `tests/test_phase4.py::test_suggest_prefers_basename_over_directory_only_matches` |
| suggestions update non-blocking | `tests/test_phase5.py::test_autocomplete_precedence_is_explicit` |
| suggestions rebuild after publish | `tests/test_phase4.py::test_build_index_invokes_callback_after_successful_publish` |

## Phase 5 - Textual UI

| Acceptance Criterion | Evidence |
|---|---|
| app launches with input focused | manual checklist |
| keybindings behave as specified | `tests/test_phase7.py`, manual checklist |
| empty/loading/no-results/error states distinct | `tests/test_phase7.py::ScreenTextTests` |
| search usable during rebuild | `tests/test_integration_rebuild_search_availability.py` |

## Phase 6 - File Actions and Polish

| Acceptance Criterion | Evidence |
|---|---|
| selected file opens via host default | `tests/test_phase6.py::test_open_file_uses_platform_default_command`, manual checklist |
| failures are non-fatal | `tests/test_phase6.py::test_open_selected_result_reports_missing_file_non_fatally` |
| snippets display for content matches | `tests/test_phase3.py::test_text_search_returns_snippet_for_content_matches` |
| app remains local/offline | architecture and dependencies, no network code paths |
