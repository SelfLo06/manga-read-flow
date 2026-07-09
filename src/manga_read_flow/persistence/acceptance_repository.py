from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sqlite3
from typing import Mapping

from manga_read_flow.persistence.content_state_repository import (
    _load_page,
    _load_text_block,
)
from manga_read_flow.persistence.sqlite_repository_helpers import (
    connect_existing,
    utc_now,
)
from manga_read_flow.persistence.workflow_execution_repository import (
    _load_task,
    _task_conflicts,
)


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


class AcceptanceRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def accept_stage(self, command: AcceptanceCommand) -> AcceptanceOutcome:
        with connect_existing(self._project_db_path) as connection:
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
                    utc_now(),
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
                utc_now(),
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
                utc_now(),
            ),
        )
    else:
        raise ValueError(f"Unsupported result type: {result.result_type}")


def _apply_active_pointer(
    connection: sqlite3.Connection,
    project_id: str,
    pointer: ActivePointerUpdate,
) -> None:
    now = utc_now()
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
    now = utc_now()
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
            utc_now(),
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
            utc_now(),
            project_id,
            status_update.target_id,
        ),
    )
