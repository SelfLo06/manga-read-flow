from __future__ import annotations

from hashlib import sha256
import sqlite3

import pytest

from manga_read_flow.persistence import project_store as project_store_module
from manga_read_flow.persistence.project_store import (
    AppStore,
    PROJECT_GROUPING_CHECK_CHECKSUM,
    PROJECT_GROUPING_CHECK_REQUIRED_SCHEMA_OBJECTS,
    PROJECT_GROUPING_CHECK_VERSION,
    ProjectOpenStatus,
)


FORBIDDEN_TABLES = {
    "grouping_stale_facts",
}


def test_fresh_project_records_v6_immutable_check_schema_without_acceptance(tmp_path):
    store, project = _project(tmp_path)

    opened = store.open_project(project.project_id)

    assert opened.status is ProjectOpenStatus.READY
    assert PROJECT_GROUPING_CHECK_VERSION in {
        migration.version for migration in opened.project_migrations
    }
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (PROJECT_GROUPING_CHECK_VERSION,),
        ).fetchone() == (PROJECT_GROUPING_CHECK_CHECKSUM,)
        for object_type, name in PROJECT_GROUPING_CHECK_REQUIRED_SCHEMA_OBJECTS:
            assert connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
                (object_type, name),
            ).fetchone() == (1,)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert FORBIDDEN_TABLES.isdisjoint(tables)
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM page_grouping_state"
        ).fetchone() == (0,)


def test_existing_v5_project_upgrades_without_backfill_or_data_loss(tmp_path):
    store, project = _project(tmp_path)
    repositories = store.open_project(project.project_id).repositories()
    settings_json = '{"profile":"preserved-before-v6"}'
    repositories.workflow_execution.ensure_profile_snapshot(
        profile_snapshot_id="preserved-v5-profile",
        settings_json=settings_json,
        settings_hash=sha256(settings_json.encode("utf-8")).hexdigest(),
    )
    _remove_grouping_check_schema(project.project_db_path)

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
            WHERE profile_snapshot_id = 'preserved-v5-profile'
            """
        ).fetchone() == (settings_json,)
        assert connection.execute(
            "SELECT count(*) FROM frozen_grouping_evidence_snapshots"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM grouping_check_results"
        ).fetchone() == (0,)


def test_v6_migration_failure_rolls_back_ddl_and_marker(tmp_path, monkeypatch):
    store, project = _project(tmp_path)
    _remove_grouping_check_schema(project.project_db_path)

    def fail_migration(connection):
        connection.execute(
            "CREATE TABLE grouping_check_partial_write (id TEXT PRIMARY KEY)"
        )
        raise sqlite3.OperationalError("injected grouping check migration failure")

    monkeypatch.setattr(
        project_store_module,
        "initialize_grouping_check_schema",
        fail_migration,
    )

    outcome = store.migrate_project(project.project_id)

    assert outcome.status is ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (PROJECT_GROUPING_CHECK_VERSION,),
        ).fetchone() is None
        assert connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'grouping_check_partial_write'
            """
        ).fetchone() is None


def test_v6_checksum_mismatch_fails_closed(tmp_path):
    store, project = _project(tmp_path)
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = 'tampered' WHERE version = ?",
            (PROJECT_GROUPING_CHECK_VERSION,),
        )

    assert store.open_project(project.project_id).status is ProjectOpenStatus.CHECKSUM_MISMATCH
    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.CHECKSUM_MISMATCH


def test_v6_foreign_key_rejects_unknown_snapshot(tmp_path):
    _, project = _project(tmp_path)
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO grouping_check_results (
                    check_result_id, project_id, page_id, snapshot_id, check_name,
                    check_version, input_fingerprint, candidate_manifest_sha256,
                    candidate_dependency_fingerprint, metrics_json,
                    finding_codes_json, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"grouping-check-result-v1:{'1' * 64}",
                    project.project_id,
                    "missing-page",
                    "missing-snapshot",
                    "grouping_structural_check",
                    "grouping-check.v1",
                    "1" * 64,
                    "2" * 64,
                    "3" * 64,
                    "{}",
                    "[]",
                    "2026-07-19T00:00:00+00:00",
                ),
            )


def _project(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Grouping check migration",
        source_language="ja",
        target_language="zh-Hans",
    )
    return store, project


def _remove_grouping_check_schema(project_db_path):
    with sqlite3.connect(project_db_path) as connection:
        connection.execute("DROP TABLE grouping_check_executions")
        connection.execute("DROP TABLE grouping_check_result_issues")
        connection.execute("DROP TABLE grouping_check_results")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            (PROJECT_GROUPING_CHECK_VERSION,),
        )
