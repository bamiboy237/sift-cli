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


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Resolved config and storage locations."""

    config_path: Path
    state_dir: Path
    active_db_path: Path
    staging_db_path: Path
