"""Configuration loading for phase 1."""

from __future__ import annotations

from pathlib import Path
from tomllib import load as load_toml

from .models import AppConfig
from .paths import default_config_path, default_index_roots, normalize_path

DEFAULT_IGNORE_DIRS = (
    ".git",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".cache",
    ".npm",
    ".uv",
)
DEFAULT_MAX_EXTRACTED_FILE_SIZE = 1_048_576


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from TOML, falling back to spec defaults."""

    path = config_path if config_path is not None else default_config_path()
    if not path.exists():
        return default_config()

    with path.open("rb") as file_handle:
        raw = load_toml(file_handle)

    roots = raw.get("roots")
    ignore_dirs = raw.get("ignore_dirs")
    max_size = raw.get("max_extracted_file_size")

    return AppConfig(
        roots=_load_roots(roots),
        ignore_dirs=_load_ignore_dirs(ignore_dirs),
        max_extracted_file_size=_load_max_size(max_size),
    )


def default_config() -> AppConfig:
    """Return the spec defaults."""

    return AppConfig(
        roots=default_index_roots(),
        ignore_dirs=DEFAULT_IGNORE_DIRS,
        max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
    )


def _load_roots(value: object) -> tuple[Path, ...]:
    if value is None:
        return default_index_roots()
    if not isinstance(value, list):
        raise ValueError("roots must be a list of paths")

    roots: list[Path] = []
    for item in value:
        if not isinstance(item, (str, Path)):
            raise ValueError("roots entries must be strings or paths")
        roots.append(Path(normalize_path(item)))
    return tuple(roots)


def _load_ignore_dirs(value: object) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_IGNORE_DIRS
    if not isinstance(value, list):
        raise ValueError("ignore_dirs must be a list of directory names")
    return tuple(str(item) for item in value)


def _load_max_size(value: object) -> int:
    if value is None:
        return DEFAULT_MAX_EXTRACTED_FILE_SIZE
    if not isinstance(value, int) or value < 0:
        raise ValueError("max_extracted_file_size must be a non-negative integer")
    return value
