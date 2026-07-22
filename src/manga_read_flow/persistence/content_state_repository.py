from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
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
    geometry_hash: str | None
    active_ocr_result_id: str | None
    active_translation_result_id: str | None
    locked_translation_result_id: str | None
    detection_status: str
    ocr_status: str
    translation_status: str
    translation_check_status: str
    cleaning_status: str
    typesetting_status: str


@dataclass(frozen=True)
class ActiveOcrInput:
    text_block_id: str
    active_ocr_result_id: str | None
    source_text: str | None
    source_text_hash: str | None


@dataclass(frozen=True)
class ExactActiveOcrDependency:
    text_block_id: str
    page_id: str
    ocr_result_id: str
    version_number: int
    source_text: str
    source_text_hash: str
    geometry_hash: str
    input_hash: str


class ExactOcrDependenciesNotReadyError(ValueError):
    """Raised when exact Detection members lack complete accepted/current OCR."""


@dataclass(frozen=True)
class ActiveTranslationInput:
    text_block_id: str
    active_translation_result_id: str | None
    translation_text: str | None
    translation_text_hash: str | None


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
                    detection_status,
                    ocr_status,
                    translation_status,
                    translation_check_status,
                    cleaning_status,
                    typesetting_status,
                    review_status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    text_block_id,
                    self._project_id,
                    page_id,
                    reading_order,
                    "done",
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

    def get_page(self, page_id: str) -> PageSnapshot:
        with connect_existing(self._project_db_path) as connection:
            return _load_page(connection, self._project_id, page_id)

    def list_text_blocks_for_page(self, page_id: str) -> tuple[TextBlockSnapshot, ...]:
        with connect_existing(self._project_db_path) as connection:
            rows = connection.execute(
                """
                SELECT text_block_id
                FROM text_blocks
                WHERE project_id = ? AND page_id = ?
                ORDER BY reading_order
                """,
                (self._project_id, page_id),
            ).fetchall()
            return tuple(
                _load_text_block(connection, self._project_id, row["text_block_id"])
                for row in rows
            )

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

    def reusable_active_ocr_for_page(
        self,
        page_id: str,
        *,
        provider_name: str,
        model_id: str | None,
        input_hash: str,
        config_hash: str,
    ) -> tuple[ActiveOcrInput, ...]:
        rows = self.active_ocr_inputs_for_page(page_id)
        if not rows:
            return ()

        with connect_existing(self._project_db_path) as connection:
            evidence = connection.execute(
                """
                SELECT
                    tb.text_block_id,
                    tb.ocr_status,
                    tb.active_ocr_result_id,
                    tb.geometry_hash,
                    ocr.source_text,
                    ocr.source_text_hash,
                    ocr.provider_name,
                    ocr.model_id,
                    ocr.input_hash,
                    ocr.config_hash,
                    ocr.geometry_hash AS result_geometry_hash
                FROM text_blocks tb
                LEFT JOIN ocr_results ocr
                    ON ocr.project_id = tb.project_id
                    AND ocr.ocr_result_id = tb.active_ocr_result_id
                WHERE tb.project_id = ? AND tb.page_id = ?
                ORDER BY tb.reading_order
                """,
                (self._project_id, page_id),
            ).fetchall()

        reusable: list[ActiveOcrInput] = []
        for row in evidence:
            if (
                row["ocr_status"] != "done"
                or row["active_ocr_result_id"] is None
                or row["source_text_hash"] is None
                or row["result_geometry_hash"] != row["geometry_hash"]
                or row["provider_name"] != provider_name
                or row["model_id"] != model_id
                or row["input_hash"] != input_hash
                or row["config_hash"] != config_hash
            ):
                return ()
            reusable.append(
                ActiveOcrInput(
                    text_block_id=row["text_block_id"],
                    active_ocr_result_id=row["active_ocr_result_id"],
                    source_text=row["source_text"],
                    source_text_hash=row["source_text_hash"],
                )
            )
        return tuple(reusable)

    def active_ocr_inputs_for_page(self, page_id: str) -> tuple[ActiveOcrInput, ...]:
        with connect_existing(self._project_db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    tb.text_block_id,
                    tb.active_ocr_result_id,
                    ocr.source_text,
                    ocr.source_text_hash
                FROM text_blocks tb
                LEFT JOIN ocr_results ocr
                    ON ocr.project_id = tb.project_id
                    AND ocr.ocr_result_id = tb.active_ocr_result_id
                WHERE tb.project_id = ? AND tb.page_id = ?
                ORDER BY tb.reading_order
                """,
                (self._project_id, page_id),
            ).fetchall()
        return tuple(
            ActiveOcrInput(
                text_block_id=row["text_block_id"],
                active_ocr_result_id=row["active_ocr_result_id"],
                source_text=row["source_text"],
                source_text_hash=row["source_text_hash"],
            )
            for row in rows
        )

    def exact_active_ocr_dependencies(
        self,
        *,
        page_id: str,
        text_block_ids: tuple[str, ...],
    ) -> tuple[ExactActiveOcrDependency, ...]:
        if len(set(text_block_ids)) != len(text_block_ids):
            raise ValueError("Exact OCR dependency identities must be unique.")
        ordered_ids = tuple(sorted(text_block_ids, key=lambda value: value.encode("utf-8")))
        if not ordered_ids:
            return ()
        placeholders = ",".join("?" for _ in ordered_ids)
        with connect_existing(self._project_db_path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    tb.text_block_id,
                    tb.page_id,
                    tb.ocr_status,
                    tb.geometry_hash AS text_block_geometry_hash,
                    tb.active_ocr_result_id,
                    ocr.ocr_result_id,
                    ocr.version_number,
                    ocr.source_text,
                    ocr.source_text_hash,
                    ocr.geometry_hash,
                    ocr.input_hash
                FROM text_blocks tb
                LEFT JOIN ocr_results ocr
                    ON ocr.project_id = tb.project_id
                    AND ocr.text_block_id = tb.text_block_id
                    AND ocr.ocr_result_id = tb.active_ocr_result_id
                WHERE tb.project_id = ?
                  AND tb.text_block_id IN ({placeholders})
                ORDER BY tb.text_block_id
                """,
                (self._project_id, *ordered_ids),
            ).fetchall()
        by_id = {row["text_block_id"]: row for row in rows}
        if set(by_id) != set(ordered_ids):
            raise ExactOcrDependenciesNotReadyError(
                "One or more exact Detection members do not exist."
            )
        dependencies = []
        for text_block_id in ordered_ids:
            row = by_id[text_block_id]
            if row["page_id"] != page_id:
                raise ExactOcrDependenciesNotReadyError(
                    "Exact OCR dependency is bound to another Page."
                )
            if (
                row["ocr_status"] != "done"
                or row["active_ocr_result_id"] is None
                or row["ocr_result_id"] != row["active_ocr_result_id"]
                or row["version_number"] is None
                or row["version_number"] < 1
                or row["source_text"] is None
                or row["source_text_hash"] is None
                or row["geometry_hash"] is None
                or row["input_hash"] is None
                or not _is_sha256(row["source_text_hash"])
                or not _is_sha256(row["geometry_hash"])
                or not _is_sha256(row["input_hash"])
                or row["geometry_hash"] != row["text_block_geometry_hash"]
                or sha256(row["source_text"].encode("utf-8")).hexdigest()
                != row["source_text_hash"]
            ):
                raise ExactOcrDependenciesNotReadyError(
                    f"Exact OCR dependency is not ready: {text_block_id}"
                )
            dependencies.append(
                ExactActiveOcrDependency(
                    text_block_id=text_block_id,
                    page_id=row["page_id"],
                    ocr_result_id=row["ocr_result_id"],
                    version_number=row["version_number"],
                    source_text=row["source_text"],
                    source_text_hash=row["source_text_hash"],
                    geometry_hash=row["geometry_hash"],
                    input_hash=row["input_hash"],
                )
            )
        return tuple(dependencies)

    def reusable_active_translations_for_page(
        self,
        page_id: str,
        *,
        provider_name: str,
        model_id: str | None,
        input_hash: str,
        config_hash: str,
        glossary_version_id: str,
    ) -> tuple[ActiveTranslationInput, ...]:
        with connect_existing(self._project_db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    tb.text_block_id,
                    tb.translation_status,
                    tb.active_ocr_result_id,
                    tb.active_translation_result_id,
                    ocr.source_text_hash AS active_source_text_hash,
                    tr.source_ocr_result_id,
                    tr.source_text_hash,
                    tr.translation_text,
                    tr.translation_text_hash,
                    tr.glossary_version_id,
                    tr.provider_name,
                    tr.model_id,
                    tr.input_hash,
                    tr.config_hash
                FROM text_blocks tb
                LEFT JOIN ocr_results ocr
                    ON ocr.project_id = tb.project_id
                    AND ocr.ocr_result_id = tb.active_ocr_result_id
                LEFT JOIN translation_results tr
                    ON tr.project_id = tb.project_id
                    AND tr.translation_result_id = tb.active_translation_result_id
                WHERE tb.project_id = ? AND tb.page_id = ?
                ORDER BY tb.reading_order
                """,
                (self._project_id, page_id),
            ).fetchall()

        if not rows:
            return ()

        reusable: list[ActiveTranslationInput] = []
        for row in rows:
            if (
                row["translation_status"] != "done"
                or row["active_ocr_result_id"] is None
                or row["active_translation_result_id"] is None
                or row["source_ocr_result_id"] != row["active_ocr_result_id"]
                or row["source_text_hash"] != row["active_source_text_hash"]
                or row["translation_text_hash"] is None
                or row["glossary_version_id"] != glossary_version_id
                or row["provider_name"] != provider_name
                or row["model_id"] != model_id
                or row["input_hash"] != input_hash
                or row["config_hash"] != config_hash
            ):
                return ()
            reusable.append(
                ActiveTranslationInput(
                    text_block_id=row["text_block_id"],
                    active_translation_result_id=row["active_translation_result_id"],
                    translation_text=row["translation_text"],
                    translation_text_hash=row["translation_text_hash"],
                )
            )
        return tuple(reusable)

    def locked_active_translations_for_page(
        self,
        page_id: str,
    ) -> tuple[ActiveTranslationInput, ...]:
        with connect_existing(self._project_db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    tb.text_block_id,
                    tb.translation_status,
                    tb.active_ocr_result_id,
                    tb.active_translation_result_id,
                    tb.locked_translation_result_id,
                    ocr.source_text_hash AS active_source_text_hash,
                    tr.source_ocr_result_id,
                    tr.source_text_hash,
                    tr.translation_text,
                    tr.translation_text_hash
                FROM text_blocks tb
                LEFT JOIN ocr_results ocr
                    ON ocr.project_id = tb.project_id
                    AND ocr.ocr_result_id = tb.active_ocr_result_id
                LEFT JOIN translation_results tr
                    ON tr.project_id = tb.project_id
                    AND tr.translation_result_id = tb.active_translation_result_id
                WHERE tb.project_id = ? AND tb.page_id = ?
                ORDER BY tb.reading_order
                """,
                (self._project_id, page_id),
            ).fetchall()

        if not rows:
            return ()

        reusable: list[ActiveTranslationInput] = []
        for row in rows:
            if (
                row["translation_status"] != "done"
                or row["locked_translation_result_id"] is None
                or row["locked_translation_result_id"]
                != row["active_translation_result_id"]
                or row["source_ocr_result_id"] != row["active_ocr_result_id"]
                or row["source_text_hash"] != row["active_source_text_hash"]
                or row["translation_text_hash"] is None
            ):
                return ()
            reusable.append(
                ActiveTranslationInput(
                    text_block_id=row["text_block_id"],
                    active_translation_result_id=row["active_translation_result_id"],
                    translation_text=row["translation_text"],
                    translation_text_hash=row["translation_text_hash"],
                )
            )
        return tuple(reusable)

    def active_translation_inputs_for_page(
        self,
        page_id: str,
    ) -> tuple[ActiveTranslationInput, ...]:
        with connect_existing(self._project_db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    tb.text_block_id,
                    tb.active_translation_result_id,
                    tr.translation_text,
                    tr.translation_text_hash
                FROM text_blocks tb
                LEFT JOIN translation_results tr
                    ON tr.project_id = tb.project_id
                    AND tr.translation_result_id = tb.active_translation_result_id
                WHERE tb.project_id = ? AND tb.page_id = ?
                ORDER BY tb.reading_order
                """,
                (self._project_id, page_id),
            ).fetchall()
        return tuple(
            ActiveTranslationInput(
                text_block_id=row["text_block_id"],
                active_translation_result_id=row["active_translation_result_id"],
                translation_text=row["translation_text"],
                translation_text_hash=row["translation_text_hash"],
            )
            for row in rows
        )


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
            detection_status TEXT NOT NULL,
            bbox_json TEXT,
            polygon_json TEXT,
            geometry_hash TEXT,
            detection_provider TEXT,
            detection_confidence REAL,
            active_ocr_result_id TEXT,
            active_translation_result_id TEXT,
            locked_translation_result_id TEXT,
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
            version_number INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_text TEXT,
            source_text_hash TEXT,
            provider_name TEXT,
            model_id TEXT,
            workflow_attempt_id TEXT,
            tool_run_id TEXT,
            input_hash TEXT,
            config_hash TEXT,
            geometry_hash TEXT,
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
            version_number INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_ocr_result_id TEXT,
            source_text_hash TEXT,
            translation_text TEXT,
            translation_text_hash TEXT,
            glossary_version_id TEXT,
            provider_name TEXT,
            model_id TEXT,
            workflow_attempt_id TEXT,
            tool_run_id TEXT,
            input_hash TEXT,
            config_hash TEXT,
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
            locked_translation_result_id,
            geometry_hash,
            detection_status,
            ocr_status,
            translation_status,
            translation_check_status,
            cleaning_status,
            typesetting_status
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
        geometry_hash=row["geometry_hash"],
        active_ocr_result_id=row["active_ocr_result_id"],
        active_translation_result_id=row["active_translation_result_id"],
        locked_translation_result_id=row["locked_translation_result_id"],
        detection_status=row["detection_status"],
        ocr_status=row["ocr_status"],
        translation_status=row["translation_status"],
        translation_check_status=row["translation_check_status"],
        cleaning_status=row["cleaning_status"],
        typesetting_status=row["typesetting_status"],
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
