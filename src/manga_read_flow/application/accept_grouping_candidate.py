from __future__ import annotations

from dataclasses import dataclass
import json
from uuid import uuid4

from manga_read_flow.application.check_grouping_candidate import (
    CheckGroupingCandidateApplicationService,
    CheckGroupingCandidateCommand,
)
from manga_read_flow.persistence.grouping_acceptance_repository import (
    CurrentGroupingSnapshot,
    ExpectedGroupingIssue,
    ExpectedGroupingOcrDependency,
    GroupingAcceptanceSnapshot,
    GroupingDecisionContextDraft,
    grouping_acceptance_id,
)
from manga_read_flow.persistence.repository_uow_core import (
    AcceptanceCommand,
    AcceptanceOutcome,
    ExpectedState,
    TaskProgressUpdate,
    WorkflowDecisionDraft,
)
from manga_read_flow.persistence.workflow_execution_repository import (
    WorkflowDecisionSnapshot,
)
from manga_read_flow.quality.grouping_check import grouping_check_input_fingerprint
from manga_read_flow.workflow.engine import (
    GroupingWorkflowDecisionInput,
    GroupingWorkflowIssue,
    WorkflowLoopEngine,
)


GROUPING_ACCEPTED = "ACCEPTED"
GROUPING_ACCEPTANCE_REPLAYED = "REPLAYED"
GROUPING_DECISION_BLOCKED = "BLOCKED"
GROUPING_ACCEPTANCE_CONFLICT = "CONFLICT_RELOAD"


@dataclass(frozen=True)
class AcceptGroupingCandidateCommand:
    page_id: str
    snapshot_id: str
    check_result_id: str
    check_execution_id: str
    task_id: str
    attempt_id: str
    current_detection_dependency_id: str
    current_profile_snapshot_id: str
    expected_producer_name: str
    expected_producer_version: str
    expected_producer_implementation_hash: str
    expected_operation_semantics_version: str
    expected_active_grouping_snapshot_id: str | None
    expected_page_grouping_state_version: int | None
    runtime_config_json: str = "{}"
    decision_execution_id: str | None = None
    decision_id: str | None = None


@dataclass(frozen=True)
class AcceptGroupingCandidateResult:
    status: str
    decision: WorkflowDecisionSnapshot | None
    acceptance: GroupingAcceptanceSnapshot | None
    current: CurrentGroupingSnapshot | None
    conflict_fields: tuple[str, ...] = ()


class AcceptGroupingCandidateApplicationService:
    """Formal Grouping Workflow/UoW acceptance entry."""

    def __init__(
        self,
        *,
        project_id: str,
        repositories,
        artifact_service,
    ) -> None:
        self._project_id = project_id
        self._repositories = repositories
        self._artifact_service = artifact_service

    def accept(
        self,
        command: AcceptGroupingCandidateCommand,
    ) -> AcceptGroupingCandidateResult:
        _validate_command(command)
        candidate = self._repositories.grouping_snapshots.get(command.snapshot_id)
        check_result = self._repositories.grouping_checks.get(command.check_result_id)
        if (
            candidate.project_id != self._project_id
            or candidate.page_id != command.page_id
        ):
            raise ValueError("Grouping acceptance candidate Project/Page binding is invalid.")
        if (
            check_result.project_id != self._project_id
            or check_result.page_id != command.page_id
            or check_result.snapshot_id != candidate.snapshot_id
            or check_result.candidate_manifest_sha256
            != candidate.manifest_artifact_sha256
            or check_result.candidate_dependency_fingerprint
            != candidate.dependency_fingerprint
        ):
            raise ValueError("Grouping acceptance CheckResult binding is invalid.")

        executions = self._repositories.grouping_checks.list_executions(
            check_result.check_result_id
        )
        if not any(
            item.execution_id == command.check_execution_id
            and item.snapshot_id == candidate.snapshot_id
            and item.input_fingerprint == check_result.input_fingerprint
            for item in executions
        ):
            raise ValueError("Grouping acceptance Check execution binding is invalid.")

        exact_issue_ids = self._repositories.grouping_checks.issue_ids_for_result(
            check_result.check_result_id
        )
        issues = self._repositories.quality_issues.list_for_result(
            check_result.check_result_id
        )
        if tuple(sorted(item.issue_id for item in issues)) != exact_issue_ids:
            raise ValueError("Grouping acceptance QualityIssue relation is inconsistent.")

        task = self._repositories.workflow_execution.get_task(command.task_id)
        terminal_replay = self._terminal_replay(command, candidate, task)
        if terminal_replay is not None:
            return terminal_replay
        profile = self._repositories.workflow_execution.get_profile_snapshot(
            command.current_profile_snapshot_id
        )
        page = self._repositories.content_state.get_page(command.page_id)
        source = self._repositories.artifact_metadata.get_artifact(
            page.original_artifact_id
        )
        detection = self._repositories.detection_evidence.get(
            command.current_detection_dependency_id
        )
        current_ocr = self._repositories.result_versions.exact_active_ocr_dependencies(
            page_id=command.page_id,
            text_block_ids=tuple(
                item.text_block_id for item in candidate.ocr_dependencies
            ),
        )

        source_integrity = self._artifact_service.validate_artifact(
            source.artifact_id,
            expected_use="grouping_acceptance_source",
        )
        manifest_integrity = self._artifact_service.validate_artifact(
            candidate.manifest_artifact_id,
            expected_use="grouping_acceptance_manifest",
        )
        check_evidence_valid = True
        if check_result.evidence_artifact_id is not None:
            check_evidence = self._artifact_service.validate_artifact(
                check_result.evidence_artifact_id,
                expected_use="grouping_acceptance_check_evidence",
            )
            check_evidence_valid = (
                check_evidence.integrity_status == "valid"
                and check_evidence.observed_hash
                == check_result.evidence_artifact_sha256
            )
        current_check_input = CheckGroupingCandidateApplicationService(
            project_id=self._project_id,
            repositories=self._repositories,
            artifact_service=self._artifact_service,
        ).build_input(
            CheckGroupingCandidateCommand(
                page_id=command.page_id,
                snapshot_id=command.snapshot_id,
                current_detection_dependency_id=(
                    command.current_detection_dependency_id
                ),
                current_profile_snapshot_id=command.current_profile_snapshot_id,
                expected_producer_name=command.expected_producer_name,
                expected_producer_version=command.expected_producer_version,
                expected_producer_implementation_hash=(
                    command.expected_producer_implementation_hash
                ),
                expected_operation_semantics_version=(
                    command.expected_operation_semantics_version
                ),
                runtime_config_json=command.runtime_config_json,
                execution_id=command.check_execution_id,
            )
        )
        current_check_input_fingerprint = grouping_check_input_fingerprint(
            current_check_input
        )

        current_ocr_context = tuple(
            ExpectedGroupingOcrDependency(
                text_block_id=item.text_block_id,
                ocr_result_id=item.ocr_result_id,
                version_number=item.version_number,
                text_hash=item.source_text_hash,
                geometry_hash=item.geometry_hash,
                input_hash=item.input_hash,
            )
            for item in current_ocr
        )
        dependencies_valid = (
            task.target_type == "page"
            and task.target_id == command.page_id
            and task.profile_snapshot_id == command.current_profile_snapshot_id
            and source_integrity.integrity_status == "valid"
            and source_integrity.observed_hash == candidate.source_sha256
            and source.artifact_id == candidate.source_artifact_id
            and detection.page_id == candidate.page_id
            and detection.detection_dependency_id
            == candidate.detection_dependency_id
            and detection.canonical_manifest_sha256
            == candidate.detection_dependency_hash
            and _ocr_matches_candidate(current_ocr_context, candidate)
            and profile.profile_snapshot_id == candidate.profile_snapshot_id
            and profile.settings_hash == candidate.profile_settings_hash
            and candidate.producer_name == command.expected_producer_name
            and candidate.producer_version == command.expected_producer_version
            and candidate.producer_implementation_hash
            == command.expected_producer_implementation_hash
            and candidate.operation_semantics_version
            == command.expected_operation_semantics_version
        )
        check_applicable = (
            current_check_input_fingerprint == check_result.input_fingerprint
            and manifest_integrity.integrity_status == "valid"
            and manifest_integrity.observed_hash
            == check_result.candidate_manifest_sha256
            and check_evidence_valid
        )
        retry_budget = _grouping_retry_budget(profile.settings_json)
        workflow_decision = WorkflowLoopEngine.decide_grouping(
            GroupingWorkflowDecisionInput(
                snapshot_id=candidate.snapshot_id,
                check_result_id=check_result.check_result_id,
                execution_id=command.check_execution_id,
                candidate_disposition=candidate.candidate_disposition,
                related_issues=tuple(
                    GroupingWorkflowIssue(
                        issue_id=item.issue_id,
                        status=item.status,
                        is_blocking=item.is_blocking,
                    )
                    for item in issues
                ),
                retry_budget=retry_budget,
                dependencies_valid=dependencies_valid,
                check_applicable=check_applicable,
                expected_active_grouping_snapshot_id=(
                    command.expected_active_grouping_snapshot_id
                ),
                expected_page_grouping_state_version=(
                    command.expected_page_grouping_state_version
                ),
            )
        )

        decision_id = command.decision_id or f"decision-grouping-{uuid4()}"
        execution_id = (
            command.decision_execution_id
            or f"grouping-acceptance-execution-{uuid4()}"
        )
        is_accept = workflow_decision.decision_type == "accept"
        context = GroupingDecisionContextDraft(
            page_id=command.page_id,
            snapshot_id=candidate.snapshot_id,
            check_result_id=check_result.check_result_id,
            check_execution_id=command.check_execution_id,
            decision_execution_id=execution_id,
            current_detection_dependency_id=detection.detection_dependency_id,
            current_detection_dependency_hash=detection.canonical_manifest_sha256,
            current_profile_snapshot_id=profile.profile_snapshot_id,
            current_profile_settings_hash=profile.settings_hash,
            current_source_artifact_id=source.artifact_id,
            current_source_sha256=source.file_hash,
            current_ocr_dependencies=current_ocr_context,
            current_check_input_fingerprint=current_check_input_fingerprint,
            expected_producer_name=command.expected_producer_name,
            expected_producer_version=command.expected_producer_version,
            expected_producer_implementation_hash=(
                command.expected_producer_implementation_hash
            ),
            expected_operation_semantics_version=(
                command.expected_operation_semantics_version
            ),
            expected_active_grouping_snapshot_id=(
                command.expected_active_grouping_snapshot_id
            ),
            expected_page_grouping_state_version=(
                command.expected_page_grouping_state_version
            ),
            expected_issues=tuple(
                ExpectedGroupingIssue(
                    issue_id=item.issue_id,
                    status=item.status,
                    is_blocking=item.is_blocking,
                    updated_at=item.updated_at,
                )
                for item in issues
            ),
            acceptance_id=(
                grouping_acceptance_id(
                    snapshot_id=candidate.snapshot_id,
                    check_result_id=check_result.check_result_id,
                )
                if is_accept
                else None
            ),
        )
        outcome = self._repositories.uow.accept_stage(
            AcceptanceCommand(
                task_id=command.task_id,
                expected=ExpectedState(
                    task_status="running",
                    current_stage="grouping",
                    attempt_id=command.attempt_id,
                    attempt_status="running",
                ),
                accepted_results=(),
                active_pointers=(),
                issue_lifecycle=(),
                workflow_decision=WorkflowDecisionDraft(
                    decision_id=decision_id,
                    attempt_id=command.attempt_id,
                    stage="grouping",
                    decision_type=workflow_decision.decision_type,
                    reason_code=workflow_decision.reason_code,
                    linked_issue_ids=workflow_decision.linked_issue_ids,
                ),
                retry_budget_after={"grouping": retry_budget},
                task_progress=TaskProgressUpdate(
                    status="succeeded" if is_accept else "blocked",
                    current_stage="grouping" if is_accept else "block",
                    progress_state=workflow_decision.reason_code,
                ),
                stage_statuses=(),
                attempt_terminal_status="succeeded" if is_accept else "failed",
                grouping_context=context,
            )
        )
        if not outcome.committed:
            return AcceptGroupingCandidateResult(
                status=GROUPING_ACCEPTANCE_CONFLICT,
                decision=None,
                acceptance=None,
                current=None,
                conflict_fields=outcome.conflict_fields,
            )
        return self._exact_result(
            outcome=outcome,
            decision_id=decision_id,
            page_id=command.page_id,
            accepted=is_accept,
        )

    def _terminal_replay(self, command, candidate, task):
        if task.status not in {"succeeded", "blocked"} or command.decision_id is None:
            return None
        try:
            decision = self._repositories.workflow_execution.get_decision(
                command.decision_id
            )
        except LookupError:
            return None
        if (
            decision.task_id != command.task_id
            or decision.attempt_id != command.attempt_id
            or decision.stage != "grouping"
        ):
            return None
        if decision.decision_type != "accept":
            if decision.decision_type == "block" and task.status == "blocked":
                return AcceptGroupingCandidateResult(
                    status=GROUPING_DECISION_BLOCKED,
                    decision=decision,
                    acceptance=None,
                    current=None,
                )
            return None
        acceptance_id = grouping_acceptance_id(
            snapshot_id=candidate.snapshot_id,
            check_result_id=command.check_result_id,
        )
        try:
            acceptance = self._repositories.grouping_acceptance.get_acceptance(
                acceptance_id
            )
            current = self._repositories.grouping_acceptance.get_current(
                command.page_id
            )
        except (LookupError, ValueError):
            return None
        if (
            acceptance.workflow_decision_id != decision.decision_id
            or acceptance.workflow_attempt_id != command.attempt_id
            or acceptance.acceptance_execution_id
            != command.decision_execution_id
            or current.acceptance.acceptance_id != acceptance.acceptance_id
        ):
            return None
        source_integrity = self._artifact_service.validate_artifact(
            candidate.source_artifact_id,
            expected_use="grouping_terminal_replay_source",
        )
        manifest_integrity = self._artifact_service.validate_artifact(
            candidate.manifest_artifact_id,
            expected_use="grouping_terminal_replay_manifest",
        )
        if (
            source_integrity.integrity_status != "valid"
            or source_integrity.observed_hash != candidate.source_sha256
            or manifest_integrity.integrity_status != "valid"
            or manifest_integrity.observed_hash != candidate.manifest_artifact_sha256
        ):
            raise ValueError("Grouping terminal replay artifact integrity is invalid.")
        return AcceptGroupingCandidateResult(
            status=GROUPING_ACCEPTANCE_REPLAYED,
            decision=decision,
            acceptance=acceptance,
            current=current,
        )

    def _exact_result(
        self,
        *,
        outcome: AcceptanceOutcome,
        decision_id: str,
        page_id: str,
        accepted: bool,
    ) -> AcceptGroupingCandidateResult:
        decision = self._repositories.workflow_execution.get_decision(decision_id)
        if not accepted:
            return AcceptGroupingCandidateResult(
                status=GROUPING_DECISION_BLOCKED,
                decision=decision,
                acceptance=None,
                current=None,
            )
        if outcome.grouping_acceptance_id is None:
            raise ValueError("Committed Grouping accept decision lacks acceptance identity.")
        acceptance = self._repositories.grouping_acceptance.get_acceptance(
            outcome.grouping_acceptance_id
        )
        current = self._repositories.grouping_acceptance.get_current(page_id)
        if (
            current.acceptance.acceptance_id != acceptance.acceptance_id
            or current.page_state.version != outcome.page_grouping_state_version
        ):
            raise ValueError("Grouping acceptance exact read-back is inconsistent.")
        return AcceptGroupingCandidateResult(
            status=(
                GROUPING_ACCEPTANCE_REPLAYED
                if outcome.grouping_acceptance_replayed
                else GROUPING_ACCEPTED
            ),
            decision=decision,
            acceptance=acceptance,
            current=current,
        )


def _ocr_matches_candidate(current, candidate) -> bool:
    stored = tuple(
        ExpectedGroupingOcrDependency(
            text_block_id=item.text_block_id,
            ocr_result_id=item.ocr_result_id,
            version_number=item.ocr_version_number,
            text_hash=item.ocr_text_hash,
            geometry_hash=item.ocr_geometry_hash,
            input_hash=item.ocr_input_hash,
        )
        for item in candidate.ocr_dependencies
    )
    return current == stored


def _grouping_retry_budget(settings_json: str) -> int:
    settings = json.loads(settings_json)
    budgets = settings.get("retry_budgets", {})
    value = budgets.get("grouping", 0) if isinstance(budgets, dict) else 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("ProcessingProfileSnapshot Grouping retry budget is invalid.")
    return value


def _validate_command(command: AcceptGroupingCandidateCommand) -> None:
    for name in (
        "page_id",
        "snapshot_id",
        "check_result_id",
        "check_execution_id",
        "task_id",
        "attempt_id",
        "current_detection_dependency_id",
        "current_profile_snapshot_id",
        "expected_producer_name",
        "expected_producer_version",
        "expected_producer_implementation_hash",
        "expected_operation_semantics_version",
    ):
        if not getattr(command, name):
            raise ValueError(f"Grouping acceptance command {name} is required.")
    if command.expected_page_grouping_state_version is not None and (
        command.expected_page_grouping_state_version < 1
    ):
        raise ValueError("Expected Grouping page state version is invalid.")
