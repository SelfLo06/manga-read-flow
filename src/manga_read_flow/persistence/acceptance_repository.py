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
class ExpectedStageStatus:
    target_type: str
    target_id: str
    stage: str
    status: str


@dataclass(frozen=True)
class ExpectedState:
    task_status: str
    current_stage: str
    active_ocr_result_ids: Mapping[str, str | None] = field(default_factory=dict)
    active_translation_result_ids: Mapping[str, str | None] = field(default_factory=dict)
    page_artifact_ids: Mapping[str, Mapping[str, str | None]] = field(default_factory=dict)
    stage_statuses: tuple[ExpectedStageStatus, ...] = ()


@dataclass(frozen=True)
class AcceptedResult:
    result_type: str
    result_id: str
    target_type: str
    target_id: str
    source_text: str | None = None
    source_text_hash: str | None = None
    translation_text: str | None = None
    translation_text_hash: str | None = None
    source_ocr_result_id: str | None = None
    glossary_version_id: str | None = None
    provider_name: str | None = None
    model_id: str | None = None
    workflow_attempt_id: str | None = None
    tool_run_id: str | None = None


@dataclass(frozen=True)
class AcceptedTextBlock:
    text_block_id: str
    page_id: str
    reading_order: int
    bbox_json: str
    polygon_json: str
    geometry_hash: str
    detection_provider: str
    detection_confidence: float | None = None


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
    target_type: str | None = None
    target_id: str | None = None
    batch_id: str | None = None
    page_id: str | None = None
    text_block_id: str | None = None
    discovered_stage: str | None = None
    root_stage: str | None = None
    error_code: str | None = None
    severity: str | None = None
    message_key: str | None = None
    message_params_json: str | None = None
    suggested_action_key: str | None = None
    related_attempt_id: str | None = None
    related_tool_run_id: str | None = None
    related_artifact_id: str | None = None
    applies_to_result_id: str | None = None
    input_hash: str | None = None
    config_hash: str | None = None
    dedupe_key: str | None = None


@dataclass(frozen=True)
class WorkflowDecisionDraft:
    decision_id: str
    attempt_id: str | None
    stage: str
    decision_type: str
    reason_code: str
    linked_issue_ids: tuple[str, ...] = ()
    issue_relation_type: str = "caused_by"


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
class PageStatusUpdate:
    page_id: str
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
    accepted_text_blocks: tuple[AcceptedTextBlock, ...] = ()
    page_statuses: tuple[PageStatusUpdate, ...] = ()
    attempt_terminal_status: str | None = None


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
            conflicts.extend(
                _stage_status_conflicts(connection, self._project_id, command.expected)
            )
            if conflicts:
                return AcceptanceOutcome(
                    committed=False,
                    reload_required=True,
                    conflict_fields=tuple(dict.fromkeys(conflicts)),
                )

            for text_block in command.accepted_text_blocks:
                _insert_accepted_text_block(connection, self._project_id, text_block)
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
            for page_status in command.page_statuses:
                _apply_page_status(connection, self._project_id, page_status)
            if command.attempt_terminal_status is not None:
                _apply_attempt_terminal_status(
                    connection,
                    self._project_id,
                    command.workflow_decision.attempt_id,
                    command.attempt_terminal_status,
                )

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


def _stage_status_conflicts(
    connection: sqlite3.Connection,
    project_id: str,
    expected: ExpectedState,
) -> tuple[str, ...]:
    conflicts: list[str] = []
    columns = {
        "detection": "detection_status",
        "ocr": "ocr_status",
        "translation": "translation_status",
        "translation_check": "translation_check_status",
        "cleaning": "cleaning_status",
        "typesetting": "typesetting_status",
        "review": "review_status",
    }
    for expected_status in expected.stage_statuses:
        if expected_status.target_type != "text_block":
            raise ValueError(
                f"Unsupported expected status target type: {expected_status.target_type}"
            )
        column = columns.get(expected_status.stage)
        if column is None:
            raise ValueError(f"Unsupported expected status stage: {expected_status.stage}")
        block = _load_text_block(connection, project_id, expected_status.target_id)
        actual_status = getattr(block, column)
        if actual_status != expected_status.status:
            conflicts.append(column)
    return tuple(conflicts)


def _insert_accepted_text_block(
    connection: sqlite3.Connection,
    project_id: str,
    text_block: AcceptedTextBlock,
) -> None:
    connection.execute(
        """
        INSERT INTO text_blocks (
            text_block_id,
            project_id,
            page_id,
            reading_order,
            detection_status,
            bbox_json,
            polygon_json,
            geometry_hash,
            detection_provider,
            detection_confidence,
            active_ocr_result_id,
            active_translation_result_id,
            ocr_status,
            translation_status,
            translation_check_status,
            cleaning_status,
            typesetting_status,
            review_status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            text_block.text_block_id,
            project_id,
            text_block.page_id,
            text_block.reading_order,
            "done",
            text_block.bbox_json,
            text_block.polygon_json,
            text_block.geometry_hash,
            text_block.detection_provider,
            text_block.detection_confidence,
            None,
            None,
            "pending",
            "pending",
            "pending",
            "pending",
            "pending",
            "pending",
            utc_now(),
            utc_now(),
        ),
    )


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
                version_number,
                source_type,
                source_text,
                source_text_hash,
                provider_name,
                model_id,
                workflow_attempt_id,
                tool_run_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.result_id,
                project_id,
                result.target_id,
                _next_result_version(
                    connection,
                    project_id,
                    result.target_id,
                    result_table="ocr_results",
                    result_id_column="ocr_result_id",
                ),
                "workflow_acceptance",
                result.source_text,
                result.source_text_hash,
                result.provider_name,
                result.model_id,
                result.workflow_attempt_id,
                result.tool_run_id,
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
                version_number,
                source_type,
                source_ocr_result_id,
                source_text_hash,
                translation_text,
                translation_text_hash,
                glossary_version_id,
                provider_name,
                model_id,
                workflow_attempt_id,
                tool_run_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.result_id,
                project_id,
                result.target_id,
                _next_result_version(
                    connection,
                    project_id,
                    result.target_id,
                    result_table="translation_results",
                    result_id_column="translation_result_id",
                ),
                "workflow_acceptance",
                result.source_ocr_result_id,
                result.source_text_hash,
                result.translation_text,
                result.translation_text_hash,
                result.glossary_version_id,
                result.provider_name,
                result.model_id,
                result.workflow_attempt_id,
                result.tool_run_id,
                utc_now(),
            ),
        )
    else:
        raise ValueError(f"Unsupported result type: {result.result_type}")


def _next_result_version(
    connection: sqlite3.Connection,
    project_id: str,
    text_block_id: str,
    *,
    result_table: str,
    result_id_column: str,
) -> int:
    if result_table not in {"ocr_results", "translation_results"}:
        raise ValueError(f"Unsupported result table: {result_table}")
    if result_id_column not in {"ocr_result_id", "translation_result_id"}:
        raise ValueError(f"Unsupported result id column: {result_id_column}")

    row = connection.execute(
        f"""
        SELECT COALESCE(MAX(version_number), 0) + 1 AS version_number
        FROM {result_table}
        WHERE project_id = ? AND text_block_id = ?
        """,
        (project_id, text_block_id),
    ).fetchone()
    return int(row["version_number"])


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
                target_type,
                target_id,
                batch_id,
                page_id,
                text_block_id,
                discovered_stage,
                root_stage,
                issue_type,
                error_code,
                severity,
                status,
                is_blocking,
                message_key,
                message_params_json,
                suggested_action_key,
                related_attempt_id,
                related_tool_run_id,
                related_artifact_id,
                applies_to_result_id,
                input_hash,
                config_hash,
                dedupe_key,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue_change.issue_id,
                project_id,
                issue_change.target_type,
                issue_change.target_id,
                issue_change.batch_id,
                issue_change.page_id,
                issue_change.text_block_id,
                issue_change.discovered_stage,
                issue_change.root_stage,
                issue_change.issue_type,
                issue_change.error_code,
                issue_change.severity,
                issue_change.status,
                int(issue_change.is_blocking),
                issue_change.message_key,
                issue_change.message_params_json,
                issue_change.suggested_action_key,
                issue_change.related_attempt_id,
                issue_change.related_tool_run_id,
                issue_change.related_artifact_id,
                issue_change.applies_to_result_id,
                issue_change.input_hash,
                issue_change.config_hash,
                issue_change.dedupe_key,
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
    now = utc_now()
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
            now,
        ),
    )
    for issue_id in decision.linked_issue_ids:
        connection.execute(
            """
            INSERT INTO workflow_decision_issues (
                decision_id,
                issue_id,
                relation_type,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                issue_id,
                decision.issue_relation_type,
                now,
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
        "detection": "detection_status",
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


def _apply_page_status(
    connection: sqlite3.Connection,
    project_id: str,
    page_status: PageStatusUpdate,
) -> None:
    connection.execute(
        """
        UPDATE pages
        SET status = ?,
            updated_at = ?
        WHERE project_id = ? AND page_id = ?
        """,
        (
            page_status.status,
            utc_now(),
            project_id,
            page_status.page_id,
        ),
    )


def _apply_attempt_terminal_status(
    connection: sqlite3.Connection,
    project_id: str,
    attempt_id: str | None,
    status: str,
) -> None:
    if attempt_id is None:
        return
    connection.execute(
        """
        UPDATE workflow_attempts
        SET status = ?,
            updated_at = ?
        WHERE project_id = ? AND attempt_id = ?
        """,
        (status, utc_now(), project_id, attempt_id),
    )
