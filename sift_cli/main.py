"""Minimal application entrypoint for phase 1."""

from __future__ import annotations

from .config import load_config
from .db import initialize_active_database, resolve_runtime_paths
from .indexer import build_index


def main() -> None:
    """Bootstrap config and storage for the app."""

    runtime_paths = resolve_runtime_paths()
    config = load_config(runtime_paths.config_path)
    initialize_active_database(runtime_paths.active_db_path)
    build_index(
        roots=config.roots,
        active_db_path=runtime_paths.active_db_path,
        staging_db_path=runtime_paths.staging_db_path,
        ignore_dirs=config.ignore_dirs,
        max_extracted_file_size=config.max_extracted_file_size,
    )
    print(f"sift-cli ready with {len(config.roots)} configured roots")


if __name__ == "__main__":
    main()
