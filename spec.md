# sift-CLI — Master Specification

## 1. Project Title

**sift-CLI** — a local, offline, interactive-first file search TUI.

---

## 2. Product Definition

`sift-CLI` is a single-user terminal application for searching files inside a configured set of local directories. It indexes file metadata plus extracted text content for supported file types, then provides a fast interactive search interface with ranked results, autocomplete, snippets, and file actions.

The product is explicitly:

- local-first
- offline-only
- interactive-first
- keyboard-driven
- scoped to user-selected roots

It is not a system-wide search daemon, a cloud service, or an AI/semantic retrieval tool.

---

## 3. Goal

Build a local search tool that feels fast, calm, and dependable:

- the user launches it once into a persistent Textual session
- types queries interactively
- sees ranked results update without blocking the UI
- opens files directly from the terminal
- refreshes the local index on demand

The app must remain useful on ordinary developer and knowledge-worker folders without trying to index the whole filesystem.

---

## 4. Product Feel

The app should feel:

- immediate: search responds quickly while typing
- stable: indexing never freezes the UI
- legible: results are easy to scan and compare
- predictable: query operators and ranking rules are explicit
- disciplined: V1 solves local file search well without speculative features

The interface should feel closer to a focused terminal application than a one-shot shell command.

---

## 5. Core User Requirements

The user must be able to:

1. launch the app into a persistent terminal UI
2. search by filename
3. search by file content
4. search both at once
5. filter by extension, path, modified date, and file size
6. run filter-only queries without free text
7. get ranked results with snippets and metadata
8. navigate results entirely by keyboard
9. autocomplete likely filenames and paths while typing
10. refresh the index without losing UI responsiveness
11. keep searching against the last completed index while a rebuild runs
12. open the selected file in the platform default application
13. work fully offline with no cloud or external API dependency

---

## 6. Scope

### V1 — Included

- indexing of user-configured roots only
- SQLite storage with FTS5 for filename + content search
- Textual-based TUI as the primary and required UI framework
- reactive UI state and background workers
- metadata filters:
  - `ext`
  - `path`
  - `after`
  - `before`
  - `size`
- ranked results with deterministic tie-breakers
- content snippets
- trigram-based fuzzy filename/path index for autocomplete
- manual refresh / rebuild
- open selected file from the terminal
- configurable defaults for:
  - indexed roots
  - max extracted file size
  - ignored directories

### V1 — Explicitly Excluded

- semantic search
- vector search
- embeddings
- OCR
- daemonized filesystem watching
- whole-filesystem indexing
- network services
- cloud sync
- external APIs
- multi-user coordination
- remote filesystems as a product feature
- heavyweight document extraction beyond V1’s supported text formats

---

## 7. Tech Stack

| Layer | Choice | Role |
|---|---|---|
| Language | Python 3.12+ | Main implementation language |
| Package / env | `uv` | Dependency and environment management |
| UI | **Textual** | Primary TUI framework |
| Rendering | `rich` | Styled text, snippets, metadata formatting |
| Storage | `sqlite3` | Local database |
| Search | SQLite FTS5 | Full-text indexing and ranking |

### Runtime and storage conventions

V1 should use conventional per-user paths unless explicitly overridden by configuration:

- config file:
  - Linux/macOS: `~/.config/sift/config.toml`
  - Windows: platform-appropriate user config directory
- application state directory:
  - Linux/macOS: `~/.local/state/sift/`
  - Windows: platform-appropriate user state directory
- active database path:
  - `<state_dir>/index.db`
- staging database path:
  - `<state_dir>/index.build.db`

The implementation should create missing parent directories on startup as needed.

### Core framework decision

The UI framework choice is settled:

- **Textual is the primary and required V1 UI framework.**

This is normative, not optional.

---

## 8. Architecture

V1 has five core subsystems:

1. **Textual App**
   - application shell
   - layout
   - focus management
   - keybindings
   - reactive state
   - status and error display

2. **Search Engine**
   - query parsing
   - SQL / FTS query generation
   - ranking
   - snippets
   - metadata-only result retrieval

3. **Indexer**
   - directory traversal
   - path normalization
   - metadata extraction
   - content extraction
   - database writes
   - staged rebuild publication

4. **Fuzzy Filename Index**
   - in-memory trigram index built from the last completed database
   - autocomplete suggestions for filenames and paths

5. **Platform Actions**
   - open selected file
   - reveal parent directory where applicable
   - copy/display full path

### Runtime model

- The UI runs continuously in the foreground.
- Search reads from the **last completed active index**.
- Indexing runs in the background.
- A new index is only published after a successful rebuild.
- At most **one indexing job** may run at a time.

### Textual worker and message contract

The app should use a small, explicit event contract between background work and the main UI thread.

Recommended worker lifecycle states:

- idle
- running
- succeeded
- failed

Recommended internal messages/events:

- `IndexBuildStarted`
- `IndexBuildProgress`
- `IndexBuildSucceeded`
- `IndexBuildFailed`
- `IndexPublished`
- `SearchRequested`
- `SearchCompleted`
- `SearchFailed`

Minimum behavioral requirements:

- worker-thread code must not mutate UI state directly
- UI state changes should be applied on the main thread only
- background index progress updates must be safe to ignore if the UI is busy
- stale search results must not overwrite newer query results after a later search completes

---

## 9. Data Model and Storage

### 9.1 Database schema

The core schema must use a `files` table plus an external-content FTS5 table.

```sql
CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY,
    path         TEXT UNIQUE NOT NULL,
    filename     TEXT NOT NULL,
    ext          TEXT,
    content      TEXT,
    size         INTEGER NOT NULL,
    created_at   REAL,
    modified_at  REAL NOT NULL,
    indexed_at   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_ext ON files(ext);
CREATE INDEX IF NOT EXISTS idx_files_modified_at ON files(modified_at);
CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);
CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    filename,
    content,
    content='files',
    content_rowid='id',
    tokenize='porter unicode61',
    prefix='2 3'
);

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, filename, content)
    VALUES (new.id, new.filename, new.content);
END;

CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, filename, content)
    VALUES ('delete', old.id, old.filename, old.content);
END;

CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, filename, content)
    VALUES ('delete', old.id, old.filename, old.content);
    INSERT INTO files_fts(rowid, filename, content)
    VALUES (new.id, new.filename, new.content);
END;
```

### 9.2 Column semantics

- `path`
  - canonical stored path string
  - unique within the database
  - absolute path only
- `filename`
  - basename of `path`
- `ext`
  - lowercase extension without the leading dot
  - examples: `md`, `py`, `json`
  - `NULL` if the file has no extension
- `content`
  - extracted text content
  - `NULL` for unsupported, oversized, binary, unreadable, or metadata-only files
- `size`
  - byte size from filesystem metadata
- `created_at`
  - filesystem creation/birth time when available
  - otherwise `NULL`
- `modified_at`
  - filesystem modified time
- `indexed_at`
  - UTC Unix timestamp in seconds for the indexing job that most recently wrote the row

### 9.3 Path normalization rules

These rules are normative and must be applied before insert, comparison, or deduplication:

1. Expand user paths and configured roots to absolute paths.
2. Normalize `.` and `..` segments.
3. Store path strings using forward slashes for deterministic storage and display.
4. Do not store trailing slashes for files.
5. Preserve the filesystem’s visible case for display.
6. Use casefolded comparisons in application logic for:
   - `path:` filters
   - fuzzy autocomplete matching
   - duplicate protection on case-insensitive platforms where needed

### 9.4 Timestamp semantics

- All stored timestamps are UTC Unix epoch seconds as `REAL`.
- Filtering with `after:` and `before:` applies to `modified_at`.
- UI rendering may display local timezone formatting, but storage and comparisons remain UTC-based.

### 9.5 Active index and staged index

The app should maintain:

- an **active database** used for search
- a **staging database** used for rebuilds

A staged rebuild is published only after the rebuild succeeds. Until then, the active database remains searchable.

This is the preferred V1 lifecycle because it keeps the UI responsive and avoids exposing partial indexes.

### 9.6 Canonical in-memory models

The implementation should use explicit typed models for the core runtime contracts.

Recommended query model:

- `ParsedQuery`
  - `raw: str`
  - `text_terms: list[str]`
  - `phrases: list[str]`
  - `filename_terms: list[str]`
  - `content_terms: list[str]`
  - `exts: list[str]`
  - `path_terms: list[str]`
  - `after: float | None`
  - `before: float | None`
  - `size_min: int | None`
  - `size_max: int | None`

Recommended result model:

- `SearchResult`
  - `path: str`
  - `filename: str`
  - `ext: str | None`
  - `size: int`
  - `modified_at: float`
  - `snippet: str | None`
  - `matched_filename: bool`
  - `matched_content: bool`
  - `score: float | None`

These models do not need to be stored verbatim in the database, but they should define the internal contract between parser, search, and UI layers.

---

## 10. Indexing Rules and Lifecycle

### 10.1 Indexed roots

Only configured roots are indexed.

Default roots may include:

- `~/Documents`
- `~/Desktop`
- `~/Downloads`
- `~/Projects`

These defaults must be configurable.

### 10.2 Default ignored directories

The default ignore set must be configurable and should include at least:

- `.git`
- `node_modules`
- `dist`
- `build`
- `__pycache__`
- `.cache`
- `.npm`
- `.uv`

Hidden directories may be skipped by default unless the user explicitly configures otherwise.

### 10.3 File eligibility

The indexer must consider only regular files under configured roots that are not excluded by ignore rules.

### 10.4 Extraction policy

V1 extraction behavior must be explicit and predictable:

1. **Always store metadata** for traversed eligible files.
2. **Attempt content extraction only if all are true:**
   - the file extension is in the supported text allowlist
   - the file size is less than or equal to the configured maximum
   - the file appears to be text, not binary
3. A file is treated as binary for V1 if:
   - it is outside the supported text allowlist, or
   - a quick byte inspection detects NUL bytes in the sampled prefix, or
   - decoding fails in a way the extractor does not support
4. For supported text files:
   - read bytes
   - attempt UTF-8 decode
   - if strict UTF-8 decode fails, decode with UTF-8 replacement behavior
   - store the resulting text
5. If extraction fails after the file is discovered:
   - store metadata
   - set `content = NULL`
   - record the failure in job diagnostics / counters
6. Oversized files are metadata-only:
   - store metadata
   - set `content = NULL`

### 10.5 Supported content types in V1

V1 content indexing should support a conservative text allowlist such as:

- `txt`
- `md`
- `py`
- `js`
- `ts`
- `json`
- `csv`
- `html`
- `css`
- `java`
- `log`
- `yaml`
- `yml`
- `toml`
- `ini`
- `sh`
- `rs`
- `go`

This list may be configurable, but V1 should stay conservative.

### 10.6 Refresh and rebuild lifecycle

V1 indexing semantics:

1. On startup, load the last completed active index if present.
2. If the user triggers refresh, start one background indexing job.
3. If an indexing job is already running:
   - do not start a second one
   - surface a status message instead
4. While indexing runs:
   - the UI remains responsive
   - searches continue against the last completed active index
5. On successful rebuild:
   - atomically publish the staging database as the new active database
   - rebuild the in-memory fuzzy filename index from the new active database
6. On failed rebuild:
   - keep the previous active database
   - surface an error state and retain the last good index

### 10.7 Stale-row deletion semantics

The required product behavior is:

- after a successful refresh, the published index must not contain rows for files that were deleted, moved away, or are no longer eligible under the configured roots at scan completion time

For a staged full rebuild, this happens naturally because only currently discovered files are inserted into the staging database.

If an implementation later adds in-place root-scoped refreshes, the stale-row rule is:

- after a successful scan of a root, delete rows under that scanned root where `indexed_at < scan_started_at`

Stale deletion must never run after a failed or partial refresh in a way that would drop good data from the last completed index.

### 10.8 Missing and unreadable files

The indexer must handle filesystem races safely:

- if a file disappears before stat or read completes, skip it and count it as transiently missing
- if a file cannot be read due to permissions or decode/extraction issues, keep metadata if available and set `content = NULL`
- these conditions must not crash the app or abort the entire indexing job by default

### 10.9 Symlink policy

V1 should keep symlink behavior simple and predictable:

- do not follow directory symlinks by default
- file symlinks may be skipped entirely in V1 unless explicitly supported later
- avoid cycles and duplicate indexing caused by symlink traversal

---

## 11. Search Semantics and Ranking

### 11.1 Search modes

The search engine supports:

- combined filename + content search
- filename-only search
- content-only search
- metadata-only filtered listing

### 11.2 Text query behavior

- Unquoted free-text terms are combined as logical AND.
- Quoted strings are phrase matches.
- Field-scoped terms apply only to the immediately following token or quoted phrase.
- Unknown operator-like text should fall back to free text rather than hard-failing.

### 11.3 Metadata-only queries

Queries containing only metadata filters and no free text are valid.

Examples:

- `ext:md after:2024-01-01`
- `path:notes size<=1mb`
- `before:2024-03-01 ext:txt ext:md`

For metadata-only queries:

- do not require an FTS `MATCH`
- return filtered rows directly from `files`
- order results by:
  1. `modified_at DESC`
  2. `filename ASC`
  3. `path ASC`

### 11.4 Ranking policy for text queries

Ranking must be explicit and deterministic.

#### Base relevance

Use weighted FTS relevance with filename weighted more heavily than content.

Normative policy:

- `filename` column weight: `8.0`
- `content` column weight: `1.0`

This may be implemented with SQLite FTS5 `bm25(files_fts, 8.0, 1.0)` or an equivalent weighted FTS score.

#### Required boosts

After base FTS relevance, apply these logical boosts:

1. **Filename boost**
   - boost when the normalized free-text query appears in the basename
   - stronger boost for exact basename match or basename prefix match

2. **Both-fields boost**
   - boost when the query matched both:
     - filename
     - content

#### Deterministic ordering

For text queries, final ordering must be deterministic:

1. weighted FTS relevance
2. filename boost
3. both-fields boost
4. `modified_at DESC`
5. shorter `filename`
6. `path ASC`

The exact implementation may compute one final score or layered SQL/application ordering, but the result ordering must reflect the above priorities consistently.

### 11.5 Search qualification rules

For text queries:

- a result qualifies if it matches the effective query in:
  - `filename`, or
  - `content`, or
  - both

For field-scoped terms:

- `filename:` terms only constrain `filename`
- `content:` terms only constrain `content`

If both field-scoped and unscoped terms are present, all must be satisfied according to their scopes.

### 11.6 Search execution plan

The implementation should separate query handling into distinct steps:

1. parse the raw query into a `ParsedQuery`
2. classify the request as:
   - text query
   - filter-only query
   - empty/help-state query
3. build SQL predicates for metadata filters
4. build FTS clauses only when text search is required
5. execute the narrowest query plan needed
6. map rows into `SearchResult` values
7. apply any final deterministic application-side ordering only if SQL ordering alone is insufficient

Execution requirements:

- filter-only queries must not force FTS participation
- empty/help-state queries must not issue a “return the whole corpus” search
- search execution for an older query string must not replace visible results for a newer query string
- query parsing errors and search execution errors must remain distinguishable in the UI

### 11.7 Invalid query handling

The parser and search layer must fail gracefully:

- malformed filters should degrade to free text when safe
- malformed size/date values should surface a non-fatal UI error or validation message
- invalid FTS syntax generated from user input must not crash the app
- prior valid results may remain visible while the error state is shown

### 11.8 Snippet behavior

- If content matched, return a content snippet with highlighted terms.
- If only filename matched, snippet may be empty or replaced by a filename-match indicator.
- Snippets must never block result rendering if unavailable.

### 11.9 Result set limits

V1 should limit visible search results to a practical page/window size, such as 20–50 rows, while allowing scrolling or paging within the UI.

---

## 12. Query Grammar and Parsing Rules

### 12.1 Supported operators

The parser must support:

- free text: `transcript`
- quoted phrases: `"auth bug"`
- filename-scoped term or phrase:
  - `filename:resume`
  - `filename:"quarterly plan"`
- content-scoped term or phrase:
  - `content:error`
  - `content:"auth bug"`
- extension filter:
  - `ext:md`
  - `ext:.md`
- path filter:
  - `path:notes`
  - `path:"/projects/client-a"`
- date filters:
  - `after:2024-01-01`
  - `before:2024-03-31`
- size filters:
  - `size<1mb`
  - `size<=1mb`
  - `size>10kb`
  - `size>=500`
  - `size=0`

### 12.2 Grammar rules

The grammar is intentionally small and rule-based.

Conceptually:

- query = zero or more clauses
- clause = free-text clause | field clause | metadata filter
- field clause = `filename:` or `content:` followed by one token or one quoted phrase
- metadata filter = `ext:` | `path:` | `after:` | `before:` | size comparator

### 12.3 Parsing rules

1. Operators are case-insensitive.
2. `ext:` values are normalized to lowercase without a leading dot.
3. `filename:` and `content:` are search-field operators, not metadata filters.
4. Free-text remainder becomes the general text query.
5. If a token looks like an operator but is malformed or unsupported, treat it as free text unless doing so would be ambiguous and unsafe.
6. An empty raw query with no filters returns the empty/help state, not the full corpus.

### 12.4 Repeated filter semantics

These rules are normative:

- repeated `ext:` filters are combined with **OR**
  - `ext:md ext:txt` means extension is `md` OR `txt`
- repeated `path:` filters are combined with **AND**
  - each path token must match the normalized stored path
- repeated `after:` filters are combined with **AND**
  - effective lower bound is the latest parsed `after`
- repeated `before:` filters are combined with **AND**
  - effective upper bound is the earliest parsed `before`
- repeated size constraints are combined with **AND**
  - example: `size>=10kb size<=1mb`

### 12.5 Path filter semantics

`path:` matches the normalized stored path using casefolded substring matching in V1.

Examples:

- `path:notes` matches paths containing `notes`
- `path:"/projects/client-a"` matches paths containing that normalized segment string

### 12.6 Natural-language date phrases

V1 supports only lightweight, explicit date phrases. Supported examples may include:

- `today`
- `yesterday`
- `this week`
- `last 7 days`
- `from march`
- `from march 2024`

Rules:

- these phrases map to `after` / `before` bounds
- if the parser cannot confidently interpret the phrase, it must fall back to free text
- no AI or probabilistic language understanding is used in V1

### 12.7 Query examples

Free text:

- `transcript`
- `"auth bug"`
- `budget review`

Field-scoped:

- `filename:resume`
- `content:"auth bug"`
- `filename:report content:"quarterly plan"`

Mixed text + filters:

- `transcript ext:md`
- `budget after:2024-01-01 before:2024-03-31`
- `filename:resume ext:md path:applications`
- `content:error size<=1mb`

Filter-only:

- `ext:md ext:txt`
- `after:2024-01-01`
- `path:notes size<=1mb`
- `before:2024-03-01 ext:md`

Natural-language date examples:

- `transcript from march`
- `notes last 7 days`
- `ext:md from march 2024`

---

## 13. Fuzzy Filename Index and Autocomplete

### 13.1 Purpose

Autocomplete is filename/path-oriented, not semantic. It helps the user quickly converge on likely files while typing.

### 13.2 Data source

The fuzzy index is built from the **last completed active index** only.

It must use normalized path strings and should strongly favor basename matches over deep directory matches.

### 13.3 Trigram strategy

V1 should use an in-memory trigram inverted index for path and filename retrieval.

Core behavior:

1. normalize candidate strings with casefolding
2. extract trigrams
3. build an inverted map:
   - trigram -> candidate ids
4. retrieve candidates by trigram overlap
5. score candidates with filename-heavy positional weighting

Example trigram helpers:

```python
def _extract_trigrams(text: str) -> set[str]:
    padded = f"  {text} "
    return {padded[i:i+3] for i in range(len(padded) - 2)}

def _build_trigram_index(paths: list[str]) -> dict[str, set[int]]:
    index: dict[str, set[int]] = defaultdict(set)
    for i, path in enumerate(paths):
        for trigram in _extract_trigrams(path.casefold()):
            index[trigram].add(i)
    return index
```

### 13.4 Length-based fallbacks

These rules are required:

- 1-character query:
  - use simple prefix / segment scanning
  - do not rely on trigrams
- 2–3 character query:
  - use lightweight fallback matching such as prefix / character-set subset logic
- 4+ character query:
  - use full trigram candidate filtering and scoring

### 13.5 Scoring priorities

Autocomplete should prefer, in order:

1. exact basename match
2. basename prefix match
3. strong basename trigram overlap
4. path segment boundary matches
5. deeper path matches

### 13.6 Suggestion behavior

- show a practical cap such as top 10–20 suggestions
- keep ordering deterministic
- refresh suggestions as the query changes
- rebuild the fuzzy index only after a new active index is successfully published

### 13.7 Autocomplete insertion rules

The autocomplete layer must be explicit about what gets inserted into the input.

V1 recommendation:

- free-text suggestions should insert the basename by default
- `path:` suggestions should insert the normalized path fragment or full normalized path string, consistently
- accepting a suggestion should replace only the active token under the cursor, not the whole query
- autocomplete should remain advisory and must not constrain later free-text editing

### 13.8 Scope of autocomplete

V1 autocomplete should help with:

- free-text filename/path search entry
- `path:` value entry
- optionally `ext:` from a static known set

It does not need to autocomplete arbitrary content terms.

Autocomplete precedence rules:

- if an autocomplete menu is open, `Up` / `Down` should move within suggestions before affecting result-list selection
- `Enter` should accept the active suggestion when a suggestion is explicitly selected
- `Esc` should dismiss suggestions before dismissing broader transient UI state

---

## 14. Terminal UI Behavior

### 14.1 Layout

The Textual UI should have, at minimum:

1. header / status area
2. search input area
3. results list
4. preview or detail area
5. footer / keybinding hints

The layout may adapt for terminal width, but those conceptual regions remain.

### 14.2 Reactive state

The UI should maintain explicit reactive state for at least:

- current raw query
- parsed query
- current results
- selected result id / index
- autocomplete suggestions
- indexing status
- last successful index timestamp
- transient error / status message
- loading flags

### 14.3 Search interaction model

- App starts with input focused.
- Search should update as the user types, with a small debounce.
- Search and indexing must never freeze the UI.
- If the query is empty and no filters are present, show the empty/help state.

### 14.4 Focus behavior

These focus rules are normative:

1. On launch, focus is in the search input.
2. Pressing `/` returns focus to the search input and places the cursor at the end.
3. From the input:
   - `Down` moves focus to the first result if results exist
4. In the results list:
   - `Down` moves selection downward
   - `Up` moves selection upward
   - `Up` on the first result returns focus to the input
5. The preview pane is non-primary in V1 and should not trap focus unless deliberately made focusable.
6. Transient overlays must be dismissible with `Esc`.

### 14.5 Keybindings

Required V1 bindings:

- `Up` / `Down`
  - navigate autocomplete suggestions or results depending on focus/context
- `Enter`
  - in input: commit current query / suggestion
  - in results: open selected file
- `Tab`
  - accept the current autocomplete suggestion if one is active
- `/`
  - focus the input
- `Ctrl-R`
  - start refresh/rebuild if no indexing job is running
- `Esc`
  - close autocomplete or dismiss transient UI state
- `q`
  - quit when no modal/transient interaction is active
- `Ctrl-C`
  - immediate quit

Interaction precedence must be deterministic:

1. modal or transient overlay
2. autocomplete suggestion list
3. results list
4. search input global shortcuts

### 14.6 Loading, empty, and error states

The UI must handle these states explicitly.

#### No index yet

Show a clear empty state explaining:

- no completed index exists yet
- which roots will be indexed
- how to start the first build

#### Rebuild running with existing index

Show:

- indexing spinner / status
- search remains available against the last completed index

#### Rebuild running with no prior index

Show:

- loading state
- indexing status
- no-result area should explain that results will appear after the first successful build

#### Empty query

Show:

- concise help text
- example queries
- keybinding hint to refresh/build if needed

#### No matches

Show:

- “No matching files”
- the active filters / query summary
- no crash, no blank screen

#### Search error

Show:

- non-fatal error banner or toast
- prior results may remain visible if appropriate
- the app stays running

#### Indexing error

Show:

- indexing failed
- last good index retained if one exists
- concise diagnostic summary

### 14.7 Result presentation

Each result row should display, where available:

- filename
- path
- relative or formatted modified time
- optional size
- match indicator
- snippet preview for content matches

Rendering rules:

- long paths should truncate predictably rather than wrapping uncontrollably
- highlighted terms should remain readable in both light and dark terminal themes
- snippet length should be bounded
- raw internal scores do not need to be displayed unless intentionally exposed as a debug or advanced mode

---

## 15. File Actions and Platform Behavior

### 15.1 Open selected file

Opening a file must use the platform default application:

- macOS: `open`
- Linux: `xdg-open`
- Windows: `os.startfile` or equivalent shell open behavior

### 15.2 Additional actions

V1 may also support:

- copy full path
- reveal parent directory

These are secondary to the open-file action.

### 15.3 Action behavior

- file actions must be non-blocking from the user’s perspective
- failures must surface as UI error messages, not crashes
- actions always operate on the currently selected result row

### 15.4 Missing-file action handling

Because the filesystem may change after indexing:

- opening a file that no longer exists must show a non-fatal error
- reveal/copy actions should still work where possible using the stored path
- action failures must not clear current search state or selection unless necessary

---

## 16. Module Plan

| Module | Responsibility |
|---|---|
| `main.py` | App entry point |
| `app.py` | Root Textual app and worker wiring |
| `config.py` | Roots, ignore rules, file size limit, defaults |
| `db.py` | SQLite setup, schema creation, DB paths, publication swap |
| `indexer.py` | Traversal, metadata extraction, content extraction, staged rebuild |
| `extractors.py` | File decoding and extraction helpers |
| `parser.py` | Query parsing and filter normalization |
| `search.py` | FTS and metadata query execution, ranking, snippets |
| `fuzzy_index.py` | Trigram index and scoring |
| `autocomplete.py` | UI-facing suggestion glue |
| `actions.py` | Open file / reveal / copy path |
| `models.py` | Query/result dataclasses or typed models |
| `messages.py` | Textual message/event classes for worker and UI coordination |
| `utils.py` | Shared helpers, time/size parsing, path normalization |

---

## 17. Development Phases with Acceptance Criteria

### Phase 1 — Storage and Configuration

Deliverables:

- config loading
- DB path management
- schema creation
- active/staging DB handling

Acceptance criteria:

- schema creates successfully on a clean machine
- `files` and `files_fts` exist with triggers
- `ext` normalization is consistent
- path normalization is deterministic
- active DB remains untouched if staging DB creation fails

### Phase 2 — Indexing

Deliverables:

- traversal
- ignore rules
- metadata extraction
- content extraction
- staged rebuild publication

Acceptance criteria:

- supported text files are indexed with content
- oversized / binary / unsupported files are metadata-only
- unreadable files do not crash the job
- deleted files are absent after a successful refresh
- only one indexing job can run at a time
- UI remains usable during indexing

### Phase 3 — Query Parser and Search

Deliverables:

- operator parser
- FTS query generation
- metadata-only queries
- deterministic ordering

Acceptance criteria:

- free-text, field-scoped, mixed, and filter-only queries all parse correctly
- repeated `ext:` behaves as OR
- repeated date/size/path filters behave as AND
- empty raw query with no filters shows help state
- metadata-only queries return results without FTS text
- ranking is deterministic across repeated runs on unchanged data

### Phase 4 — Fuzzy Index and Autocomplete

Deliverables:

- trigram index
- length-based fallbacks
- UI suggestion integration

Acceptance criteria:

- 1-character, 2–3 character, and 4+ character queries each use the expected fallback/search path
- basename matches outrank deep directory-only matches
- suggestions update without blocking typing
- suggestions rebuild after successful index publication

### Phase 5 — Textual UI

Deliverables:

- layout
- reactive state wiring
- focus behavior
- keybindings
- loading/error/empty states

Acceptance criteria:

- app launches with input focused
- `/`, `Tab`, `Enter`, `Up`, `Down`, `Esc`, `Ctrl-R`, `q`, and `Ctrl-C` behave as specified
- empty, loading, no-results, and error states are visible and distinct
- search remains usable against the last completed index during rebuild

### Phase 6 — File Actions and Polish

Deliverables:

- open-file action
- status messaging
- preview refinement
- validation cleanup

Acceptance criteria:

- selected file opens successfully on the host platform
- action failures surface as non-fatal errors
- snippets display for content matches
- the app remains fully offline and local-only

### Validation guidance

V1 should include at least:

- unit tests for parser behavior
- unit tests for size/date normalization
- unit tests for path normalization
- unit tests for autocomplete token replacement behavior
- integration tests for indexing and stale-row semantics
- integration tests for metadata-only queries
- integration tests for deterministic ranking order
- integration tests for active-vs-staging publication behavior
- a manual TUI checklist for focus and keybinding behavior
- a manual TUI checklist for search-result race handling during rapid query changes

### Implementation-readiness notes

The initial implementation should prefer a small number of explicit contracts over framework magic:

- one typed query model
- one typed result model
- one message/event module for worker-to-UI communication
- one place where config and storage paths are resolved
- one place where path normalization rules are enforced

---

## 18. Non-Negotiable Requirements

- fully local and offline
- Textual is the primary V1 UI framework
- interactive-first terminal experience
- no whole-filesystem indexing
- no daemon watcher in V1
- no semantic/vector search
- no OCR
- no cloud or external APIs
- filename + content search in one tool
- metadata-only filter queries must be valid
- ranking must be explicit and deterministic
- search must continue against the last completed index during rebuild
- at most one indexing job at a time

---

## 19. Stretch Goals

Post-V1 only:

- incremental in-place refresh optimization
- optional filesystem watcher
- richer preview pane
- broader document extractors such as PDF or DOCX
- saved searches
- configurable themes / layout variants
- recent-files or pinned-files views

These are intentionally out of scope for V1.

---

## 20. Implementation References (Toad Appendix)

This section is **non-normative**. It is implementation guidance only, not product requirements.

Useful Toad references to study and adapt:

- `src/toad/fuzzy_index.py`
  - trigram candidate filtering
  - weighted path scoring
  - length-based fuzzy fallbacks
- `src/toad/directory_suggester.py`
  - suggestion wiring
- `src/toad/path_complete.py`
  - path completion mechanics
- `src/toad/path_filter.py`
  - ignore-rule structure
- `src/toad/app.py`
  - Textual app structure
  - `@work(thread=True)` usage
  - reactive state patterns
  - `watch_*` methods
- `src/toad/db.py`
  - SQLite wrapper patterns
- `src/toad/atomic.py`
  - atomic write pattern for config/state files
- `src/toad/directory_watcher.py`
  - future watcher reference for post-V1 work

Guidance for use:

- borrow architectural patterns, not product scope
- keep core requirements in this spec authoritative
- do not let Toad-specific details override V1 boundaries defined above