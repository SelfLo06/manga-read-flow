from __future__ import annotations

import sqlite3

from manga_read_flow.persistence import project_store as project_store_module
from manga_read_flow.persistence.project_store import (
    AppStore,
    PROJECT_DETECTION_EVIDENCE_CHECKSUM,
    PROJECT_DETECTION_EVIDENCE_REQUIRED_SCHEMA_OBJECTS,
    PROJECT_DETECTION_EVIDENCE_VERSION,
    PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,
    ProjectOpenStatus,
)


COMPLETION_TABLES = (
    "combined_cleaning_candidates",
    "combined_cleaning_candidate_members",
    "page_cleaning_validation_records",
    "cleaning_quality_issue_relations",
    "accepted_segment_cleaning_dispositions",
    "page_cleaning_acceptances",
)


def test_fresh_project_records_detection_evidence_migration_and_schema(tmp_path):
    store, project = _project(tmp_path)

    opened = store.open_project(project.project_id)

    assert opened.status is ProjectOpenStatus.READY
    assert PROJECT_DETECTION_EVIDENCE_VERSION in {
        migration.version for migration in opened.project_migrations
    }
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (PROJECT_DETECTION_EVIDENCE_VERSION,),
        ).fetchone() == (PROJECT_DETECTION_EVIDENCE_CHECKSUM,)
        for object_type, name in PROJECT_DETECTION_EVIDENCE_REQUIRED_SCHEMA_OBJECTS:
            assert connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
                (object_type, name),
            ).fetchone() == (1,)


def test_existing_project_applies_detection_evidence_migration_without_data_loss(tmp_path):
    store, project = _project(tmp_path)
    repositories = store.open_project(project.project_id).repositories()
    repositories.workflow_execution.ensure_profile_snapshot(
        profile_snapshot_id="preserved-profile",
        settings_json='{"profile":"preserved"}',
        settings_hash="a" * 64,
    )
    _remove_detection_evidence_schema(project.project_db_path)

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
            WHERE profile_snapshot_id = 'preserved-profile'
            """
        ).fetchone() == ('{"profile":"preserved"}',)
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (PROJECT_DETECTION_EVIDENCE_VERSION,),
        ).fetchone() == (PROJECT_DETECTION_EVIDENCE_CHECKSUM,)


def test_detection_evidence_migration_failure_rolls_back_ddl_and_marker(
    tmp_path, monkeypatch
):
    store, project = _project(tmp_path)
    _remove_detection_evidence_schema(project.project_db_path)

    def fail_migration(connection):
        connection.execute(
            "CREATE TABLE detection_evidence_partial_write (id TEXT PRIMARY KEY)"
        )
        raise sqlite3.OperationalError("injected detection evidence migration failure")

    monkeypatch.setattr(
        project_store_module,
        "initialize_detection_evidence_schema",
        fail_migration,
    )

    outcome = store.migrate_project(project.project_id)

    assert outcome.status is ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (PROJECT_DETECTION_EVIDENCE_VERSION,),
        ).fetchone() is None
        assert connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'detection_evidence_partial_write'
            """
        ).fetchone() is None


def test_detection_evidence_migration_checksum_mismatch_fails_closed(tmp_path):
    store, project = _project(tmp_path)
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = 'tampered' WHERE version = ?",
            (PROJECT_DETECTION_EVIDENCE_VERSION,),
        )

    assert (
        store.open_project(project.project_id).status
        is ProjectOpenStatus.CHECKSUM_MISMATCH
    )
    assert (
        store.migrate_project(project.project_id).status
        is ProjectOpenStatus.CHECKSUM_MISMATCH
    )


def test_project_missing_completion_v3_and_detection_v4_migrates_in_order(tmp_path):
    store, project = _project(tmp_path)
    _remove_detection_evidence_schema(project.project_db_path)
    with sqlite3.connect(project.project_db_path) as connection:
        for table in reversed(COMPLETION_TABLES):
            connection.execute(f"DROP TABLE {table}")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            (PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,),
        )

    assert (
        store.open_project(project.project_id).status
        is ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED
    )
    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.READY


def _project(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Detection migration",
        source_language="ja",
        target_language="zh-Hans",
    )
    return store, project


def _remove_detection_evidence_schema(project_db_path):
    with sqlite3.connect(project_db_path) as connection:
        connection.execute("DROP TABLE detection_evidence_acceptance_provenance")
        connection.execute("DROP TABLE accepted_detection_evidence_members")
        connection.execute("DROP TABLE accepted_detection_evidence_sets")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            (PROJECT_DETECTION_EVIDENCE_VERSION,),
        )
