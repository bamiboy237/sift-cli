"""Worker and UI message types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import SearchResult


@dataclass(frozen=True, slots=True)
class IndexBuildStarted:
    root_count: int


@dataclass(frozen=True, slots=True)
class IndexBuildProgress:
    files_seen: int
    files_indexed: int


@dataclass(frozen=True, slots=True)
class IndexBuildSucceeded:
    active_db_path: Path
    files_indexed: int = 0
    files_skipped: int = 0


@dataclass(frozen=True, slots=True)
class IndexBuildFailed:
    error: str


@dataclass(frozen=True, slots=True)
class IndexBuildAlreadyRunning:
    message: str = "Index refresh already running."


@dataclass(frozen=True, slots=True)
class SearchRequested:
    query: str
    request_id: int


@dataclass(frozen=True, slots=True)
class SearchCompleted:
    request_id: int
    result_count: int


@dataclass(frozen=True, slots=True)
class SearchCompletedWithResults:
    request_id: int
    query: str
    results: tuple[SearchResult, ...]


@dataclass(frozen=True, slots=True)
class SearchQueryFailed:
    request_id: int
    query: str
    error: str


@dataclass(frozen=True, slots=True)
class SearchFailed:
    request_id: int
    error: str
