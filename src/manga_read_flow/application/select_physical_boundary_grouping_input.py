from __future__ import annotations

from dataclasses import dataclass

from manga_read_flow.persistence.grouping_acceptance_repository import (
    GroupingBlockedError,
    GroupingDependencyMismatchError,
    GroupingStaleError,
    NoCurrentGroupingError,
)


@dataclass(frozen=True)
class SelectPhysicalBoundaryGroupingInputCommand:
    page_id: str
    current_detection_dependency_id: str
    current_profile_snapshot_id: str
    expected_grouping_producer_name: str
    expected_grouping_producer_version: str
    expected_grouping_producer_implementation_hash: str
    expected_grouping_operation_semantics_version: str


@dataclass(frozen=True)
class PhysicalBoundaryOcrInputBinding:
    text_block_id: str
    ocr_result_id: str
    version_number: int
    text_hash: str
    geometry_hash: str
    input_hash: str


@dataclass(frozen=True)
class PhysicalBoundaryGroupingInputBinding:
    project_id: str
    page_id: str
    grouping_acceptance_id: str
    grouping_check_result_id: str
    grouping_snapshot_id: str
    grouping_manifest_artifact_id: str
    grouping_manifest_sha256: str
    grouping_dependency_fingerprint: str
    source_artifact_id: str
    source_sha256: str
    coordinate_space_json: str
    detection_dependency_id: str
    detection_dependency_hash: str
    ocr_dependencies: tuple[PhysicalBoundaryOcrInputBinding, ...]
    profile_snapshot_id: str
    profile_settings_hash: str
    grouping_producer_name: str
    grouping_producer_version: str
    grouping_producer_implementation_hash: str
    grouping_operation_semantics_version: str


@dataclass(frozen=True)
class SelectPhysicalBoundaryGroupingInputResult:
    status: str
    binding: PhysicalBoundaryGroupingInputBinding | None
    error_code: str | None = None


class SelectPhysicalBoundaryGroupingInputApplicationService:
    """Select exact accepted/current Grouping input; never starts a producer."""

    def __init__(self, *, project_id: str, repositories, artifact_service) -> None:
        self._project_id = project_id
        self._repositories = repositories
        self._artifact_service = artifact_service

    def select(self, command: SelectPhysicalBoundaryGroupingInputCommand) -> SelectPhysicalBoundaryGroupingInputResult:
        try:
            current = self._repositories.grouping_acceptance.get_current(command.page_id)
        except NoCurrentGroupingError:
            return SelectPhysicalBoundaryGroupingInputResult("REJECTED", None, "NO_CURRENT_GROUPING")
        except GroupingStaleError:
            return SelectPhysicalBoundaryGroupingInputResult("REJECTED", None, "GROUPING_STALE")
        except GroupingDependencyMismatchError:
            return SelectPhysicalBoundaryGroupingInputResult("REJECTED", None, "GROUPING_DEPENDENCY_MISMATCH")
        except GroupingBlockedError:
            return SelectPhysicalBoundaryGroupingInputResult("REJECTED", None, "GROUPING_BLOCKED")
        except (LookupError, ValueError):
            return SelectPhysicalBoundaryGroupingInputResult(
                "REJECTED", None, "GROUPING_POINTER_CONFLICT"
            )
        snapshot = current.snapshot
        try:
            detection = self._repositories.detection_evidence.get(
                command.current_detection_dependency_id
            )
            profile = self._repositories.workflow_execution.get_profile_snapshot(
                command.current_profile_snapshot_id
            )
        except (LookupError, ValueError):
            return SelectPhysicalBoundaryGroupingInputResult(
                "REJECTED", None, "GROUPING_DEPENDENCY_MISMATCH"
            )
        expected = (
            snapshot.detection_dependency_id == detection.detection_dependency_id,
            snapshot.detection_dependency_hash == detection.canonical_manifest_sha256,
            snapshot.profile_snapshot_id == profile.profile_snapshot_id,
            snapshot.profile_settings_hash == profile.settings_hash,
            snapshot.producer_name == command.expected_grouping_producer_name,
            snapshot.producer_version == command.expected_grouping_producer_version,
            snapshot.producer_implementation_hash == command.expected_grouping_producer_implementation_hash,
            snapshot.operation_semantics_version == command.expected_grouping_operation_semantics_version,
        )
        if not all(expected):
            return SelectPhysicalBoundaryGroupingInputResult("REJECTED", None, "GROUPING_SELECTION_MISMATCH")
        try:
            source = self._artifact_service.validate_artifact(
                snapshot.source_artifact_id, expected_use="physical_boundary_grouping_source"
            )
            manifest = self._artifact_service.validate_artifact(
                snapshot.manifest_artifact_id, expected_use="physical_boundary_grouping_manifest"
            )
            detection_manifest = self._artifact_service.validate_artifact(
                detection.manifest_artifact_id,
                expected_use="physical_boundary_detection_dependency",
            )
        except (LookupError, ValueError):
            return SelectPhysicalBoundaryGroupingInputResult(
                "REJECTED", None, "GROUPING_ARTIFACT_INVALID"
            )
        if (
            source.integrity_status != "valid" or source.observed_hash != snapshot.source_sha256
            or manifest.integrity_status != "valid"
            or manifest.observed_hash != snapshot.manifest_artifact_sha256
            or detection_manifest.integrity_status != "valid"
            or detection_manifest.observed_hash != detection.canonical_manifest_sha256
        ):
            return SelectPhysicalBoundaryGroupingInputResult("REJECTED", None, "GROUPING_ARTIFACT_INVALID")
        binding = PhysicalBoundaryGroupingInputBinding(
            project_id=self._project_id, page_id=command.page_id,
            grouping_acceptance_id=current.acceptance.acceptance_id,
            grouping_check_result_id=current.acceptance.check_result_id,
            grouping_snapshot_id=snapshot.snapshot_id,
            grouping_manifest_artifact_id=snapshot.manifest_artifact_id,
            grouping_manifest_sha256=snapshot.manifest_artifact_sha256,
            grouping_dependency_fingerprint=snapshot.dependency_fingerprint,
            source_artifact_id=snapshot.source_artifact_id, source_sha256=snapshot.source_sha256,
            coordinate_space_json=snapshot.coordinate_space_json,
            detection_dependency_id=snapshot.detection_dependency_id,
            detection_dependency_hash=snapshot.detection_dependency_hash,
            ocr_dependencies=tuple(PhysicalBoundaryOcrInputBinding(
                text_block_id=item.text_block_id, ocr_result_id=item.ocr_result_id,
                version_number=item.ocr_version_number, text_hash=item.ocr_text_hash,
                geometry_hash=item.ocr_geometry_hash, input_hash=item.ocr_input_hash,
            ) for item in snapshot.ocr_dependencies),
            profile_snapshot_id=snapshot.profile_snapshot_id,
            profile_settings_hash=snapshot.profile_settings_hash,
            grouping_producer_name=snapshot.producer_name,
            grouping_producer_version=snapshot.producer_version,
            grouping_producer_implementation_hash=snapshot.producer_implementation_hash,
            grouping_operation_semantics_version=snapshot.operation_semantics_version,
        )
        return SelectPhysicalBoundaryGroupingInputResult("SELECTED", binding)
