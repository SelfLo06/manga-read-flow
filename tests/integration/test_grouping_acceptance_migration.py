from __future__ import annotations

from hashlib import sha256
import sqlite3

import pytest

from manga_read_flow.persistence import project_store as project_store_module
from manga_read_flow.persistence.project_store import (
    AppStore,
    PROJECT_GROUPING_ACCEPTANCE_CHECKSUM,
    PROJECT_GROUPING_ACCEPTANCE_REQUIRED_SCHEMA_OBJECTS,
    PROJECT_GROUPING_ACCEPTANCE_VERSION,
    ProjectOpenStatus,
)


def test_fresh_project_records_v7_grouping_acceptance_schema_without_backfill(tmp_path):
    store, project = _project(tmp_path)

    opened = store.open_project(project.project_id)

    assert opened.status is ProjectOpenStatus.READY
    assert PROJECT_GROUPING_ACCEPTANCE_VERSION in {
        migration.version for migration in opened.project_migrations
    }
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (PROJECT_GROUPING_ACCEPTANCE_VERSION,),
        ).fetchone() == (PROJECT_GROUPING_ACCEPTANCE_CHECKSUM,)
        for object_type, name in PROJECT_GROUPING_ACCEPTANCE_REQUIRED_SCHEMA_OBJECTS:
            assert connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
                (object_type, name),
            ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM page_grouping_state"
        ).fetchone() == (0,)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "grouping_stale_facts" not in tables
    assert "page_physical_boundary_evidence_state" not in tables


def test_existing_v6_project_upgrades_without_accepting_historical_rows(tmp_path):
    store, project = _project(tmp_path)
    repositories = store.open_project(project.project_id).repositories()
    settings_json = '{"profile":"preserved-before-v7"}'
    repositories.workflow_execution.ensure_profile_snapshot(
        profile_snapshot_id="preserved-v6-profile",
        settings_json=settings_json,
        settings_hash=sha256(settings_json.encode("utf-8")).hexdigest(),
    )
    _remove_v7_schema(project.project_db_path)

    assert (
        store.open_project(project.project_id).status
        is ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED
    )
    migrated = store.migrate_project(project.project_id)

    assert migrated.status is ProjectOpenStatus.READY
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            """
            SELECT settings_json FROM processing_profile_snapshots
            WHERE profile_snapshot_id = 'preserved-v6-profile'
            """
        ).fetchone() == (settings_json,)
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM page_grouping_state"
        ).fetchone() == (0,)


def test_v7_migration_failure_rolls_back_schema_and_marker(tmp_path, monkeypatch):
    store, project = _project(tmp_path)
    _remove_v7_schema(project.project_db_path)

    def fail_migration(connection):
        connection.execute(
            "CREATE TABLE grouping_acceptance_partial_write (id TEXT PRIMARY KEY)"
        )
        raise sqlite3.OperationalError("injected v7 migration failure")

    monkeypatch.setattr(
        project_store_module,
        "initialize_grouping_acceptance_schema",
        fail_migration,
    )

    outcome = store.migrate_project(project.project_id)

    assert outcome.status is ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (PROJECT_GROUPING_ACCEPTANCE_VERSION,),
        ).fetchone() is None
        assert connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'grouping_acceptance_partial_write'
            """
        ).fetchone() is None


def test_v7_checksum_mismatch_fails_closed(tmp_path):
    store, project = _project(tmp_path)
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = 'tampered' WHERE version = ?",
            (PROJECT_GROUPING_ACCEPTANCE_VERSION,),
        )

    assert store.open_project(project.project_id).status is ProjectOpenStatus.CHECKSUM_MISMATCH
    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.CHECKSUM_MISMATCH


def test_page_grouping_pointer_rejects_snapshot_without_acceptance(tmp_path):
    store, project = _project(tmp_path)
    repositories = store.open_project(project.project_id).repositories()
    repositories.content_state.create_page(
        page_id="page",
        batch_id="batch",
        original_artifact_id="original",
        status="uploaded",
    )

    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError, match="requires an acceptance"):
            connection.execute(
                """
                INSERT INTO page_grouping_state (
                    project_id, page_id, active_grouping_snapshot_id, version, updated_at
                ) VALUES (?, 'page', 'missing-snapshot', 1, 'now')
                """,
                (project.project_id,),
            )


def _project(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Grouping acceptance migration",
        source_language="ja",
        target_language="zh-Hans",
    )
    return store, project


def _remove_v7_schema(project_db_path):
    with sqlite3.connect(project_db_path) as connection:
        connection.execute("DROP TABLE grouping_acceptance_executions")
        connection.execute("DROP TABLE page_grouping_state")
        connection.execute("DROP TABLE grouping_snapshot_acceptances")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            (PROJECT_GROUPING_ACCEPTANCE_VERSION,),
        )
