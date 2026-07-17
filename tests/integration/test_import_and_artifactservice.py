from __future__ import annotations

import sqlite3
import struct
import zlib
from pathlib import Path

import pytest

from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService
from manga_read_flow.application.import_page import ImportPageCommitError
from manga_read_flow.artifacts.service import ArtifactRegistrationError
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.persistence.project_store import AppStore, ProjectOpenStatus


def test_tiny_png_imports_one_page_and_keeps_bytes_in_workspace_not_sqlite(tmp_path):
    project, repositories = _ready_project(tmp_path)
    source_png = tmp_path / "incoming" / "page.png"
    source_png.parent.mkdir()
    source_png.write_bytes(_tiny_png(width=8, height=8))

    artifact_service = ArtifactService(
        project_id=project.project_id,
        project_workspace_path=project.workspace_path,
        artifact_repository=repositories.artifact_metadata,
    )
    import_service = ImportPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
    )

    imported = import_service.import_page(
        ImportPageCommand(
            source_path=source_png,
            batch_name="Imported pages",
            page_index=1,
        )
    )

    artifact = imported.original_artifact
    page = imported.page
    official_path = project.workspace_path / artifact.relative_path

    assert official_path.is_file()
    assert official_path.read_bytes() == source_png.read_bytes()
    assert not Path(artifact.relative_path).is_absolute()
    assert artifact.relative_path.startswith("originals/")
    assert artifact.artifact_type == "original_image"
    assert artifact.source_stage == "import"
    assert artifact.storage_state == "present"
    assert artifact.retention_class == "permanent_original"
    assert artifact.mime_type == "image/png"
    assert artifact.byte_size == len(source_png.read_bytes())
    assert artifact.width == 8
    assert artifact.height == 8
    assert artifact.may_contain_original_image
    assert page.original_artifact_id == artifact.artifact_id
    assert page.status == "uploaded"

    with sqlite3.connect(project.project_db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT
                artifact_type,
                relative_path,
                file_hash,
                hash_algorithm,
                byte_size,
                mime_type,
                width,
                height,
                retention_class,
                storage_state
            FROM processing_artifacts
            WHERE artifact_id = ?
            """,
            (artifact.artifact_id,),
        ).fetchone()

    assert row is not None
    assert row["artifact_type"] == "original_image"
    assert row["relative_path"] == artifact.relative_path
    assert row["file_hash"] == artifact.file_hash
    assert row["hash_algorithm"] == "sha256"
    assert row["byte_size"] == len(source_png.read_bytes())
    assert row["mime_type"] == "image/png"
    assert row["width"] == 8
    assert row["height"] == 8
    assert row["retention_class"] == "permanent_original"
    assert row["storage_state"] == "present"
    assert source_png.read_bytes() not in project.project_db_path.read_bytes()


def test_duplicate_original_filenames_create_distinct_paths_without_overwrite(tmp_path):
    project, repositories = _ready_project(tmp_path)
    import_service, _artifact_service = _import_services(project, repositories)
    first_source = tmp_path / "first" / "page.png"
    second_source = tmp_path / "second" / "page.png"
    first_source.parent.mkdir()
    second_source.parent.mkdir()
    first_source.write_bytes(_tiny_png(width=8, height=8))
    second_source.write_bytes(_tiny_png(width=16, height=16))

    first = import_service.import_page(
        ImportPageCommand(
            source_path=first_source,
            batch_id="batch-duplicates",
            batch_name="Duplicates",
            page_id="page-duplicate-1",
            page_index=1,
        )
    )
    second = import_service.import_page(
        ImportPageCommand(
            source_path=second_source,
            batch_id="batch-duplicates",
            batch_name="Duplicates",
            page_id="page-duplicate-2",
            page_index=2,
        )
    )

    first_path = project.workspace_path / first.original_artifact.relative_path
    second_path = project.workspace_path / second.original_artifact.relative_path

    assert first.original_artifact.relative_path != second.original_artifact.relative_path
    assert first_path.read_bytes() == first_source.read_bytes()
    assert second_path.read_bytes() == second_source.read_bytes()
    assert first.batch.batch_id == second.batch.batch_id
    assert second.batch.page_count == 2


def test_path_traversal_original_filename_is_rejected(tmp_path):
    project, repositories = _ready_project(tmp_path)
    import_service, _artifact_service = _import_services(project, repositories)
    source_png = tmp_path / "page.png"
    source_png.write_bytes(_tiny_png(width=8, height=8))

    with pytest.raises(ArtifactRegistrationError):
        import_service.import_page(
            ImportPageCommand(
                source_path=source_png,
                batch_name="Traversal",
                page_index=1,
                original_filename="../page.png",
            )
        )


def test_unsupported_extension_and_invalid_image_are_rejected(tmp_path):
    project, repositories = _ready_project(tmp_path)
    import_service, _artifact_service = _import_services(project, repositories)
    unsupported = tmp_path / "page.gif"
    invalid_png = tmp_path / "invalid.png"
    unsupported.write_bytes(_tiny_png(width=8, height=8))
    invalid_png.write_bytes(b"not a valid image")

    with pytest.raises(ArtifactRegistrationError):
        import_service.import_page(
            ImportPageCommand(
                source_path=unsupported,
                batch_name="Unsupported",
                page_index=1,
            )
        )

    with pytest.raises(ArtifactRegistrationError):
        import_service.import_page(
            ImportPageCommand(
                source_path=invalid_png,
                batch_name="Invalid",
                page_index=1,
            )
        )


def test_deleted_original_artifact_reports_missing_and_updates_storage_state(tmp_path):
    project, repositories = _ready_project(tmp_path)
    import_service, artifact_service = _import_services(project, repositories)
    source_png = tmp_path / "page.png"
    source_png.write_bytes(_tiny_png(width=8, height=8))
    imported = import_service.import_page(
        ImportPageCommand(
            source_path=source_png,
            batch_name="Missing",
            page_index=1,
        )
    )
    (project.workspace_path / imported.original_artifact.relative_path).unlink()

    report = artifact_service.validate_artifact(
        imported.original_artifact.artifact_id,
        expected_use="recovery",
        active_reference="page.original_artifact_id",
    )
    artifact_after_validation = repositories.artifact_metadata.get_artifact(
        imported.original_artifact.artifact_id
    )

    assert report.integrity_status == "missing_path"
    assert report.observed_state == "missing"
    assert report.relative_path == imported.original_artifact.relative_path
    assert report.rebuildability_hint == "non_rebuildable"
    assert artifact_after_validation.storage_state == "missing"


def test_corrupt_original_artifact_reports_hash_mismatch_and_updates_storage_state(tmp_path):
    project, repositories = _ready_project(tmp_path)
    import_service, artifact_service = _import_services(project, repositories)
    source_png = tmp_path / "page.png"
    source_png.write_bytes(_tiny_png(width=8, height=8))
    imported = import_service.import_page(
        ImportPageCommand(
            source_path=source_png,
            batch_name="Corrupt",
            page_index=1,
        )
    )
    official_path = project.workspace_path / imported.original_artifact.relative_path
    official_path.write_bytes(_tiny_png(width=4, height=4))

    report = artifact_service.validate_artifact(
        imported.original_artifact.artifact_id,
        expected_use="recovery",
    )
    artifact_after_validation = repositories.artifact_metadata.get_artifact(
        imported.original_artifact.artifact_id
    )

    assert report.integrity_status == "hash_mismatch"
    assert report.observed_state == "missing"
    assert report.expected_hash == imported.original_artifact.file_hash
    assert report.observed_hash != imported.original_artifact.file_hash
    assert artifact_after_validation.storage_state == "missing"


def test_import_transaction_failure_leaves_artifact_but_no_imported_page(tmp_path):
    project, repositories = _ready_project(tmp_path)
    import_service, _artifact_service = _import_services(project, repositories)
    first_source = tmp_path / "first.png"
    second_source = tmp_path / "second.png"
    first_source.write_bytes(_tiny_png(width=8, height=8))
    second_source.write_bytes(_tiny_png(width=16, height=16))

    import_service.import_page(
        ImportPageCommand(
            source_path=first_source,
            batch_id="batch-rollback",
            batch_name="Rollback",
            page_id="page-existing",
            page_index=1,
        )
    )

    with pytest.raises(ImportPageCommitError) as error:
        import_service.import_page(
            ImportPageCommand(
                source_path=second_source,
                batch_id="batch-rollback",
                batch_name="Rollback",
                page_id="page-not-imported",
                page_index=1,
            )
        )

    failed_artifact = error.value.original_artifact
    with sqlite3.connect(project.project_db_path) as connection:
        artifact_count = connection.execute(
            "SELECT COUNT(*) FROM processing_artifacts WHERE artifact_id = ?",
            (failed_artifact.artifact_id,),
        ).fetchone()[0]
        page_count = connection.execute(
            "SELECT COUNT(*) FROM pages WHERE page_id = ?",
            ("page-not-imported",),
        ).fetchone()[0]

    assert artifact_count == 1
    assert page_count == 0
    assert (project.workspace_path / failed_artifact.relative_path).is_file()


def test_artifact_service_promotes_json_evidence_without_image_inspection(tmp_path):
    project, repositories = _ready_project(tmp_path)
    _, artifact_service = _import_services(project, repositories)
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"decision":"pass"}\n', encoding="utf-8")

    artifact = artifact_service.register_stage_json(
        temp_path=evidence,
        batch_id="batch-json",
        page_id="page-json",
        owner_type="cleaning_result",
        owner_id="result-json",
        artifact_type="validation_evidence",
        source_stage="cleaning",
    )

    assert artifact.mime_type == "application/json"
    assert (project.workspace_path / artifact.relative_path).read_text(encoding="utf-8") == evidence.read_text(encoding="utf-8")


def _ready_project(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(
        name="Artifact Import",
        source_language="ja",
        target_language="zh-Hans",
    )
    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.READY
    return created, opened.repositories()


def _import_services(project, repositories):
    artifact_service = ArtifactService(
        project_id=project.project_id,
        project_workspace_path=project.workspace_path,
        artifact_repository=repositories.artifact_metadata,
    )
    import_service = ImportPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
    )
    return import_service, artifact_service


def _tiny_png(*, width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw_rows = b"".join(b"\x00" + (b"\xff\x00\x00" * width) for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw_rows))
        + chunk(b"IEND", b"")
    )
