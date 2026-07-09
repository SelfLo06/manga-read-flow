from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Callable
from uuid import uuid4

from manga_read_flow.domain.provider_contracts import ProviderOutcome, ProviderResult
from manga_read_flow.persistence.repository_uow_core import (
    AcceptanceCommand,
    AttemptReservation,
    ExpectedStageStatus,
    StageStatusUpdate,
)
from manga_read_flow.workflow.stage_executor import StageResult


@dataclass(frozen=True)
class ReusePlan:
    next_stage: str
    reason_code: str
    expected_ocr: dict[str, str | None] | None = None
    expected_translation: dict[str, str | None] | None = None
    expected_page_artifacts: dict[str, str | None] | None = None
    stage_statuses: tuple[StageStatusUpdate, ...] = ()
    expected_stage_statuses: tuple[ExpectedStageStatus, ...] = ()


class ReuseReservationConflictError(RuntimeError):
    """Raised when a cached-result reuse attempt cannot be reserved."""


class WorkflowReuseService:
    def __init__(self, *, repositories, artifact_service, provider, config_hash: str) -> None:
        self._repositories = repositories
        self._artifact_service = artifact_service
        self._provider = provider
        self._config_hash = config_hash

    def plan_reuse(self, task, page) -> ReusePlan | None:
        stage = task.current_stage
        blocks = self._repositories.content_state.list_text_blocks_for_page(page.page_id)

        if stage == "detection":
            if blocks and all(block.detection_status == "done" for block in blocks):
                return ReusePlan(
                    next_stage="ocr",
                    reason_code="detected_text_blocks_already_committed",
                    stage_statuses=tuple(
                        StageStatusUpdate(
                            target_type="text_block",
                            target_id=block.text_block_id,
                            stage="detection",
                            status="done",
                        )
                        for block in blocks
                    ),
                    expected_stage_statuses=tuple(
                        ExpectedStageStatus(
                            target_type="text_block",
                            target_id=block.text_block_id,
                            stage="detection",
                            status=block.detection_status,
                        )
                        for block in blocks
                    ),
                )

        if stage == "ocr":
            reusable = self._repositories.result_versions.reusable_active_ocr_for_page(
                page.page_id,
                provider_name=self._provider.provider_name,
                model_id=self._provider.model_id,
                input_hash=self.stage_input_hash("ocr", page),
                config_hash=self._config_hash,
            )
            if reusable and len(reusable) == len(blocks):
                return ReusePlan(
                    next_stage="translation",
                    reason_code="active_ocr_results_reused",
                    expected_ocr={
                        row.text_block_id: row.active_ocr_result_id for row in reusable
                    },
                    stage_statuses=tuple(
                        StageStatusUpdate(
                            target_type="text_block",
                            target_id=row.text_block_id,
                            stage="ocr",
                            status="done",
                        )
                        for row in reusable
                    ),
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

        if stage == "translation":
            locked = (
                self._repositories.result_versions.locked_active_translations_for_page(
                    page.page_id
                )
            )
            if locked and len(locked) == len(blocks):
                return ReusePlan(
                    next_stage="translation_check",
                    reason_code="locked_translation_preserved",
                    expected_translation={
                        row.text_block_id: row.active_translation_result_id
                        for row in locked
                    },
                    stage_statuses=tuple(
                        StageStatusUpdate(
                            target_type="text_block",
                            target_id=row.text_block_id,
                            stage="translation",
                            status="done",
                        )
                        for row in locked
                    ),
                    expected_stage_statuses=tuple(
                        ExpectedStageStatus(
                            target_type="text_block",
                            target_id=block.text_block_id,
                            stage="translation",
                            status=block.translation_status,
                        )
                        for block in blocks
                    ),
                )

            reusable = (
                self._repositories.result_versions.reusable_active_translations_for_page(
                    page.page_id,
                    provider_name=self._provider.provider_name,
                    model_id=self._provider.model_id,
                    input_hash=self.stage_input_hash("translation", page),
                    config_hash=self._config_hash,
                    glossary_version_id=self._repositories.glossary.ensure_empty_version(),
                )
            )
            if reusable and len(reusable) == len(blocks):
                return ReusePlan(
                    next_stage="translation_check",
                    reason_code="active_translation_results_reused",
                    expected_translation={
                        row.text_block_id: row.active_translation_result_id
                        for row in reusable
                    },
                    stage_statuses=tuple(
                        StageStatusUpdate(
                            target_type="text_block",
                            target_id=row.text_block_id,
                            stage="translation",
                            status="done",
                        )
                        for row in reusable
                    ),
                    expected_stage_statuses=tuple(
                        ExpectedStageStatus(
                            target_type="text_block",
                            target_id=block.text_block_id,
                            stage="translation",
                            status=block.translation_status,
                        )
                        for block in blocks
                    ),
                )

        if stage == "translation_check":
            translations = (
                self._repositories.result_versions.reusable_active_translations_for_page(
                    page.page_id,
                    provider_name=self._provider.provider_name,
                    model_id=self._provider.model_id,
                    input_hash=self.stage_input_hash("translation", page),
                    config_hash=self._config_hash,
                    glossary_version_id=self._repositories.glossary.ensure_empty_version(),
                )
            )
            if (
                translations
                and len(translations) == len(blocks)
                and all(block.translation_check_status == "done" for block in blocks)
            ):
                return ReusePlan(
                    next_stage="cleaning",
                    reason_code="translation_check_already_committed",
                    expected_translation={
                        row.text_block_id: row.active_translation_result_id
                        for row in translations
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

        if stage == "cleaning":
            if (
                page.active_cleaned_artifact_id is not None
                and blocks
                and all(block.cleaning_status == "done" for block in blocks)
                and self._artifact_is_valid(
                    page.active_cleaned_artifact_id,
                    page=page,
                    expected_use="reuse_check",
                    active_reference="page.active_cleaned_artifact_id",
                    expected_type="cleaned_image",
                )
            ):
                return ReusePlan(
                    next_stage="typesetting",
                    reason_code="active_cleaned_artifact_reused",
                    expected_page_artifacts={
                        "active_cleaned_artifact_id": page.active_cleaned_artifact_id,
                        "active_typeset_artifact_id": page.active_typeset_artifact_id,
                    },
                    stage_statuses=tuple(
                        StageStatusUpdate(
                            target_type="text_block",
                            target_id=block.text_block_id,
                            stage="cleaning",
                            status="done",
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

        if stage == "typesetting":
            if (
                page.active_typeset_artifact_id is not None
                and blocks
                and all(block.typesetting_status == "done" for block in blocks)
                and self._artifact_is_valid(
                    page.active_typeset_artifact_id,
                    page=page,
                    expected_use="reuse_check",
                    active_reference="page.active_typeset_artifact_id",
                    expected_type="typeset_image",
                )
            ):
                return ReusePlan(
                    next_stage="export_check",
                    reason_code="active_typeset_artifact_reused",
                    expected_page_artifacts={
                        "active_cleaned_artifact_id": page.active_cleaned_artifact_id,
                        "active_typeset_artifact_id": page.active_typeset_artifact_id,
                    },
                    stage_statuses=tuple(
                        StageStatusUpdate(
                            target_type="text_block",
                            target_id=block.text_block_id,
                            stage="typesetting",
                            status="done",
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

        return None

    def stage_input_hash(self, stage: str, page) -> str:
        blocks = self._repositories.content_state.list_text_blocks_for_page(page.page_id)
        if stage == "detection":
            return _hash_parts(stage, page.original_artifact_id)

        if stage in {"ocr", "cleaning"}:
            return _hash_parts(
                stage,
                page.original_artifact_id,
                *(
                    (block.text_block_id, block.reading_order, block.geometry_hash)
                    for block in blocks
                ),
            )

        if stage in {"translation", "translation_check"}:
            ocr_inputs = self._repositories.result_versions.active_ocr_inputs_for_page(
                page.page_id
            )
            return _hash_parts(
                stage,
                *(
                    (
                        row.text_block_id,
                        row.active_ocr_result_id,
                        row.source_text_hash,
                    )
                    for row in ocr_inputs
                ),
            )

        if stage == "typesetting":
            translations = (
                self._repositories.result_versions.active_translation_inputs_for_page(
                    page.page_id
                )
            )
            return _hash_parts(
                stage,
                page.active_cleaned_artifact_id,
                *(
                    (block.text_block_id, block.reading_order, block.geometry_hash)
                    for block in blocks
                ),
                *(
                    (
                        row.text_block_id,
                        row.active_translation_result_id,
                        row.translation_text_hash,
                    )
                    for row in translations
                ),
            )

        if stage == "export_check":
            return _hash_parts(stage, page.active_typeset_artifact_id)

        return _hash_parts(stage, page.page_id)

    def _artifact_is_valid(
        self,
        artifact_id: str,
        *,
        page,
        expected_use: str,
        active_reference: str,
        expected_type: str,
    ) -> bool:
        artifact = self._repositories.artifact_metadata.get_artifact(artifact_id)
        if artifact.artifact_type != expected_type or artifact.storage_state != "present":
            return False
        report = self._artifact_service.validate_artifact(
            artifact_id,
            expected_use=expected_use,
            active_reference=active_reference,
        )
        return (
            report.integrity_status == "valid"
            and artifact.dependency_hash == self.stage_input_hash(
                artifact.source_stage,
                page,
            )
        )


def accept_reuse_plan(
    *,
    repositories,
    task,
    page,
    plan: ReusePlan,
    build_command: Callable[..., AcceptanceCommand],
):
    attempt_id = f"attempt-{task.current_stage}-reuse-{uuid4()}"
    reservation = repositories.workflow_execution.reserve_attempt(
        AttemptReservation(
            task_id=task.task_id,
            attempt_id=attempt_id,
            stage=task.current_stage,
            target_type=task.target_type,
            target_id=task.target_id,
            expected_task_status=task.status,
            expected_current_stage=task.current_stage,
            runner_id="local-taskrunner",
        )
    )
    if not reservation.committed:
        raise ReuseReservationConflictError("Stage reuse reservation was rejected.")
    return repositories.uow.accept_stage(
        build_command(
            task_id=task.task_id,
            task_status=task.status,
            current_stage=task.current_stage,
            page=page,
            stage_result=_reused_stage_result(
                task_id=task.task_id,
                stage=task.current_stage,
                page_id=page.page_id,
                attempt_id=attempt_id,
            ),
            decision_type="reuse_cached_result",
            reason_code=plan.reason_code,
            next_stage=plan.next_stage,
            expected_ocr=plan.expected_ocr,
            expected_translation=plan.expected_translation,
            expected_page_artifacts=plan.expected_page_artifacts,
            stage_statuses=plan.stage_statuses,
            expected_stage_statuses=plan.expected_stage_statuses,
            attempt_terminal_status="reused_cached",
        )
    )


def _reused_stage_result(
    *,
    task_id: str,
    stage: str,
    page_id: str,
    attempt_id: str,
) -> StageResult:
    return StageResult(
        status="reused_cached",
        stage=stage,
        task_id=task_id,
        attempt_id=attempt_id,
        target_type="page",
        target_id=page_id,
        provider_called=False,
        provider_result=ProviderResult(
            outcome=ProviderOutcome.SUCCESS,
            provider_name="workflow-loop",
        ),
        candidate_outputs={},
    )


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _hash_parts(*parts: object) -> str:
    return _hash_text(repr(parts))
