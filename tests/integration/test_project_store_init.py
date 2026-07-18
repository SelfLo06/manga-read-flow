import sqlite3
import shutil

import pytest

from manga_read_flow.persistence.project_store import (
    AppStore,
    ProjectOpenStatus,
    ProjectStoreNotReadyError,
)


def test_app_store_initializes_temporary_app_db_and_migration_ledger(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")

    assert store.is_ready
    assert store.app_db_path == tmp_path / "workspace" / "app.db"
    assert store.app_db_path.is_file()

    migrations = store.app_migrations()

    assert [migration.version for migration in migrations] == ["app_baseline_v1"]
    assert all(migration.checksum for migration in migrations)


def test_project_creation_initializes_project_db_identity_and_ready_repositories(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")

    created = store.create_project(
        name="Reader Project",
        source_language="ja",
        target_language="zh-Hans",
    )

    assert created.project_id
    assert created.workspace_path.is_dir()
    assert created.project_db_path == created.workspace_path / "project.db"
    assert created.project_db_path.is_file()

    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.READY
    assert opened.project_id == created.project_id
    assert opened.metadata.project_id == created.project_id
    assert [migration.version for migration in opened.project_migrations] == [
        "project_baseline_v1",
        "project_visual_contract_v2",
        "project_full_page_cleaning_ledger_v3",
    ]
    assert opened.repositories().identity.get_metadata().project_id == created.project_id


def test_existing_v1_project_requires_and_can_apply_visual_contract_migration(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(name="Upgrade", source_language="ja", target_language="zh-Hans")
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version = ?", ("project_visual_contract_v2",))
        connection.execute("DROP TABLE cleaning_result_records")
    assert store.open_project(project.project_id).status is ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED
    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.READY



def test_project_store_keeps_second_project_isolated(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")

    first = store.create_project(name="First", source_language="ja", target_language="zh-Hans")
    second = store.create_project(name="Second", source_language="ja", target_language="zh-Hans")

    assert first.project_id != second.project_id
    assert first.workspace_path != second.workspace_path
    assert first.project_db_path != second.project_db_path

    first_open = store.open_project(first.project_id)
    second_open = store.open_project(second.project_id)

    assert first_open.status is ProjectOpenStatus.READY
    assert second_open.status is ProjectOpenStatus.READY
    assert first_open.repositories().identity.get_metadata().project_id == first.project_id
    assert second_open.repositories().identity.get_metadata().project_id == second.project_id


def test_missing_project_db_blocks_project_repositories(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(name="Missing DB", source_language="ja", target_language="zh-Hans")
    created.project_db_path.unlink()

    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.DATABASE_MISSING
    assert opened.metadata is None

    with pytest.raises(ProjectStoreNotReadyError):
        opened.repositories()


def test_project_metadata_identity_mismatch_blocks_project_repositories(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(name="Mismatch", source_language="ja", target_language="zh-Hans")

    with sqlite3.connect(created.project_db_path) as connection:
        connection.execute(
            "UPDATE project_metadata SET project_id = ?",
            ("different-project-id",),
        )

    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.IDENTITY_MISMATCH

    with pytest.raises(ProjectStoreNotReadyError):
        opened.repositories()


def test_project_migration_checksum_mismatch_blocks_project_repositories(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(name="Checksum", source_language="ja", target_language="zh-Hans")

    with sqlite3.connect(created.project_db_path) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = ?",
            ("tampered-checksum", "project_baseline_v1"),
        )

    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.CHECKSUM_MISMATCH

    with pytest.raises(ProjectStoreNotReadyError):
        opened.repositories()


def test_app_migration_checksum_mismatch_blocks_project_open(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(name="App Checksum", source_language="ja", target_language="zh-Hans")

    with sqlite3.connect(store.app_db_path) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = ?",
            ("tampered-checksum", "app_baseline_v1"),
        )

    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.CHECKSUM_MISMATCH

    with pytest.raises(ProjectStoreNotReadyError):
        opened.repositories()


def test_app_migration_missing_marker_blocks_project_open(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(name="App Missing", source_language="ja", target_language="zh-Hans")

    with sqlite3.connect(store.app_db_path) as connection:
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            ("app_baseline_v1",),
        )

    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.APP_MIGRATION_REQUIRED

    with pytest.raises(ProjectStoreNotReadyError):
        opened.repositories()


def test_registry_path_outside_workspace_blocks_project_open(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(name="Rogue Path", source_language="ja", target_language="zh-Hans")
    rogue_project_db = tmp_path / "rogue" / "project.db"
    rogue_project_db.parent.mkdir()
    shutil.copy2(created.project_db_path, rogue_project_db)

    with sqlite3.connect(store.app_db_path) as connection:
        connection.execute(
            "UPDATE projects SET project_db_path = ? WHERE project_id = ?",
            (str(rogue_project_db), created.project_id),
        )

    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.REPAIR_REQUIRED

    with pytest.raises(ProjectStoreNotReadyError):
        opened.repositories()


def test_workspace_identity_mismatch_blocks_project_open(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(
        name="Workspace Identity",
        source_language="ja",
        target_language="zh-Hans",
    )

    with sqlite3.connect(created.project_db_path) as connection:
        connection.execute(
            "UPDATE project_metadata SET workspace_identity = ? WHERE project_id = ?",
            ("tampered-workspace-identity", created.project_id),
        )

    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.IDENTITY_MISMATCH

    with pytest.raises(ProjectStoreNotReadyError):
        opened.repositories()


def test_repository_access_after_project_db_removed_does_not_recreate_database(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(name="Deleted After Open", source_language="ja", target_language="zh-Hans")
    opened = store.open_project(created.project_id)
    repositories = opened.repositories()
    created.project_db_path.unlink()

    with pytest.raises(ProjectStoreNotReadyError):
        repositories.identity.get_metadata()

    assert not created.project_db_path.exists()
