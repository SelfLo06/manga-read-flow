from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from manga_read_flow.persistence.sqlite_repository_helpers import (
    connect_existing,
    utc_now,
)


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
class UnitOfWorkOutcome:
    committed: bool
    reload_required: bool
    conflict_fields: tuple[str, ...] = ()
    attempt_id: str | None = None


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
        now = utc_now()
        with connect_existing(self._project_db_path) as connection:
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

    def reserve_attempt(self, command: AttemptReservation) -> UnitOfWorkOutcome:
        with connect_existing(self._project_db_path) as connection:
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

            now = utc_now()
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


class QualityIssueRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def count_open_blockers(self) -> int:
        with connect_existing(self._project_db_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM quality_issues
                WHERE project_id = ? AND is_blocking = 1 AND status = ?
                """,
                (self._project_id, "open"),
            ).fetchone()
        return int(row["count"])


class ReadinessQueryRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def get_task_readiness(self, task_id: str) -> ReadinessSnapshot:
        with connect_existing(self._project_db_path) as connection:
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
        now = utc_now()
        with connect_existing(self._project_db_path) as connection:
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
        with connect_existing(self._project_db_path) as connection:
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
                    utc_now(),
                    self._project_id,
                    command.tool_run_id,
                ),
            )
            return _load_tool_run(connection, self._project_id, command.tool_run_id)

    def record_attempt_evidence(self, command: AttemptEvidence) -> AttemptSnapshot:
        with connect_existing(self._project_db_path) as connection:
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
                    utc_now(),
                    self._project_id,
                    command.attempt_id,
                ),
            )
            return _load_attempt(connection, self._project_id, command.attempt_id)


def initialize_workflow_execution_schema(connection: sqlite3.Connection) -> None:
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
