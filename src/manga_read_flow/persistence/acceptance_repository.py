from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sqlite3
from typing import Mapping

from manga_read_flow.domain.detection_evidence import (
    AcceptedDetectionEvidenceSetDraft,
)
from manga_read_flow.persistence.detection_evidence_repository import (
    persist_detection_evidence_provenance,
    persist_detection_evidence_set,
)
from manga_read_flow.persistence.grouping_acceptance_repository import (
    GroupingCommitResult,
    GroupingDecisionContextDraft,
    persist_grouping_commit,
    persist_stale_plans_and_clear_pointer,
    plan_upstream_grouping_stale,
    validate_grouping_commit,
    _ocr_dependency_hash,
)
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
from manga_read_flow.persistence.visual_contract_repository import (
    CleaningResultDraft,
    insert_cleaning_result,
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
    visual_contract_revision_ids: Mapping[str, str] = field(default_factory=dict)
    attempt_id: str | None = None
    attempt_status: str | None = None
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
    geometry_hash: str | None = None
    input_hash: str | None = None
    config_hash: str | None = None


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
    accepted_detection_evidence: AcceptedDetectionEvidenceSetDraft | None = None
    page_statuses: tuple[PageStatusUpdate, ...] = ()
    attempt_terminal_status: str | None = None
    cleaning_result: CleaningResultDraft | None = None
    grouping_context: GroupingDecisionContextDraft | None = None


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
    accepted_detection_evidence_set_id: str | None = None
    grouping_acceptance_id: str | None = None
    active_grouping_snapshot_id: str | None = None
    page_grouping_state_version: int | None = None
    grouping_acceptance_replayed: bool = False
    grouping_stale_fact_ids: tuple[str, ...] = ()
    grouping_pointer_cleared: bool = False


class AcceptanceRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def accept_stage(self, command: AcceptanceCommand) -> AcceptanceOutcome:
        with connect_existing(self._project_db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
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
            conflicts.extend(
                _visual_contract_conflicts(connection, self._project_id, command.expected)
            )
            conflicts.extend(
                _attempt_conflicts(connection, self._project_id, command.expected)
            )
            grouping_plan = None
            if command.grouping_context is not None:
                grouping_plan, grouping_conflicts = validate_grouping_commit(
                    connection,
                    project_id=self._project_id,
                    task_id=command.task_id,
                    decision=command.workflow_decision,
                    context=command.grouping_context,
                )
                conflicts.extend(grouping_conflicts)
            if conflicts:
                return AcceptanceOutcome(
                    committed=False,
                    reload_required=True,
                    conflict_fields=tuple(dict.fromkeys(conflicts)),
                )

            if command.grouping_context is not None and (
                command.accepted_detection_evidence is not None
                or any(result.result_type == "ocr" for result in command.accepted_results)
            ):
                raise ValueError("Grouping acceptance cannot also mutate its dependencies.")

            stale_plans = []
            detection = command.accepted_detection_evidence
            if detection is not None:
                plan = plan_upstream_grouping_stale(
                    connection, project_id=self._project_id, page_id=detection.page_id,
                    reason_type="DETECTION_DEPENDENCY_CHANGED",
                    previous_dependency_type="ACCEPTED_DETECTION_EVIDENCE_SET",
                    replacement_dependency_id=detection.detection_dependency_id,
                    replacement_dependency_hash=detection.canonical_manifest_sha256,
                    triggering_operation_type="DETECTION_ACCEPTANCE",
                    triggering_operation_id=detection.provenance.acceptance_id,
                )
                if plan is not None:
                    stale_plans.append(plan)
            result_by_id = {result.result_id: result for result in command.accepted_results}
            for pointer in command.active_pointers:
                if pointer.pointer_name != "active_ocr_result_id" or pointer.value_id is None:
                    continue
                result = result_by_id.get(pointer.value_id)
                if result is None or result.result_type != "ocr":
                    continue
                row = connection.execute(
                    "SELECT page_id FROM text_blocks WHERE project_id = ? AND text_block_id = ?",
                    (self._project_id, pointer.owner_id),
                ).fetchone()
                if row is None:
                    continue
                existing_result = connection.execute(
                    "SELECT version_number FROM ocr_results WHERE project_id = ? AND ocr_result_id = ?",
                    (self._project_id, result.result_id),
                ).fetchone()
                if existing_result is None:
                    version = connection.execute(
                        "SELECT COALESCE(MAX(version_number), 0) + 1 AS version FROM ocr_results WHERE project_id = ? AND text_block_id = ?",
                        (self._project_id, pointer.owner_id),
                    ).fetchone()["version"]
                else:
                    version = existing_result["version_number"]
                replacement_hash = _ocr_dependency_hash(
                    result.result_id, version, result.source_text_hash or "",
                    result.geometry_hash or "", result.input_hash or "",
                )
                plan = plan_upstream_grouping_stale(
                    connection, project_id=self._project_id, page_id=row["page_id"],
                    reason_type="OCR_DEPENDENCY_CHANGED",
                    previous_dependency_type="OCR_RESULT",
                    replacement_dependency_id=result.result_id,
                    replacement_dependency_hash=replacement_hash,
                    triggering_operation_type="OCR_ACCEPTANCE",
                    triggering_operation_id=command.workflow_decision.decision_id,
                    text_block_id=pointer.owner_id,
                )
                if plan is not None:
                    stale_plans.append(plan)

            if (
                command.accepted_text_blocks
                and command.accepted_detection_evidence is None
            ):
                raise ValueError(
                    "Accepted Detection blocks and evidence set must be persisted together."
                )
            if command.accepted_detection_evidence is not None and (
                command.workflow_decision.stage != "detection"
                or command.workflow_decision.attempt_id
                != command.accepted_detection_evidence.provenance.workflow_attempt_id
                or command.workflow_decision.decision_id
                != command.accepted_detection_evidence.provenance.workflow_decision_id
            ):
                raise ValueError("Detection evidence must bind the acceptance decision.")

            for text_block in command.accepted_text_blocks:
                _insert_accepted_text_block(connection, self._project_id, text_block)
            if command.accepted_detection_evidence is not None:
                persist_detection_evidence_set(
                    connection,
                    self._project_id,
                    command.accepted_detection_evidence,
                    command.accepted_text_blocks,
                )
            for result in command.accepted_results:
                _insert_accepted_result(connection, self._project_id, result)
            for pointer in command.active_pointers:
                _apply_active_pointer(connection, self._project_id, pointer)
            grouping_stale_ids, grouping_stale_version = persist_stale_plans_and_clear_pointer(
                connection, plans=tuple(stale_plans)
            )
            for issue_change in command.issue_lifecycle:
                _apply_issue_change(connection, self._project_id, issue_change)
            if command.cleaning_result is not None:
                insert_cleaning_result(
                    connection,
                    self._project_id,
                    command.cleaning_result,
                )
            _insert_workflow_decision(
                connection,
                self._project_id,
                command.task_id,
                command.workflow_decision,
            )
            grouping_commit = GroupingCommitResult(None, None, None, False)
            if grouping_plan is not None:
                grouping_commit = persist_grouping_commit(
                    connection,
                    project_id=self._project_id,
                    decision=command.workflow_decision,
                    plan=grouping_plan,
                )
            if command.accepted_detection_evidence is not None:
                persist_detection_evidence_provenance(
                    connection,
                    self._project_id,
                    command.accepted_detection_evidence,
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
            accepted_detection_evidence_set_id=(
                command.accepted_detection_evidence.detection_dependency_id
                if command.accepted_detection_evidence is not None
                else None
            ),
            grouping_acceptance_id=grouping_commit.acceptance_id,
            active_grouping_snapshot_id=grouping_commit.active_grouping_snapshot_id,
            page_grouping_state_version=grouping_commit.page_grouping_state_version,
            grouping_acceptance_replayed=grouping_commit.replayed,
            grouping_stale_fact_ids=(
                tuple(grouping_stale_ids) + grouping_commit.stale_fact_ids
            ),
            grouping_pointer_cleared=bool(grouping_stale_ids),
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


def _visual_contract_conflicts(
    connection: sqlite3.Connection,
    project_id: str,
    expected: ExpectedState,
) -> tuple[str, ...]:
    conflicts = []
    for page_id, revision_id in expected.visual_contract_revision_ids.items():
        row = connection.execute(
            """
            SELECT active_visual_contract_revision_id
            FROM page_visual_contract_state
            WHERE project_id = ? AND page_id = ?
            """,
            (project_id, page_id),
        ).fetchone()
        if row is None or row["active_visual_contract_revision_id"] != revision_id:
            conflicts.append("active_visual_contract_revision_id")
    return tuple(conflicts)


def _attempt_conflicts(
    connection: sqlite3.Connection,
    project_id: str,
    expected: ExpectedState,
) -> tuple[str, ...]:
    if expected.attempt_id is None:
        return ()
    row = connection.execute(
        """
        SELECT status
        FROM workflow_attempts
        WHERE project_id = ? AND attempt_id = ?
        """,
        (project_id, expected.attempt_id),
    ).fetchone()
    if row is None:
        return ("attempt_id",)
    if expected.attempt_status is not None and row["status"] != expected.attempt_status:
        return ("attempt_status",)
    return ()


def _insert_accepted_text_block(
    connection: sqlite3.Connection,
    project_id: str,
    text_block: AcceptedTextBlock,
) -> None:
    existing = connection.execute(
        """
        SELECT
            project_id,
            page_id,
            reading_order,
            detection_status,
            bbox_json,
            polygon_json,
            geometry_hash,
            detection_provider,
            detection_confidence
        FROM text_blocks
        WHERE text_block_id = ?
        """,
        (text_block.text_block_id,),
    ).fetchone()
    if existing is not None:
        if (
            existing["project_id"] != project_id
            or existing["page_id"] != text_block.page_id
        ):
            raise ValueError(
                "Accepted Detection member conflicts with another Project or Page."
            )
        expected = (
            project_id,
            text_block.page_id,
            text_block.reading_order,
            "done",
            text_block.bbox_json,
            text_block.polygon_json,
            text_block.geometry_hash,
            text_block.detection_provider,
            text_block.detection_confidence,
        )
        actual = tuple(existing)
        if actual == expected:
            return
        now = utc_now()
        block_update = connection.execute(
            """
            UPDATE text_blocks
            SET reading_order = ?,
                detection_status = 'done',
                bbox_json = ?,
                polygon_json = ?,
                geometry_hash = ?,
                detection_provider = ?,
                detection_confidence = ?,
                active_ocr_result_id = NULL,
                active_translation_result_id = NULL,
                ocr_status = 'pending',
                translation_status = 'pending',
                translation_check_status = 'pending',
                cleaning_status = 'pending',
                typesetting_status = 'pending',
                review_status = 'pending',
                updated_at = ?
            WHERE project_id = ? AND text_block_id = ?
            """,
            (
                text_block.reading_order,
                text_block.bbox_json,
                text_block.polygon_json,
                text_block.geometry_hash,
                text_block.detection_provider,
                text_block.detection_confidence,
                now,
                project_id,
                text_block.text_block_id,
            ),
        )
        page_update = connection.execute(
            """
            UPDATE pages
            SET active_cleaned_artifact_id = NULL,
                active_typeset_artifact_id = NULL,
                updated_at = ?
            WHERE project_id = ? AND page_id = ?
            """,
            (now, project_id, text_block.page_id),
        )
        if block_update.rowcount != 1 or page_update.rowcount != 1:
            raise ValueError(
                "Accepted Detection member stale propagation was not applied."
            )
        return
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
                input_hash,
                config_hash,
                geometry_hash,
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
                result.input_hash,
                result.config_hash,
                result.geometry_hash,
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
                input_hash,
                config_hash,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                result.input_hash,
                result.config_hash,
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


def apply_issue_lifecycle_change(
    connection: sqlite3.Connection,
    project_id: str,
    issue_change: IssueLifecycleChange,
) -> None:
    """Apply the shared QualityIssue lifecycle inside an owning UoW transaction."""
    _apply_issue_change(connection, project_id, issue_change)


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
