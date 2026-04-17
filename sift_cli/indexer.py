"""Indexing lifecycle and filesystem traversal."""

from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .db import initialize_database, publish_staging_database
from .extractors import extract_text_content
from .paths import normalize_path

Extractor = Callable[[Path, str | None, int], str | None]


@dataclass(frozen=True, slots=True)
class IndexStats:
    """Simple indexing counters."""

    files_seen: int = 0
    files_indexed: int = 0
    extraction_failures: int = 0


def build_index(
    *,
    roots: tuple[Path, ...],
    active_db_path: Path,
    staging_db_path: Path,
    ignore_dirs: tuple[str, ...],
    max_extracted_file_size: int,
    extractor: Extractor | None = None,
) -> IndexStats:
    """Build a staging index and publish it on success."""

    active_db_path.parent.mkdir(parents=True, exist_ok=True)
    initialize_database(staging_db_path)

    extractor_func = extractor or extract_text_content
    stats = IndexStats()
    rows: list[tuple[str, str, str | None, str | None, int, float | None, float]] = []

    try:
        for root in roots:
            for file_path in _iter_files(root, ignore_dirs):
                stats = IndexStats(
                    files_seen=stats.files_seen + 1,
                    files_indexed=stats.files_indexed,
                    extraction_failures=stats.extraction_failures,
                )
                row, extraction_failed = _build_row(
                    file_path, max_extracted_file_size, extractor_func
                )
                rows.append(row)
                if extraction_failed:
                    stats = IndexStats(
                        files_seen=stats.files_seen,
                        files_indexed=stats.files_indexed,
                        extraction_failures=stats.extraction_failures + 1,
                    )

        with sqlite3.connect(staging_db_path) as connection:
            connection.executemany(
                "INSERT INTO files(path, filename, ext, content, size, created_at, modified_at, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            connection.commit()

        publish_staging_database(active_db_path, staging_db_path)
        return IndexStats(
            files_seen=stats.files_seen,
            files_indexed=len(rows),
            extraction_failures=stats.extraction_failures,
        )
    except Exception:
        if staging_db_path.exists():
            staging_db_path.unlink()
        raise


class IndexingService:
    """Single-job guard around index rebuilds."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def refresh(self, **kwargs) -> IndexStats | None:
        if not self._lock.acquire(blocking=False):
            return None
        try:
            return build_index(**kwargs)
        finally:
            self._lock.release()


def _iter_files(root: Path, ignore_dirs: tuple[str, ...]):
    root_path = Path(root)
    if not root_path.exists():
        return

    ignore_names = {name.casefold() for name in ignore_dirs}
    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
        dirnames[:] = [
            name
            for name in dirnames
            if name.casefold() not in ignore_names and not name.startswith(".")
        ]
        current_dir = Path(dirpath)
        for filename in filenames:
            file_path = current_dir / filename
            if file_path.is_symlink() or not file_path.is_file():
                continue
            yield file_path


def _build_row(
    path: Path,
    max_extracted_file_size: int,
    extractor: Extractor,
) -> tuple[tuple[str, str, str | None, str | None, int, float | None, float], bool]:
    stat_result = path.stat()
    normalized_path = normalize_path(path)
    filename = path.name
    ext = path.suffix.lstrip(".").casefold() or None
    content = None
    extraction_failed = False

    try:
        content = extractor(path, ext, max_extracted_file_size)
    except Exception:
        extraction_failed = True

    if content is None and extraction_failed:
        content = None

    return (
        (
            normalized_path,
            filename,
            ext,
            content,
            stat_result.st_size,
            getattr(stat_result, "st_birthtime", None),
            stat_result.st_mtime,
            stat_result.st_mtime,
        ),
        extraction_failed,
    )
