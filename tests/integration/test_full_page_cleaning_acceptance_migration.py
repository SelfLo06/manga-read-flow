from __future__ import annotations

import sqlite3

import pytest

from manga_read_flow.persistence import project_store as project_store_module
from manga_read_flow.persistence.project_store import (
    AppStore,
    PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_CHECKSUM,
    PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,
    PROJECT_FULL_PAGE_CLEANING_LEDGER_CHECKSUM,
    PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,
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


def _new_project(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="迁移测试",
        source_language="ja",
        target_language="zh-CN",
    )
    return store, project


def _migration_rows(project_db_path):
    with sqlite3.connect(project_db_path) as connection:
        return connection.execute(
            "SELECT version, checksum FROM schema_migrations ORDER BY applied_at, version"
        ).fetchall()


def _make_foundation_only(project_db_path):
    with sqlite3.connect(project_db_path) as connection:
        for table in reversed(COMPLETION_TABLES):
            connection.execute(f"DROP TABLE {table}")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            (PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,),
        )


def test_fresh_project_records_ordered_foundation_and_completion_migrations(tmp_path):
    store, project = _new_project(tmp_path)

    opened = store.open_project(project.project_id)
    rows = _migration_rows(project.project_db_path)

    versions = [row[0] for row in rows]
    assert opened.status is ProjectOpenStatus.READY
    assert opened.metadata.project_schema_version == PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION
    assert versions.index(PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION) < versions.index(
        PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION
    )
    assert (PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION, PROJECT_FULL_PAGE_CLEANING_LEDGER_CHECKSUM) in rows
    assert (
        PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,
        PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_CHECKSUM,
    ) in rows
    with sqlite3.connect(project.project_db_path) as connection:
        for table in COMPLETION_TABLES:
            assert connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone() == (1,)


def test_foundation_only_project_requires_then_applies_completion_without_data_loss(tmp_path):
    store, project = _new_project(tmp_path)
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            """
            INSERT INTO page_cleaning_runs (
                page_cleaning_run_id, project_id, batch_id, page_id,
                visual_contract_revision_id, source_artifact_id, source_hash,
                profile_snapshot_id, config_hash, idempotency_key, status,
                supersedes_run_id, stale_by_dependency_fingerprint, created_at
            ) VALUES ('foundation-run', ?, 'batch', 'page', 'visual', 'source',
                      'source-hash', NULL, 'config', 'foundation-key', 'planned',
                      NULL, NULL, '2026-07-18T00:00:00+00:00')
            """,
            (project.project_id,),
        )
    _make_foundation_only(project.project_db_path)

    before = dict(_migration_rows(project.project_db_path))
    readiness = store.open_project(project.project_id)
    migrated = store.migrate_project(project.project_id)
    after = dict(_migration_rows(project.project_db_path))

    assert readiness.status is ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED
    assert migrated.status is ProjectOpenStatus.READY
    assert before[PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION] == PROJECT_FULL_PAGE_CLEANING_LEDGER_CHECKSUM
    assert after[PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION] == before[PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION]
    assert after[PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION] == PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_CHECKSUM
    assert migrated.metadata.project_schema_version == PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT status FROM page_cleaning_runs WHERE page_cleaning_run_id = 'foundation-run'"
        ).fetchone() == ("planned",)


def test_full_v3_reopen_and_migrate_are_idempotent(tmp_path):
    store, project = _new_project(tmp_path)
    before = _migration_rows(project.project_db_path)

    assert store.open_project(project.project_id).status is ProjectOpenStatus.READY
    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.READY
    assert store.open_project(project.project_id).status is ProjectOpenStatus.READY

    assert _migration_rows(project.project_db_path) == before


@pytest.mark.parametrize(
    "version",
    [
        PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,
        PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,
    ],
)
def test_each_v3_migration_checksum_mismatch_blocks_readiness(tmp_path, version):
    store, project = _new_project(tmp_path)
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = 'tampered' WHERE version = ?",
            (version,),
        )

    assert store.open_project(project.project_id).status is ProjectOpenStatus.CHECKSUM_MISMATCH
    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.CHECKSUM_MISMATCH


def test_completion_migration_failure_rolls_back_ddl_and_marker(tmp_path, monkeypatch):
    store, project = _new_project(tmp_path)
    _make_foundation_only(project.project_db_path)

    def fail_during_completion(connection):
        connection.execute("CREATE TABLE completion_partial_write (id TEXT PRIMARY KEY)")
        raise sqlite3.OperationalError("injected completion migration failure")

    monkeypatch.setattr(
        project_store_module,
        "initialize_full_page_cleaning_acceptance_schema",
        fail_during_completion,
    )

    outcome = store.migrate_project(project.project_id)

    assert outcome.status is ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,),
        ).fetchone() is None
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'completion_partial_write'"
        ).fetchone() is None
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,),
        ).fetchone() == (PROJECT_FULL_PAGE_CLEANING_LEDGER_CHECKSUM,)


def test_malformed_preexisting_completion_table_never_receives_success_marker(tmp_path):
    store, project = _new_project(tmp_path)
    _make_foundation_only(project.project_db_path)
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "CREATE TABLE combined_cleaning_candidates (wrong_column TEXT PRIMARY KEY)"
        )

    outcome = store.migrate_project(project.project_id)

    assert outcome.status is ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,),
        ).fetchone() is None
        assert connection.execute(
            "PRAGMA table_info(combined_cleaning_candidates)"
        ).fetchall()[0][1] == "wrong_column"


def test_future_schema_is_not_downgraded_or_unknown_marker_deleted(tmp_path):
    store, project = _new_project(tmp_path)
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "UPDATE project_metadata SET project_schema_version = 'project_future_v9'"
        )
        connection.execute(
            "INSERT INTO schema_migrations(version, checksum, applied_at) "
            "VALUES ('project_future_v9', 'future-checksum', '2026-07-18T00:00:00+00:00')"
        )

    outcome = store.migrate_project(project.project_id)

    assert outcome.status is ProjectOpenStatus.NEWER_INCOMPATIBLE_SCHEMA
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = 'project_future_v9'"
        ).fetchone() == ("future-checksum",)
        assert connection.execute(
            "SELECT project_schema_version FROM project_metadata"
        ).fetchone() == ("project_future_v9",)
