from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from manga_read_flow.providers.fake import FakeProvider
from manga_read_flow.quality import (
    QualityCheckInput,
    QualityCheckReport,
    QualityCheckService,
)
from manga_read_flow.persistence.repository_uow_core import (
    AcceptanceCommand,
    AcceptedResult,
    AcceptedTextBlock,
    ActivePointerUpdate,
    ExpectedState,
    ExpectedStageStatus,
    IssueLifecycleChange,
    PageStatusUpdate,
    StageStatusUpdate,
    TaskProgressUpdate,
    WorkflowDecisionDraft,
)
from manga_read_flow.workflow.detection_outputs import detected_text_blocks
from manga_read_flow.workflow.quality_acceptance import issue_changes_from_drafts
from manga_read_flow.workflow.readiness import accept_export_check
from manga_read_flow.workflow.reuse import (
    ReuseReservationConflictError,
    WorkflowReuseService,
    accept_reuse_plan,
)
from manga_read_flow.workflow.stage_results import stage_error_code, synthetic_stage_result
from manga_read_flow.workflow.stage_executor import (
    StageExecutionConflictError,
    StageExecutionContext,
    StageExecutor,
    StageResult,
)


_STAGE_ORDER = (
    "detection",
    "ocr",
    "translation",
    "translation_check",
    "cleaning",
    "typesetting",
    "export_check",
)


@dataclass(frozen=True)
class ProcessPageResult:
    task_id: str
    task_status: str
    page_id: str
    page_status: str
    final_decision: str


class WorkflowLoopEngine:
    def __init__(
        self,
        *,
        repositories,
        artifact_service,
        stage_executor: StageExecutor,
        provider: FakeProvider,
        quality_check_service: QualityCheckService | None = None,
    ) -> None:
        self._repositories = repositories
        self._artifact_service = artifact_service
        self._stage_executor = stage_executor
        self._provider = provider
        self._quality_check_service = quality_check_service or QualityCheckService()
        self._project_id = repositories.identity.get_metadata().project_id
        self._config_hash = _hash_text("fakeprovider-default-config")
        self._reuse = WorkflowReuseService(
            repositories=repositories,
            artifact_service=artifact_service,
            provider=provider,
            config_hash=self._config_hash,
        )

    def run_task(self, task_id: str) -> ProcessPageResult:
        while True:
            task = self._repositories.workflow_execution.get_task(task_id)
            page = self._repositories.content_state.get_page(task.target_id)
            if task.status in {"succeeded", "succeeded_with_warnings", "blocked", "failed"}:
                return ProcessPageResult(
                    task_id=task.task_id,
                    task_status=task.status,
                    page_id=page.page_id,
                    page_status=page.status,
                    final_decision=task.current_stage,
                )

            precondition = self._precondition_block(task, page)
            if precondition is not None:
                return precondition

            reuse_plan = self._reuse.plan_reuse(task, page)
            if reuse_plan is not None:
                try:
                    reuse = accept_reuse_plan(
                        repositories=self._repositories,
                        task=task,
                        page=page,
                        plan=reuse_plan,
                        build_command=self._command,
                    )
                except ReuseReservationConflictError:
                    return ProcessPageResult(
                        task_id=task.task_id,
                        task_status="conflict",
                        page_id=page.page_id,
                        page_status=page.status,
                        final_decision="reload_required",
                    )
                if not reuse.committed:
                    return ProcessPageResult(
                        task_id=task.task_id,
                        task_status="conflict",
                        page_id=page.page_id,
                        page_status=page.status,
                        final_decision="reload_required",
                    )
                continue

            try:
                stage_result = self._execute_stage(task, page)
            except StageExecutionConflictError:
                return ProcessPageResult(
                    task_id=task.task_id,
                    task_status="conflict",
                    page_id=page.page_id,
                    page_status=page.status,
                    final_decision="reload_required",
                )
            quality_report = self._quality_report(task, page, stage_result)

            acceptance = self._accept_stage(task, page, stage_result, quality_report)
            if not acceptance.committed:
                return ProcessPageResult(
                    task_id=task.task_id,
                    task_status="conflict",
                    page_id=page.page_id,
                    page_status=page.status,
                    final_decision="reload_required",
                )
            if acceptance.task_status in {
                "succeeded",
                "succeeded_with_warnings",
                "blocked",
                "failed",
            }:
                latest_page = self._repositories.content_state.get_page(page.page_id)
                return ProcessPageResult(
                    task_id=task.task_id,
                    task_status=acceptance.task_status,
                    page_id=latest_page.page_id,
                    page_status=latest_page.status,
                    final_decision=acceptance.current_stage or stage_result.stage,
                )

    def _execute_stage(self, task, page) -> StageResult:
        text_block_ids = tuple(
            block.text_block_id
            for block in self._repositories.content_state.list_text_blocks_for_page(
                page.page_id
            )
        )
        input_hash = self._reuse.stage_input_hash(task.current_stage, page)
        attempt_id = f"attempt-{task.current_stage}-{uuid4()}"
        tool_run_id = f"tool-run-{task.current_stage}-{uuid4()}"
        request_id = f"request-{task.current_stage}-{uuid4()}"
        with TemporaryDirectory(prefix=f"mrf-{task.current_stage}-") as temp_dir:
            return self._stage_executor.execute(
                StageExecutionContext(
                    project_id=self._project_id,
                    task_id=task.task_id,
                    attempt_id=attempt_id,
                    tool_run_id=tool_run_id,
                    request_id=request_id,
                    stage=task.current_stage,
                    target_type=task.target_type,
                    target_id=task.target_id,
                    batch_id=page.batch_id,
                    page_id=page.page_id,
                    text_block_ids=text_block_ids,
                    expected_task_status=task.status,
                    expected_current_stage=task.current_stage,
                    runner_id="local-taskrunner",
                    attempt_temp_root=Path(temp_dir),
                    input_hash=input_hash,
                    config_hash=self._config_hash,
                    context_hash=_hash_text(f"{page.page_id}:{task.current_stage}:context"),
                    source_language="ja",
                    target_language="zh-Hans",
                ),
                self._provider,
            )

    def _precondition_block(self, task, page) -> ProcessPageResult | None:
        if task.current_stage == "translation":
            ocr_inputs = self._repositories.result_versions.active_ocr_inputs_for_page(
                page.page_id
            )
            if any(row.active_ocr_result_id is None for row in ocr_inputs):
                return self._accept_blocked(
                    task_id=task.task_id,
                    page_id=page.page_id,
                    task_status=task.status,
                    current_stage=task.current_stage,
                    attempt_id=None,
                    reason_code="missing_active_ocr_pointer",
                    issue_type="missing_active_ocr_pointer",
                )
        if task.current_stage == "typesetting":
            translations = (
                self._repositories.result_versions.active_translation_inputs_for_page(
                    page.page_id
                )
            )
            if any(row.active_translation_result_id is None for row in translations):
                return self._accept_blocked(
                    task_id=task.task_id,
                    page_id=page.page_id,
                    task_status=task.status,
                    current_stage=task.current_stage,
                    attempt_id=None,
                    reason_code="missing_active_translation_pointer",
                    issue_type="missing_active_translation_pointer",
                )
        return None

    def _quality_report(self, task, page, stage_result: StageResult) -> QualityCheckReport:
        error = stage_result.provider_result.error
        return self._quality_check_service.check(
            QualityCheckInput(
                stage=stage_result.stage,
                target_type=stage_result.target_type,
                target_id=stage_result.target_id,
                batch_id=page.batch_id,
                page_id=page.page_id,
                text_block_ids=tuple(
                    block.text_block_id
                    for block in self._repositories.content_state.list_text_blocks_for_page(
                        page.page_id
                    )
                ),
                provider_outcome=stage_result.provider_result.outcome.value,
                error_kind=error.kind if error is not None else None,
                error_code=stage_error_code(stage_result)
                if stage_result.status != "succeeded"
                else None,
                is_provider_refusal=error.is_provider_refusal
                if error is not None
                else False,
                workflow_attempt_id=stage_result.attempt_id,
                tool_run_id=stage_result.tool_run_id,
                input_hash=self._reuse.stage_input_hash(stage_result.stage, page),
                config_hash=self._config_hash,
                candidate_outputs=stage_result.candidate_outputs,
                registered_artifact_ids=tuple(
                    artifact.artifact_id
                    for artifact in stage_result.registered_artifacts
                ),
            )
        )

    def _accept_stage(
        self,
        task,
        page,
        stage_result: StageResult,
        quality_report: QualityCheckReport,
    ):
        if stage_result.stage == "detection":
            return self._accept_detection(task, page, stage_result)
        if stage_result.stage == "ocr":
            return self._accept_ocr(task, page, stage_result)
        if stage_result.stage == "translation":
            return self._accept_translation(task, page, stage_result, quality_report)
        if stage_result.stage == "translation_check":
            return self._accept_stage_status_only(task, page, stage_result)
        if stage_result.stage == "cleaning":
            return self._accept_cleaning(task, page, stage_result, quality_report)
        if stage_result.stage == "typesetting":
            return self._accept_typesetting(task, page, stage_result, quality_report)
        if stage_result.stage == "export_check":
            return accept_export_check(
                repositories=self._repositories,
                artifact_service=self._artifact_service,
                task=task,
                page=page,
                stage_result=stage_result,
                build_command=self._command,
                build_blocked_command=self._blocked_command,
            )
        raise ValueError(f"Unsupported stage: {stage_result.stage}")

    def _accept_detection(self, task, page, stage_result: StageResult):
        return self._repositories.uow.accept_stage(
            self._command(
                task_id=task.task_id,
                task_status=task.status,
                current_stage=task.current_stage,
                page=page,
                stage_result=stage_result,
                decision_type="continue",
                reason_code="fake_detection_accepted",
                next_stage="ocr",
                accepted_text_blocks=tuple(
                    AcceptedTextBlock(
                        text_block_id=text_block.text_block_id,
                        page_id=page.page_id,
                        reading_order=text_block.reading_order,
                        bbox_json=text_block.bbox_json,
                        polygon_json=text_block.polygon_json,
                        geometry_hash=text_block.geometry_hash,
                        detection_provider=stage_result.provider_result.provider_name,
                        detection_confidence=text_block.confidence,
                    )
                    for text_block in detected_text_blocks(
                        page.page_id,
                        stage_result.candidate_outputs,
                    )
                ),
                page_status="processing",
            )
        )

    def _accept_ocr(self, task, page, stage_result: StageResult):
        blocks = self._repositories.content_state.list_text_blocks_for_page(page.page_id)
        result_by_block = {
            str(result["text_block_id"]): result
            for result in stage_result.candidate_outputs.get("ocr_items", ())
        }
        accepted_results = []
        active_pointers = []
        stage_statuses = []
        input_hash = self._reuse.stage_input_hash("ocr", page)
        for block in blocks:
            result = result_by_block[block.text_block_id]
            result_id = f"ocr-{block.text_block_id}-{uuid4()}"
            source_text = str(result["source_text"])
            accepted_results.append(
                AcceptedResult(
                    result_type="ocr",
                    result_id=result_id,
                    target_type="text_block",
                    target_id=block.text_block_id,
                    source_text=source_text,
                    source_text_hash=_hash_text(source_text),
                    provider_name=stage_result.provider_result.provider_name,
                    model_id=stage_result.provider_result.model_id,
                    workflow_attempt_id=stage_result.attempt_id,
                    tool_run_id=stage_result.provider_result.payload.get("tool_run_id"),
                    geometry_hash=block.geometry_hash,
                    input_hash=input_hash,
                    config_hash=self._config_hash,
                )
            )
            active_pointers.append(
                ActivePointerUpdate(
                    owner_type="text_block",
                    owner_id=block.text_block_id,
                    pointer_name="active_ocr_result_id",
                    value_id=result_id,
                )
            )
            stage_statuses.append(
                StageStatusUpdate(
                    target_type="text_block",
                    target_id=block.text_block_id,
                    stage="ocr",
                    status="done",
                )
            )

        return self._repositories.uow.accept_stage(
            self._command(
                task_id=task.task_id,
                task_status=task.status,
                current_stage=task.current_stage,
                page=page,
                stage_result=stage_result,
                decision_type="continue",
                reason_code="fake_ocr_accepted",
                next_stage="translation",
                expected_ocr={
                    block.text_block_id: block.active_ocr_result_id for block in blocks
                },
                accepted_results=tuple(accepted_results),
                active_pointers=tuple(active_pointers),
                stage_statuses=tuple(stage_statuses),
                expected_stage_statuses=tuple(
                    ExpectedStageStatus(
                        target_type="text_block",
                        target_id=block.text_block_id,
                        stage="ocr",
                        status=block.ocr_status,
                    )
                    for block in blocks
                ),
            )
        )

    def _accept_translation(
        self,
        task,
        page,
        stage_result: StageResult,
        quality_report: QualityCheckReport,
    ):
        if stage_result.status in {"invalid_output", "refused", "failed"}:
            return self._accept_quality_block(
                task,
                page,
                stage_result,
                quality_report,
                reason_code=stage_error_code(stage_result),
                attempt_terminal_status="refused"
                if stage_result.status == "refused"
                else "failed",
            )

        glossary_version_id = self._repositories.glossary.ensure_empty_version()
        ocr_inputs = self._repositories.result_versions.active_ocr_inputs_for_page(
            page.page_id
        )
        blocks_by_id = {
            block.text_block_id: block
            for block in self._repositories.content_state.list_text_blocks_for_page(
                page.page_id
            )
        }
        result_by_block = {
            str(result["text_block_id"]): result
            for result in stage_result.candidate_outputs.get("translations", ())
        }
        accepted_results = []
        active_pointers = []
        stage_statuses = []
        input_hash = self._reuse.stage_input_hash("translation", page)
        missing_block_ids = {
            draft.target_id
            for draft in quality_report.issue_drafts
            if draft.issue_type == "translation_missing_block"
        }
        for row in ocr_inputs:
            text_block_id = row.text_block_id
            if text_block_id in missing_block_ids:
                stage_statuses.append(
                    StageStatusUpdate(
                        target_type="text_block",
                        target_id=text_block_id,
                        stage="translation",
                        status="blocked",
                    )
                )
                continue
            result = result_by_block[text_block_id]
            result_id = f"translation-{text_block_id}-{uuid4()}"
            translation_text = str(result["translation_text"])
            accepted_results.append(
                AcceptedResult(
                    result_type="translation",
                    result_id=result_id,
                    target_type="text_block",
                    target_id=text_block_id,
                    source_ocr_result_id=row.active_ocr_result_id,
                    source_text_hash=row.source_text_hash,
                    translation_text=translation_text,
                    translation_text_hash=_hash_text(translation_text),
                    glossary_version_id=glossary_version_id,
                    provider_name=stage_result.provider_result.provider_name,
                    model_id=stage_result.provider_result.model_id,
                    workflow_attempt_id=stage_result.attempt_id,
                    tool_run_id=stage_result.provider_result.payload.get("tool_run_id"),
                    input_hash=input_hash,
                    config_hash=self._config_hash,
                )
            )
            active_pointers.append(
                ActivePointerUpdate(
                    owner_type="text_block",
                    owner_id=text_block_id,
                    pointer_name="active_translation_result_id",
                    value_id=result_id,
                )
            )
            stage_statuses.append(
                StageStatusUpdate(
                    target_type="text_block",
                    target_id=text_block_id,
                    stage="translation",
                    status="done",
                )
            )

        issue_changes = issue_changes_from_drafts(quality_report.issue_drafts)
        has_blocker = quality_report.summary.has_blocking_issue
        return self._repositories.uow.accept_stage(
            self._command(
                task_id=task.task_id,
                task_status=task.status,
                current_stage=task.current_stage,
                page=page,
                stage_result=stage_result,
                decision_type="block" if has_blocker else "continue",
                reason_code="translation_missing_text_block"
                if has_blocker
                else "fake_translation_accepted",
                next_stage="block" if has_blocker else "translation_check",
                task_terminal_status="blocked" if has_blocker else "running",
                page_status="blocked" if has_blocker else None,
                expected_translation={
                    row.text_block_id: blocks_by_id[
                        row.text_block_id
                    ].active_translation_result_id
                    for row in ocr_inputs
                },
                accepted_results=tuple(accepted_results),
                active_pointers=tuple(active_pointers),
                issue_lifecycle=issue_changes,
                stage_statuses=tuple(stage_statuses),
                expected_stage_statuses=tuple(
                    ExpectedStageStatus(
                        target_type="text_block",
                        target_id=row.text_block_id,
                        stage="translation",
                        status=blocks_by_id[row.text_block_id].translation_status,
                    )
                    for row in ocr_inputs
                ),
            )
        )

    def _accept_stage_status_only(self, task, page, stage_result: StageResult):
        blocks = self._repositories.content_state.list_text_blocks_for_page(page.page_id)
        return self._repositories.uow.accept_stage(
            self._command(
                task_id=task.task_id,
                task_status=task.status,
                current_stage=task.current_stage,
                page=page,
                stage_result=stage_result,
                decision_type="continue",
                reason_code="translation_check_passed",
                next_stage="cleaning",
                expected_translation={
                    block.text_block_id: block.active_translation_result_id
                    for block in blocks
                },
                stage_statuses=tuple(
                    StageStatusUpdate(
                        target_type="text_block",
                        target_id=block.text_block_id,
                        stage="translation_check",
                        status="done",
                    )
                    for block in blocks
                ),
                expected_stage_statuses=tuple(
                    ExpectedStageStatus(
                        target_type="text_block",
                        target_id=block.text_block_id,
                        stage="translation_check",
                        status=block.translation_check_status,
                    )
                    for block in blocks
                ),
            )
        )

    def _accept_cleaning(
        self,
        task,
        page,
        stage_result: StageResult,
        quality_report: QualityCheckReport,
    ):
        if quality_report.issue_drafts and not quality_report.summary.has_blocking_issue:
            blocks = self._repositories.content_state.list_text_blocks_for_page(
                page.page_id
            )
            return self._repositories.uow.accept_stage(
                self._command(
                    task_id=task.task_id,
                    task_status=task.status,
                    current_stage=task.current_stage,
                    page=page,
                    stage_result=stage_result,
                    decision_type="mark_warning",
                    reason_code="cleaning_complex_background",
                    next_stage="typesetting",
                    issue_lifecycle=issue_changes_from_drafts(
                        quality_report.issue_drafts
                    ),
                    stage_statuses=tuple(
                        StageStatusUpdate(
                            target_type="text_block",
                            target_id=block.text_block_id,
                            stage="cleaning",
                            status="skipped",
                        )
                        for block in blocks
                    ),
                    expected_stage_statuses=tuple(
                        ExpectedStageStatus(
                            target_type="text_block",
                            target_id=block.text_block_id,
                            stage="cleaning",
                            status=block.cleaning_status,
                        )
                        for block in blocks
                    ),
                )
            )
        if quality_report.summary.has_blocking_issue or stage_result.status != "succeeded":
            return self._accept_quality_block(
                task,
                page,
                stage_result,
                quality_report,
                reason_code=stage_error_code(stage_result),
            )
        return self._accept_page_artifact(task, page, stage_result)

    def _accept_typesetting(
        self,
        task,
        page,
        stage_result: StageResult,
        quality_report: QualityCheckReport,
    ):
        if quality_report.issue_drafts and not quality_report.summary.has_blocking_issue:
            if not stage_result.registered_artifacts:
                return self._accept_quality_block(
                    task,
                    page,
                    stage_result,
                    quality_report,
                    reason_code="typeset_overflow_without_preview",
                )
            artifact = stage_result.registered_artifacts[0]
            blocks = self._repositories.content_state.list_text_blocks_for_page(
                page.page_id
            )
            return self._repositories.uow.accept_stage(
                self._command(
                    task_id=task.task_id,
                    task_status=task.status,
                    current_stage=task.current_stage,
                    page=page,
                    stage_result=stage_result,
                    decision_type="mark_warning",
                    reason_code="typeset_overflow",
                    next_stage="export_check",
                    expected_page_artifacts={
                        "active_cleaned_artifact_id": page.active_cleaned_artifact_id,
                        "active_typeset_artifact_id": page.active_typeset_artifact_id,
                    },
                    active_pointers=(
                        ActivePointerUpdate(
                            owner_type="page",
                            owner_id=page.page_id,
                            pointer_name="active_typeset_artifact_id",
                            value_id=artifact.artifact_id,
                        ),
                    ),
                    issue_lifecycle=issue_changes_from_drafts(
                        quality_report.issue_drafts
                    ),
                    stage_statuses=tuple(
                        StageStatusUpdate(
                            target_type="text_block",
                            target_id=block.text_block_id,
                            stage="typesetting",
                            status="skipped",
                        )
                        for block in blocks
                    ),
                    expected_stage_statuses=tuple(
                        ExpectedStageStatus(
                            target_type="text_block",
                            target_id=block.text_block_id,
                            stage="typesetting",
                            status=block.typesetting_status,
                        )
                        for block in blocks
                    ),
                )
            )
        if quality_report.summary.has_blocking_issue or stage_result.status != "succeeded":
            return self._accept_quality_block(
                task,
                page,
                stage_result,
                quality_report,
                reason_code=stage_error_code(stage_result),
            )
        return self._accept_page_artifact(task, page, stage_result)

    def _accept_page_artifact(self, task, page, stage_result: StageResult):
        if not stage_result.registered_artifacts:
            raise RuntimeError(f"{stage_result.stage} did not return an artifact")
        artifact = stage_result.registered_artifacts[0]
        blocks = self._repositories.content_state.list_text_blocks_for_page(page.page_id)
        if stage_result.stage == "cleaning":
            pointer_name = "active_cleaned_artifact_id"
            next_stage = "typesetting"
            reason_code = "fake_cleaning_accepted"
            status_stage = "cleaning"
        else:
            pointer_name = "active_typeset_artifact_id"
            next_stage = "export_check"
            reason_code = "fake_typesetting_accepted"
            status_stage = "typesetting"

        return self._repositories.uow.accept_stage(
            self._command(
                task_id=task.task_id,
                task_status=task.status,
                current_stage=task.current_stage,
                page=page,
                stage_result=stage_result,
                decision_type="continue",
                reason_code=reason_code,
                next_stage=next_stage,
                expected_page_artifacts={
                    "active_cleaned_artifact_id": page.active_cleaned_artifact_id,
                    "active_typeset_artifact_id": page.active_typeset_artifact_id,
                },
                active_pointers=(
                    ActivePointerUpdate(
                        owner_type="page",
                        owner_id=page.page_id,
                        pointer_name=pointer_name,
                        value_id=artifact.artifact_id,
                    ),
                ),
                stage_statuses=tuple(
                    StageStatusUpdate(
                        target_type="text_block",
                        target_id=block.text_block_id,
                        stage=status_stage,
                        status="done",
                    )
                    for block in blocks
                ),
                expected_stage_statuses=tuple(
                    ExpectedStageStatus(
                        target_type="text_block",
                        target_id=block.text_block_id,
                        stage=status_stage,
                        status=getattr(block, f"{status_stage}_status"),
                    )
                    for block in blocks
                ),
            )
        )

    def _accept_blocked(
        self,
        *,
        task_id: str,
        page_id: str,
        task_status: str,
        current_stage: str,
        attempt_id: str | None,
        reason_code: str,
        issue_type: str,
    ) -> ProcessPageResult:
        page = self._repositories.content_state.get_page(page_id)
        outcome = self._repositories.uow.accept_stage(
            self._blocked_command(
                task_id=task_id,
                task_status=task_status,
                current_stage=current_stage,
                page_id=page_id,
                page=page,
                attempt_id=attempt_id,
                reason_code=reason_code,
                issue_type=issue_type,
            )
        )
        latest_page = self._repositories.content_state.get_page(page_id)
        return ProcessPageResult(
            task_id=task_id,
            task_status=outcome.task_status or "blocked",
            page_id=page_id,
            page_status=latest_page.status,
            final_decision="block",
        )

    def _accept_quality_block(
        self,
        task,
        page,
        stage_result: StageResult,
        quality_report: QualityCheckReport,
        *,
        reason_code: str,
        attempt_terminal_status: str = "failed",
    ):
        issue_changes = issue_changes_from_drafts(quality_report.issue_drafts)
        if not issue_changes:
            return self._repositories.uow.accept_stage(
                self._blocked_command(
                    task_id=task.task_id,
                    task_status=task.status,
                    current_stage=task.current_stage,
                    page_id=page.page_id,
                    page=page,
                    attempt_id=stage_result.attempt_id,
                    reason_code=reason_code,
                    issue_type=reason_code,
                )
            )
        return self._repositories.uow.accept_stage(
            self._command(
                task_id=task.task_id,
                task_status=task.status,
                current_stage=task.current_stage,
                page=page,
                stage_result=stage_result,
                decision_type="block",
                reason_code=reason_code,
                next_stage="block",
                task_terminal_status="blocked",
                page_status="blocked",
                issue_lifecycle=issue_changes,
                attempt_terminal_status=attempt_terminal_status,
            )
        )

    def _blocked_command(
        self,
        *,
        task_id: str,
        task_status: str,
        current_stage: str,
        page_id: str,
        page,
        attempt_id: str | None,
        reason_code: str,
        issue_type: str,
    ) -> AcceptanceCommand:
        issue_id = f"issue-{current_stage}-{uuid4()}"
        return self._command(
            task_id=task_id,
            task_status=task_status,
            current_stage=current_stage,
            page=page,
            stage_result=synthetic_stage_result(
                task_id=task_id,
                stage=current_stage,
                page_id=page_id,
                attempt_id=attempt_id,
            ),
            decision_type="block",
            reason_code=reason_code,
            next_stage="block",
            task_terminal_status="blocked",
            page_status="blocked",
            issue_lifecycle=(
                IssueLifecycleChange(
                    issue_id=issue_id,
                    action="create",
                    status="open",
                    issue_type=issue_type,
                    is_blocking=True,
                ),
            ),
        )

    def _command(
        self,
        *,
        task_id: str,
        task_status: str,
        current_stage: str,
        page,
        stage_result: StageResult,
        decision_type: str,
        reason_code: str,
        next_stage: str,
        task_terminal_status: str = "running",
        page_status: str | None = None,
        expected_ocr: dict[str, str | None] | None = None,
        expected_translation: dict[str, str | None] | None = None,
        expected_page_artifacts: dict[str, str | None] | None = None,
        accepted_text_blocks: tuple[AcceptedTextBlock, ...] = (),
        accepted_results: tuple[AcceptedResult, ...] = (),
        active_pointers: tuple[ActivePointerUpdate, ...] = (),
        issue_lifecycle: tuple[IssueLifecycleChange, ...] = (),
        stage_statuses: tuple[StageStatusUpdate, ...] = (),
        expected_stage_statuses: tuple[ExpectedStageStatus, ...] = (),
        linked_issue_ids: tuple[str, ...] = (),
        attempt_terminal_status: str | None = None,
    ) -> AcceptanceCommand:
        stage_index = _STAGE_ORDER.index(current_stage) + 1
        page_statuses = (
            (PageStatusUpdate(page_id=page.page_id, status=page_status),)
            if page_status is not None
            else ()
        )
        decision_issue_ids = linked_issue_ids or tuple(
            issue_change.issue_id for issue_change in issue_lifecycle
        )
        return AcceptanceCommand(
            task_id=task_id,
            expected=ExpectedState(
                task_status="running"
                if stage_result.attempt_id is not None
                else task_status,
                current_stage=current_stage,
                active_ocr_result_ids=expected_ocr or {},
                active_translation_result_ids=expected_translation or {},
                page_artifact_ids={
                    page.page_id: expected_page_artifacts
                }
                if expected_page_artifacts is not None
                else {},
                stage_statuses=expected_stage_statuses,
            ),
            accepted_results=accepted_results,
            active_pointers=active_pointers,
            issue_lifecycle=issue_lifecycle,
            workflow_decision=WorkflowDecisionDraft(
                decision_id=f"decision-{stage_index:02d}-{current_stage}-{uuid4()}",
                attempt_id=stage_result.attempt_id,
                stage=current_stage,
                decision_type=decision_type,
                reason_code=reason_code,
                linked_issue_ids=decision_issue_ids,
            ),
            retry_budget_after={},
            task_progress=TaskProgressUpdate(
                status=task_terminal_status,
                current_stage=next_stage,
                progress_state=reason_code,
            ),
            stage_statuses=stage_statuses,
            accepted_text_blocks=accepted_text_blocks,
            page_statuses=page_statuses,
            attempt_terminal_status=attempt_terminal_status
            or ("succeeded" if task_terminal_status != "blocked" else "failed"),
        )


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
