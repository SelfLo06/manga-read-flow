from __future__ import annotations

from pathlib import Path
import sqlite3

from manga_read_flow.domain.artifacts import (
    ProcessingArtifactSnapshot,
    RegisterArtifactMetadata,
)
from manga_read_flow.persistence.sqlite_repository_helpers import (
    connect_existing as _connect_existing,
    utc_now as _utc_now,
)


class ArtifactMetadataRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def register_artifact(
        self,
        command: RegisterArtifactMetadata,
    ) -> ProcessingArtifactSnapshot:
        now = _utc_now()
        with _connect_existing(self._project_db_path) as connection:
            connection.execute(
                """
                INSERT INTO processing_artifacts (
                    artifact_id,
                    project_id,
                    batch_id,
                    page_id,
                    owner_type,
                    owner_id,
                    artifact_type,
                    source_stage,
                    relative_path,
                    file_hash,
                    hash_algorithm,
                    byte_size,
                    mime_type,
                    width,
                    height,
                    retention_class,
                    storage_state,
                    is_debug,
                    may_contain_original_image,
                    may_contain_ocr_text,
                    may_contain_translation,
                    may_contain_provider_response,
                    contains_secret_redacted,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.artifact_id,
                    self._project_id,
                    command.batch_id,
                    command.page_id,
                    command.owner_type,
                    command.owner_id,
                    command.artifact_type,
                    command.source_stage,
                    command.relative_path,
                    command.file_hash,
                    command.hash_algorithm,
                    command.byte_size,
                    command.mime_type,
                    command.width,
                    command.height,
                    command.retention_class,
                    command.storage_state,
                    int(command.safety.is_debug),
                    int(command.safety.may_contain_original_image),
                    int(command.safety.may_contain_ocr_text),
                    int(command.safety.may_contain_translation),
                    int(command.safety.may_contain_provider_response),
                    int(command.safety.contains_secret_redacted),
                    now,
                    now,
                ),
            )
            return _load_artifact(connection, self._project_id, command.artifact_id)

    def get_artifact(self, artifact_id: str) -> ProcessingArtifactSnapshot:
        with _connect_existing(self._project_db_path) as connection:
            return _load_artifact(connection, self._project_id, artifact_id)

    def update_storage_state(
        self,
        *,
        artifact_id: str,
        storage_state: str,
    ) -> ProcessingArtifactSnapshot:
        with _connect_existing(self._project_db_path) as connection:
            connection.execute(
                """
                UPDATE processing_artifacts
                SET storage_state = ?,
                    updated_at = ?
                WHERE project_id = ? AND artifact_id = ?
                """,
                (storage_state, _utc_now(), self._project_id, artifact_id),
            )
            return _load_artifact(connection, self._project_id, artifact_id)

    def note_metadata_contract(self) -> str:
        return "artifact_metadata_repository"


def initialize_artifact_metadata_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS processing_artifacts (
            artifact_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            batch_id TEXT,
            page_id TEXT,
            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            source_stage TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            hash_algorithm TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            mime_type TEXT NOT NULL,
            width INTEGER,
            height INTEGER,
            retention_class TEXT NOT NULL,
            storage_state TEXT NOT NULL,
            is_debug INTEGER NOT NULL DEFAULT 0,
            may_contain_original_image INTEGER NOT NULL DEFAULT 0,
            may_contain_ocr_text INTEGER NOT NULL DEFAULT 0,
            may_contain_translation INTEGER NOT NULL DEFAULT 0,
            may_contain_provider_response INTEGER NOT NULL DEFAULT 0,
            contains_secret_redacted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, relative_path)
        )
        """
    )


def _load_artifact(
    connection: sqlite3.Connection,
    project_id: str,
    artifact_id: str,
) -> ProcessingArtifactSnapshot:
    row = connection.execute(
        """
        SELECT
            artifact_id,
            batch_id,
            page_id,
            owner_type,
            owner_id,
            artifact_type,
            source_stage,
            relative_path,
            file_hash,
            hash_algorithm,
            byte_size,
            mime_type,
            width,
            height,
            retention_class,
            storage_state,
            is_debug,
            may_contain_original_image,
            may_contain_ocr_text,
            may_contain_translation,
            may_contain_provider_response,
            contains_secret_redacted
        FROM processing_artifacts
        WHERE project_id = ? AND artifact_id = ?
        """,
        (project_id, artifact_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"ProcessingArtifact not found: {artifact_id}")
    return ProcessingArtifactSnapshot(
        artifact_id=row["artifact_id"],
        artifact_type=row["artifact_type"],
        source_stage=row["source_stage"],
        relative_path=row["relative_path"],
        file_hash=row["file_hash"],
        hash_algorithm=row["hash_algorithm"],
        byte_size=row["byte_size"],
        mime_type=row["mime_type"],
        width=row["width"],
        height=row["height"],
        retention_class=row["retention_class"],
        storage_state=row["storage_state"],
        is_debug=bool(row["is_debug"]),
        may_contain_original_image=bool(row["may_contain_original_image"]),
        may_contain_ocr_text=bool(row["may_contain_ocr_text"]),
        may_contain_translation=bool(row["may_contain_translation"]),
        may_contain_provider_response=bool(row["may_contain_provider_response"]),
        contains_secret_redacted=bool(row["contains_secret_redacted"]),
        batch_id=row["batch_id"],
        page_id=row["page_id"],
        owner_type=row["owner_type"],
        owner_id=row["owner_id"],
    )
