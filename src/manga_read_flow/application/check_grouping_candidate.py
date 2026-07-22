from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from manga_read_flow.artifacts.service import ArtifactValidationError
from manga_read_flow.domain.artifacts import (
    ArtifactSafetyMetadata,
    ProcessingArtifactSnapshot,
)
from manga_read_flow.persistence.content_state_repository import (
    ExactOcrDependenciesNotReadyError,
)
from manga_read_flow.persistence.grouping_check_repository import (
    GroupingCheckExecutionDraft,
    GroupingCheckExecutionSnapshot,
)
from manga_read_flow.persistence.workflow_execution_repository import (
    QualityIssueSnapshot,
)
from manga_read_flow.quality import QualityCheckService
from manga_read_flow.quality.grouping_check import (
    CurrentDetectionCheckBinding,
    CurrentProfileCheckBinding,
    GroupingCandidateCheckFact,
    GroupingCheckEvaluation,
    GroupingCheckGenerationFact,
    GroupingCheckInput,
    GroupingCheckOcrBinding,
    GroupingCheckResult,
    GroupingCurrentUsability,
    GroupingManifestEvidence,
    grouping_check_evidence_bytes,
)
from manga_read_flow.workflow.quality_acceptance import issue_changes_from_drafts


GROUPING_CHECK_APPLICATION_COMPLETED = "CHECK_COMPLETED"
GROUPING_CHECK_APPLICATION_REUSED = "REUSED_EXISTING_CHECK"


@dataclass(frozen=True)
class CheckGroupingCandidateCommand:
    page_id: str
    snapshot_id: str
    current_detection_dependency_id: str
    current_profile_snapshot_id: str
    expected_producer_name: str
    expected_producer_version: str
    expected_producer_implementation_hash: str
    expected_operation_semantics_version: str
    runtime_config_json: str = "{}"
    execution_id: str | None = None


@dataclass(frozen=True)
class CheckGroupingCandidateResult:
    status: str
    check_result: GroupingCheckResult
    quality_issues: tuple[QualityIssueSnapshot, ...]
    execution: GroupingCheckExecutionSnapshot


class GroupingCheckCommitError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        evidence_artifact: ProcessingArtifactSnapshot | None,
    ) -> None:
        super().__init__(message)
        self.evidence_artifact = evidence_artifact


class CheckGroupingCandidateApplicationService:
    """Formal Grouping Check entry without acceptance or Workflow authority."""

    def __init__(
        self,
        *,
        project_id: str,
        repositories,
        artifact_service,
        quality_check_service: QualityCheckService | None = None,
    ) -> None:
        self._project_id = project_id
        self._repositories = repositories
        self._artifact_service = artifact_service
        self._quality_check_service = quality_check_service or QualityCheckService()

    def check(
        self,
        command: CheckGroupingCandidateCommand,
    ) -> CheckGroupingCandidateResult:
        execution_id = command.execution_id or f"grouping-check-execution-{uuid4()}"
        candidate = self._repositories.grouping_snapshots.get(command.snapshot_id)
        page = self._repositories.content_state.get_page(command.page_id)
        check_input = self.build_input(command)
        evaluation = self._quality_check_service.check_grouping(check_input)

        existing = self._repositories.grouping_checks.get_optional_by_input_fingerprint(
            evaluation.check_result.input_fingerprint
        )
        evidence_artifact = None
        if existing is None:
            evidence_artifact = self._register_evidence(page, evaluation)
            evaluation = replace(
                evaluation,
                check_result=replace(
                    evaluation.check_result,
                    evidence_artifact_id=evidence_artifact.artifact_id,
                    evidence_artifact_sha256=evidence_artifact.file_hash,
                ),
            )
        else:
            if existing.check_result_id != evaluation.check_result.check_result_id:
                raise ValueError("Grouping check idempotency identity is inconsistent.")
            evaluation = replace(
                evaluation,
                check_result=replace(
                    evaluation.check_result,
                    evidence_artifact_id=existing.evidence_artifact_id,
                    evidence_artifact_sha256=existing.evidence_artifact_sha256,
                ),
            )
            if existing.evidence_artifact_id is not None:
                self._artifact_service.read_json_artifact(
                    existing.evidence_artifact_id,
                    expected_use="grouping_check_reuse",
                )

        issue_changes = issue_changes_from_drafts(
            evaluation.issue_drafts,
            deterministic_issue_ids=True,
        )
        try:
            committed = self._repositories.uow.commit_grouping_check_evaluation(
                check_result=evaluation.check_result,
                issue_changes=issue_changes,
                execution=GroupingCheckExecutionDraft(
                    execution_id=execution_id,
                    check_result_id=evaluation.check_result.check_result_id,
                    snapshot_id=candidate.snapshot_id,
                    page_id=candidate.page_id,
                    input_fingerprint=evaluation.check_result.input_fingerprint,
                ),
            )
        except Exception as exc:
            raise GroupingCheckCommitError(
                "Grouping check evidence was prepared, but CheckResult and QualityIssues did not commit.",
                evidence_artifact=evidence_artifact,
            ) from exc

        exact_result = self._repositories.uow.get_grouping_check_result(
            committed.check_result.check_result_id
        )
        exact_issue_ids = self._repositories.grouping_checks.issue_ids_for_result(
            exact_result.check_result_id
        )
        exact_issues = self._repositories.quality_issues.list_for_result(
            exact_result.check_result_id
        )
        if tuple(sorted((item.issue_id for item in exact_issues))) != exact_issue_ids:
            raise ValueError("Grouping CheckResult exact QualityIssue read-back failed.")
        if exact_result.evidence_artifact_id is not None:
            self._artifact_service.read_json_artifact(
                exact_result.evidence_artifact_id,
                expected_use="grouping_check_exact_read",
            )
        return CheckGroupingCandidateResult(
            status=(
                GROUPING_CHECK_APPLICATION_COMPLETED
                if committed.created
                else GROUPING_CHECK_APPLICATION_REUSED
            ),
            check_result=exact_result,
            quality_issues=exact_issues,
            execution=committed.execution,
        )

    def build_input(self, command: CheckGroupingCandidateCommand) -> GroupingCheckInput:
        """Resolve current persisted facts without evaluating or persisting a Check."""
        runtime_config_hash = _runtime_config_hash(command.runtime_config_json)
        _validate_command(command)
        candidate = self._repositories.grouping_snapshots.get(command.snapshot_id)
        if (
            candidate.project_id != self._project_id
            or candidate.page_id != command.page_id
        ):
            raise ValueError("Grouping check candidate Project/Page binding is invalid.")
        page = self._repositories.content_state.get_page(command.page_id)

        manifest_evidence = self._manifest_evidence(candidate)
        stored_detection_status, stored_detection_members = (
            self._stored_detection_members(candidate)
        )
        current_detection = self._current_detection(
            command.current_detection_dependency_id
        )
        current_ocr_status, current_ocr = self._current_ocr(candidate)
        current_profile = self._current_profile(command.current_profile_snapshot_id)
        source_status, source_artifact_id, source_sha256 = self._current_source(page)

        return GroupingCheckInput(
            project_id=self._project_id,
            page_id=command.page_id,
            candidate=_candidate_fact(candidate),
            stored_detection_resolution_status=stored_detection_status,
            stored_detection_member_ids=stored_detection_members,
            manifest_evidence=manifest_evidence,
            current=GroupingCurrentUsability(
                source_integrity_status=source_status,
                source_artifact_id=source_artifact_id,
                source_sha256=source_sha256,
                detection=current_detection,
                ocr_resolution_status=current_ocr_status,
                ocr_dependencies=current_ocr,
                profile=current_profile,
                expected_producer_name=command.expected_producer_name,
                expected_producer_version=command.expected_producer_version,
                expected_producer_implementation_hash=(
                    command.expected_producer_implementation_hash
                ),
                expected_operation_semantics_version=(
                    command.expected_operation_semantics_version
                ),
            ),
            completed_at=datetime.now(timezone.utc).isoformat(),
            runtime_config_hash=runtime_config_hash,
        )

    def _manifest_evidence(self, candidate) -> GroupingManifestEvidence:
        try:
            artifact = self._repositories.artifact_metadata.get_artifact(
                candidate.manifest_artifact_id
            )
        except LookupError:
            return GroupingManifestEvidence(
                integrity_status="missing",
                observed_sha256=None,
                canonical_sha256=None,
                metadata_matches_snapshot=False,
                manifest=None,
            )
        metadata_matches = (
            artifact.page_id == candidate.page_id
            and artifact.owner_type == "frozen_grouping_evidence_snapshot"
            and artifact.owner_id == candidate.snapshot_id
            and artifact.artifact_type == "frozen_grouping_evidence_manifest"
            and artifact.source_stage == "grouping"
            and artifact.mime_type == "application/json"
            and artifact.dependency_hash == candidate.dependency_fingerprint
            and artifact.file_hash == candidate.manifest_artifact_sha256
        )
        try:
            integrity = self._artifact_service.validate_artifact(
                artifact.artifact_id,
                expected_use="grouping_check_manifest",
            )
        except (ArtifactValidationError, LookupError):
            return GroupingManifestEvidence(
                integrity_status="inaccessible",
                observed_sha256=None,
                canonical_sha256=None,
                metadata_matches_snapshot=metadata_matches,
                manifest=None,
            )
        if integrity.integrity_status != "valid":
            status = (
                "missing"
                if integrity.integrity_status in {
                    "missing_path",
                    "deleted",
                    "moved_to_trash",
                    "metadata_only_cleaned",
                }
                else integrity.integrity_status
            )
            return GroupingManifestEvidence(
                integrity_status=status,
                observed_sha256=integrity.observed_hash,
                canonical_sha256=None,
                metadata_matches_snapshot=metadata_matches,
                manifest=None,
            )
        try:
            payload = self._artifact_service.read_artifact_bytes(
                artifact.artifact_id,
                expected_use="grouping_check_manifest",
            )
            manifest = json.loads(payload.decode("utf-8"))
            canonical_bytes = json.dumps(
                manifest,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (ArtifactValidationError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return GroupingManifestEvidence(
                integrity_status="malformed",
                observed_sha256=integrity.observed_hash,
                canonical_sha256=None,
                metadata_matches_snapshot=metadata_matches,
                manifest=None,
            )
        return GroupingManifestEvidence(
            integrity_status="valid",
            observed_sha256=sha256(payload).hexdigest(),
            canonical_sha256=sha256(canonical_bytes).hexdigest(),
            metadata_matches_snapshot=metadata_matches,
            manifest=manifest,
        )

    def _stored_detection_members(self, candidate) -> tuple[str, tuple[str, ...]]:
        try:
            detection = self._repositories.detection_evidence.get(
                candidate.detection_dependency_id
            )
        except (LookupError, ValueError):
            return "invalid", ()
        if (
            detection.project_id != candidate.project_id
            or detection.page_id != candidate.page_id
            or detection.canonical_manifest_sha256
            != candidate.detection_dependency_hash
        ):
            return "invalid", tuple(
                member.text_block_id for member in detection.members
            )
        return "valid", tuple(member.text_block_id for member in detection.members)

    def _current_detection(self, dependency_id: str) -> CurrentDetectionCheckBinding:
        try:
            detection = self._repositories.detection_evidence.get(dependency_id)
        except (LookupError, ValueError):
            return CurrentDetectionCheckBinding(
                resolution_status="invalid",
                dependency_id=dependency_id,
                dependency_hash=None,
                source_artifact_id=None,
                source_sha256=None,
            )
        return CurrentDetectionCheckBinding(
            resolution_status="valid",
            dependency_id=detection.detection_dependency_id,
            dependency_hash=detection.canonical_manifest_sha256,
            source_artifact_id=detection.source_artifact_id,
            source_sha256=detection.source_sha256,
            member_ids=tuple(member.text_block_id for member in detection.members),
        )

    def _current_ocr(self, candidate) -> tuple[str, tuple[GroupingCheckOcrBinding, ...]]:
        try:
            dependencies = self._repositories.result_versions.exact_active_ocr_dependencies(
                page_id=candidate.page_id,
                text_block_ids=tuple(
                    dependency.text_block_id
                    for dependency in candidate.ocr_dependencies
                ),
            )
        except ExactOcrDependenciesNotReadyError:
            return "not_ready", ()
        return "valid", tuple(
            GroupingCheckOcrBinding(
                text_block_id=item.text_block_id,
                ocr_result_id=item.ocr_result_id,
                version_number=item.version_number,
                text_hash=item.source_text_hash,
                geometry_hash=item.geometry_hash,
                input_hash=item.input_hash,
            )
            for item in dependencies
        )

    def _current_profile(self, profile_snapshot_id: str) -> CurrentProfileCheckBinding:
        try:
            profile = self._repositories.workflow_execution.get_profile_snapshot(
                profile_snapshot_id
            )
        except (LookupError, ValueError):
            return CurrentProfileCheckBinding(
                resolution_status="invalid",
                profile_snapshot_id=profile_snapshot_id,
                settings_hash=None,
            )
        return CurrentProfileCheckBinding(
            resolution_status="valid",
            profile_snapshot_id=profile.profile_snapshot_id,
            settings_hash=profile.settings_hash,
        )

    def _current_source(self, page) -> tuple[str, str | None, str | None]:
        try:
            artifact = self._repositories.artifact_metadata.get_artifact(
                page.original_artifact_id
            )
            integrity = self._artifact_service.validate_artifact(
                artifact.artifact_id,
                expected_use="grouping_check_source",
            )
        except (ArtifactValidationError, LookupError):
            return "invalid", page.original_artifact_id, None
        return integrity.integrity_status, artifact.artifact_id, artifact.file_hash

    def _register_evidence(
        self,
        page,
        evaluation: GroupingCheckEvaluation,
    ) -> ProcessingArtifactSnapshot:
        payload = grouping_check_evidence_bytes(evaluation)
        with TemporaryDirectory(prefix="grouping-check-evidence-") as temp_root:
            evidence_path = Path(temp_root) / "grouping-check-evidence.json"
            evidence_path.write_bytes(payload)
            artifact = self._artifact_service.register_stage_json(
                temp_path=evidence_path,
                batch_id=page.batch_id,
                page_id=page.page_id,
                owner_type="grouping_check_result",
                owner_id=evaluation.check_result.check_result_id,
                artifact_type="grouping_check_evidence",
                source_stage="grouping_check",
                retention_class="successful_payload",
                safety=ArtifactSafetyMetadata(),
                dependency_hash=evaluation.check_result.input_fingerprint,
            )
        if artifact.file_hash != sha256(payload).hexdigest():
            raise ValueError("Grouping check evidence ArtifactService hash is inconsistent.")
        return artifact


def _candidate_fact(candidate) -> GroupingCandidateCheckFact:
    return GroupingCandidateCheckFact(
        snapshot_id=candidate.snapshot_id,
        project_id=candidate.project_id,
        page_id=candidate.page_id,
        source_artifact_id=candidate.source_artifact_id,
        source_sha256=candidate.source_sha256,
        coordinate_space_json=candidate.coordinate_space_json,
        detection_dependency_id=candidate.detection_dependency_id,
        detection_dependency_hash=candidate.detection_dependency_hash,
        manifest_artifact_id=candidate.manifest_artifact_id,
        manifest_artifact_sha256=candidate.manifest_artifact_sha256,
        manifest_schema_version=candidate.manifest_schema_version,
        profile_snapshot_id=candidate.profile_snapshot_id,
        profile_settings_hash=candidate.profile_settings_hash,
        producer_name=candidate.producer_name,
        producer_version=candidate.producer_version,
        producer_implementation_hash=candidate.producer_implementation_hash,
        operation_semantics_version=candidate.operation_semantics_version,
        dependency_fingerprint=candidate.dependency_fingerprint,
        candidate_disposition=candidate.candidate_disposition,
        ocr_dependencies=tuple(
            GroupingCheckOcrBinding(
                text_block_id=item.text_block_id,
                ocr_result_id=item.ocr_result_id,
                version_number=item.ocr_version_number,
                text_hash=item.ocr_text_hash,
                geometry_hash=item.ocr_geometry_hash,
                input_hash=item.ocr_input_hash,
            )
            for item in candidate.ocr_dependencies
        ),
        generation_facts=tuple(
            GroupingCheckGenerationFact(
                generation_run_id=item.generation_run_id,
                outcome=item.outcome,
                materialization_status=item.materialization_status,
                snapshot_id=item.snapshot_id,
            )
            for item in candidate.generation_runs
        ),
    )


def _runtime_config_hash(runtime_config_json: str) -> str:
    try:
        value = json.loads(runtime_config_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Grouping check runtime configuration is malformed.") from exc
    if not isinstance(value, dict):
        raise ValueError("Grouping check runtime configuration must be an object.")
    canonical = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def _validate_command(command: CheckGroupingCandidateCommand) -> None:
    for name, value in (
        ("page_id", command.page_id),
        ("snapshot_id", command.snapshot_id),
        ("current_detection_dependency_id", command.current_detection_dependency_id),
        ("current_profile_snapshot_id", command.current_profile_snapshot_id),
        ("expected_producer_name", command.expected_producer_name),
        ("expected_producer_version", command.expected_producer_version),
        (
            "expected_operation_semantics_version",
            command.expected_operation_semantics_version,
        ),
    ):
        if not value:
            raise ValueError(f"Grouping check command {name} is required.")
    if (
        len(command.expected_producer_implementation_hash) != 64
        or any(
            character not in "0123456789abcdef"
            for character in command.expected_producer_implementation_hash
        )
    ):
        raise ValueError("Grouping check expected producer hash is invalid.")
