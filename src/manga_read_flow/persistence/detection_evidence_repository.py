from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Protocol

from manga_read_flow.domain.detection_evidence import (
    AcceptedDetectionEvidenceSetDraft,
)
from manga_read_flow.persistence.sqlite_repository_helpers import (
    connect_existing,
    utc_now,
)


class AcceptedTextBlockLike(Protocol):
    text_block_id: str
    page_id: str
    reading_order: int
    bbox_json: str
    polygon_json: str
    geometry_hash: str
    detection_provider: str
    detection_confidence: float | None


@dataclass(frozen=True)
class AcceptedDetectionEvidenceMemberSnapshot:
    text_block_id: str
    canonical_ordinal: int


@dataclass(frozen=True)
class DetectionEvidenceAcceptanceProvenanceSnapshot:
    acceptance_id: str
    workflow_attempt_id: str
    workflow_decision_id: str
    provider_execution_reference: str | None
    accepted_at: str


@dataclass(frozen=True)
class AcceptedDetectionEvidenceSetSnapshot:
    detection_dependency_id: str
    project_id: str
    page_id: str
    source_artifact_id: str
    source_sha256: str
    coordinate_space_json: str
    canonical_member_count: int
    manifest_artifact_id: str
    canonical_manifest_sha256: str
    schema_version: str
    created_at: str
    members: tuple[AcceptedDetectionEvidenceMemberSnapshot, ...]
    provenance: tuple[DetectionEvidenceAcceptanceProvenanceSnapshot, ...]


class DetectionEvidenceRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def get(
        self,
        detection_dependency_id: str,
    ) -> AcceptedDetectionEvidenceSetSnapshot:
        with connect_existing(self._project_db_path) as connection:
            return _load_and_validate_evidence_set(
                connection,
                self._project_id,
                detection_dependency_id,
            )

    def get_optional(
        self,
        detection_dependency_id: str,
    ) -> AcceptedDetectionEvidenceSetSnapshot | None:
        with connect_existing(self._project_db_path) as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM accepted_detection_evidence_sets
                WHERE project_id = ? AND detection_dependency_id = ?
                """,
                (self._project_id, detection_dependency_id),
            ).fetchone()
            if row is None:
                return None
            return _load_and_validate_evidence_set(
                connection,
                self._project_id,
                detection_dependency_id,
            )


def persist_detection_evidence_set(
    connection: sqlite3.Connection,
    project_id: str,
    draft: AcceptedDetectionEvidenceSetDraft,
    accepted_text_blocks: tuple[AcceptedTextBlockLike, ...],
) -> None:
    if draft.project_id != project_id:
        raise ValueError("Detection evidence project binding is invalid.")
    if draft.canonical_member_count != len(draft.member_ids):
        raise ValueError("Detection evidence member count does not match its manifest.")
    if len(set(draft.member_ids)) != len(draft.member_ids):
        raise ValueError("Detection evidence contains duplicate member identities.")
    accepted_ids = tuple(sorted(block.text_block_id for block in accepted_text_blocks))
    if tuple(draft.member_ids) != accepted_ids:
        raise ValueError(
            "Detection evidence members must come from the exact acceptance command."
        )
    if any(block.page_id != draft.page_id for block in accepted_text_blocks):
        raise ValueError("Detection evidence member page binding is invalid.")

    _validate_source_and_manifest_artifacts(connection, project_id, draft)
    existing = connection.execute(
        """
        SELECT
            project_id,
            page_id,
            source_artifact_id,
            source_sha256,
            coordinate_space_json,
            canonical_member_count,
            manifest_artifact_id,
            canonical_manifest_sha256,
            schema_version
        FROM accepted_detection_evidence_sets
        WHERE detection_dependency_id = ?
        """,
        (draft.detection_dependency_id,),
    ).fetchone()
    expected = {
        "project_id": project_id,
        "page_id": draft.page_id,
        "source_artifact_id": draft.source_artifact_id,
        "source_sha256": draft.source_sha256,
        "coordinate_space_json": draft.coordinate_space_json,
        "canonical_member_count": draft.canonical_member_count,
        "manifest_artifact_id": draft.manifest_artifact_id,
        "canonical_manifest_sha256": draft.canonical_manifest_sha256,
        "schema_version": draft.schema_version,
    }
    if existing is None:
        connection.execute(
            """
            INSERT INTO accepted_detection_evidence_sets (
                detection_dependency_id,
                project_id,
                page_id,
                source_artifact_id,
                source_sha256,
                coordinate_space_json,
                canonical_member_count,
                manifest_artifact_id,
                canonical_manifest_sha256,
                schema_version,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft.detection_dependency_id,
                project_id,
                draft.page_id,
                draft.source_artifact_id,
                draft.source_sha256,
                draft.coordinate_space_json,
                draft.canonical_member_count,
                draft.manifest_artifact_id,
                draft.canonical_manifest_sha256,
                draft.schema_version,
                utc_now(),
            ),
        )
        for ordinal, text_block_id in enumerate(draft.member_ids):
            _validate_accepted_member_row(
                connection,
                project_id,
                draft.page_id,
                text_block_id,
            )
            connection.execute(
                """
                INSERT INTO accepted_detection_evidence_members (
                    detection_dependency_id,
                    project_id,
                    page_id,
                    text_block_id,
                    canonical_ordinal
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    draft.detection_dependency_id,
                    project_id,
                    draft.page_id,
                    text_block_id,
                    ordinal,
                ),
            )
        return

    if any(existing[key] != value for key, value in expected.items()):
        raise ValueError("Detection dependency ID conflicts with immutable metadata.")
    snapshot = _load_and_validate_evidence_set(
        connection,
        project_id,
        draft.detection_dependency_id,
    )
    if tuple(member.text_block_id for member in snapshot.members) != draft.member_ids:
        raise ValueError("Detection dependency ID conflicts with immutable membership.")


def persist_detection_evidence_provenance(
    connection: sqlite3.Connection,
    project_id: str,
    draft: AcceptedDetectionEvidenceSetDraft,
) -> None:
    provenance = draft.provenance
    decision = connection.execute(
        """
        SELECT task_id, attempt_id, stage
        FROM workflow_decisions
        WHERE project_id = ? AND decision_id = ?
        """,
        (project_id, provenance.workflow_decision_id),
    ).fetchone()
    if (
        decision is None
        or decision["stage"] != "detection"
        or decision["attempt_id"] != provenance.workflow_attempt_id
    ):
        raise ValueError("Detection evidence acceptance provenance is invalid.")
    existing = connection.execute(
        """
        SELECT
            detection_dependency_id,
            workflow_attempt_id,
            workflow_decision_id,
            provider_execution_reference
        FROM detection_evidence_acceptance_provenance
        WHERE acceptance_id = ?
        """,
        (provenance.acceptance_id,),
    ).fetchone()
    expected = (
        draft.detection_dependency_id,
        provenance.workflow_attempt_id,
        provenance.workflow_decision_id,
        provenance.provider_execution_reference,
    )
    if existing is not None:
        actual = (
            existing["detection_dependency_id"],
            existing["workflow_attempt_id"],
            existing["workflow_decision_id"],
            existing["provider_execution_reference"],
        )
        if actual != expected:
            raise ValueError("Detection evidence acceptance identity conflicts.")
        return
    connection.execute(
        """
        INSERT INTO detection_evidence_acceptance_provenance (
            acceptance_id,
            detection_dependency_id,
            project_id,
            page_id,
            workflow_attempt_id,
            workflow_decision_id,
            provider_execution_reference,
            accepted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            provenance.acceptance_id,
            draft.detection_dependency_id,
            project_id,
            draft.page_id,
            provenance.workflow_attempt_id,
            provenance.workflow_decision_id,
            provenance.provider_execution_reference,
            utc_now(),
        ),
    )


def initialize_detection_evidence_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS accepted_detection_evidence_sets (
            detection_dependency_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            source_artifact_id TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            coordinate_space_json TEXT NOT NULL,
            canonical_member_count INTEGER NOT NULL CHECK(canonical_member_count >= 0),
            manifest_artifact_id TEXT NOT NULL,
            canonical_manifest_sha256 TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK(
                detection_dependency_id =
                'detection-set-v1:' || canonical_manifest_sha256
            ),
            FOREIGN KEY(page_id) REFERENCES pages(page_id),
            FOREIGN KEY(source_artifact_id) REFERENCES processing_artifacts(artifact_id),
            FOREIGN KEY(manifest_artifact_id) REFERENCES processing_artifacts(artifact_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS accepted_detection_evidence_members (
            detection_dependency_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            text_block_id TEXT NOT NULL,
            canonical_ordinal INTEGER NOT NULL CHECK(canonical_ordinal >= 0),
            PRIMARY KEY(detection_dependency_id, text_block_id),
            UNIQUE(detection_dependency_id, canonical_ordinal),
            FOREIGN KEY(detection_dependency_id)
                REFERENCES accepted_detection_evidence_sets(detection_dependency_id),
            FOREIGN KEY(text_block_id) REFERENCES text_blocks(text_block_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS detection_evidence_acceptance_provenance (
            acceptance_id TEXT PRIMARY KEY,
            detection_dependency_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            workflow_attempt_id TEXT NOT NULL,
            workflow_decision_id TEXT NOT NULL,
            provider_execution_reference TEXT,
            accepted_at TEXT NOT NULL,
            UNIQUE(project_id, workflow_decision_id),
            FOREIGN KEY(detection_dependency_id)
                REFERENCES accepted_detection_evidence_sets(detection_dependency_id),
            FOREIGN KEY(workflow_attempt_id) REFERENCES workflow_attempts(attempt_id),
            FOREIGN KEY(workflow_decision_id) REFERENCES workflow_decisions(decision_id),
            FOREIGN KEY(provider_execution_reference) REFERENCES tool_run_logs(tool_run_id)
        )
        """
    )
    for table in (
        "accepted_detection_evidence_sets",
        "accepted_detection_evidence_members",
        "detection_evidence_acceptance_provenance",
    ):
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_immutable_update
            BEFORE UPDATE ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{table} is immutable');
            END
            """
        )
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_immutable_delete
            BEFORE DELETE ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{table} is immutable');
            END
            """
        )


def _validate_source_and_manifest_artifacts(
    connection: sqlite3.Connection,
    project_id: str,
    draft: AcceptedDetectionEvidenceSetDraft,
) -> None:
    page = connection.execute(
        """
        SELECT original_artifact_id
        FROM pages
        WHERE project_id = ? AND page_id = ?
        """,
        (project_id, draft.page_id),
    ).fetchone()
    if page is None or page["original_artifact_id"] != draft.source_artifact_id:
        raise ValueError("Detection evidence source Page binding is invalid.")
    source = connection.execute(
        """
        SELECT file_hash, artifact_type, storage_state
        FROM processing_artifacts
        WHERE project_id = ? AND artifact_id = ?
        """,
        (project_id, draft.source_artifact_id),
    ).fetchone()
    if (
        source is None
        or source["artifact_type"] != "original_image"
        or source["storage_state"] != "present"
        or source["file_hash"] != draft.source_sha256
    ):
        raise ValueError("Detection evidence source artifact binding is invalid.")
    manifest = connection.execute(
        """
        SELECT
            page_id,
            owner_type,
            owner_id,
            artifact_type,
            source_stage,
            file_hash,
            mime_type,
            storage_state,
            dependency_hash
        FROM processing_artifacts
        WHERE project_id = ? AND artifact_id = ?
        """,
        (project_id, draft.manifest_artifact_id),
    ).fetchone()
    if (
        manifest is None
        or manifest["page_id"] != draft.page_id
        or manifest["owner_type"] != "accepted_detection_evidence_set"
        or manifest["owner_id"] != draft.detection_dependency_id
        or manifest["artifact_type"] != "accepted_detection_evidence_manifest"
        or manifest["source_stage"] != "detection"
        or manifest["file_hash"] != draft.canonical_manifest_sha256
        or manifest["mime_type"] != "application/json"
        or manifest["storage_state"] != "present"
        or manifest["dependency_hash"] != draft.canonical_manifest_sha256
    ):
        raise ValueError("Detection evidence manifest artifact binding is invalid.")


def _validate_accepted_member_row(
    connection: sqlite3.Connection,
    project_id: str,
    page_id: str,
    text_block_id: str,
) -> None:
    row = connection.execute(
        """
        SELECT
            project_id,
            page_id,
            detection_status,
            bbox_json,
            polygon_json,
            geometry_hash,
            detection_provider
        FROM text_blocks
        WHERE text_block_id = ?
        """,
        (text_block_id,),
    ).fetchone()
    if (
        row is None
        or row["project_id"] != project_id
        or row["page_id"] != page_id
        or row["detection_status"] != "done"
        or row["bbox_json"] is None
        or row["polygon_json"] is None
        or row["geometry_hash"] is None
        or row["detection_provider"] is None
    ):
        raise ValueError("Detection evidence member is not a formally accepted row.")


def _load_and_validate_evidence_set(
    connection: sqlite3.Connection,
    project_id: str,
    detection_dependency_id: str,
) -> AcceptedDetectionEvidenceSetSnapshot:
    row = connection.execute(
        """
        SELECT
            detection_dependency_id,
            project_id,
            page_id,
            source_artifact_id,
            source_sha256,
            coordinate_space_json,
            canonical_member_count,
            manifest_artifact_id,
            canonical_manifest_sha256,
            schema_version,
            created_at
        FROM accepted_detection_evidence_sets
        WHERE project_id = ? AND detection_dependency_id = ?
        """,
        (project_id, detection_dependency_id),
    ).fetchone()
    if row is None:
        raise LookupError(
            f"AcceptedDetectionEvidenceSet not found: {detection_dependency_id}"
        )
    json.loads(row["coordinate_space_json"])
    members = tuple(
        AcceptedDetectionEvidenceMemberSnapshot(
            text_block_id=member["text_block_id"],
            canonical_ordinal=member["canonical_ordinal"],
        )
        for member in connection.execute(
            """
            SELECT text_block_id, canonical_ordinal
            FROM accepted_detection_evidence_members
            WHERE project_id = ? AND detection_dependency_id = ?
            ORDER BY canonical_ordinal
            """,
            (project_id, detection_dependency_id),
        ).fetchall()
    )
    if len(members) != row["canonical_member_count"]:
        raise ValueError("Detection evidence member count is inconsistent.")
    if tuple(member.canonical_ordinal for member in members) != tuple(
        range(len(members))
    ):
        raise ValueError("Detection evidence member ordinals are inconsistent.")
    _validate_persisted_artifact_bindings(connection, project_id, row)
    for member in members:
        bound = connection.execute(
            """
            SELECT project_id, page_id
            FROM text_blocks
            WHERE text_block_id = ?
            """,
            (member.text_block_id,),
        ).fetchone()
        if (
            bound is None
            or bound["project_id"] != project_id
            or bound["page_id"] != row["page_id"]
        ):
            raise ValueError("Detection evidence member binding is inconsistent.")
    provenance = tuple(
        DetectionEvidenceAcceptanceProvenanceSnapshot(
            acceptance_id=item["acceptance_id"],
            workflow_attempt_id=item["workflow_attempt_id"],
            workflow_decision_id=item["workflow_decision_id"],
            provider_execution_reference=item["provider_execution_reference"],
            accepted_at=item["accepted_at"],
        )
        for item in connection.execute(
            """
            SELECT
                acceptance_id,
                workflow_attempt_id,
                workflow_decision_id,
                provider_execution_reference,
                accepted_at
            FROM detection_evidence_acceptance_provenance
            WHERE project_id = ? AND detection_dependency_id = ?
            ORDER BY accepted_at, acceptance_id
            """,
            (project_id, detection_dependency_id),
        ).fetchall()
    )
    return AcceptedDetectionEvidenceSetSnapshot(
        detection_dependency_id=row["detection_dependency_id"],
        project_id=row["project_id"],
        page_id=row["page_id"],
        source_artifact_id=row["source_artifact_id"],
        source_sha256=row["source_sha256"],
        coordinate_space_json=row["coordinate_space_json"],
        canonical_member_count=row["canonical_member_count"],
        manifest_artifact_id=row["manifest_artifact_id"],
        canonical_manifest_sha256=row["canonical_manifest_sha256"],
        schema_version=row["schema_version"],
        created_at=row["created_at"],
        members=members,
        provenance=provenance,
    )


def _validate_persisted_artifact_bindings(
    connection: sqlite3.Connection,
    project_id: str,
    evidence_set: sqlite3.Row,
) -> None:
    page = connection.execute(
        "SELECT original_artifact_id FROM pages WHERE project_id = ? AND page_id = ?",
        (project_id, evidence_set["page_id"]),
    ).fetchone()
    source = connection.execute(
        """
        SELECT file_hash, storage_state, artifact_type
        FROM processing_artifacts
        WHERE project_id = ? AND artifact_id = ?
        """,
        (project_id, evidence_set["source_artifact_id"]),
    ).fetchone()
    manifest = connection.execute(
        """
        SELECT
            page_id,
            owner_type,
            owner_id,
            source_stage,
            file_hash,
            storage_state,
            mime_type,
            artifact_type,
            dependency_hash
        FROM processing_artifacts
        WHERE project_id = ? AND artifact_id = ?
        """,
        (project_id, evidence_set["manifest_artifact_id"]),
    ).fetchone()
    if (
        page is None
        or page["original_artifact_id"] != evidence_set["source_artifact_id"]
        or source is None
        or source["file_hash"] != evidence_set["source_sha256"]
        or source["storage_state"] != "present"
        or source["artifact_type"] != "original_image"
        or manifest is None
        or manifest["page_id"] != evidence_set["page_id"]
        or manifest["owner_type"] != "accepted_detection_evidence_set"
        or manifest["owner_id"] != evidence_set["detection_dependency_id"]
        or manifest["source_stage"] != "detection"
        or manifest["file_hash"] != evidence_set["canonical_manifest_sha256"]
        or manifest["storage_state"] != "present"
        or manifest["mime_type"] != "application/json"
        or manifest["artifact_type"] != "accepted_detection_evidence_manifest"
        or manifest["dependency_hash"]
        != evidence_set["canonical_manifest_sha256"]
    ):
        raise ValueError("Detection evidence artifact/source binding is inconsistent.")
