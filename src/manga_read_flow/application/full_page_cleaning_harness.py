"""Configuration-driven orchestration for a real full-page Cleaning run.

This module deliberately keeps image work and provider calls outside SQLite
transactions.  It is a narrow Slice 3 harness adapter: callers supply a
frozen visual contract and evidence paths; this module persists the formal
Slice 1/2 facts and leaves the final accept/block decision to its caller.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from manga_read_flow.application.full_page_cleaning import (
    FullPageCleaningPreparationService,
    FullPagePreparationMember,
    PrepareFullPageCleaningCommand,
)
from manga_read_flow.domain.artifacts import ArtifactSafetyMetadata
from manga_read_flow.persistence.full_page_cleaning_ledger_repository import (
    CleaningInventoryItemDraft,
    InstanceCleaningResultDraft,
    PageCleaningRunDraft,
    SegmentCleaningDispositionDraft,
)
from manga_read_flow.persistence.visual_contract_repository import (
    BubbleInstanceRevisionDraft,
    CleaningEligibilityDraft,
    SegmentInstanceAssignmentDraft,
    TextSegmentRevisionDraft,
    VisualContractRevisionDraft,
)
from manga_read_flow.quality.cleaning_validation import validate_cleaning_output
from manga_read_flow.workflow.stage_executor import StageExecutionContext, StageExecutor


@dataclass(frozen=True)
class FullPageCleaningTarget:
    text_segment_id: str
    text_segment_revision_id: str
    source_text_block_id: str
    bubble_instance_id: str
    bubble_instance_revision_id: str
    region_hash: str
    inventory_ordinal: int
    target_class: str
    eligibility: str
    support_completeness: str
    reason_code: str
    dependency_fingerprint: str
    instance_mask_path: Path
    required_support_path: Path
    safe_edit_path: Path
    protected_mask_path: Path
    uncertainty_mask_path: Path
    visible_support_path: Path
    disposition_code: str | None = None
    disposition_blocking: bool = True
    evidence_summary_json: str = "{}"
    eligibility_evidence_json: str = "{}"

    @property
    def is_composition_eligible(self) -> bool:
        return self.eligibility == "E1" and self.support_completeness == "COMPLETE"


@dataclass(frozen=True)
class FullPageCleaningHarnessCommand:
    page_cleaning_run_id: str
    page_cleaning_run_idempotency_key: str
    page_id: str
    batch_id: str
    source_artifact_id: str
    source_hash: str
    source_image_path: Path
    visual_contract_revision_id: str
    input_hash: str
    config_hash: str
    validator_config_hash: str
    work_root: Path
    targets: tuple[FullPageCleaningTarget, ...]
    task_id: str | None = None


@dataclass(frozen=True)
class FullPageCleaningHarnessResult:
    page_cleaning_run_id: str
    task_id: str
    profile_snapshot_id: str
    inventory_item_ids: tuple[str, ...]
    instance_result_ids: tuple[str, ...]
    disposition_ids: tuple[str, ...]
    issue_ids: tuple[str, ...]
    combined_cleaning_candidate_id: str
    combined_artifact_id: str
    combined_hash: str
    combined_delta_artifact_id: str
    page_cleaning_validation_record_id: str
    validation_status: str
    target_result_ids: dict[str, str]
    target_inventory_ids: dict[str, str]


@dataclass(frozen=True)
class _ExecutionGroup:
    target: FullPageCleaningTarget
    covered_targets: tuple[FullPageCleaningTarget, ...]


class FullPageCleaningHarnessService:
    """Persist one frozen full-page run without selecting an active pointer."""

    def __init__(self, *, project_id: str, repositories, artifact_service, cleaner_provider) -> None:
        self._project_id = project_id
        self._repositories = repositories
        self._artifact_service = artifact_service
        self._cleaner_provider = cleaner_provider

    def prepare(self, command: FullPageCleaningHarnessCommand, *, before_execution=None) -> FullPageCleaningHarnessResult:
        _validate_command(command)
        page = self._repositories.content_state.get_page(command.page_id)
        if page.original_artifact_id != command.source_artifact_id:
            raise ValueError("Full-page Cleaning source artifact does not match Page original.")
        if _file_hash(command.source_image_path) != command.source_hash:
            raise ValueError("Full-page Cleaning source hash is not frozen input hash.")

        command.work_root.mkdir(parents=True, exist_ok=True)
        execution_groups = _execution_groups(command)
        self._register_visual_contract(command, execution_groups)
        profile = self._ensure_profile(command.config_hash, command.validator_config_hash)
        task_id = command.task_id or f"task-full-page-cleaning-{uuid4()}"
        self._repositories.workflow_execution.create_task(
            task_id=task_id,
            target_type="page",
            target_id=command.page_id,
            task_type="mvp1_full_page_cleaning",
            status="queued",
            current_stage="cleaning",
            profile_snapshot_id=profile.profile_snapshot_id,
        )

        self._repositories.uow.create_or_replay_page_cleaning_run(
            PageCleaningRunDraft(
                command.page_cleaning_run_id,
                command.batch_id,
                command.page_id,
                command.visual_contract_revision_id,
                command.source_artifact_id,
                command.source_hash,
                profile.profile_snapshot_id,
                command.config_hash,
                command.page_cleaning_run_idempotency_key,
            )
        )
        inventory = self._repositories.uow.freeze_cleaning_inventory(
            page_cleaning_run_id=command.page_cleaning_run_id,
            inventory_fingerprint=_fingerprint(
                {
                    "revision": command.visual_contract_revision_id,
                    "targets": [target.text_segment_revision_id for target in command.targets],
                }
            ),
            items=tuple(
                CleaningInventoryItemDraft(
                    cleaning_inventory_item_id=_inventory_id(command.page_cleaning_run_id, target),
                    text_segment_id=target.text_segment_id,
                    text_segment_revision_id=target.text_segment_revision_id,
                    bubble_instance_id=target.bubble_instance_id,
                    bubble_instance_revision_id=target.bubble_instance_revision_id,
                    assignment_id=_assignment_id(command.visual_contract_revision_id, target),
                    target_class=target.target_class,
                    eligibility=target.eligibility,
                    support_policy=target.support_completeness,
                    dependency_fingerprint=target.dependency_fingerprint,
                    evidence_artifact_id=None,
                    inventory_ordinal=target.inventory_ordinal,
                )
                for target in command.targets
            ),
        )
        self._repositories.uow.transition_page_cleaning_run(
            page_cleaning_run_id=command.page_cleaning_run_id,
            target_status="executing",
        )
        if before_execution is not None:
            before_execution(command.page_cleaning_run_id)
        inventory_by_segment = {
            item.text_segment_revision_id: item.cleaning_inventory_item_id for item in inventory
        }

        members: list[FullPagePreparationMember] = []
        result_ids: dict[str, str] = {}
        disposition_ids: list[str] = []
        issue_ids: list[str] = []
        has_executed_target = False
        for group in execution_groups:
            if not group.target.is_composition_eligible:
                for target in group.covered_targets:
                    disposition_id, issue_id = self._record_blocking_target(
                        command=command,
                        target=target,
                        inventory_id=inventory_by_segment[target.text_segment_revision_id],
                    )
                    disposition_ids.append(disposition_id)
                    issue_ids.append(issue_id)
                continue
            member = self._execute_target(
                command=command,
                target=group.target,
                inventory_item_ids=tuple(
                    inventory_by_segment[target.text_segment_revision_id]
                    for target in group.covered_targets
                ),
                task_id=task_id,
                profile_snapshot_id=profile.profile_snapshot_id,
                expected_task_status="running" if has_executed_target else "queued",
            )
            members.append(member)
            for target in group.covered_targets:
                result_ids[target.text_segment_revision_id] = member.instance_cleaning_result_id
            has_executed_target = True

        existing_dispositions = tuple(
            (item.cleaning_inventory_item_id, item.disposition_code, item.is_blocking)
            for item in self._repositories.uow.list_current_segment_cleaning_dispositions(
                page_cleaning_run_id=command.page_cleaning_run_id
            )
        )
        candidate_id = f"candidate-full-page-{uuid4()}"
        validation_id = f"validation-full-page-{uuid4()}"
        prepared = FullPageCleaningPreparationService(
            artifact_service=self._artifact_service,
            acceptance_repository=self._repositories.full_page_cleaning_acceptance,
        ).prepare(
            PrepareFullPageCleaningCommand(
                candidate_id,
                validation_id,
                command.page_cleaning_run_id,
                command.batch_id,
                command.page_id,
                command.source_artifact_id,
                command.source_hash,
                command.source_image_path.read_bytes(),
                tuple(item.cleaning_inventory_item_id for item in inventory),
                command.config_hash,
                _fingerprint(
                    {
                        "validator_config_hash": command.validator_config_hash,
                        "run": command.page_cleaning_run_id,
                        "candidate": candidate_id,
                    }
                ),
                tuple(members),
                existing_dispositions,
            )
        )
        combined_artifact = self._repositories.artifact_metadata.get_artifact(
            prepared.combined_artifact_id
        )
        return FullPageCleaningHarnessResult(
            command.page_cleaning_run_id,
            task_id,
            profile.profile_snapshot_id,
            tuple(item.cleaning_inventory_item_id for item in inventory),
            tuple(result_ids.values()),
            tuple(disposition_ids),
            tuple(issue_ids),
            candidate_id,
            prepared.combined_artifact_id,
            combined_artifact.file_hash,
            prepared.combined_delta_artifact_id,
            validation_id,
            prepared.validation_status,
            result_ids,
            inventory_by_segment,
        )

    def _register_visual_contract(
        self,
        command: FullPageCleaningHarnessCommand,
        execution_groups: tuple[_ExecutionGroup, ...],
    ) -> None:
        manifest = command.work_root / "visual-contract-evidence.json"
        manifest.write_text(
            json.dumps(
                {
                    "kind": "mvp1_full_page_cleaning_slice3_visual_contract",
                    "page_id": command.page_id,
                    "visual_contract_revision_id": command.visual_contract_revision_id,
                    "input_hash": command.input_hash,
                    "targets": [
                        {
                            "segment_revision": target.text_segment_revision_id,
                            "instance_revision": target.bubble_instance_revision_id,
                            "eligibility": target.eligibility,
                            "support_completeness": target.support_completeness,
                            "reason_code": target.reason_code,
                            "dependency_fingerprint": target.dependency_fingerprint,
                            "eligibility_decision": json.loads(target.eligibility_evidence_json),
                        }
                        for target in command.targets
                    ],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        evidence = self._artifact_service.register_stage_json(
            temp_path=manifest,
            batch_id=command.batch_id,
            page_id=command.page_id,
            owner_type="visual_contract_revision",
            owner_id=command.visual_contract_revision_id,
            artifact_type="validation_evidence",
            source_stage="cleaning_input",
            dependency_hash=command.input_hash,
        )
        artifacts: dict[str, dict[str, object]] = {}
        for group in execution_groups:
            target = group.target
            per_target: dict[str, object] = {}
            for key, path in {
                "instance": target.instance_mask_path,
                "required": target.required_support_path,
                "safe": target.safe_edit_path,
                "protected": target.protected_mask_path,
                "uncertainty": target.uncertainty_mask_path,
                "visible": target.visible_support_path,
            }.items():
                per_target[key] = self._artifact_service.register_stage_output(
                    temp_path=path,
                    batch_id=command.batch_id,
                    page_id=command.page_id,
                    owner_type="bubble_instance_revision",
                    owner_id=target.bubble_instance_revision_id,
                    artifact_type="mask_image",
                    source_stage="cleaning_input",
                    retention_class="successful_payload",
                    safety=ArtifactSafetyMetadata(may_contain_original_image=False),
                    dependency_hash=target.dependency_fingerprint,
                )
            artifacts[target.text_segment_revision_id] = per_target
        self._repositories.visual_contract.prepare_contract(
            revision=VisualContractRevisionDraft(
                command.visual_contract_revision_id,
                command.page_id,
                command.source_artifact_id,
                command.input_hash,
            ),
            instances=tuple(
                BubbleInstanceRevisionDraft(
                    target.bubble_instance_revision_id,
                    target.bubble_instance_id,
                    command.page_id,
                    command.visual_contract_revision_id,
                    target.region_hash,
                    artifacts[target.text_segment_revision_id]["instance"].artifact_id,
                    artifacts[target.text_segment_revision_id]["required"].artifact_id,
                    artifacts[target.text_segment_revision_id]["safe"].artifact_id,
                    artifacts[target.text_segment_revision_id]["protected"].artifact_id,
                    artifacts[target.text_segment_revision_id]["uncertainty"].artifact_id,
                )
                for group in execution_groups
                for target in (group.target,)
            ),
            segments=tuple(
                TextSegmentRevisionDraft(
                    target.text_segment_revision_id,
                    target.text_segment_id,
                    command.page_id,
                    command.visual_contract_revision_id,
                    target.source_text_block_id,
                    target.inventory_ordinal,
                )
                for target in command.targets
            ),
            assignments=tuple(
                SegmentInstanceAssignmentDraft(
                    _assignment_id(command.visual_contract_revision_id, target),
                    command.visual_contract_revision_id,
                    target.text_segment_revision_id,
                    target.bubble_instance_revision_id,
                    "assigned",
                    "unique_instance_assignment",
                    evidence.artifact_id,
                )
                for target in command.targets
            ),
            eligibility=tuple(
                CleaningEligibilityDraft(
                    f"eligibility::{command.visual_contract_revision_id}::{target.bubble_instance_revision_id}",
                    target.bubble_instance_revision_id,
                    target.eligibility,
                    target.support_completeness,
                    target.reason_code,
                    evidence.artifact_id,
                )
                for group in execution_groups
                for target in (group.target,)
            ),
        )

    def _execute_target(self, *, command, target, inventory_item_ids, task_id, profile_snapshot_id, expected_task_status):
        attempt_id = f"attempt-full-page-cleaning-{uuid4()}"
        attempt_root = command.work_root / "attempts" / attempt_id
        stage = StageExecutor(
            attempt_recorder=self._repositories.workflow_execution,
            evidence_writer=self._repositories.stage_evidence_writer,
            artifact_service=self._artifact_service,
        ).execute(
            StageExecutionContext(
                project_id=self._project_id,
                task_id=task_id,
                attempt_id=attempt_id,
                tool_run_id=f"tool-run-full-page-cleaning-{uuid4()}",
                request_id=f"request-full-page-cleaning-{uuid4()}",
                stage="cleaning",
                target_type="page",
                target_id=command.page_id,
                batch_id=command.batch_id,
                page_id=command.page_id,
                text_block_ids=(target.source_text_block_id,),
                expected_task_status=expected_task_status,
                expected_current_stage="cleaning",
                runner_id="mvp1-full-page-cleaning-slice3",
                attempt_temp_root=attempt_root,
                input_hash=target.dependency_fingerprint,
                config_hash=command.config_hash,
                context_hash=command.visual_contract_revision_id,
                source_language="ja",
                target_language="zh-Hans",
                inputs={
                    "source_image_path": str(command.source_image_path),
                    "candidate_mask_path": str(target.required_support_path),
                    "safe_edit_mask_path": str(target.safe_edit_path),
                    "instance_mask_path": str(target.instance_mask_path),
                    "protected_mask_path": str(target.protected_mask_path),
                    "uncertainty_mask_path": str(target.uncertainty_mask_path),
                },
            ),
            self._cleaner_provider,
        )
        if stage.status != "succeeded" or stage.artifact_errors:
            raise RuntimeError(f"Cleaner did not produce a promotable result for {target.text_segment_revision_id}.")
        candidate = _artifact(stage.registered_artifacts, "cleaned_image")
        cleaned_path = _temp_path(stage, "cleaned_image")
        validation = validate_cleaning_output(
            source_image_path=command.source_image_path,
            cleaned_image_path=cleaned_path,
            required_support_path=target.required_support_path,
            safe_edit_path=target.safe_edit_path,
            instance_mask_path=target.instance_mask_path,
            protected_mask_path=target.protected_mask_path,
            uncertainty_mask_path=target.uncertainty_mask_path,
            output_dir=attempt_root / "validator",
        )
        if any(validation.issue_flags.values()):
            raise RuntimeError(f"Independent validator rejected {target.text_segment_revision_id}: {validation.issue_flags}")
        result_id = f"instance-cleaning-result-{uuid4()}"
        validation_evidence = self._artifact_service.register_stage_json(
            temp_path=validation.evidence_path,
            batch_id=command.batch_id,
            page_id=command.page_id,
            owner_type="instance_cleaning_result",
            owner_id=result_id,
            artifact_type="validation_evidence",
            source_stage="cleaning_validation",
            dependency_hash=target.dependency_fingerprint,
        )
        actual_changed = self._artifact_service.register_stage_output(
            temp_path=validation.actual_changed_mask_path,
            batch_id=command.batch_id,
            page_id=command.page_id,
            owner_type="instance_cleaning_result",
            owner_id=result_id,
            artifact_type="mask_image",
            source_stage="cleaning_validation",
            retention_class="successful_payload",
            safety=ArtifactSafetyMetadata(may_contain_original_image=False),
            dependency_hash=target.dependency_fingerprint,
        )
        residue = self._artifact_service.register_stage_output(
            temp_path=validation.residue_mask_path,
            batch_id=command.batch_id,
            page_id=command.page_id,
            owner_type="instance_cleaning_result",
            owner_id=result_id,
            artifact_type="mask_image",
            source_stage="cleaning_validation",
            retention_class="successful_payload",
            safety=ArtifactSafetyMetadata(may_contain_original_image=False),
            dependency_hash=target.dependency_fingerprint,
        )
        boundary = self._artifact_service.register_stage_output(
            temp_path=validation.structure_damage_mask_path,
            batch_id=command.batch_id,
            page_id=command.page_id,
            owner_type="instance_cleaning_result",
            owner_id=result_id,
            artifact_type="mask_image",
            source_stage="cleaning_validation",
            retention_class="successful_payload",
            safety=ArtifactSafetyMetadata(may_contain_original_image=False),
            dependency_hash=target.dependency_fingerprint,
        )
        background = self._artifact_service.register_stage_output(
            temp_path=validation.background_difference_mask_path,
            batch_id=command.batch_id,
            page_id=command.page_id,
            owner_type="instance_cleaning_result",
            owner_id=result_id,
            artifact_type="mask_image",
            source_stage="cleaning_validation",
            retention_class="successful_payload",
            safety=ArtifactSafetyMetadata(may_contain_original_image=False),
            dependency_hash=target.dependency_fingerprint,
        )
        result = self._repositories.uow.append_instance_cleaning_result(
            InstanceCleaningResultDraft(
                result_id,
                command.page_cleaning_run_id,
                target.bubble_instance_id,
                target.bubble_instance_revision_id,
                command.source_artifact_id,
                command.source_hash,
                target.dependency_fingerprint,
                command.config_hash,
                "validated",
                candidate.artifact_id,
                actual_changed.artifact_id,
                validation_evidence.artifact_id,
                int(validation.metrics["actual_changed_pixels"]),
                0,
                int(validation.metrics["residue_candidate_pixels"]),
                json.dumps(validation.metrics, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                workflow_attempt_id=attempt_id,
                provider_name=self._cleaner_provider.identity.provider_name,
                profile_snapshot_id=profile_snapshot_id,
                provider_candidate_artifact_id=candidate.artifact_id,
                required_support_artifact_id=self._register_input_mask(command, target, "required-result", target.required_support_path).artifact_id,
                safe_edit_artifact_id=self._register_input_mask(command, target, "safe-result", target.safe_edit_path).artifact_id,
                protected_artifact_id=self._register_input_mask(command, target, "protected-result", target.protected_mask_path).artifact_id,
                uncertainty_artifact_id=self._register_input_mask(command, target, "uncertainty-result", target.uncertainty_mask_path).artifact_id,
                visible_support_artifact_id=self._register_input_mask(command, target, "visible-result", target.visible_support_path).artifact_id,
                residue_artifact_id=residue.artifact_id,
                boundary_damage_artifact_id=boundary.artifact_id,
                background_difference_artifact_id=background.artifact_id,
            ),
            inventory_item_ids=inventory_item_ids,
        )
        return FullPagePreparationMember(
            result.instance_cleaning_result_id,
            target.bubble_instance_revision_id,
            target.text_segment_revision_id,
            candidate_png=cleaned_path.read_bytes(),
            actual_changed_mask_png=validation.actual_changed_mask_path.read_bytes(),
            actual_changed_artifact_id=actual_changed.artifact_id,
            actual_changed_hash=actual_changed.file_hash,
            inventory_item_ids=inventory_item_ids,
            instance_ownership_mask_png=target.instance_mask_path.read_bytes(),
            safe_edit_mask_png=target.safe_edit_path.read_bytes(),
            protected_mask_png=target.protected_mask_path.read_bytes(),
            uncertainty_mask_png=target.uncertainty_mask_path.read_bytes(),
            boundary_damage_pixel_count=int(validation.metrics["changed_on_instance_boundary_pixels"]),
            residue_pixel_count=int(validation.metrics["residue_candidate_pixels"]),
            dependencies_fresh=True,
        )

    def _record_blocking_target(self, *, command, target, inventory_id):
        if target.disposition_code is None:
            raise ValueError(f"Non-composition target requires a formal disposition: {target.text_segment_revision_id}")
        evidence_path = command.work_root / "dispositions" / f"{target.text_segment_revision_id}.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(
                {
                    "segment_revision": target.text_segment_revision_id,
                    "eligibility": target.eligibility,
                    "support_completeness": target.support_completeness,
                    "reason_code": target.reason_code,
                    "dependency_fingerprint": target.dependency_fingerprint,
                    "evidence_summary": json.loads(target.evidence_summary_json),
                    "eligibility_decision": json.loads(target.eligibility_evidence_json),
                },
                ensure_ascii=False,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        evidence = self._artifact_service.register_stage_json(
            temp_path=evidence_path, batch_id=command.batch_id, page_id=command.page_id,
            owner_type="page_cleaning_run", owner_id=command.page_cleaning_run_id,
            artifact_type="validation_evidence", source_stage="cleaning_input",
            dependency_hash=target.dependency_fingerprint,
        )
        disposition_id = f"disposition-{uuid4()}"
        self._repositories.uow.record_or_supersede_segment_disposition(
            SegmentCleaningDispositionDraft(
                disposition_id, inventory_id, target.disposition_code, target.reason_code,
                "cleaning_input", target.disposition_blocking,
                json.dumps({"eligibility": target.eligibility, "support_completeness": target.support_completeness}, sort_keys=True),
                target.dependency_fingerprint, evidence.artifact_id,
            )
        )
        issue_id = f"issue-full-page-cleaning-{uuid4()}"
        from manga_read_flow.persistence.acceptance_repository import IssueLifecycleChange
        from manga_read_flow.persistence.full_page_cleaning_acceptance_repository import CleaningIssueRelationDraft
        self._repositories.uow.persist_cleaning_issue_lifecycle(
            issue_changes=(IssueLifecycleChange(issue_id, "create", "open", "full_page_cleaning_blocker", target.disposition_blocking, target_type="text_segment_revision", target_id=target.text_segment_revision_id, page_id=command.page_id, discovered_stage="cleaning", root_stage="cleaning_input", error_code=target.reason_code, severity="blocking" if target.disposition_blocking else "warning", message_key=target.disposition_code, message_params_json="{}", input_hash=target.dependency_fingerprint, config_hash=command.config_hash, dedupe_key=f"{command.page_cleaning_run_id}:{target.text_segment_revision_id}:{target.disposition_code}"),),
            relations=(
                CleaningIssueRelationDraft(
                    f"relation-{uuid4()}", issue_id, "blocks_run",
                    page_cleaning_run_id=command.page_cleaning_run_id,
                ),
                CleaningIssueRelationDraft(
                    f"relation-{uuid4()}", issue_id, "blocks_inventory",
                    cleaning_inventory_item_id=inventory_id,
                ),
            ),
        )
        return disposition_id, issue_id

    def _register_input_mask(self, command, target, role, path):
        return self._artifact_service.register_stage_output(
            temp_path=path, batch_id=command.batch_id, page_id=command.page_id,
            owner_type="instance_cleaning_result", owner_id=f"input::{target.text_segment_revision_id}",
            artifact_type="mask_image", source_stage="cleaning_input", retention_class="successful_payload",
            safety=ArtifactSafetyMetadata(may_contain_original_image=False), dependency_hash=target.dependency_fingerprint,
        )

    def _ensure_profile(self, config_hash: str, validator_config_hash: str):
        settings_json = json.dumps({"snapshot_schema_version": "mvp1-full-page-cleaning-slice3.v1", "cleaner": self._cleaner_provider.identity.provider_name, "config_hash": config_hash, "validator_config_hash": validator_config_hash, "retry_budgets": {"cleaning": 0}}, sort_keys=True, separators=(",", ":"))
        return self._repositories.workflow_execution.ensure_profile_snapshot(
            profile_snapshot_id="profile-snapshot-mvp1-full-page-" + sha256(settings_json.encode()).hexdigest()[:16],
            settings_json=settings_json,
            settings_hash=sha256(settings_json.encode()).hexdigest(),
        )


def _validate_command(command: FullPageCleaningHarnessCommand) -> None:
    if not command.targets:
        raise ValueError("Full-page Cleaning requires a frozen non-empty inventory.")
    if len({target.text_segment_revision_id for target in command.targets}) != len(command.targets):
        raise ValueError("Full-page Cleaning inventory segment revisions must be unique.")
    if len({target.inventory_ordinal for target in command.targets}) != len(command.targets):
        raise ValueError("Full-page Cleaning inventory ordinals must be unique.")
    for target in command.targets:
        if not all(path.is_file() for path in (target.instance_mask_path, target.required_support_path, target.safe_edit_path, target.protected_mask_path, target.uncertainty_mask_path, target.visible_support_path)):
            raise ValueError(f"Full-page Cleaning target lacks complete evidence files: {target.text_segment_revision_id}")


def _execution_groups(command: FullPageCleaningHarnessCommand) -> tuple[_ExecutionGroup, ...]:
    by_revision: dict[str, list[FullPageCleaningTarget]] = {}
    for target in command.targets:
        by_revision.setdefault(target.bubble_instance_revision_id, []).append(target)
    groups: list[_ExecutionGroup] = []
    for revision_id, targets in by_revision.items():
        first = targets[0]
        if any(
            target.bubble_instance_id != first.bubble_instance_id
            or target.instance_mask_path.read_bytes() != first.instance_mask_path.read_bytes()
            for target in targets[1:]
        ):
            raise ValueError(f"BubbleInstance revision has inconsistent target evidence: {revision_id}")
        if len(targets) == 1:
            groups.append(_ExecutionGroup(first, (first,)))
            continue
        paths = _union_group_masks(command.work_root, revision_id, tuple(targets))
        eligibility = first.eligibility if all(target.eligibility == first.eligibility for target in targets) else "REVIEW"
        completeness = first.support_completeness if all(target.support_completeness == first.support_completeness for target in targets) else "INCOMPLETE_REVIEW"
        disposition_code = first.disposition_code if all(target.disposition_code == first.disposition_code for target in targets) else "INCOMPLETE_REVIEW"
        groups.append(
            _ExecutionGroup(
                replace(
                    first,
                    dependency_fingerprint=_fingerprint({"instance_revision": revision_id, "target_dependencies": [target.dependency_fingerprint for target in targets]}),
                    instance_mask_path=paths["instance"],
                    required_support_path=paths["required"],
                    safe_edit_path=paths["safe"],
                    protected_mask_path=paths["protected"],
                    uncertainty_mask_path=paths["uncertainty"],
                    visible_support_path=paths["visible"],
                    eligibility=eligibility,
                    support_completeness=completeness,
                    disposition_code=disposition_code,
                ),
                tuple(targets),
            )
        )
    return tuple(groups)


def _union_group_masks(work_root: Path, revision_id: str, targets: tuple[FullPageCleaningTarget, ...]) -> dict[str, Path]:
    output_root = work_root / "instance-evidence" / sha256(revision_id.encode()).hexdigest()[:20]
    output_root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for role, attribute in {
        "instance": "instance_mask_path",
        "required": "required_support_path",
        "safe": "safe_edit_path",
        "protected": "protected_mask_path",
        "uncertainty": "uncertainty_mask_path",
        "visible": "visible_support_path",
    }.items():
        masks = [_read_mask(getattr(target, attribute)) for target in targets]
        union = np.logical_or.reduce(masks)
        path = output_root / f"{role}.png"
        if not cv2.imwrite(str(path), union.astype(np.uint8) * 255):
            raise ValueError(f"Unable to create grouped instance evidence: {role}")
        paths[role] = path
    return paths


def _read_mask(path: Path) -> np.ndarray:
    pixels = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if pixels is None:
        raise ValueError(f"Unreadable full-page Cleaning evidence mask: {path}")
    return pixels > 0


def _artifact(artifacts, artifact_type):
    matches = tuple(artifact for artifact in artifacts if artifact.artifact_type == artifact_type)
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {artifact_type} artifact.")
    return matches[0]


def _temp_path(stage, temp_ref_id):
    matches = tuple(ref.temp_path for ref in stage.provider_result.temp_files if ref.temp_ref_id == temp_ref_id)
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one temporary {temp_ref_id} output.")
    return matches[0]


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _fingerprint(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _inventory_id(run_id: str, target: FullPageCleaningTarget) -> str:
    return f"inventory::{run_id}::{target.text_segment_revision_id}"


def _assignment_id(revision_id: str, target: FullPageCleaningTarget) -> str:
    return f"assignment::{revision_id}::{target.text_segment_revision_id}"


__all__ = ["FullPageCleaningHarnessCommand", "FullPageCleaningHarnessResult", "FullPageCleaningHarnessService", "FullPageCleaningTarget"]
