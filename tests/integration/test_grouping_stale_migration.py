from __future__ import annotations

import sqlite3

from manga_read_flow.persistence import project_store as project_store_module
from manga_read_flow.persistence.project_store import (
    AppStore,
    PROJECT_GROUPING_STALE_CHECKSUM,
    PROJECT_GROUPING_STALE_VERSION,
    ProjectOpenStatus,
)


def _project(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(name="Grouping stale migration", source_language="ja", target_language="zh-Hans")
    return store, project


def _remove_v8(db_path):
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE grouping_snapshot_stale_facts")
        connection.execute("DELETE FROM schema_migrations WHERE version = ?", (PROJECT_GROUPING_STALE_VERSION,))


def test_existing_v7_project_upgrades_to_empty_v8_without_backfill(tmp_path):
    store, project = _project(tmp_path)
    _remove_v8(project.project_db_path)

    assert store.open_project(project.project_id).status is ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED
    migrated = store.migrate_project(project.project_id)

    assert migrated.status is ProjectOpenStatus.READY
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (PROJECT_GROUPING_STALE_VERSION,),
        ).fetchone() == (PROJECT_GROUPING_STALE_CHECKSUM,)
        assert connection.execute("SELECT COUNT(*) FROM grouping_snapshot_stale_facts").fetchone() == (0,)


def test_v8_ddl_failure_rolls_back_table_and_marker(tmp_path, monkeypatch):
    store, project = _project(tmp_path)
    _remove_v8(project.project_db_path)

    def fail(connection):
        connection.execute("CREATE TABLE grouping_stale_partial_write (id TEXT)")
        raise sqlite3.OperationalError("injected v8 failure")

    monkeypatch.setattr(project_store_module, "initialize_grouping_stale_schema", fail)
    outcome = store.migrate_project(project.project_id)

    assert outcome.status is ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (PROJECT_GROUPING_STALE_VERSION,)
        ).fetchone() is None
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'grouping_stale_partial_write'"
        ).fetchone() is None
