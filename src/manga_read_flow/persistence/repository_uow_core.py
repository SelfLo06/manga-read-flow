from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Mapping
from urllib.parse import quote


@dataclass(frozen=True)
class PageSnapshot:
    page_id: str
    batch_id: str
    original_artifact_id: str
    status: str
    active_cleaned_artifact_id: str | None
    active_typeset_artifact_id: str | None


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
class ProcessingTaskSnapshot:
    task_id: str
    target_type: str
    target_id: str
    task_type: str
    status: str
    current_stage: str


@dataclass(frozen=True)
class ReadinessSnapshot:
    task_id: str
    task_status: str
    current_stage: str
    page_id: str | None


@dataclass(frozen=True)
class AttemptSnapshot:
    attempt_id: str
    task_id: str
    stage: str
    target_type: str
    target_id: str
    status: str
    provider_name: str | None = None
    model_id: str | None = None
    tool_name: str | None = None
    error_code: str | None = None
    sanitized_message: str | None = None


@dataclass(frozen=True)
class ToolRunSnapshot:
    tool_run_id: str
    task_id: str
    attempt_id: str
    stage: str
    tool_name: str
    status: str
    provider_name: str | None = None
    model_id: str | None = None
    error_code: str | None = None
    error_class: str | None = None
    is_provider_refusal: bool = False
    sanitized_message: str | None = None


@dataclass(frozen=True)
class AttemptReservation:
    task_id: str
    attempt_id: str
    stage: str
    target_type: str
    target_id: str
    expected_task_status: str
    expected_current_stage: str
    runner_id: str


@dataclass(frozen=True)
class ToolRunStart:
    tool_run_id: str
    task_id: str
    attempt_id: str
    stage: str
    tool_name: str
    tool_version: str
    provider_name: str
    model_id: str | None
    input_hash: str
    config_hash: str


@dataclass(frozen=True)
class ToolRunOutcome:
    tool_run_id: str
    status: str
    error_code: str | None = None
    error_class: str | None = None
    is_provider_refusal: bool = False
    sanitized_message: str | None = None


@dataclass(frozen=True)
class AttemptEvidence:
    attempt_id: str
    provider_name: str | None
    model_id: str | None
    tool_name: str | None
    status: str
    error_code: str | None = None
    sanitized_message: str | None = None


@dataclass(frozen=True)
class ExpectedState:
    task_status: str
    current_stage: str
    active_ocr_result_ids: Mapping[str, str | None] = field(default_factory=dict)
    active_translation_result_ids: Mapping[str, str | None] = field(default_factory=dict)
    page_artifact_ids: Mapping[str, Mapping[str, str | None]] = field(default_factory=dict)


@dataclass(frozen=True)
class AcceptedResult:
    result_type: str
    result_id: str
    target_type: str
    target_id: str


@dataclass(frozen=True)
class ActivePointerUpdate:
    owner_type: str
    owner_id: str
    pointer_name: str
    value_id: str | None


@dataclass(frozen=True)
class IssueLifecycleChange:
    issue_id: str
    action: str
    status: str
    issue_type: str
    is_blocking: bool


@dataclass(frozen=True)
class WorkflowDecisionDraft:
    decision_id: str
    attempt_id: str | None
    stage: str
    decision_type: str
    reason_code: str


@dataclass(frozen=True)
class TaskProgressUpdate:
    status: str
    current_stage: str
    progress_state: str


@dataclass(frozen=True)
class StageStatusUpdate:
    target_type: str
    target_id: str
    stage: str
    status: str


@dataclass(frozen=True)
class AcceptanceCommand:
    task_id: str
    expected: ExpectedState
    accepted_results: tuple[AcceptedResult, ...]
    active_pointers: tuple[ActivePointerUpdate, ...]
    issue_lifecycle: tuple[IssueLifecycleChange, ...]
    workflow_decision: WorkflowDecisionDraft
    retry_budget_after: dict[str, int]
    task_progress: TaskProgressUpdate
    stage_statuses: tuple[StageStatusUpdate, ...]


@dataclass(frozen=True)
class UnitOfWorkOutcome:
    committed: bool
    reload_required: bool
    conflict_fields: tuple[str, ...] = ()
    attempt_id: str | None = None


@dataclass(frozen=True)
class AcceptanceOutcome:
    committed: bool
    reload_required: bool
    conflict_fields: tuple[str, ...] = ()
    accepted_result_ids: tuple[str, ...] = ()
    active_pointer_updates: tuple[str, ...] = ()
    issue_changes: tuple[str, ...] = ()
    workflow_decision_id: str | None = None
    retry_budget_after: dict[str, int] = field(default_factory=dict)
    task_status: str | None = None
    current_stage: str | None = None
    stage_status_updates: tuple[str, ...] = ()


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
    ) -> PageSnapshot:
        now = _utc_now()
        with _connect_existing(self._project_db_path) as connection:
            connection.execute(
                """
                INSERT INTO pages (
                    page_id,
                    project_id,
                    batch_id,
                    original_artifact_id,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    self._project_id,
                    batch_id,
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
        now = _utc_now()
        with _connect_existing(self._project_db_path) as connection:
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


class ResultVersionRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def latest_text_block_versions(self, text_block_id: str) -> tuple[str | None, str | None]:
        with _connect_existing(self._project_db_path) as connection:
            block = _load_text_block(connection, self._project_id, text_block_id)
        return block.active_ocr_result_id, block.active_translation_result_id


class GlossaryRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def ensure_empty_version(self) -> str:
        with _connect_existing(self._project_db_path) as connection:
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
                    _utc_now(),
                ),
            )
            return version_id


class WorkflowExecutionRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def create_task(
        self,
        *,
        task_id: str,
        target_type: str,
        target_id: str,
        task_type: str,
        status: str,
        current_stage: str,
    ) -> ProcessingTaskSnapshot:
        now = _utc_now()
        with _connect_existing(self._project_db_path) as connection:
            connection.execute(
                """
                INSERT INTO processing_tasks (
                    task_id,
                    project_id,
                    target_type,
                    target_id,
                    task_type,
                    status,
                    current_stage,
                    progress_state,
                    retry_budget_json,
                    heartbeat_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    self._project_id,
                    target_type,
                    target_id,
                    task_type,
                    status,
                    current_stage,
                    "created",
                    "{}",
                    None,
                    now,
                    now,
                ),
            )
            return _load_task(connection, self._project_id, task_id)


class QualityIssueRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def count_open_blockers(self) -> int:
        with _connect_existing(self._project_db_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM quality_issues
                WHERE project_id = ? AND is_blocking = 1 AND status = ?
                """,
                (self._project_id, "open"),
            ).fetchone()
        return int(row["count"])


class ArtifactMetadataRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def note_metadata_contract(self) -> str:
        return "artifact_metadata_repository"


class ReadinessQueryRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def get_task_readiness(self, task_id: str) -> ReadinessSnapshot:
        with _connect_existing(self._project_db_path) as connection:
            task = _load_task(connection, self._project_id, task_id)
        page_id = task.target_id if task.target_type == "page" else None
        return ReadinessSnapshot(
            task_id=task.task_id,
            task_status=task.status,
            current_stage=task.current_stage,
            page_id=page_id,
        )


class StageEvidenceWriter:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def start_tool_run(self, command: ToolRunStart) -> ToolRunSnapshot:
        now = _utc_now()
        with _connect_existing(self._project_db_path) as connection:
            connection.execute(
                """
                INSERT INTO tool_run_logs (
                    tool_run_id,
                    project_id,
                    task_id,
                    attempt_id,
                    stage,
                    tool_name,
                    tool_version,
                    provider_name,
                    model_id,
                    input_hash,
                    config_hash,
                    status,
                    started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.tool_run_id,
                    self._project_id,
                    command.task_id,
                    command.attempt_id,
                    command.stage,
                    command.tool_name,
                    command.tool_version,
                    command.provider_name,
                    command.model_id,
                    command.input_hash,
                    command.config_hash,
                    "running",
                    now,
                ),
            )
            return _load_tool_run(connection, self._project_id, command.tool_run_id)

    def record_tool_outcome(self, command: ToolRunOutcome) -> ToolRunSnapshot:
        with _connect_existing(self._project_db_path) as connection:
            connection.execute(
                """
                UPDATE tool_run_logs
                SET status = ?,
                    error_code = ?,
                    error_class = ?,
                    is_provider_refusal = ?,
                    sanitized_message = ?,
                    finished_at = ?
                WHERE project_id = ? AND tool_run_id = ?
                """,
                (
                    command.status,
                    command.error_code,
                    command.error_class,
                    int(command.is_provider_refusal),
                    command.sanitized_message,
                    _utc_now(),
                    self._project_id,
                    command.tool_run_id,
                ),
            )
            return _load_tool_run(connection, self._project_id, command.tool_run_id)

    def record_attempt_evidence(self, command: AttemptEvidence) -> AttemptSnapshot:
        with _connect_existing(self._project_db_path) as connection:
            connection.execute(
                """
                UPDATE workflow_attempts
                SET provider_name = ?,
                    model_id = ?,
                    tool_name = ?,
                    status = ?,
                    error_code = ?,
                    sanitized_message = ?,
                    updated_at = ?
                WHERE project_id = ? AND attempt_id = ?
                """,
                (
                    command.provider_name,
                    command.model_id,
                    command.tool_name,
                    command.status,
                    command.error_code,
                    command.sanitized_message,
                    _utc_now(),
                    self._project_id,
                    command.attempt_id,
                ),
            )
            return _load_attempt(connection, self._project_id, command.attempt_id)


class ProjectUnitOfWork:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def reserve_attempt(self, command: AttemptReservation) -> UnitOfWorkOutcome:
        with _connect_existing(self._project_db_path) as connection:
            task = _load_task(connection, self._project_id, command.task_id)
            conflicts = _task_conflicts(
                task,
                expected_status=command.expected_task_status,
                expected_stage=command.expected_current_stage,
            )
            if conflicts:
                return UnitOfWorkOutcome(
                    committed=False,
                    reload_required=True,
                    conflict_fields=conflicts,
                )

            now = _utc_now()
            attempt_number = _next_attempt_number(connection, self._project_id, command.task_id)
            connection.execute(
                """
                INSERT INTO workflow_attempts (
                    attempt_id,
                    project_id,
                    task_id,
                    stage,
                    target_type,
                    target_id,
                    attempt_number,
                    runner_id,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.attempt_id,
                    self._project_id,
                    command.task_id,
                    command.stage,
                    command.target_type,
                    command.target_id,
                    attempt_number,
                    command.runner_id,
                    "running",
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE processing_tasks
                SET status = ?,
                    current_stage = ?,
                    heartbeat_at = ?,
                    updated_at = ?
                WHERE project_id = ? AND task_id = ?
                """,
                (
                    "running",
                    command.stage,
                    now,
                    now,
                    self._project_id,
                    command.task_id,
                ),
            )

        return UnitOfWorkOutcome(
            committed=True,
            reload_required=False,
            attempt_id=command.attempt_id,
        )

    def accept_stage(self, command: AcceptanceCommand) -> AcceptanceOutcome:
        with _connect_existing(self._project_db_path) as connection:
            task = _load_task(connection, self._project_id, command.task_id)
            conflicts = list(
                _task_conflicts(
                    task,
                    expected_status=command.expected.task_status,
                    expected_stage=command.expected.current_stage,
                )
            )
            conflicts.extend(
                _active_pointer_conflicts(connection, self._project_id, command.expected)
            )
            if conflicts:
                return AcceptanceOutcome(
                    committed=False,
                    reload_required=True,
                    conflict_fields=tuple(dict.fromkeys(conflicts)),
                )

            for result in command.accepted_results:
                _insert_accepted_result(connection, self._project_id, result)
            for pointer in command.active_pointers:
                _apply_active_pointer(connection, self._project_id, pointer)
            for issue_change in command.issue_lifecycle:
                _apply_issue_change(connection, self._project_id, issue_change)
            _insert_workflow_decision(
                connection,
                self._project_id,
                command.task_id,
                command.workflow_decision,
            )
            for status_update in command.stage_statuses:
                _apply_stage_status(connection, self._project_id, status_update)

            connection.execute(
                """
                UPDATE processing_tasks
                SET status = ?,
                    current_stage = ?,
                    progress_state = ?,
                    retry_budget_json = ?,
                    updated_at = ?
                WHERE project_id = ? AND task_id = ?
                """,
                (
                    command.task_progress.status,
                    command.task_progress.current_stage,
                    command.task_progress.progress_state,
                    json.dumps(command.retry_budget_after, sort_keys=True),
                    _utc_now(),
                    self._project_id,
                    command.task_id,
                ),
            )

        return AcceptanceOutcome(
            committed=True,
            reload_required=False,
            accepted_result_ids=tuple(result.result_id for result in command.accepted_results),
            active_pointer_updates=tuple(
                f"{pointer.owner_type}:{pointer.owner_id}:{pointer.pointer_name}"
                for pointer in command.active_pointers
            ),
            issue_changes=tuple(
                f"{issue_change.action}:{issue_change.issue_id}"
                for issue_change in command.issue_lifecycle
            ),
            workflow_decision_id=command.workflow_decision.decision_id,
            retry_budget_after=command.retry_budget_after,
            task_status=command.task_progress.status,
            current_stage=command.task_progress.current_stage,
            stage_status_updates=tuple(
                f"{status.target_type}:{status.target_id}:{status.stage}"
                for status in command.stage_statuses
            ),
        )


def initialize_repository_core_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pages (
            page_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            original_artifact_id TEXT NOT NULL,
            active_cleaned_artifact_id TEXT,
            active_typeset_artifact_id TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS processing_tasks (
            task_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            status TEXT NOT NULL,
            current_stage TEXT NOT NULL,
            progress_state TEXT NOT NULL,
            retry_budget_json TEXT NOT NULL,
            heartbeat_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_attempts (
            attempt_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            runner_id TEXT,
            provider_name TEXT,
            model_id TEXT,
            tool_name TEXT,
            status TEXT NOT NULL,
            error_code TEXT,
            sanitized_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_run_logs (
            tool_run_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            tool_version TEXT NOT NULL,
            provider_name TEXT,
            model_id TEXT,
            input_hash TEXT,
            config_hash TEXT,
            status TEXT NOT NULL,
            error_code TEXT,
            error_class TEXT,
            is_provider_refusal INTEGER NOT NULL DEFAULT 0,
            sanitized_message TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_decisions (
            decision_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            attempt_id TEXT,
            stage TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS quality_issues (
            issue_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            status TEXT NOT NULL,
            is_blocking INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS processing_artifacts (
            artifact_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            relative_path TEXT,
            file_hash TEXT,
            storage_state TEXT NOT NULL,
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
    )


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


def _load_task(
    connection: sqlite3.Connection,
    project_id: str,
    task_id: str,
) -> ProcessingTaskSnapshot:
    row = connection.execute(
        """
        SELECT task_id, target_type, target_id, task_type, status, current_stage
        FROM processing_tasks
        WHERE project_id = ? AND task_id = ?
        """,
        (project_id, task_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"ProcessingTask not found: {task_id}")
    return ProcessingTaskSnapshot(
        task_id=row["task_id"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        task_type=row["task_type"],
        status=row["status"],
        current_stage=row["current_stage"],
    )


def _load_attempt(
    connection: sqlite3.Connection,
    project_id: str,
    attempt_id: str,
) -> AttemptSnapshot:
    row = connection.execute(
        """
        SELECT
            attempt_id,
            task_id,
            stage,
            target_type,
            target_id,
            status,
            provider_name,
            model_id,
            tool_name,
            error_code,
            sanitized_message
        FROM workflow_attempts
        WHERE project_id = ? AND attempt_id = ?
        """,
        (project_id, attempt_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"WorkflowAttempt not found: {attempt_id}")
    return AttemptSnapshot(
        attempt_id=row["attempt_id"],
        task_id=row["task_id"],
        stage=row["stage"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        status=row["status"],
        provider_name=row["provider_name"],
        model_id=row["model_id"],
        tool_name=row["tool_name"],
        error_code=row["error_code"],
        sanitized_message=row["sanitized_message"],
    )


def _load_tool_run(
    connection: sqlite3.Connection,
    project_id: str,
    tool_run_id: str,
) -> ToolRunSnapshot:
    row = connection.execute(
        """
        SELECT
            tool_run_id,
            task_id,
            attempt_id,
            stage,
            tool_name,
            status,
            provider_name,
            model_id,
            error_code,
            error_class,
            is_provider_refusal,
            sanitized_message
        FROM tool_run_logs
        WHERE project_id = ? AND tool_run_id = ?
        """,
        (project_id, tool_run_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"ToolRunLog not found: {tool_run_id}")
    return ToolRunSnapshot(
        tool_run_id=row["tool_run_id"],
        task_id=row["task_id"],
        attempt_id=row["attempt_id"],
        stage=row["stage"],
        tool_name=row["tool_name"],
        status=row["status"],
        provider_name=row["provider_name"],
        model_id=row["model_id"],
        error_code=row["error_code"],
        error_class=row["error_class"],
        is_provider_refusal=bool(row["is_provider_refusal"]),
        sanitized_message=row["sanitized_message"],
    )


def _task_conflicts(
    task: ProcessingTaskSnapshot,
    *,
    expected_status: str,
    expected_stage: str,
) -> tuple[str, ...]:
    conflicts: list[str] = []
    if task.status != expected_status:
        conflicts.append("task_status")
    if task.current_stage != expected_stage:
        conflicts.append("current_stage")
    return tuple(conflicts)


def _active_pointer_conflicts(
    connection: sqlite3.Connection,
    project_id: str,
    expected: ExpectedState,
) -> tuple[str, ...]:
    conflicts: list[str] = []

    for text_block_id, expected_result_id in expected.active_ocr_result_ids.items():
        block = _load_text_block(connection, project_id, text_block_id)
        if block.active_ocr_result_id != expected_result_id:
            conflicts.append("active_ocr_result_id")

    for text_block_id, expected_result_id in expected.active_translation_result_ids.items():
        block = _load_text_block(connection, project_id, text_block_id)
        if block.active_translation_result_id != expected_result_id:
            conflicts.append("active_translation_result_id")

    for page_id, expected_artifacts in expected.page_artifact_ids.items():
        page = _load_page(connection, project_id, page_id)
        for pointer_name, expected_artifact_id in expected_artifacts.items():
            if pointer_name == "active_cleaned_artifact_id":
                actual = page.active_cleaned_artifact_id
            elif pointer_name == "active_typeset_artifact_id":
                actual = page.active_typeset_artifact_id
            else:
                raise ValueError(f"Unsupported page artifact pointer: {pointer_name}")
            if actual != expected_artifact_id:
                conflicts.append(pointer_name)

    return tuple(conflicts)


def _insert_accepted_result(
    connection: sqlite3.Connection,
    project_id: str,
    result: AcceptedResult,
) -> None:
    if result.target_type != "text_block":
        raise ValueError(f"Unsupported result target type: {result.target_type}")

    if result.result_type == "ocr":
        connection.execute(
            """
            INSERT INTO ocr_results (
                ocr_result_id,
                project_id,
                text_block_id,
                source_type,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                result.result_id,
                project_id,
                result.target_id,
                "workflow_acceptance",
                _utc_now(),
            ),
        )
    elif result.result_type == "translation":
        connection.execute(
            """
            INSERT INTO translation_results (
                translation_result_id,
                project_id,
                text_block_id,
                source_type,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                result.result_id,
                project_id,
                result.target_id,
                "workflow_acceptance",
                _utc_now(),
            ),
        )
    else:
        raise ValueError(f"Unsupported result type: {result.result_type}")


def _apply_active_pointer(
    connection: sqlite3.Connection,
    project_id: str,
    pointer: ActivePointerUpdate,
) -> None:
    now = _utc_now()
    if pointer.owner_type == "text_block":
        columns = {
            "active_ocr_result_id": "active_ocr_result_id",
            "active_translation_result_id": "active_translation_result_id",
        }
        column = columns.get(pointer.pointer_name)
        if column is None:
            raise ValueError(f"Unsupported text block pointer: {pointer.pointer_name}")
        connection.execute(
            f"""
            UPDATE text_blocks
            SET {column} = ?,
                updated_at = ?
            WHERE project_id = ? AND text_block_id = ?
            """,
            (pointer.value_id, now, project_id, pointer.owner_id),
        )
        return

    if pointer.owner_type == "page":
        columns = {
            "active_cleaned_artifact_id": "active_cleaned_artifact_id",
            "active_typeset_artifact_id": "active_typeset_artifact_id",
        }
        column = columns.get(pointer.pointer_name)
        if column is None:
            raise ValueError(f"Unsupported page pointer: {pointer.pointer_name}")
        connection.execute(
            f"""
            UPDATE pages
            SET {column} = ?,
                updated_at = ?
            WHERE project_id = ? AND page_id = ?
            """,
            (pointer.value_id, now, project_id, pointer.owner_id),
        )
        return

    raise ValueError(f"Unsupported pointer owner type: {pointer.owner_type}")


def _apply_issue_change(
    connection: sqlite3.Connection,
    project_id: str,
    issue_change: IssueLifecycleChange,
) -> None:
    now = _utc_now()
    if issue_change.action == "create":
        connection.execute(
            """
            INSERT INTO quality_issues (
                issue_id,
                project_id,
                issue_type,
                status,
                is_blocking,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue_change.issue_id,
                project_id,
                issue_change.issue_type,
                issue_change.status,
                int(issue_change.is_blocking),
                now,
                now,
            ),
        )
        return

    connection.execute(
        """
        UPDATE quality_issues
        SET status = ?,
            is_blocking = ?,
            updated_at = ?
        WHERE project_id = ? AND issue_id = ?
        """,
        (
            issue_change.status,
            int(issue_change.is_blocking),
            now,
            project_id,
            issue_change.issue_id,
        ),
    )


def _insert_workflow_decision(
    connection: sqlite3.Connection,
    project_id: str,
    task_id: str,
    decision: WorkflowDecisionDraft,
) -> None:
    connection.execute(
        """
        INSERT INTO workflow_decisions (
            decision_id,
            project_id,
            task_id,
            attempt_id,
            stage,
            decision_type,
            reason_code,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision.decision_id,
            project_id,
            task_id,
            decision.attempt_id,
            decision.stage,
            decision.decision_type,
            decision.reason_code,
            _utc_now(),
        ),
    )


def _apply_stage_status(
    connection: sqlite3.Connection,
    project_id: str,
    status_update: StageStatusUpdate,
) -> None:
    if status_update.target_type != "text_block":
        raise ValueError(f"Unsupported status target type: {status_update.target_type}")

    columns = {
        "ocr": "ocr_status",
        "translation": "translation_status",
        "translation_check": "translation_check_status",
        "cleaning": "cleaning_status",
        "typesetting": "typesetting_status",
        "review": "review_status",
    }
    column = columns.get(status_update.stage)
    if column is None:
        raise ValueError(f"Unsupported status stage: {status_update.stage}")

    connection.execute(
        f"""
        UPDATE text_blocks
        SET {column} = ?,
            updated_at = ?
        WHERE project_id = ? AND text_block_id = ?
        """,
        (
            status_update.status,
            _utc_now(),
            project_id,
            status_update.target_id,
        ),
    )


def _next_attempt_number(
    connection: sqlite3.Connection,
    project_id: str,
    task_id: str,
) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(attempt_number), 0) + 1 AS attempt_number
        FROM workflow_attempts
        WHERE project_id = ? AND task_id = ?
        """,
        (project_id, task_id),
    ).fetchone()
    return int(row["attempt_number"])


def _connect_existing(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(_sqlite_readwrite_uri(path), uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _sqlite_readwrite_uri(path: Path) -> str:
    return f"file:{quote(str(path), safe='/')}?mode=rw"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
