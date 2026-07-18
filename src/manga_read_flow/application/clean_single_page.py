from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from manga_read_flow.domain.artifacts import ArtifactSafetyMetadata
from manga_read_flow.persistence.acceptance_repository import (
    AcceptanceCommand,
    ActivePointerUpdate,
    ExpectedState,
    PageStatusUpdate,
    StageStatusUpdate,
    TaskProgressUpdate,
    WorkflowDecisionDraft,
)
from manga_read_flow.persistence.visual_contract_repository import (
    BubbleInstanceRevisionDraft,
    CleaningEligibilityDraft,
    CleaningResultDraft,
    SegmentInstanceAssignmentDraft,
    TextSegmentRevisionDraft,
    VisualContractRevisionDraft,
)
from manga_read_flow.quality import QualityCheckInput, QualityCheckService
from manga_read_flow.quality.cleaning_validation import validate_cleaning_output
from manga_read_flow.workflow.quality_acceptance import issue_changes_from_drafts
from manga_read_flow.workflow.stage_executor import StageExecutionContext, StageExecutor


@dataclass(frozen=True)
class CleaningSliceInstanceInput:
    bubble_instance_id: str
    bubble_instance_revision_id: str
    region_hash: str
    text_segment_id: str
    text_segment_revision_id: str
    source_text_block_id: str
    segment_order: int
    instance_mask_path: Path
    required_support_path: Path | None
    safe_edit_path: Path | None
    protected_mask_path: Path | None
    uncertainty_mask_path: Path | None
    eligibility: str
    required_safe_completeness: str
    reason_code: str
    execute_cleaner: bool = True


@dataclass(frozen=True)
class SinglePageCleaningCommand:
    page_id: str
    batch_id: str
    source_artifact_id: str
    source_image_path: Path
    visual_contract_revision_id: str
    input_hash: str
    config_hash: str
    work_root: Path
    instances: tuple[CleaningSliceInstanceInput, ...]
    task_id: str | None = None
    page_scope_complete: bool = True


@dataclass(frozen=True)
class SinglePageCleaningResult:
    task_id: str | None
    attempt_id: str | None
    decision: str
    candidate_artifact_id: str
    evidence_artifact_id: str
    active_cleaned_artifact_id: str | None
    issue_ids: tuple[str, ...]
    provider_called: bool
    reused: bool
    timings_ms: dict[str, float]


class SinglePageCleaningService:
    """MVP-1 bounded Cleaning slice; intentionally not a general page pipeline."""

    def __init__(
        self,
        *,
        project_id: str,
        repositories,
        artifact_service,
        cleaner_provider,
    ) -> None:
        self._project_id = project_id
        self._repositories = repositories
        self._artifact_service = artifact_service
        self._cleaner_provider = cleaner_provider

    def run(self, command: SinglePageCleaningCommand) -> SinglePageCleaningResult:
        started = perf_counter()
        timings: dict[str, float] = {}
        page = self._repositories.content_state.get_page(command.page_id)
        if page.original_artifact_id != command.source_artifact_id:
            raise ValueError("Cleaning source artifact does not match the Page original.")
        known_blocks = {
            block.text_block_id
            for block in self._repositories.content_state.list_text_blocks_for_page(
                command.page_id
            )
        }
        missing_blocks = {
            item.source_text_block_id for item in command.instances
        } - known_blocks
        if missing_blocks:
            raise ValueError("Visual contract references unknown source TextBlocks.")

        command.work_root.mkdir(parents=True, exist_ok=True)
        reusable = self._repositories.visual_contract.find_reusable_pass(
            visual_contract_revision_id=command.visual_contract_revision_id,
            input_hash=command.input_hash,
            config_hash=command.config_hash,
        )
        if reusable is not None:
            integrity = self._artifact_service.validate_artifact(
                reusable.cleaned_artifact_id,
                expected_use="cleaning_reuse",
                active_reference="page.active_cleaned_artifact_id",
            )
            current_revision_id = self._repositories.visual_contract.current_revision_id(
                page_id=command.page_id
            )
            if (
                integrity.integrity_status == "valid"
                and current_revision_id == command.visual_contract_revision_id
                and page.active_cleaned_artifact_id == reusable.cleaned_artifact_id
            ):
                current_page = self._repositories.content_state.get_page(command.page_id)
                return SinglePageCleaningResult(
                    task_id=None,
                    attempt_id=reusable.workflow_attempt_id,
                    decision="pass",
                    candidate_artifact_id=reusable.cleaned_artifact_id,
                    evidence_artifact_id=reusable.evidence_artifact_id,
                    active_cleaned_artifact_id=current_page.active_cleaned_artifact_id,
                    issue_ids=(),
                    provider_called=False,
                    reused=True,
                    timings_ms={
                        **timings,
                        "total": (perf_counter() - started) * 1000,
                    },
                )

        phase = perf_counter()
        revision_exists = self._repositories.visual_contract.has_revision(
            visual_contract_revision_id=command.visual_contract_revision_id
        )
        if revision_exists:
            if (
                self._repositories.visual_contract.current_revision_id(
                    page_id=command.page_id
                )
                != command.visual_contract_revision_id
            ):
                raise ValueError("Cleaning command references a stale visual revision.")
        else:
            contract_artifacts, contract_evidence = self._register_contract(command)
            self._prepare_contract(
                command,
                contract_artifacts,
                contract_evidence.artifact_id,
            )
        timings["contract_artifact_and_persistence"] = (perf_counter() - phase) * 1000

        executable = tuple(
            item
            for item in command.instances
            if item.eligibility == "E1"
            and item.required_safe_completeness == "COMPLETE"
            and item.execute_cleaner
        )
        if len(executable) != 1:
            raise ValueError("The bounded Cleaning slice requires exactly one executable E1 instance.")
        target = executable[0]
        if any(
            path is None
            for path in (
                target.required_support_path,
                target.safe_edit_path,
                target.protected_mask_path,
                target.uncertainty_mask_path,
            )
        ):
            raise ValueError("Executable E1 instance is missing pixel evidence.")
        profile = self._ensure_profile(command.config_hash)
        task_id = command.task_id or f"task-cleaning-{uuid4()}"
        self._repositories.workflow_execution.create_task(
            task_id=task_id,
            target_type="page",
            target_id=command.page_id,
            task_type="mvp1_single_page_cleaning",
            status="queued",
            current_stage="cleaning",
            profile_snapshot_id=profile.profile_snapshot_id,
        )

        attempt_id = f"attempt-cleaning-{uuid4()}"
        attempt_root = command.work_root / "attempts" / attempt_id
        stage_executor = StageExecutor(
            attempt_recorder=self._repositories.workflow_execution,
            evidence_writer=self._repositories.stage_evidence_writer,
            artifact_service=self._artifact_service,
        )
        phase = perf_counter()
        stage_result = stage_executor.execute(
            StageExecutionContext(
                project_id=self._project_id,
                task_id=task_id,
                attempt_id=attempt_id,
                tool_run_id=f"tool-run-cleaning-{uuid4()}",
                request_id=f"request-cleaning-{uuid4()}",
                stage="cleaning",
                target_type="page",
                target_id=command.page_id,
                batch_id=command.batch_id,
                page_id=command.page_id,
                text_block_ids=(target.source_text_block_id,),
                expected_task_status="queued",
                expected_current_stage="cleaning",
                runner_id="mvp1-single-page-cleaning-slice",
                attempt_temp_root=attempt_root,
                input_hash=command.input_hash,
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
        timings["provider_and_output_promotion"] = (perf_counter() - phase) * 1000
        candidate_artifact = _single_artifact(stage_result.registered_artifacts, "cleaned_image")
        cleaned_temp = _temp_file(stage_result, "cleaned_image")
        phase = perf_counter()
        validation = validate_cleaning_output(
            source_image_path=command.source_image_path,
            cleaned_image_path=cleaned_temp,
            required_support_path=target.required_support_path,
            safe_edit_path=target.safe_edit_path,
            instance_mask_path=target.instance_mask_path,
            protected_mask_path=target.protected_mask_path,
            uncertainty_mask_path=target.uncertainty_mask_path,
            output_dir=attempt_root / "validator",
        )
        result_id = f"cleaning-result-{uuid4()}"
        validation_artifacts = self._register_validation_artifacts(
            command=command,
            result_id=result_id,
            validation=validation,
        )
        evidence_artifact = validation_artifacts["validation_evidence"]
        timings["validator_and_evidence_promotion"] = (perf_counter() - phase) * 1000

        issue_flags = dict(validation.issue_flags)
        incomplete_text_block_ids = tuple(
            item.source_text_block_id
            for item in command.instances
            if item.required_safe_completeness != "COMPLETE"
            and item.eligibility in {"E1", "E2", "E3", "REVIEW"}
        )
        issue_flags["required_support_incomplete"] = bool(incomplete_text_block_ids)
        issue_flags["page_scope_incomplete"] = not command.page_scope_complete
        issue_flags["incomplete_text_block_ids"] = incomplete_text_block_ids
        issue_flags["primary_evidence_artifact_id"] = evidence_artifact.artifact_id
        phase = perf_counter()
        quality_report = QualityCheckService().check(
            QualityCheckInput(
                stage="cleaning",
                target_type="page",
                target_id=command.page_id,
                page_id=command.page_id,
                text_block_ids=tuple(
                    item.source_text_block_id for item in command.instances
                ),
                provider_outcome=stage_result.provider_result.outcome.value,
                workflow_attempt_id=attempt_id,
                tool_run_id=stage_result.tool_run_id,
                input_hash=command.input_hash,
                config_hash=command.config_hash,
                candidate_outputs=issue_flags,
                registered_artifact_ids=tuple(
                    artifact.artifact_id
                    for artifact in stage_result.registered_artifacts
                    + tuple(validation_artifacts.values())
                ),
            )
        )
        issue_changes = issue_changes_from_drafts(quality_report.issue_drafts)
        decision = "block" if quality_report.summary.has_blocking_issue else "pass"
        timings["quality_classification"] = (perf_counter() - phase) * 1000
        active_pointers = ()
        if decision == "pass":
            active_pointers = (
                ActivePointerUpdate(
                    owner_type="page",
                    owner_id=command.page_id,
                    pointer_name="active_cleaned_artifact_id",
                    value_id=candidate_artifact.artifact_id,
                ),
            )

        phase = perf_counter()
        acceptance = self._repositories.uow.accept_stage(
            AcceptanceCommand(
                task_id=task_id,
                expected=ExpectedState(
                    task_status="running",
                    current_stage="cleaning",
                    visual_contract_revision_ids={
                        command.page_id: command.visual_contract_revision_id
                    },
                    attempt_id=attempt_id,
                    attempt_status="succeeded",
                    page_artifact_ids={
                        command.page_id: {
                            "active_cleaned_artifact_id": page.active_cleaned_artifact_id
                        }
                    },
                ),
                accepted_results=(),
                active_pointers=active_pointers,
                issue_lifecycle=issue_changes,
                workflow_decision=WorkflowDecisionDraft(
                    decision_id=f"decision-cleaning-{uuid4()}",
                    attempt_id=attempt_id,
                    stage="cleaning",
                    decision_type=decision,
                    reason_code=(
                        "cleaning_validation_passed"
                        if decision == "pass"
                        else "cleaning_input_or_output_blocked"
                    ),
                    linked_issue_ids=tuple(change.issue_id for change in issue_changes),
                ),
                retry_budget_after={"cleaning": 0},
                task_progress=TaskProgressUpdate(
                    status="completed" if decision == "pass" else "blocked",
                    current_stage="cleaning",
                    progress_state="cleaning_passed" if decision == "pass" else "review_required",
                ),
                stage_statuses=tuple(
                    StageStatusUpdate(
                        target_type="text_block",
                        target_id=item.source_text_block_id,
                        stage="cleaning",
                        status=(
                            "done"
                            if decision == "pass"
                            else "blocked"
                        ),
                    )
                    for item in command.instances
                ),
                page_statuses=(
                    PageStatusUpdate(
                        page_id=command.page_id,
                        status="cleaned" if decision == "pass" else "review_required",
                    ),
                ),
                attempt_terminal_status="succeeded",
                cleaning_result=CleaningResultDraft(
                    cleaning_result_id=result_id,
                    page_id=command.page_id,
                    visual_contract_revision_id=command.visual_contract_revision_id,
                    workflow_attempt_id=attempt_id,
                    cleaned_artifact_id=candidate_artifact.artifact_id,
                    evidence_artifact_id=evidence_artifact.artifact_id,
                    input_hash=command.input_hash,
                    config_hash=command.config_hash,
                    decision=decision,
                ),
            )
        )
        if not acceptance.committed:
            raise RuntimeError(
                "Cleaning decision transaction conflicted: "
                + ", ".join(acceptance.conflict_fields)
            )
        timings["decision_transaction"] = (perf_counter() - phase) * 1000
        updated_page = self._repositories.content_state.get_page(command.page_id)
        timings["total"] = (perf_counter() - started) * 1000
        return SinglePageCleaningResult(
            task_id=task_id,
            attempt_id=attempt_id,
            decision=decision,
            candidate_artifact_id=candidate_artifact.artifact_id,
            evidence_artifact_id=evidence_artifact.artifact_id,
            active_cleaned_artifact_id=updated_page.active_cleaned_artifact_id,
            issue_ids=tuple(change.issue_id for change in issue_changes),
            provider_called=True,
            reused=False,
            timings_ms=timings,
        )

    def _register_contract(self, command):
        manifest_path = command.work_root / "visual-contract-evidence.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "visual_contract_revision_id": command.visual_contract_revision_id,
                    "page_id": command.page_id,
                    "input_hash": command.input_hash,
                    "instances": [
                        {
                            "bubble_instance_id": item.bubble_instance_id,
                            "bubble_instance_revision_id": item.bubble_instance_revision_id,
                            "text_segment_id": item.text_segment_id,
                            "text_segment_revision_id": item.text_segment_revision_id,
                            "eligibility": item.eligibility,
                            "required_safe_completeness": item.required_safe_completeness,
                            "reason_code": item.reason_code,
                        }
                        for item in command.instances
                    ],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        evidence = self._artifact_service.register_stage_json(
            temp_path=manifest_path,
            batch_id=command.batch_id,
            page_id=command.page_id,
            owner_type="visual_contract_revision",
            owner_id=command.visual_contract_revision_id,
            artifact_type="validation_evidence",
            source_stage="cleaning_input",
            dependency_hash=command.input_hash,
        )
        artifacts = {}
        for item in command.instances:
            per_instance = {}
            for key, path in {
                "instance_mask": item.instance_mask_path,
                "required_support": item.required_support_path,
                "safe_edit": item.safe_edit_path,
                "protected": item.protected_mask_path,
                "uncertainty": item.uncertainty_mask_path,
            }.items():
                if path is None:
                    continue
                per_instance[key] = self._artifact_service.register_stage_output(
                    temp_path=path,
                    batch_id=command.batch_id,
                    page_id=command.page_id,
                    owner_type="bubble_instance_revision",
                    owner_id=item.bubble_instance_revision_id,
                    artifact_type="mask_image",
                    source_stage="cleaning_input",
                    retention_class="successful_payload",
                    safety=ArtifactSafetyMetadata(may_contain_original_image=False),
                    dependency_hash=command.input_hash,
                )
            artifacts[item.bubble_instance_revision_id] = per_instance
        return artifacts, evidence

    def _prepare_contract(self, command, artifacts, evidence_artifact_id):
        self._repositories.visual_contract.prepare_contract(
            revision=VisualContractRevisionDraft(
                visual_contract_revision_id=command.visual_contract_revision_id,
                page_id=command.page_id,
                source_artifact_id=command.source_artifact_id,
                input_hash=command.input_hash,
            ),
            instances=tuple(
                BubbleInstanceRevisionDraft(
                    bubble_instance_revision_id=item.bubble_instance_revision_id,
                    bubble_instance_id=item.bubble_instance_id,
                    page_id=command.page_id,
                    visual_contract_revision_id=command.visual_contract_revision_id,
                    region_hash=item.region_hash,
                    instance_mask_artifact_id=artifacts[item.bubble_instance_revision_id]["instance_mask"].artifact_id,
                    required_support_artifact_id=_optional_artifact_id(artifacts[item.bubble_instance_revision_id], "required_support"),
                    safe_edit_artifact_id=_optional_artifact_id(artifacts[item.bubble_instance_revision_id], "safe_edit"),
                    protected_artifact_id=_optional_artifact_id(artifacts[item.bubble_instance_revision_id], "protected"),
                    uncertainty_artifact_id=_optional_artifact_id(artifacts[item.bubble_instance_revision_id], "uncertainty"),
                )
                for item in command.instances
            ),
            segments=tuple(
                TextSegmentRevisionDraft(
                    text_segment_revision_id=item.text_segment_revision_id,
                    text_segment_id=item.text_segment_id,
                    page_id=command.page_id,
                    visual_contract_revision_id=command.visual_contract_revision_id,
                    source_text_block_id=item.source_text_block_id,
                    segment_order=item.segment_order,
                )
                for item in command.instances
            ),
            assignments=tuple(
                SegmentInstanceAssignmentDraft(
                    assignment_id=f"assignment::{item.text_segment_revision_id}",
                    visual_contract_revision_id=command.visual_contract_revision_id,
                    text_segment_revision_id=item.text_segment_revision_id,
                    bubble_instance_revision_id=item.bubble_instance_revision_id,
                    disposition="assigned",
                    reason_code="unique_instance_assignment",
                    evidence_artifact_id=evidence_artifact_id,
                )
                for item in command.instances
            ),
            eligibility=tuple(
                CleaningEligibilityDraft(
                    cleaning_eligibility_id=f"eligibility::{item.bubble_instance_revision_id}",
                    bubble_instance_revision_id=item.bubble_instance_revision_id,
                    eligibility=item.eligibility,
                    required_safe_completeness=item.required_safe_completeness,
                    reason_code=item.reason_code,
                    evidence_artifact_id=evidence_artifact_id,
                )
                for item in command.instances
            ),
        )

    def _register_validation_artifacts(self, *, command, result_id, validation):
        registered = {
            "validation_evidence": self._artifact_service.register_stage_json(
                temp_path=validation.evidence_path,
                batch_id=command.batch_id,
                page_id=command.page_id,
                owner_type="cleaning_result",
                owner_id=result_id,
                artifact_type="validation_evidence",
                source_stage="cleaning",
                dependency_hash=command.input_hash,
            )
        }
        for key, path in {
            "actual_changed": validation.actual_changed_mask_path,
            "residue": validation.residue_mask_path,
            "structure_damage": validation.structure_damage_mask_path,
            "background_difference": validation.background_difference_mask_path,
        }.items():
            registered[key] = self._artifact_service.register_stage_output(
                temp_path=path,
                batch_id=command.batch_id,
                page_id=command.page_id,
                owner_type="cleaning_result",
                owner_id=result_id,
                artifact_type="mask_image",
                source_stage="cleaning",
                retention_class="successful_payload",
                dependency_hash=command.input_hash,
            )
        return registered

    def _ensure_profile(self, config_hash: str):
        settings = {
            "snapshot_schema_version": "mvp1-cleaning-slice.v1",
            "source_profile_id": "mvp1_bounded_e1",
            "source_profile_version": "1",
            "cleaner": self._cleaner_provider.identity.provider_name,
            "config_hash": config_hash,
            "retry_budgets": {"cleaning": 0},
        }
        settings_json = json.dumps(settings, sort_keys=True, separators=(",", ":"))
        return self._repositories.workflow_execution.ensure_profile_snapshot(
            profile_snapshot_id=(
                "profile-snapshot-mvp1-cleaning-"
                + sha256(settings_json.encode("utf-8")).hexdigest()[:16]
            ),
            settings_json=settings_json,
            settings_hash=sha256(settings_json.encode("utf-8")).hexdigest(),
        )


def _single_artifact(artifacts, artifact_type: str):
    matches = tuple(
        artifact for artifact in artifacts if artifact.artifact_type == artifact_type
    )
    if len(matches) != 1:
        raise RuntimeError(f"Expected one registered {artifact_type} artifact.")
    return matches[0]


def _temp_file(stage_result, temp_ref_id: str) -> Path:
    matches = tuple(
        ref.temp_path
        for ref in stage_result.provider_result.temp_files
        if ref.temp_ref_id == temp_ref_id
    )
    if len(matches) != 1:
        raise RuntimeError(f"Expected one Provider temp file: {temp_ref_id}.")
    return matches[0]


def _optional_artifact_id(artifacts: dict[str, object], key: str) -> str | None:
    artifact = artifacts.get(key)
    return artifact.artifact_id if artifact is not None else None


__all__ = [
    "CleaningSliceInstanceInput",
    "SinglePageCleaningCommand",
    "SinglePageCleaningResult",
    "SinglePageCleaningService",
]
