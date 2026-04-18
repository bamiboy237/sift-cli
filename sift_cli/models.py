"""Core phase-1 data models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """User configuration loaded from TOML."""

    roots: tuple[Path, ...]
    ignore_dirs: tuple[str, ...]
    max_extracted_file_size: int
    include_hidden_dirs: bool = False


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Resolved config and storage locations."""

    config_path: Path
    state_dir: Path
    active_db_path: Path
    staging_db_path: Path


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Search result contract shared by search and UI."""

    path: str
    filename: str
    ext: str | None
    size: int
    modified_at: float
    snippet: str | None
    matched_filename: bool
    matched_content: bool
    score: float | None


@dataclass(frozen=True, slots=True)
class SearchPreview:
    """Preview text rendered for the selected result."""

    title: str
    detail: str


@dataclass(frozen=True, slots=True)
class ResultViewModel:
    """Rendered data for a result row."""

    filename: str
    path: str
    modified_label: str
    size_label: str | None
    snippet: str | None
    matched_filename: bool
    matched_content: bool
