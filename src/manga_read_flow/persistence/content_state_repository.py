from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from manga_read_flow.persistence.sqlite_repository_helpers import (
    connect_existing,
    utc_now,
)


@dataclass(frozen=True)
class BatchSnapshot:
    batch_id: str
    name: str
    status: str
    page_count: int


@dataclass(frozen=True)
class PageSnapshot:
    page_id: str
    batch_id: str
    original_artifact_id: str
    status: str
    active_cleaned_artifact_id: str | None
    active_typeset_artifact_id: str | None
    page_index: int | None = None
    original_filename: str | None = None


@dataclass(frozen=True)
class TextBlockSnapshot:
    text_block_id: str
    page_id: str
    reading_order: int
    active_ocr_result_id: str | None
    active_translation_result_id: str | None
    ocr_status: str
    translation_status: str


@dataclass(frozen=True)
class ImportPageStateCommand:
    batch_id: str
    batch_name: str
    page_id: str
    page_index: int
    original_filename: str
    original_artifact_id: str


@dataclass(frozen=True)
class ImportPageStateOutcome:
    batch: BatchSnapshot
    page: PageSnapshot


class ContentStateRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def create_page(
        self,
        *,
        page_id: str,
        batch_id: str,
        original_artifact_id: str,
        status: str,
        page_index: int = 0,
        original_filename: str = "unknown",
    ) -> PageSnapshot:
        now = utc_now()
        with connect_existing(self._project_db_path) as connection:
            connection.execute(
                """
                INSERT INTO pages (
                    page_id,
                    project_id,
                    batch_id,
                    page_index,
                    original_filename,
                    original_artifact_id,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    self._project_id,
                    batch_id,
                    page_index,
                    original_filename,
                    original_artifact_id,
                    status,
                    now,
                    now,
                ),
            )
            return _load_page(connection, self._project_id, page_id)

    def create_text_block(
        self,
        *,
        text_block_id: str,
        page_id: str,
        reading_order: int,
        ocr_status: str,
        translation_status: str,
    ) -> TextBlockSnapshot:
        now = utc_now()
        with connect_existing(self._project_db_path) as connection:
            connection.execute(
                """
                INSERT INTO text_blocks (
                    text_block_id,
                    project_id,
                    page_id,
                    reading_order,
                    ocr_status,
                    translation_status,
                    translation_check_status,
                    cleaning_status,
                    typesetting_status,
                    review_status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    text_block_id,
                    self._project_id,
                    page_id,
                    reading_order,
                    ocr_status,
                    translation_status,
                    "pending",
                    "pending",
                    "pending",
                    "pending",
                    now,
                    now,
                ),
            )
            return _load_text_block(connection, self._project_id, text_block_id)

    def import_page_original(
        self,
        command: ImportPageStateCommand,
    ) -> ImportPageStateOutcome:
        now = utc_now()
        with connect_existing(self._project_db_path) as connection:
            batch = _load_batch_or_none(connection, self._project_id, command.batch_id)
            if batch is None:
                connection.execute(
                    """
                    INSERT INTO batches (
                        batch_id,
                        project_id,
                        name,
                        page_count,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        command.batch_id,
                        self._project_id,
                        command.batch_name,
                        0,
                        "imported",
                        now,
                        now,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE batches
                    SET name = ?,
                        updated_at = ?
                    WHERE project_id = ? AND batch_id = ?
                    """,
                    (
                        command.batch_name,
                        now,
                        self._project_id,
                        command.batch_id,
                    ),
                )

            connection.execute(
                """
                INSERT INTO pages (
                    page_id,
                    project_id,
                    batch_id,
                    page_index,
                    original_filename,
                    original_artifact_id,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.page_id,
                    self._project_id,
                    command.batch_id,
                    command.page_index,
                    command.original_filename,
                    command.original_artifact_id,
                    "uploaded",
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE batches
                SET page_count = (
                        SELECT COUNT(*)
                        FROM pages
                        WHERE project_id = ? AND batch_id = ?
                    ),
                    status = ?,
                    updated_at = ?
                WHERE project_id = ? AND batch_id = ?
                """,
                (
                    self._project_id,
                    command.batch_id,
                    "imported",
                    now,
                    self._project_id,
                    command.batch_id,
                ),
            )
            batch = _load_batch(connection, self._project_id, command.batch_id)
            page = _load_page(connection, self._project_id, command.page_id)

        return ImportPageStateOutcome(batch=batch, page=page)


class ResultVersionRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def latest_text_block_versions(self, text_block_id: str) -> tuple[str | None, str | None]:
        with connect_existing(self._project_db_path) as connection:
            block = _load_text_block(connection, self._project_id, text_block_id)
        return block.active_ocr_result_id, block.active_translation_result_id


class GlossaryRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def ensure_empty_version(self) -> str:
        with connect_existing(self._project_db_path) as connection:
            row = connection.execute(
                """
                SELECT glossary_version_id
                FROM glossary_versions
                WHERE project_id = ?
                ORDER BY version_number
                LIMIT 1
                """,
                (self._project_id,),
            ).fetchone()
            if row is not None:
                return row["glossary_version_id"]

            version_id = "glossary-empty-v1"
            connection.execute(
                """
                INSERT INTO glossary_versions (
                    glossary_version_id,
                    project_id,
                    version_number,
                    terms_hash,
                    term_count,
                    created_reason,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    self._project_id,
                    1,
                    "empty",
                    0,
                    "initial_empty_glossary",
                    utc_now(),
                ),
            )
            return version_id


def initialize_content_state_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pages (
            page_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            page_index INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            original_artifact_id TEXT NOT NULL,
            active_cleaned_artifact_id TEXT,
            active_typeset_artifact_id TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, batch_id, page_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS text_blocks (
            text_block_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            reading_order INTEGER NOT NULL,
            active_ocr_result_id TEXT,
            active_translation_result_id TEXT,
            ocr_status TEXT NOT NULL,
            translation_status TEXT NOT NULL,
            translation_check_status TEXT NOT NULL,
            cleaning_status TEXT NOT NULL,
            typesetting_status TEXT NOT NULL,
            review_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ocr_results (
            ocr_result_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            text_block_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS translation_results (
            translation_result_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            text_block_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS glossary_versions (
            glossary_version_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            terms_hash TEXT NOT NULL,
            term_count INTEGER NOT NULL,
            created_reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def _load_page(
    connection: sqlite3.Connection,
    project_id: str,
    page_id: str,
) -> PageSnapshot:
    row = connection.execute(
        """
        SELECT
            page_id,
            batch_id,
            page_index,
            original_filename,
            original_artifact_id,
            status,
            active_cleaned_artifact_id,
            active_typeset_artifact_id
        FROM pages
        WHERE project_id = ? AND page_id = ?
        """,
        (project_id, page_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"Page not found: {page_id}")
    return PageSnapshot(
        page_id=row["page_id"],
        batch_id=row["batch_id"],
        original_artifact_id=row["original_artifact_id"],
        status=row["status"],
        active_cleaned_artifact_id=row["active_cleaned_artifact_id"],
        active_typeset_artifact_id=row["active_typeset_artifact_id"],
        page_index=row["page_index"],
        original_filename=row["original_filename"],
    )


def _load_batch_or_none(
    connection: sqlite3.Connection,
    project_id: str,
    batch_id: str,
) -> BatchSnapshot | None:
    row = connection.execute(
        """
        SELECT batch_id, name, status, page_count
        FROM batches
        WHERE project_id = ? AND batch_id = ?
        """,
        (project_id, batch_id),
    ).fetchone()
    if row is None:
        return None
    return BatchSnapshot(
        batch_id=row["batch_id"],
        name=row["name"],
        status=row["status"],
        page_count=row["page_count"],
    )


def _load_batch(
    connection: sqlite3.Connection,
    project_id: str,
    batch_id: str,
) -> BatchSnapshot:
    batch = _load_batch_or_none(connection, project_id, batch_id)
    if batch is None:
        raise LookupError(f"Batch not found: {batch_id}")
    return batch


def _load_text_block(
    connection: sqlite3.Connection,
    project_id: str,
    text_block_id: str,
) -> TextBlockSnapshot:
    row = connection.execute(
        """
        SELECT
            text_block_id,
            page_id,
            reading_order,
            active_ocr_result_id,
            active_translation_result_id,
            ocr_status,
            translation_status
        FROM text_blocks
        WHERE project_id = ? AND text_block_id = ?
        """,
        (project_id, text_block_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"TextBlock not found: {text_block_id}")
    return TextBlockSnapshot(
        text_block_id=row["text_block_id"],
        page_id=row["page_id"],
        reading_order=row["reading_order"],
        active_ocr_result_id=row["active_ocr_result_id"],
        active_translation_result_id=row["active_translation_result_id"],
        ocr_status=row["ocr_status"],
        translation_status=row["translation_status"],
    )
