"""Platform file actions."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(str(path))

    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if hasattr(os, "startfile"):
        os.startfile(str(path))
        return

    raise RuntimeError("unsupported platform")
