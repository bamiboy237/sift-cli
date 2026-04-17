"""Text extraction helpers for indexed files."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_TEXT_EXTENSIONS = {
    "txt",
    "md",
    "py",
    "js",
    "ts",
    "json",
    "csv",
    "html",
    "css",
    "java",
    "log",
    "yaml",
    "yml",
    "toml",
    "ini",
    "sh",
    "rs",
    "go",
}


def extract_text_content(path: Path, ext: str | None, max_size: int) -> str | None:
    """Return decoded text content or None when the file should stay metadata-only."""

    if ext is None or ext not in SUPPORTED_TEXT_EXTENSIONS:
        return None

    size = path.stat().st_size
    if size > max_size:
        return None

    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        return None

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")
