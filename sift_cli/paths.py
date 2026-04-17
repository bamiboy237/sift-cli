"""Path normalization and default location helpers."""

from __future__ import annotations

import os
from pathlib import Path


def normalize_path(path: str | Path) -> str:
    """Return an absolute forward-slash path string."""

    expanded = os.path.expanduser(os.fspath(path))
    normalized = os.path.abspath(os.path.normpath(expanded))
    return normalized.replace("\\", "/")


def casefold_path(path: str | Path) -> str:
    """Return a normalized, casefolded path string for comparisons."""

    return normalize_path(path).casefold()


def default_config_path() -> Path:
    """Return the per-user config file path."""

    if os.name == "nt":
        base_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base_dir / "sift" / "config.toml"


def default_state_dir() -> Path:
    """Return the per-user state directory."""

    if os.name == "nt":
        base_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base_dir = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base_dir / "sift"


def default_index_roots() -> tuple[Path, ...]:
    """Return the default roots suggested by the spec."""

    home = Path.home()
    return tuple(home / name for name in ("Documents", "Desktop", "Downloads", "Projects"))
