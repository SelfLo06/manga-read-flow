from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from manga_read_flow.domain.artifacts import ArtifactSafetyMetadata, ProcessingArtifactSnapshot
from manga_read_flow.domain.grouping import (
    GROUPING_OUTCOME_ABSTAINED,
    GROUPING_OUTCOME_FAILED,
    GROUPING_OUTCOME_SUCCEEDED,
    GroupingInputFragment,
    GroupingProducer,
    GroupingProducerInput,
    GroupingProducerResult,
    canonicalize_grouping_manifest,
)
from manga_read_flow.persistence.content_state_repository import (
    ExactOcrDependenciesNotReadyError,
)
from manga_read_flow.persistence.grouping_snapshot_repository import (
    FrozenGroupingEvidenceSnapshot,
    FrozenGroupingEvidenceSnapshotDraft,
    GroupingGenerationRunDraft,
    GroupingSnapshotOcrDependencyDraft,
)


GROUPING_APPLICATION_MATERIALIZED = "MATERIALIZED_CANDIDATE"
GROUPING_APPLICATION_REUSED = "REUSED_EXISTING_CANDIDATE"
GROUPING_APPLICATION_ABSTAINED = "ABSTAINED"
GROUPING_APPLICATION_FAILED = "FAILED"


@dataclass(frozen=True)
class MaterializeGroupingCandidateCommand:
    page_id: str
    detection_dependency_id: str
    profile_snapshot_id: str
    operation_semantics_version: str
    generation_run_id: str | None = None


@dataclass(frozen=True)
class MaterializeGroupingCandidateResult:
    status: str
    generation_run_id: str
    snapshot: FrozenGroupingEvidenceSnapshot | None
    reason_codes: tuple[str, ...] = ()
    error_code: str | None = None


class GroupingCandidateCommitError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        manifest_artifact: ProcessingArtifactSnapshot,
    ) -> None:
        super().__init__(message)
        self.manifest_artifact = manifest_artifact


class GroupingCandidateApplicationService:
    """Materialize immutable Grouping candidates; no Check or acceptance authority."""

    def __init__(
        self,
        *,
        project_id: str,
        repositories,
        artifact_service,
        producer: GroupingProducer,
    ) -> None:
        self._project_id = project_id
        self._repositories = repositories
        self._artifact_service = artifact_service
        self._producer = producer

    def materialize(
        self,
        command: MaterializeGroupingCandidateCommand,
    ) -> MaterializeGroupingCandidateResult:
        generation_run_id = command.generation_run_id or f"grouping-run-{uuid4()}"
        identity = self._producer.identity
        if (
            not command.operation_semantics_version
            or not identity.producer_name
            or not identity.producer_version
            or not _is_sha256(identity.implementation_hash)
        ):
            raise ValueError("Grouping producer/operation identity is invalid.")
        page = self._repositories.content_state.get_page(command.page_id)
        detection = self._repositories.detection_evidence.get(
            command.detection_dependency_id
        )
        if detection.project_id != self._project_id or detection.page_id != page.page_id:
            raise ValueError("Grouping Detection dependency Project/Page is invalid.")
        if detection.source_artifact_id != page.original_artifact_id:
            raise ValueError("Grouping Detection dependency source is not the Page original.")
        profile = self._repositories.workflow_execution.get_profile_snapshot(
            command.profile_snapshot_id
        )
        source_bytes = self._artifact_service.read_artifact_bytes(
            detection.source_artifact_id,
            expected_use="grouping_source",
        )
        detection_manifest = self._artifact_service.read_json_artifact(
            detection.manifest_artifact_id,
            expected_use="grouping_detection_dependency",
        )
        detection_fragments = _validated_detection_fragments(
            detection_manifest,
            detection=detection,
        )
        if not detection_fragments:
            reasons = ("no_detection_fragments",)
            self._record_no_candidate(
                generation_run_id=generation_run_id,
                command=command,
                outcome=GROUPING_OUTCOME_ABSTAINED,
                reason_codes=reasons,
            )
            return MaterializeGroupingCandidateResult(
                status=GROUPING_APPLICATION_ABSTAINED,
                generation_run_id=generation_run_id,
                snapshot=None,
                reason_codes=reasons,
            )

        try:
            ocr_dependencies = (
                self._repositories.result_versions.exact_active_ocr_dependencies(
                    page_id=page.page_id,
                    text_block_ids=tuple(
                        member.text_block_id for member in detection.members
                    ),
                )
            )
        except ExactOcrDependenciesNotReadyError:
            return self._input_not_ready_result(generation_run_id, command)

        ocr_by_block = {item.text_block_id: item for item in ocr_dependencies}
        try:
            producer_input = GroupingProducerInput(
                project_id=self._project_id,
                page_id=page.page_id,
                source_artifact_id=detection.source_artifact_id,
                source_bytes=source_bytes,
                source_sha256=detection.source_sha256,
                coordinate_space_json=detection.coordinate_space_json,
                detection_dependency_id=detection.detection_dependency_id,
                detection_dependency_hash=detection.canonical_manifest_sha256,
                profile_snapshot_id=profile.profile_snapshot_id,
                profile_settings_json=profile.settings_json,
                profile_settings_hash=profile.settings_hash,
                producer=self._producer.identity,
                operation_semantics_version=command.operation_semantics_version,
                fragments=tuple(
                    _producer_input_fragment(
                        fragment,
                        ocr_by_block[fragment["text_block_id"]],
                    )
                    for fragment in detection_fragments
                ),
            )
        except ExactOcrDependenciesNotReadyError:
            return self._input_not_ready_result(generation_run_id, command)
        try:
            producer_result = self._producer.produce(producer_input)
        except Exception:
            return self._failed_result(
                generation_run_id=generation_run_id,
                command=command,
                reason_codes=("producer_exception",),
                error_code="GROUPING_PRODUCER_EXCEPTION",
            )
        if not isinstance(producer_result, GroupingProducerResult):
            return self._invalid_output_result(generation_run_id, command)

        if producer_result.outcome == GROUPING_OUTCOME_ABSTAINED:
            if producer_result.candidate is not None or not producer_result.reason_codes:
                return self._invalid_output_result(generation_run_id, command)
            self._record_no_candidate(
                generation_run_id=generation_run_id,
                command=command,
                outcome=GROUPING_OUTCOME_ABSTAINED,
                reason_codes=producer_result.reason_codes,
            )
            return MaterializeGroupingCandidateResult(
                status=GROUPING_APPLICATION_ABSTAINED,
                generation_run_id=generation_run_id,
                snapshot=None,
                reason_codes=producer_result.reason_codes,
            )
        if producer_result.outcome == GROUPING_OUTCOME_FAILED:
            if producer_result.candidate is not None or not producer_result.reason_codes:
                return self._invalid_output_result(generation_run_id, command)
            return self._failed_result(
                generation_run_id=generation_run_id,
                command=command,
                reason_codes=producer_result.reason_codes,
                error_code=producer_result.error_code or "GROUPING_PRODUCER_FAILED",
            )
        if (
            producer_result.outcome != GROUPING_OUTCOME_SUCCEEDED
            or producer_result.candidate is None
        ):
            return self._invalid_output_result(generation_run_id, command)

        try:
            canonical = canonicalize_grouping_manifest(
                producer_input,
                producer_result.candidate,
            )
        except (ValueError, TypeError, AttributeError):
            return self._invalid_output_result(generation_run_id, command)

        existing = self._repositories.grouping_snapshots.get_optional(
            canonical.snapshot_id
        )
        if existing is None:
            try:
                with TemporaryDirectory(prefix="grouping-manifest-") as temp_root:
                    manifest_path = Path(temp_root) / "frozen-grouping-evidence-manifest.json"
                    manifest_path.write_bytes(canonical.canonical_bytes)
                    manifest_artifact = self._artifact_service.register_stage_json(
                        temp_path=manifest_path,
                        batch_id=page.batch_id,
                        page_id=page.page_id,
                        owner_type="frozen_grouping_evidence_snapshot",
                        owner_id=canonical.snapshot_id,
                        artifact_type="frozen_grouping_evidence_manifest",
                        source_stage="grouping",
                        retention_class="successful_payload",
                        safety=ArtifactSafetyMetadata(may_contain_ocr_text=True),
                        dependency_hash=canonical.dependency_fingerprint,
                    )
            except Exception:
                return self._failed_result(
                    generation_run_id=generation_run_id,
                    command=command,
                    reason_codes=("manifest_registration_failed",),
                    error_code="GROUPING_MANIFEST_REGISTRATION_FAILED",
                )
            if manifest_artifact.file_hash != canonical.canonical_manifest_sha256:
                raise ValueError("Grouping manifest ArtifactService hash is inconsistent.")
            manifest_artifact_id = manifest_artifact.artifact_id
            anticipated_status = "MATERIALIZED"
        else:
            if (
                existing.manifest_artifact_sha256
                != canonical.canonical_manifest_sha256
                or existing.dependency_fingerprint
                != canonical.dependency_fingerprint
            ):
                raise ValueError("Existing Grouping candidate identity is inconsistent.")
            self._artifact_service.read_json_artifact(
                existing.manifest_artifact_id,
                expected_use="grouping_candidate_reuse",
            )
            manifest_artifact_id = existing.manifest_artifact_id
            manifest_artifact = self._repositories.artifact_metadata.get_artifact(
                manifest_artifact_id
            )
            anticipated_status = "REUSED"

        snapshot_draft = FrozenGroupingEvidenceSnapshotDraft(
            snapshot_id=canonical.snapshot_id,
            project_id=self._project_id,
            page_id=page.page_id,
            source_artifact_id=detection.source_artifact_id,
            source_sha256=detection.source_sha256,
            coordinate_space_json=detection.coordinate_space_json,
            detection_dependency_id=detection.detection_dependency_id,
            detection_dependency_hash=detection.canonical_manifest_sha256,
            manifest_artifact_id=manifest_artifact_id,
            manifest_artifact_sha256=canonical.canonical_manifest_sha256,
            manifest_schema_version=canonical.schema_version,
            profile_snapshot_id=profile.profile_snapshot_id,
            profile_settings_hash=profile.settings_hash,
            producer_name=self._producer.identity.producer_name,
            producer_version=self._producer.identity.producer_version,
            producer_implementation_hash=self._producer.identity.implementation_hash,
            operation_semantics_version=command.operation_semantics_version,
            dependency_fingerprint=canonical.dependency_fingerprint,
            candidate_disposition=canonical.candidate_disposition,
            ocr_dependency_count=len(ocr_dependencies),
        )
        dependency_drafts = tuple(
            GroupingSnapshotOcrDependencyDraft(
                text_block_id=item.text_block_id,
                ocr_result_id=item.ocr_result_id,
                ocr_version_number=item.version_number,
                ocr_text_hash=item.source_text_hash,
                ocr_geometry_hash=item.geometry_hash,
                ocr_input_hash=item.input_hash,
            )
            for item in ocr_dependencies
        )
        generation_run = self._generation_run(
            generation_run_id=generation_run_id,
            command=command,
            outcome=GROUPING_OUTCOME_SUCCEEDED,
            materialization_status=anticipated_status,
            snapshot_id=canonical.snapshot_id,
        )
        try:
            materialized = self._repositories.uow.materialize_grouping_candidate(
                snapshot=snapshot_draft,
                ocr_dependencies=dependency_drafts,
                generation_run=generation_run,
            )
        except Exception as exc:
            raise GroupingCandidateCommitError(
                "Grouping manifest was registered, but candidate state did not commit.",
                manifest_artifact=manifest_artifact,
            ) from exc

        exact = self._repositories.uow.get_frozen_grouping_evidence_snapshot(
            canonical.snapshot_id
        )
        self._artifact_service.read_json_artifact(
            exact.manifest_artifact_id,
            expected_use="grouping_candidate_exact_read",
        )
        return MaterializeGroupingCandidateResult(
            status=(
                GROUPING_APPLICATION_MATERIALIZED
                if materialized.created
                else GROUPING_APPLICATION_REUSED
            ),
            generation_run_id=generation_run_id,
            snapshot=exact,
        )

    def _invalid_output_result(
        self,
        generation_run_id: str,
        command: MaterializeGroupingCandidateCommand,
    ) -> MaterializeGroupingCandidateResult:
        return self._failed_result(
            generation_run_id=generation_run_id,
            command=command,
            reason_codes=("invalid_producer_output",),
            error_code="GROUPING_PRODUCER_OUTPUT_INVALID",
        )

    def _input_not_ready_result(
        self,
        generation_run_id: str,
        command: MaterializeGroupingCandidateCommand,
    ) -> MaterializeGroupingCandidateResult:
        reasons = ("exact_ocr_dependencies_not_ready",)
        self._record_no_candidate(
            generation_run_id=generation_run_id,
            command=command,
            outcome=GROUPING_OUTCOME_ABSTAINED,
            reason_codes=reasons,
        )
        return MaterializeGroupingCandidateResult(
            status=GROUPING_APPLICATION_ABSTAINED,
            generation_run_id=generation_run_id,
            snapshot=None,
            reason_codes=reasons,
        )

    def _failed_result(
        self,
        *,
        generation_run_id: str,
        command: MaterializeGroupingCandidateCommand,
        reason_codes: tuple[str, ...],
        error_code: str,
    ) -> MaterializeGroupingCandidateResult:
        self._record_no_candidate(
            generation_run_id=generation_run_id,
            command=command,
            outcome=GROUPING_OUTCOME_FAILED,
            reason_codes=reason_codes,
            error_code=error_code,
        )
        return MaterializeGroupingCandidateResult(
            status=GROUPING_APPLICATION_FAILED,
            generation_run_id=generation_run_id,
            snapshot=None,
            reason_codes=reason_codes,
            error_code=error_code,
        )

    def _record_no_candidate(
        self,
        *,
        generation_run_id: str,
        command: MaterializeGroupingCandidateCommand,
        outcome: str,
        reason_codes: tuple[str, ...],
        error_code: str | None = None,
    ) -> None:
        self._repositories.uow.record_grouping_generation_outcome(
            self._generation_run(
                generation_run_id=generation_run_id,
                command=command,
                outcome=outcome,
                materialization_status="NO_CANDIDATE",
                reason_codes=reason_codes,
                error_code=error_code,
            )
        )

    def _generation_run(
        self,
        *,
        generation_run_id: str,
        command: MaterializeGroupingCandidateCommand,
        outcome: str,
        materialization_status: str,
        reason_codes: tuple[str, ...] = (),
        error_code: str | None = None,
        snapshot_id: str | None = None,
    ) -> GroupingGenerationRunDraft:
        identity = self._producer.identity
        return GroupingGenerationRunDraft(
            generation_run_id=generation_run_id,
            page_id=command.page_id,
            detection_dependency_id=command.detection_dependency_id,
            profile_snapshot_id=command.profile_snapshot_id,
            producer_name=identity.producer_name,
            producer_version=identity.producer_version,
            producer_implementation_hash=identity.implementation_hash,
            operation_semantics_version=command.operation_semantics_version,
            outcome=outcome,
            materialization_status=materialization_status,
            reason_codes=reason_codes,
            error_code=error_code,
            snapshot_id=snapshot_id,
        )


def _validated_detection_fragments(payload: object, *, detection) -> tuple[dict, ...]:
    if not isinstance(payload, dict):
        raise ValueError("Accepted Detection manifest must be a JSON object.")
    expected_header = {
        "schema_version": "accepted-detection-evidence-set.v1",
        "project_id": detection.project_id,
        "page_id": detection.page_id,
        "source_artifact_id": detection.source_artifact_id,
        "source_sha256": detection.source_sha256,
    }
    if any(payload.get(key) != value for key, value in expected_header.items()):
        raise ValueError("Accepted Detection manifest header is inconsistent.")
    if payload.get("coordinate_space") != json.loads(detection.coordinate_space_json):
        raise ValueError("Accepted Detection manifest coordinate space is inconsistent.")
    members = payload.get("members")
    if not isinstance(members, list) or len(members) != detection.canonical_member_count:
        raise ValueError("Accepted Detection manifest member count is inconsistent.")
    expected_ids = tuple(member.text_block_id for member in detection.members)
    actual_ids = tuple(
        member.get("text_block_id") if isinstance(member, dict) else None
        for member in members
    )
    if actual_ids != expected_ids:
        raise ValueError("Accepted Detection manifest exact membership is inconsistent.")
    canonical_bytes = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if sha256(canonical_bytes).hexdigest() != detection.canonical_manifest_sha256:
        raise ValueError("Accepted Detection manifest canonical hash is inconsistent.")
    validated = []
    coordinate_space = payload["coordinate_space"]
    for member in members:
        if (
            not isinstance(member, dict)
            or member.get("project_id") != detection.project_id
            or member.get("page_id") != detection.page_id
            or member.get("detection_status") != "done"
            or member.get("coordinate_space") != coordinate_space
            or not isinstance(member.get("bbox"), dict)
            or not isinstance(member.get("polygon"), list)
            or not isinstance(member.get("reading_order"), int)
            or not _is_sha256(member.get("geometry_hash"))
        ):
            raise ValueError("Accepted Detection manifest member is invalid.")
        validated.append(member)
    return tuple(validated)


def _producer_input_fragment(fragment: dict, ocr) -> GroupingInputFragment:
    if fragment["geometry_hash"] != ocr.geometry_hash:
        raise ExactOcrDependenciesNotReadyError(
            "Accepted OCR geometry does not match the Detection dependency."
        )
    if sha256(ocr.source_text.encode("utf-8")).hexdigest() != ocr.source_text_hash:
        raise ValueError("Accepted OCR text hash is inconsistent.")
    return GroupingInputFragment(
        fragment_id=fragment["text_block_id"],
        text_block_id=fragment["text_block_id"],
        reading_order=fragment["reading_order"],
        bbox_json=json.dumps(fragment["bbox"], ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        polygon_json=json.dumps(fragment["polygon"], ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        geometry_hash=fragment["geometry_hash"],
        coordinate_space_json=json.dumps(fragment["coordinate_space"], ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        ocr_result_id=ocr.ocr_result_id,
        ocr_version_number=ocr.version_number,
        ocr_text=ocr.source_text,
        ocr_text_hash=ocr.source_text_hash,
        ocr_geometry_hash=ocr.geometry_hash,
        ocr_input_hash=ocr.input_hash,
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
