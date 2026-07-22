from __future__ import annotations

import json
import sqlite3
import struct
import zlib
from dataclasses import replace

import pytest

from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService
from manga_read_flow.application.process_page import ProcessPageCommand, ProcessPageService
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.domain.detection_evidence import (
    AcceptedDetectionEvidenceSetDraft,
    DetectionEvidenceAcceptanceProvenanceDraft,
)
from manga_read_flow.persistence.acceptance_repository import AcceptedTextBlock
from manga_read_flow.persistence.detection_evidence_repository import (
    persist_detection_evidence_set,
)
from manga_read_flow.persistence.project_store import AppStore, ProjectOpenStatus
from manga_read_flow.providers.fake import FakeProvider


def test_formal_process_page_entry_persists_exact_detection_handoff(tmp_path):
    project, repositories, artifact_service, imported = _imported_page(tmp_path)
    service = _process_service(project, repositories, artifact_service)

    result = service.process_page(ProcessPageCommand(page_id=imported.page.page_id))

    assert result.task_status == "succeeded"
    with _connection(project.project_db_path) as connection:
        dependency_id = connection.execute(
            "SELECT detection_dependency_id FROM accepted_detection_evidence_sets"
        ).fetchone()[0]
        decision = connection.execute(
            "SELECT decision_id, attempt_id FROM workflow_decisions WHERE stage = 'detection'"
        ).fetchone()
        columns = {
            row[1]
            for table in ("pages", "accepted_detection_evidence_sets")
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }

    evidence = repositories.detection_evidence.get(dependency_id)
    manifest = repositories.artifact_metadata.get_artifact(evidence.manifest_artifact_id)
    manifest_payload = json.loads(
        (project.workspace_path / manifest.relative_path).read_text(encoding="utf-8")
    )

    assert dependency_id == f"detection-set-v1:{manifest.file_hash}"
    assert evidence.source_artifact_id == imported.original_artifact.artifact_id
    assert evidence.source_sha256 == imported.original_artifact.file_hash
    assert evidence.canonical_manifest_sha256 == manifest.file_hash
    assert tuple(member.text_block_id for member in evidence.members) == (
        "tb-page-detection-001",
        "tb-page-detection-002",
    )
    assert manifest_payload["member_count"] == 2
    assert tuple(item["text_block_id"] for item in manifest_payload["members"]) == (
        "tb-page-detection-001",
        "tb-page-detection-002",
    )
    assert manifest_payload["source_sha256"] == imported.original_artifact.file_hash
    assert manifest_payload["provider_implementation"]["tool_version"] == "0.1"
    assert evidence.provenance[0].workflow_decision_id == decision["decision_id"]
    assert evidence.provenance[0].workflow_attempt_id == decision["attempt_id"]
    assert evidence.provenance[0].provider_execution_reference is not None
    assert "active_detection_evidence_set_id" not in columns
    assert "current_detection_set" not in columns


def test_existing_auxiliary_text_block_is_not_in_formally_accepted_set(tmp_path):
    project, repositories, artifact_service, imported = _imported_page(tmp_path)
    repositories.content_state.create_text_block(
        text_block_id="auxiliary-old-row",
        page_id=imported.page.page_id,
        reading_order=99,
        ocr_status="pending",
        translation_status="pending",
    )
    with _connection(project.project_db_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER stop_before_ocr
            BEFORE INSERT ON workflow_attempts
            WHEN NEW.stage = 'ocr'
            BEGIN
                SELECT RAISE(ABORT, 'stop after detection acceptance');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="stop after detection"):
        _process_service(project, repositories, artifact_service).process_page(
            ProcessPageCommand(page_id=imported.page.page_id)
        )

    with _connection(project.project_db_path) as connection:
        dependency_id = connection.execute(
            "SELECT detection_dependency_id FROM accepted_detection_evidence_sets"
        ).fetchone()[0]
    evidence = repositories.detection_evidence.get(dependency_id)

    assert tuple(member.text_block_id for member in evidence.members) == (
        "tb-page-detection-001",
        "tb-page-detection-002",
    )
    assert "auxiliary-old-row" not in {
        member.text_block_id for member in evidence.members
    }


def test_detection_acceptance_rollback_leaves_only_orphan_manifest(tmp_path):
    project, repositories, artifact_service, imported = _imported_page(tmp_path)
    with _connection(project.project_db_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_detection_decision
            BEFORE INSERT ON workflow_decisions
            WHEN NEW.stage = 'detection'
            BEGIN
                SELECT RAISE(ABORT, 'injected detection transaction failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected detection"):
        _process_service(project, repositories, artifact_service).process_page(
            ProcessPageCommand(page_id=imported.page.page_id)
        )

    with _connection(project.project_db_path) as connection:
        assert connection.execute("SELECT count(*) FROM text_blocks").fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM accepted_detection_evidence_sets"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM accepted_detection_evidence_members"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM detection_evidence_acceptance_provenance"
        ).fetchone()[0] == 0
        manifests = connection.execute(
            """
            SELECT artifact_id, storage_state
            FROM processing_artifacts
            WHERE artifact_type = 'accepted_detection_evidence_manifest'
            """
        ).fetchall()
    assert len(manifests) == 1
    assert manifests[0]["storage_state"] == "present"


def test_formal_replay_reuses_semantic_identity_and_adds_provenance(tmp_path):
    project, repositories, artifact_service, imported = _imported_page(tmp_path)
    service = _process_service(project, repositories, artifact_service)

    first = service.process_page(ProcessPageCommand(page_id=imported.page.page_id))
    second = service.process_page(ProcessPageCommand(page_id=imported.page.page_id))

    assert first.task_status == second.task_status == "succeeded"
    with _connection(project.project_db_path) as connection:
        sets = connection.execute(
            "SELECT detection_dependency_id, manifest_artifact_id FROM accepted_detection_evidence_sets"
        ).fetchall()
        provenance = connection.execute(
            """
            SELECT workflow_attempt_id, workflow_decision_id
            FROM detection_evidence_acceptance_provenance
            ORDER BY accepted_at, acceptance_id
            """
        ).fetchall()
        manifest_count = connection.execute(
            """
            SELECT count(*) FROM processing_artifacts
            WHERE artifact_type = 'accepted_detection_evidence_manifest'
            """
        ).fetchone()[0]

    assert len(sets) == 1
    assert manifest_count == 1
    assert len(provenance) == 2
    assert len({row["workflow_attempt_id"] for row in provenance}) == 2
    assert len({row["workflow_decision_id"] for row in provenance}) == 2
    evidence = repositories.detection_evidence.get(sets[0]["detection_dependency_id"])
    assert evidence.manifest_artifact_id == sets[0]["manifest_artifact_id"]
    assert len(evidence.provenance) == 2


def test_repository_read_fails_closed_on_tampering_and_project_mismatch(tmp_path):
    project, repositories, artifact_service, imported = _imported_page(tmp_path)
    _process_service(project, repositories, artifact_service).process_page(
        ProcessPageCommand(page_id=imported.page.page_id)
    )
    with _connection(project.project_db_path) as connection:
        dependency_id, manifest_artifact_id = connection.execute(
            """
            SELECT detection_dependency_id, manifest_artifact_id
            FROM accepted_detection_evidence_sets
            """
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """
                UPDATE accepted_detection_evidence_sets
                SET canonical_member_count = canonical_member_count + 1
                WHERE detection_dependency_id = ?
                """,
                (dependency_id,),
            )
        connection.execute(
            "UPDATE processing_artifacts SET file_hash = ? WHERE artifact_id = ?",
            ("f" * 64, manifest_artifact_id),
        )

    with pytest.raises(ValueError, match="artifact/source binding"):
        repositories.detection_evidence.get(dependency_id)

    other_store = AppStore.initialize(tmp_path / "other-workspace")
    other_project = other_store.create_project(
        name="Other project",
        source_language="ja",
        target_language="zh-Hans",
    )
    other_repositories = other_store.open_project(other_project.project_id).repositories()
    with pytest.raises(LookupError, match="not found"):
        other_repositories.detection_evidence.get(dependency_id)


def test_persistence_rejects_member_count_page_and_manifest_mismatches(tmp_path):
    project, repositories, artifact_service, imported = _imported_page(tmp_path)
    _process_service(project, repositories, artifact_service).process_page(
        ProcessPageCommand(page_id=imported.page.page_id)
    )
    with _connection(project.project_db_path) as connection:
        dependency_id = connection.execute(
            "SELECT detection_dependency_id FROM accepted_detection_evidence_sets"
        ).fetchone()[0]
        rows = connection.execute(
            """
            SELECT text_block_id, page_id, reading_order, bbox_json, polygon_json,
                   geometry_hash, detection_provider, detection_confidence
            FROM text_blocks
            WHERE text_block_id IN (
                SELECT text_block_id FROM accepted_detection_evidence_members
                WHERE detection_dependency_id = ?
            )
            """,
            (dependency_id,),
        ).fetchall()
        evidence = repositories.detection_evidence.get(dependency_id)
        accepted_blocks = tuple(
            AcceptedTextBlock(
                text_block_id=row["text_block_id"],
                page_id=row["page_id"],
                reading_order=row["reading_order"],
                bbox_json=row["bbox_json"],
                polygon_json=row["polygon_json"],
                geometry_hash=row["geometry_hash"],
                detection_provider=row["detection_provider"],
                detection_confidence=row["detection_confidence"],
            )
            for row in rows
        )
        draft = AcceptedDetectionEvidenceSetDraft(
            detection_dependency_id=evidence.detection_dependency_id,
            project_id=evidence.project_id,
            page_id=evidence.page_id,
            source_artifact_id=evidence.source_artifact_id,
            source_sha256=evidence.source_sha256,
            coordinate_space_json=evidence.coordinate_space_json,
            canonical_member_count=evidence.canonical_member_count,
            manifest_artifact_id=evidence.manifest_artifact_id,
            canonical_manifest_sha256=evidence.canonical_manifest_sha256,
            schema_version=evidence.schema_version,
            member_ids=tuple(member.text_block_id for member in evidence.members),
            provenance=DetectionEvidenceAcceptanceProvenanceDraft(
                acceptance_id=evidence.provenance[0].acceptance_id,
                workflow_attempt_id=evidence.provenance[0].workflow_attempt_id,
                workflow_decision_id=evidence.provenance[0].workflow_decision_id,
                provider_execution_reference=(
                    evidence.provenance[0].provider_execution_reference
                ),
            ),
        )

        persist_detection_evidence_set(
            connection,
            project.project_id,
            draft,
            accepted_blocks,
        )
        with pytest.raises(ValueError, match="member count"):
            persist_detection_evidence_set(
                connection,
                project.project_id,
                replace(draft, canonical_member_count=3),
                accepted_blocks,
            )
        with pytest.raises(ValueError, match="exact acceptance command"):
            persist_detection_evidence_set(
                connection,
                project.project_id,
                replace(
                    draft,
                    canonical_member_count=1,
                    member_ids=draft.member_ids[:1],
                ),
                accepted_blocks,
            )
        with pytest.raises(ValueError, match="page binding"):
            persist_detection_evidence_set(
                connection,
                project.project_id,
                replace(draft, page_id="other-page"),
                accepted_blocks,
            )
        with pytest.raises(ValueError, match="source artifact binding"):
            persist_detection_evidence_set(
                connection,
                project.project_id,
                replace(draft, source_sha256="f" * 64),
                accepted_blocks,
            )


def _imported_page(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Detection handoff",
        source_language="ja",
        target_language="zh-Hans",
    )
    opened = store.open_project(project.project_id)
    assert opened.status is ProjectOpenStatus.READY
    repositories = opened.repositories()
    artifact_service = ArtifactService(
        project_id=project.project_id,
        project_workspace_path=project.workspace_path,
        artifact_repository=repositories.artifact_metadata,
    )
    source = tmp_path / "incoming" / "page.png"
    source.parent.mkdir()
    source.write_bytes(_tiny_png(width=32, height=24))
    imported = ImportPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
    ).import_page(
        ImportPageCommand(
            source_path=source,
            batch_id="batch-detection",
            batch_name="Detection",
            page_id="page-detection",
            page_index=1,
        )
    )
    return project, repositories, artifact_service, imported


def _process_service(project, repositories, artifact_service):
    return ProcessPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        provider=FakeProvider.happy_path(),
    )


def _connection(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _tiny_png(*, width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = b"".join(b"\x00" + (b"\xff\x00\x00" * width) for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
