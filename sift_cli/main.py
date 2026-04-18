"""Application entrypoint."""

from __future__ import annotations

from .config import load_config
from .config import DEFAULT_IGNORE_DIRS, DEFAULT_MAX_EXTRACTED_FILE_SIZE
from .db import initialize_active_database, resolve_runtime_paths
from .indexer import build_index
from .ui import LaunchConfig, SearchController


def build_app_config(
    *,
    db_path,
    active_db_path=None,
    staging_db_path=None,
    roots=(),
    ignore_dirs=DEFAULT_IGNORE_DIRS,
    max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
) -> LaunchConfig:
    return LaunchConfig(
        db_path=db_path,
        active_db_path=active_db_path or db_path,
        staging_db_path=staging_db_path or db_path.with_name("index.build.db"),
        roots=tuple(roots),
        ignore_dirs=tuple(ignore_dirs),
        max_extracted_file_size=max_extracted_file_size,
    )


def main() -> None:
    """Bootstrap config and launch the UI."""

    runtime_paths = resolve_runtime_paths()
    config = load_config(runtime_paths.config_path)
    initialize_active_database(runtime_paths.active_db_path)
    controller = SearchController(db_path=runtime_paths.active_db_path)
    build_index(
        roots=config.roots,
        active_db_path=runtime_paths.active_db_path,
        staging_db_path=runtime_paths.staging_db_path,
        ignore_dirs=config.ignore_dirs,
        max_extracted_file_size=config.max_extracted_file_size,
        on_published=lambda path: controller.refresh_fuzzy_index(path),
    )
    launch_config = build_app_config(
        db_path=runtime_paths.active_db_path,
        active_db_path=runtime_paths.active_db_path,
        staging_db_path=runtime_paths.staging_db_path,
        roots=config.roots,
        ignore_dirs=config.ignore_dirs,
        max_extracted_file_size=config.max_extracted_file_size,
    )

    try:
        from .app import launch_app
        launch_app(launch_config, controller=controller)
    except RuntimeError:
        print(f"sift-cli ready with {len(config.roots)} configured roots")


if __name__ == "__main__":
    main()
