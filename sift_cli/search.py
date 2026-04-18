"""SQLite query execution for sift-cli search."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import SearchResult
from .parser import ParsedQuery, is_empty_query, is_filter_only_query, parse_query


def search_files(db_path: Path, raw_query: str) -> list[SearchResult]:
    parsed = parse_query(raw_query)
    if is_empty_query(parsed):
        return []

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        if is_filter_only_query(parsed):
            return _search_metadata_only(connection, parsed)
        try:
            return _search_text(connection, parsed)
        except sqlite3.OperationalError as exc:
            if _should_fallback_from_fts_error(exc):
                return _search_metadata_only_from_text_terms(connection, parsed)
            raise


def _should_fallback_from_fts_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).casefold()
    return "fts5: syntax error" in message or "fts5" in message


def _search_metadata_only_from_text_terms(connection: sqlite3.Connection, parsed: ParsedQuery) -> list[SearchResult]:
    terms = list(parsed.text_terms) + list(parsed.phrases)
    clauses: list[str] = []
    params: list[object] = []
    for term in terms:
        clauses.append("(lower(files.filename) LIKE ? OR lower(files.path) LIKE ?)")
        params.extend((f"%{term.casefold()}%", f"%{term.casefold()}%"))
    if parsed.exts:
        placeholders = ", ".join("?" for _ in parsed.exts)
        clauses.append(f"files.ext IN ({placeholders})")
        params.extend(parsed.exts)
    for term in parsed.path_terms:
        clauses.append("lower(files.path) LIKE ?")
        params.append(f"%{term.casefold()}%")
    if parsed.after is not None:
        clauses.append("files.modified_at >= ?")
        params.append(parsed.after)
    if parsed.before is not None:
        clauses.append("files.modified_at <= ?")
        params.append(parsed.before)
    if parsed.size_min is not None:
        clauses.append("files.size >= ?")
        params.append(parsed.size_min)
    if parsed.size_max is not None:
        clauses.append("files.size <= ?")
        params.append(parsed.size_max)

    where = " AND ".join(clauses) if clauses else "1=1"
    rows = connection.execute(
        f"SELECT path, filename, ext, size, modified_at FROM files WHERE {where} ORDER BY modified_at DESC, filename ASC, path ASC LIMIT 50",
        params,
    ).fetchall()
    return [
        SearchResult(
            path=row["path"],
            filename=row["filename"],
            ext=row["ext"],
            size=row["size"],
            modified_at=row["modified_at"],
            snippet=None,
            matched_filename=False,
            matched_content=False,
            score=None,
        )
        for row in rows
    ]


def _search_metadata_only(connection: sqlite3.Connection, parsed: ParsedQuery) -> list[SearchResult]:
    clauses: list[str] = []
    params: list[object] = []

    if parsed.exts:
        placeholders = ", ".join("?" for _ in parsed.exts)
        clauses.append(f"ext IN ({placeholders})")
        params.extend(parsed.exts)
    for term in parsed.path_terms:
        clauses.append("lower(path) LIKE ?")
        params.append(f"%{term.casefold()}%")
    if parsed.after is not None:
        clauses.append("modified_at >= ?")
        params.append(parsed.after)
    if parsed.before is not None:
        clauses.append("modified_at <= ?")
        params.append(parsed.before)
    if parsed.size_min is not None:
        clauses.append("size >= ?")
        params.append(parsed.size_min)
    if parsed.size_max is not None:
        clauses.append("size <= ?")
        params.append(parsed.size_max)

    where = " AND ".join(clauses) if clauses else "1=1"
    rows = connection.execute(
        f"SELECT path, filename, ext, size, modified_at FROM files WHERE {where} ORDER BY modified_at DESC, filename ASC, path ASC LIMIT 50",
        params,
    ).fetchall()
    return [
        SearchResult(
            path=row["path"],
            filename=row["filename"],
            ext=row["ext"],
            size=row["size"],
            modified_at=row["modified_at"],
            snippet=None,
            matched_filename=False,
            matched_content=False,
            score=None,
        )
        for row in rows
    ]


def _search_text(connection: sqlite3.Connection, parsed: ParsedQuery) -> list[SearchResult]:
    all_terms = list(parsed.text_terms) + list(parsed.phrases) + list(parsed.filename_terms) + list(parsed.content_terms)
    if not all_terms:
        return _search_metadata_only(connection, parsed)

    text_terms = list(parsed.text_terms) + list(parsed.phrases)
    filename_terms = list(parsed.filename_terms)
    content_terms = list(parsed.content_terms)

    clauses: list[str] = []
    params: list[object] = []

    if text_terms:
        clauses.append("files_fts MATCH ?")
        params.append(" ".join(text_terms))
    if filename_terms:
        for term in filename_terms:
            clauses.append("lower(files.filename) LIKE ?")
            params.append(f"%{term.casefold()}%")
    if content_terms:
        for term in content_terms:
            clauses.append("lower(coalesce(files.content, '')) LIKE ?")
            params.append(f"%{term.casefold()}%")

    if parsed.exts:
        placeholders = ", ".join("?" for _ in parsed.exts)
        clauses.append(f"files.ext IN ({placeholders})")
        params.extend(parsed.exts)
    for term in parsed.path_terms:
        clauses.append("lower(files.path) LIKE ?")
        params.append(f"%{term.casefold()}%")
    if parsed.after is not None:
        clauses.append("files.modified_at >= ?")
        params.append(parsed.after)
    if parsed.before is not None:
        clauses.append("files.modified_at <= ?")
        params.append(parsed.before)
    if parsed.size_min is not None:
        clauses.append("files.size >= ?")
        params.append(parsed.size_min)
    if parsed.size_max is not None:
        clauses.append("files.size <= ?")
        params.append(parsed.size_max)

    if not clauses:
        return _search_metadata_only(connection, parsed)

    sql = f"""
        SELECT
            files.path,
            files.filename,
            files.ext,
            files.size,
            files.modified_at,
            files.content,
            COALESCE(bm25(files_fts, 8.0, 1.0), 999999.0) AS score
        FROM files
        JOIN files_fts ON files_fts.rowid = files.id
        WHERE {' AND '.join(clauses)}
        ORDER BY score ASC, files.modified_at DESC, files.path ASC
    """
    rows = connection.execute(sql, params).fetchall()
    search_terms = list(parsed.text_terms) + list(parsed.phrases) + list(parsed.filename_terms) + list(parsed.content_terms)
    normalized_free_text = _normalized_free_text_query(parsed)
    results = [
        SearchResult(
            path=row["path"],
            filename=row["filename"],
            ext=row["ext"],
            size=row["size"],
            modified_at=row["modified_at"],
            snippet=_build_snippet(row["content"], search_terms),
            matched_filename=_matched_filename(row["filename"], search_terms),
            matched_content=_matched_content(row["content"], search_terms),
            score=row["score"],
        )
        for row in rows
    ]
    results.sort(key=lambda result: _search_sort_key(result, normalized_free_text))
    return results[:50]


def _matched_filename(filename: str, terms: list[str]) -> bool:
    filename_lower = filename.casefold()
    return any(term.casefold() in filename_lower for term in terms)


def _matched_content(content: str | None, terms: list[str]) -> bool:
    if not content:
        return False
    lowered = content.casefold()
    return any(term.casefold().strip('"') in lowered for term in terms)


def _build_snippet(content: str | None, terms: list[str]) -> str | None:
    if not content:
        return None
    lowered = content.casefold()
    for term in terms:
        match = term.casefold().strip('"')
        if match and match in lowered:
            index = lowered.index(match)
            start = max(0, index - 20)
            end = min(len(content), index + len(match) + 20)
            return content[start:end]
    return None


def _normalized_free_text_query(parsed: ParsedQuery) -> str:
    terms = [term.strip().casefold() for term in list(parsed.text_terms) + list(parsed.phrases)]
    terms = [term for term in terms if term]
    return " ".join(terms)


def _filename_boost_rank(filename: str, normalized_query: str) -> int:
    if not normalized_query:
        return 3
    lowered = filename.casefold()
    if lowered == normalized_query:
        return 0
    if lowered.startswith(normalized_query):
        return 1
    if normalized_query in lowered:
        return 2
    return 3


def _both_fields_boost_rank(result: SearchResult) -> int:
    return 0 if result.matched_filename and result.matched_content else 1


def _search_sort_key(result: SearchResult, normalized_free_text: str) -> tuple[float, int, int, float, int, str]:
    score = result.score if result.score is not None else 999999.0
    filename_boost = _filename_boost_rank(result.filename, normalized_free_text)
    both_fields_boost = _both_fields_boost_rank(result)
    return (
        score,
        filename_boost,
        both_fields_boost,
        -result.modified_at,
        len(result.filename),
        result.path,
    )
