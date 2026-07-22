from __future__ import annotations

import sqlite3

from manga_read_flow.persistence import project_store as project_store_module
from manga_read_flow.persistence.project_store import (
    AppStore,
    PROJECT_DETECTION_EVIDENCE_VERSION,
    PROJECT_GROUPING_CANDIDATE_CHECKSUM,
    PROJECT_GROUPING_CANDIDATE_REQUIRED_SCHEMA_OBJECTS,
    PROJECT_GROUPING_CANDIDATE_VERSION,
    ProjectOpenStatus,
)


FORBIDDEN_TABLES = {
    "grouping_stale_facts",
}


def test_fresh_project_records_v5_migration_without_acceptance_or_pointer(tmp_path):
    store, project = _project(tmp_path)

    opened = store.open_project(project.project_id)

    assert opened.status is ProjectOpenStatus.READY
    assert PROJECT_GROUPING_CANDIDATE_VERSION in {
        migration.version for migration in opened.project_migrations
    }
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (PROJECT_GROUPING_CANDIDATE_VERSION,),
        ).fetchone() == (PROJECT_GROUPING_CANDIDATE_CHECKSUM,)
        for object_type, name in PROJECT_GROUPING_CANDIDATE_REQUIRED_SCHEMA_OBJECTS:
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


def test_existing_v4_project_upgrades_without_backfill_or_data_loss(tmp_path):
    store, project = _project(tmp_path)
    repositories = store.open_project(project.project_id).repositories()
    repositories.workflow_execution.ensure_profile_snapshot(
        profile_snapshot_id="preserved-profile",
        settings_json='{"profile":"preserved"}',
        settings_hash=(
            "fb12905630fa29d0e3057309d82f72eb20add91433a3a071e8f446a55d070264"
        ),
    )
    _remove_grouping_schema(project.project_db_path)

    assert (
        store.open_project(project.project_id).status
        is ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED
    )
    migrated = store.migrate_project(project.project_id)

    assert migrated.status is ProjectOpenStatus.READY
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT settings_json FROM processing_profile_snapshots "
            "WHERE profile_snapshot_id = 'preserved-profile'"
        ).fetchone() == ('{"profile":"preserved"}',)
        assert connection.execute(
            "SELECT count(*) FROM frozen_grouping_evidence_snapshots"
        ).fetchone() == (0,)


def test_missing_v4_and_v5_migrate_in_order(tmp_path):
    store, project = _project(tmp_path)
    _remove_grouping_schema(project.project_db_path)
    with sqlite3.connect(project.project_db_path) as connection:
        for table in (
            "detection_evidence_acceptance_provenance",
            "accepted_detection_evidence_members",
            "accepted_detection_evidence_sets",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            (PROJECT_DETECTION_EVIDENCE_VERSION,),
        )

    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.READY
    with sqlite3.connect(project.project_db_path) as connection:
        versions = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
    assert {PROJECT_DETECTION_EVIDENCE_VERSION, PROJECT_GROUPING_CANDIDATE_VERSION} <= versions


def test_v5_migration_failure_rolls_back_ddl_and_marker(tmp_path, monkeypatch):
    store, project = _project(tmp_path)
    _remove_grouping_schema(project.project_db_path)

    def fail_migration(connection):
        connection.execute(
            "CREATE TABLE grouping_candidate_partial_write (id TEXT PRIMARY KEY)"
        )
        raise sqlite3.OperationalError("injected grouping migration failure")

    monkeypatch.setattr(
        project_store_module,
        "initialize_grouping_snapshot_schema",
        fail_migration,
    )

    outcome = store.migrate_project(project.project_id)

    assert outcome.status is ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (PROJECT_GROUPING_CANDIDATE_VERSION,),
        ).fetchone() is None
        assert connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'grouping_candidate_partial_write'
            """
        ).fetchone() is None


def test_v5_checksum_mismatch_fails_closed(tmp_path):
    store, project = _project(tmp_path)
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = 'tampered' WHERE version = ?",
            (PROJECT_GROUPING_CANDIDATE_VERSION,),
        )

    assert store.open_project(project.project_id).status is ProjectOpenStatus.CHECKSUM_MISMATCH
    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.CHECKSUM_MISMATCH


def _project(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Grouping migration",
        source_language="ja",
        target_language="zh-Hans",
    )
    return store, project


def _remove_grouping_schema(project_db_path):
    with sqlite3.connect(project_db_path) as connection:
        connection.execute("DROP TABLE grouping_generation_runs")
        connection.execute("DROP TABLE grouping_snapshot_ocr_dependencies")
        connection.execute("DROP TABLE frozen_grouping_evidence_snapshots")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            (PROJECT_GROUPING_CANDIDATE_VERSION,),
        )
