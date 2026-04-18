"""Application entrypoint."""

from __future__ import annotations

from .config import load_config
from .config import DEFAULT_IGNORE_DIRS, DEFAULT_MAX_EXTRACTED_FILE_SIZE
from .db import initialize_active_database, resolve_runtime_paths
from .models import AppConfig, RuntimePaths
from .ui import LaunchConfig, SearchController


def build_app_config(
    *,
    db_path,
    active_db_path=None,
    staging_db_path=None,
    roots=(),
    ignore_dirs=DEFAULT_IGNORE_DIRS,
    max_extracted_file_size=DEFAULT_MAX_EXTRACTED_FILE_SIZE,
    include_hidden_dirs=False,
    auto_start_indexing=False,
) -> LaunchConfig:
    return LaunchConfig(
        db_path=db_path,
        active_db_path=active_db_path or db_path,
        staging_db_path=staging_db_path or db_path.with_name("index.build.db"),
        roots=tuple(roots),
        ignore_dirs=tuple(ignore_dirs),
        max_extracted_file_size=max_extracted_file_size,
        include_hidden_dirs=include_hidden_dirs,
        auto_start_indexing=auto_start_indexing,
    )


def bootstrap_app() -> tuple[LaunchConfig, SearchController, AppConfig]:
    runtime_paths = resolve_runtime_paths()
    config = load_config(runtime_paths.config_path)
    initialize_active_database(runtime_paths.active_db_path)
    controller = SearchController(db_path=runtime_paths.active_db_path)
    controller.refresh_fuzzy_index(runtime_paths.active_db_path)
    launch_config = _build_launch_config(runtime_paths, config)
    return launch_config, controller, config


def _build_launch_config(runtime_paths: RuntimePaths, config: AppConfig) -> LaunchConfig:
    return build_app_config(
        db_path=runtime_paths.active_db_path,
        active_db_path=runtime_paths.active_db_path,
        staging_db_path=runtime_paths.staging_db_path,
        roots=config.roots,
        ignore_dirs=config.ignore_dirs,
        max_extracted_file_size=config.max_extracted_file_size,
        include_hidden_dirs=config.include_hidden_dirs,
        auto_start_indexing=True,
    )


def main() -> None:
    """Bootstrap config and launch the UI."""

    launch_config, controller, config = bootstrap_app()

    try:
        from .app import launch_app
        launch_app(launch_config, controller=controller)
    except RuntimeError:
        print(f"sift-cli ready with {len(config.roots)} configured roots")


if __name__ == "__main__":
    main()
