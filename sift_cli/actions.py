"""Platform file actions."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileActionError(RuntimeError):
    message: str

    def __str__(self) -> str:
        return self.message


def open_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(str(path))

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        if hasattr(os, "startfile"):
            os.startfile(str(path))
            return
    except OSError as exc:
        raise FileActionError(f"Could not open {path}: {exc}") from exc

    raise FileActionError("Could not open file on this platform")
