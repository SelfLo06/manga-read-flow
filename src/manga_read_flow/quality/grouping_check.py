from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any

from manga_read_flow.domain.grouping import (
    GROUPING_DISPOSITION_INCOMPLETE,
    GROUPING_DISPOSITION_PRODUCED,
    GROUPING_MANIFEST_SCHEMA_VERSION,
    GroupingDependencyFingerprintInput,
    GroupingFingerprintOcrDependency,
    GroupingProducerIdentity,
    grouping_dependency_fingerprint_from_bindings,
)
from manga_read_flow.quality import IssueDraft


GROUPING_CHECK_NAME = "grouping_structural_check"
GROUPING_CHECK_VERSION = "grouping-check.v1"
GROUPING_CHECK_RESULT_ID_PREFIX = "grouping-check-result-v1:"
GROUPING_ROOT_STAGE = "grouping"

GROUPING_SOURCE_BINDING_MISMATCH = "grouping_source_binding_mismatch"
GROUPING_MANIFEST_MISSING = "grouping_manifest_missing"
GROUPING_MANIFEST_HASH_MISMATCH = "grouping_manifest_hash_mismatch"
GROUPING_UNSUPPORTED_SCHEMA = "grouping_unsupported_schema"
GROUPING_DETECTION_DEPENDENCY_MISMATCH = "grouping_detection_dependency_mismatch"
GROUPING_OCR_DEPENDENCY_MISMATCH = "grouping_ocr_dependency_mismatch"
GROUPING_PROFILE_DEPENDENCY_MISMATCH = "grouping_profile_dependency_mismatch"
GROUPING_DEPENDENCY_FINGERPRINT_MISMATCH = (
    "grouping_dependency_fingerprint_mismatch"
)
GROUPING_PRODUCER_COMPATIBILITY_MISMATCH = (
    "grouping_producer_compatibility_mismatch"
)
GROUPING_MISSING_FRAGMENT = "grouping_missing_fragment"
GROUPING_EXTRA_FRAGMENT = "grouping_extra_fragment"
GROUPING_DANGLING_REFERENCE = "grouping_dangling_reference"
GROUPING_DUPLICATE_IDENTITY = "grouping_duplicate_identity"
GROUPING_DUPLICATE_MEMBERSHIP = "grouping_duplicate_membership"
GROUPING_PROVENANCE_INCOMPLETE = "grouping_provenance_incomplete"
GROUPING_COORDINATE_SPACE_MISMATCH = "grouping_coordinate_space_mismatch"
GROUPING_UNRESOLVED_RELATION = "grouping_unresolved_relation"
GROUPING_INCOMPLETE_WITHOUT_EVIDENCE = "grouping_incomplete_without_evidence"
GROUPING_PRODUCED_WITH_UNRESOLVED_BLOCKER = (
    "grouping_produced_with_unresolved_blocker"
)
GROUPING_PHYSICAL_BOUNDARY_FACT_PRESENT = (
    "grouping_physical_boundary_fact_present"
)
GROUPING_INVALID_DISPOSITION = "grouping_invalid_disposition"

_PROHIBITED_FACT_TOKENS = (
    "bubble_instance",
    "bubble_interior",
    "cleaning_eligibility",
    "contact_boundary",
    "contact_region",
    "layout_slot",
    "page_truncation",
    "panel_boundary",
    "physical_boundary",
    "physical_container",
    "safe_edit",
    "separator",
    "visible_bubble_boundary",
)


@dataclass(frozen=True)
class GroupingCheckOcrBinding:
    text_block_id: str
    ocr_result_id: str
    version_number: int
    text_hash: str
    geometry_hash: str
    input_hash: str


@dataclass(frozen=True)
class GroupingCheckGenerationFact:
    generation_run_id: str
    outcome: str
    materialization_status: str
    snapshot_id: str | None


@dataclass(frozen=True)
class GroupingCandidateCheckFact:
    snapshot_id: str
    project_id: str
    page_id: str
    source_artifact_id: str
    source_sha256: str
    coordinate_space_json: str
    detection_dependency_id: str
    detection_dependency_hash: str
    manifest_artifact_id: str
    manifest_artifact_sha256: str
    manifest_schema_version: str
    profile_snapshot_id: str
    profile_settings_hash: str
    producer_name: str
    producer_version: str
    producer_implementation_hash: str
    operation_semantics_version: str
    dependency_fingerprint: str
    candidate_disposition: str
    ocr_dependencies: tuple[GroupingCheckOcrBinding, ...]
    generation_facts: tuple[GroupingCheckGenerationFact, ...]


@dataclass(frozen=True)
class GroupingManifestEvidence:
    integrity_status: str
    observed_sha256: str | None
    canonical_sha256: str | None
    metadata_matches_snapshot: bool
    manifest: object | None


@dataclass(frozen=True)
class CurrentDetectionCheckBinding:
    resolution_status: str
    dependency_id: str
    dependency_hash: str | None
    source_artifact_id: str | None
    source_sha256: str | None
    member_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CurrentProfileCheckBinding:
    resolution_status: str
    profile_snapshot_id: str
    settings_hash: str | None


@dataclass(frozen=True)
class GroupingCurrentUsability:
    source_integrity_status: str
    source_artifact_id: str | None
    source_sha256: str | None
    detection: CurrentDetectionCheckBinding
    ocr_resolution_status: str
    ocr_dependencies: tuple[GroupingCheckOcrBinding, ...]
    profile: CurrentProfileCheckBinding
    expected_producer_name: str
    expected_producer_version: str
    expected_producer_implementation_hash: str
    expected_operation_semantics_version: str


@dataclass(frozen=True)
class GroupingCheckInput:
    project_id: str
    page_id: str
    candidate: GroupingCandidateCheckFact
    stored_detection_resolution_status: str
    stored_detection_member_ids: tuple[str, ...]
    manifest_evidence: GroupingManifestEvidence
    current: GroupingCurrentUsability
    completed_at: str
    check_name: str = GROUPING_CHECK_NAME
    check_version: str = GROUPING_CHECK_VERSION
    runtime_config_hash: str = ""


@dataclass(frozen=True)
class GroupingCheckMetrics:
    fragment_count: int = 0
    group_count: int = 0
    membership_count: int = 0
    unresolved_relation_count: int = 0
    missing_fragment_count: int = 0
    extra_fragment_count: int = 0
    dangling_reference_count: int = 0
    duplicate_identity_count: int = 0
    incompatible_membership_count: int = 0
    missing_provenance_count: int = 0
    coordinate_mismatch_count: int = 0
    dependency_mismatch_count: int = 0
    prohibited_fact_count: int = 0
    artifact_integrity_failure_count: int = 0


@dataclass(frozen=True)
class GroupingCheckFinding:
    issue_type: str
    severity: str
    is_blocking: bool
    affected_type: str
    affected_id: str
    evidence: dict[str, object]
    message_key: str
    suggested_action_key: str


@dataclass(frozen=True)
class GroupingCheckResult:
    check_result_id: str
    project_id: str
    page_id: str
    snapshot_id: str
    check_name: str
    check_version: str
    input_fingerprint: str
    candidate_manifest_sha256: str
    candidate_dependency_fingerprint: str
    metrics: GroupingCheckMetrics
    finding_codes: tuple[str, ...]
    evidence_artifact_id: str | None
    evidence_artifact_sha256: str | None
    completed_at: str


@dataclass(frozen=True)
class GroupingCheckEvaluation:
    check_result: GroupingCheckResult
    findings: tuple[GroupingCheckFinding, ...]
    issue_drafts: tuple[IssueDraft, ...]


class GroupingCheck:
    """Oracle-free structural evaluation over immutable Grouping facts."""

    def evaluate(self, check_input: GroupingCheckInput) -> GroupingCheckEvaluation:
        input_fingerprint = grouping_check_input_fingerprint(check_input)
        check_result_id = f"{GROUPING_CHECK_RESULT_ID_PREFIX}{input_fingerprint}"
        counters = {field: 0 for field in GroupingCheckMetrics.__dataclass_fields__}
        findings: list[GroupingCheckFinding] = []
        finding_keys: set[tuple[str, str, str, str]] = set()

        def add(
            issue_type: str,
            *,
            evidence: dict[str, object],
            affected_type: str = "frozen_grouping_evidence_snapshot",
            affected_id: str | None = None,
            severity: str = "blocking",
            is_blocking: bool = True,
            message_key: str | None = None,
            suggested_action_key: str = "action.review_grouping_candidate",
        ) -> None:
            target_id = affected_id or check_input.candidate.snapshot_id
            evidence_identity = sha256(_canonical_json_bytes(evidence)).hexdigest()
            key = (issue_type, affected_type, target_id, evidence_identity)
            if key in finding_keys:
                return
            finding_keys.add(key)
            findings.append(
                GroupingCheckFinding(
                    issue_type=issue_type,
                    severity=severity,
                    is_blocking=is_blocking,
                    affected_type=affected_type,
                    affected_id=target_id,
                    evidence=evidence,
                    message_key=message_key or f"grouping.{issue_type}",
                    suggested_action_key=suggested_action_key,
                )
            )

        candidate = check_input.candidate
        self._check_candidate_bindings(check_input, counters, add)
        structure = self._check_manifest(check_input, counters, add)
        self._check_disposition(candidate, structure, counters, add)

        metrics = GroupingCheckMetrics(**counters)
        finding_codes = tuple(
            sorted({finding.issue_type for finding in findings}, key=_utf8_key)
        )
        result = GroupingCheckResult(
            check_result_id=check_result_id,
            project_id=check_input.project_id,
            page_id=check_input.page_id,
            snapshot_id=candidate.snapshot_id,
            check_name=check_input.check_name,
            check_version=check_input.check_version,
            input_fingerprint=input_fingerprint,
            candidate_manifest_sha256=candidate.manifest_artifact_sha256,
            candidate_dependency_fingerprint=candidate.dependency_fingerprint,
            metrics=metrics,
            finding_codes=finding_codes,
            evidence_artifact_id=None,
            evidence_artifact_sha256=None,
            completed_at=check_input.completed_at,
        )
        issue_drafts = tuple(
            _issue_draft(check_input, result, finding) for finding in findings
        )
        return GroupingCheckEvaluation(
            check_result=result,
            findings=tuple(findings),
            issue_drafts=issue_drafts,
        )

    def _check_candidate_bindings(self, check_input, counters, add) -> None:
        candidate = check_input.candidate
        current = check_input.current
        if candidate.project_id != check_input.project_id or candidate.page_id != check_input.page_id:
            add(
                GROUPING_SOURCE_BINDING_MISMATCH,
                evidence={
                    "candidate_project_id": candidate.project_id,
                    "candidate_page_id": candidate.page_id,
                    "expected_project_id": check_input.project_id,
                    "expected_page_id": check_input.page_id,
                },
            )
            counters["dependency_mismatch_count"] += 1
        if (
            current.source_integrity_status != "valid"
            or current.source_artifact_id != candidate.source_artifact_id
            or current.source_sha256 != candidate.source_sha256
        ):
            add(
                GROUPING_SOURCE_BINDING_MISMATCH,
                evidence={
                    "candidate_artifact_id": candidate.source_artifact_id,
                    "candidate_sha256": candidate.source_sha256,
                    "current_artifact_id": current.source_artifact_id,
                    "current_sha256": current.source_sha256,
                    "integrity_status": current.source_integrity_status,
                },
            )
            counters["dependency_mismatch_count"] += 1
            if current.source_integrity_status != "valid":
                counters["artifact_integrity_failure_count"] += 1

        detection = current.detection
        if (
            check_input.stored_detection_resolution_status != "valid"
            or detection.resolution_status != "valid"
            or detection.dependency_id != candidate.detection_dependency_id
            or detection.dependency_hash != candidate.detection_dependency_hash
            or detection.source_artifact_id != candidate.source_artifact_id
            or detection.source_sha256 != candidate.source_sha256
            or tuple(sorted(detection.member_ids, key=_utf8_key))
            != tuple(sorted(check_input.stored_detection_member_ids, key=_utf8_key))
        ):
            add(
                GROUPING_DETECTION_DEPENDENCY_MISMATCH,
                evidence={
                    "stored_resolution_status": check_input.stored_detection_resolution_status,
                    "candidate_dependency_id": candidate.detection_dependency_id,
                    "candidate_dependency_hash": candidate.detection_dependency_hash,
                    "current_resolution_status": detection.resolution_status,
                    "current_dependency_id": detection.dependency_id,
                    "current_dependency_hash": detection.dependency_hash,
                    "current_member_ids": list(detection.member_ids),
                    "stored_member_ids": list(check_input.stored_detection_member_ids),
                },
            )
            counters["dependency_mismatch_count"] += 1

        current_ocr = {item.text_block_id: item for item in current.ocr_dependencies}
        stored_ocr = {item.text_block_id: item for item in candidate.ocr_dependencies}
        ocr_mismatches: dict[str, list[str]] = {}
        if current.ocr_resolution_status != "valid" or set(current_ocr) != set(stored_ocr):
            ocr_mismatches["__set__"] = [current.ocr_resolution_status]
        for text_block_id, stored in stored_ocr.items():
            actual = current_ocr.get(text_block_id)
            if actual is None:
                ocr_mismatches[text_block_id] = ["missing"]
                continue
            fields = []
            for name in (
                "ocr_result_id",
                "version_number",
                "text_hash",
                "geometry_hash",
                "input_hash",
            ):
                if getattr(actual, name) != getattr(stored, name):
                    fields.append(name)
            if fields:
                ocr_mismatches[text_block_id] = fields
        if ocr_mismatches:
            add(
                GROUPING_OCR_DEPENDENCY_MISMATCH,
                evidence={"mismatches": ocr_mismatches},
            )
            counters["dependency_mismatch_count"] += len(ocr_mismatches)

        profile = current.profile
        if (
            profile.resolution_status != "valid"
            or profile.profile_snapshot_id != candidate.profile_snapshot_id
            or profile.settings_hash != candidate.profile_settings_hash
        ):
            add(
                GROUPING_PROFILE_DEPENDENCY_MISMATCH,
                evidence={
                    "candidate_profile_snapshot_id": candidate.profile_snapshot_id,
                    "candidate_settings_hash": candidate.profile_settings_hash,
                    "current_resolution_status": profile.resolution_status,
                    "current_profile_snapshot_id": profile.profile_snapshot_id,
                    "current_settings_hash": profile.settings_hash,
                },
            )
            counters["dependency_mismatch_count"] += 1

        producer_mismatches = [
            name
            for name, actual, expected in (
                ("producer_name", candidate.producer_name, current.expected_producer_name),
                ("producer_version", candidate.producer_version, current.expected_producer_version),
                (
                    "producer_implementation_hash",
                    candidate.producer_implementation_hash,
                    current.expected_producer_implementation_hash,
                ),
                (
                    "operation_semantics_version",
                    candidate.operation_semantics_version,
                    current.expected_operation_semantics_version,
                ),
            )
            if actual != expected
        ]
        if producer_mismatches:
            add(
                GROUPING_PRODUCER_COMPATIBILITY_MISMATCH,
                evidence={"mismatched_fields": producer_mismatches},
            )
            counters["dependency_mismatch_count"] += 1

        try:
            recomputed = grouping_dependency_fingerprint_from_bindings(
                input_data=GroupingDependencyFingerprintInput(
                    source_artifact_id=candidate.source_artifact_id,
                    source_sha256=candidate.source_sha256,
                    coordinate_space_json=candidate.coordinate_space_json,
                    detection_dependency_id=candidate.detection_dependency_id,
                    detection_dependency_hash=candidate.detection_dependency_hash,
                    profile_snapshot_id=candidate.profile_snapshot_id,
                    profile_settings_hash=candidate.profile_settings_hash,
                    producer=GroupingProducerIdentity(
                        producer_name=candidate.producer_name,
                        producer_version=candidate.producer_version,
                        implementation_hash=candidate.producer_implementation_hash,
                    ),
                    operation_semantics_version=candidate.operation_semantics_version,
                    ocr_dependencies=tuple(
                        GroupingFingerprintOcrDependency(
                            text_block_id=item.text_block_id,
                            ocr_result_id=item.ocr_result_id,
                            version_number=item.version_number,
                            text_hash=item.text_hash,
                            geometry_hash=item.geometry_hash,
                            input_hash=item.input_hash,
                        )
                        for item in candidate.ocr_dependencies
                    ),
                ),
                canonical_manifest_sha256=candidate.manifest_artifact_sha256,
            )
        except (TypeError, ValueError):
            recomputed = None
        if (
            recomputed != candidate.dependency_fingerprint
            or candidate.snapshot_id
            != f"grouping-snapshot-v1:{candidate.dependency_fingerprint}"
        ):
            add(
                GROUPING_DEPENDENCY_FINGERPRINT_MISMATCH,
                evidence={
                    "stored": candidate.dependency_fingerprint,
                    "recomputed": recomputed,
                    "snapshot_id": candidate.snapshot_id,
                },
            )
            counters["dependency_mismatch_count"] += 1

        if not any(
            fact.outcome == "SUCCEEDED"
            and fact.materialization_status in {"MATERIALIZED", "REUSED"}
            and fact.snapshot_id == candidate.snapshot_id
            for fact in candidate.generation_facts
        ):
            add(
                GROUPING_PROVENANCE_INCOMPLETE,
                evidence={"generation_outcome_binding": "missing"},
            )
            counters["missing_provenance_count"] += 1

    def _check_manifest(self, check_input, counters, add) -> dict[str, object]:
        candidate = check_input.candidate
        evidence = check_input.manifest_evidence
        if evidence.integrity_status == "missing":
            add(
                GROUPING_MANIFEST_MISSING,
                evidence={"artifact_id": candidate.manifest_artifact_id},
            )
            counters["artifact_integrity_failure_count"] += 1
        elif evidence.integrity_status != "valid":
            add(
                GROUPING_MANIFEST_HASH_MISMATCH,
                evidence={
                    "artifact_id": candidate.manifest_artifact_id,
                    "integrity_status": evidence.integrity_status,
                    "observed_sha256": evidence.observed_sha256,
                },
            )
            counters["artifact_integrity_failure_count"] += 1
        if (
            not evidence.metadata_matches_snapshot
            or evidence.observed_sha256 != candidate.manifest_artifact_sha256
            or evidence.canonical_sha256 != candidate.manifest_artifact_sha256
        ):
            add(
                GROUPING_MANIFEST_HASH_MISMATCH,
                evidence={
                    "stored_sha256": candidate.manifest_artifact_sha256,
                    "observed_sha256": evidence.observed_sha256,
                    "canonical_sha256": evidence.canonical_sha256,
                    "metadata_matches_snapshot": evidence.metadata_matches_snapshot,
                },
            )
            counters["artifact_integrity_failure_count"] += 1

        manifest = evidence.manifest
        if not isinstance(manifest, dict):
            if evidence.integrity_status != "missing":
                add(
                    GROUPING_UNSUPPORTED_SCHEMA,
                    evidence={"manifest_type": type(manifest).__name__},
                )
            return {"unresolved": False, "unassigned": False, "provenance_missing": False}

        if (
            candidate.manifest_schema_version != GROUPING_MANIFEST_SCHEMA_VERSION
            or manifest.get("schema_version") != GROUPING_MANIFEST_SCHEMA_VERSION
        ):
            add(
                GROUPING_UNSUPPORTED_SCHEMA,
                evidence={
                    "stored_schema": candidate.manifest_schema_version,
                    "manifest_schema": manifest.get("schema_version"),
                },
            )

        manifest_disposition = manifest.get("candidate_disposition")
        if (
            manifest_disposition not in {
                GROUPING_DISPOSITION_PRODUCED,
                GROUPING_DISPOSITION_INCOMPLETE,
            }
            or manifest_disposition != candidate.candidate_disposition
        ):
            add(
                GROUPING_INVALID_DISPOSITION,
                evidence={
                    "stored_disposition": candidate.candidate_disposition,
                    "manifest_disposition": manifest_disposition,
                },
            )

        header_mismatches = [
            name
            for name, actual, expected in (
                ("project_id", manifest.get("project_id"), candidate.project_id),
                ("page_id", manifest.get("page_id"), candidate.page_id),
                (
                    "source_artifact_id",
                    manifest.get("source_artifact_id"),
                    candidate.source_artifact_id,
                ),
                ("source_sha256", manifest.get("source_sha256"), candidate.source_sha256),
            )
            if actual != expected
        ]
        if header_mismatches:
            add(
                GROUPING_SOURCE_BINDING_MISMATCH,
                evidence={"manifest_header_mismatches": header_mismatches},
            )

        detection = manifest.get("detection_dependency")
        if not isinstance(detection, dict) or (
            detection.get("dependency_id") != candidate.detection_dependency_id
            or detection.get("dependency_hash") != candidate.detection_dependency_hash
        ):
            add(
                GROUPING_DETECTION_DEPENDENCY_MISMATCH,
                evidence={"manifest_detection_dependency": detection},
            )
            counters["dependency_mismatch_count"] += 1

        profile = manifest.get("profile_snapshot")
        if not isinstance(profile, dict) or (
            profile.get("profile_snapshot_id") != candidate.profile_snapshot_id
            or profile.get("settings_hash") != candidate.profile_settings_hash
        ):
            add(
                GROUPING_PROFILE_DEPENDENCY_MISMATCH,
                evidence={"manifest_profile_snapshot": profile},
            )
            counters["dependency_mismatch_count"] += 1

        manifest_producer = manifest.get("producer")
        if not isinstance(manifest_producer, dict) or any(
            manifest_producer.get(name) != expected
            for name, expected in (
                ("name", candidate.producer_name),
                ("version", candidate.producer_version),
                ("implementation_hash", candidate.producer_implementation_hash),
            )
        ) or manifest.get("operation_semantics_version") != (
            candidate.operation_semantics_version
        ):
            add(
                GROUPING_PROVENANCE_INCOMPLETE,
                evidence={
                    "manifest_producer": manifest_producer,
                    "manifest_operation_semantics_version": manifest.get(
                        "operation_semantics_version"
                    ),
                },
            )
            counters["missing_provenance_count"] += 1

        manifest_coordinate = manifest.get("coordinate_space")
        try:
            candidate_coordinate = json.loads(candidate.coordinate_space_json)
        except json.JSONDecodeError:
            candidate_coordinate = None
        if manifest_coordinate != candidate_coordinate:
            add(
                GROUPING_COORDINATE_SPACE_MISMATCH,
                evidence={"scope": "manifest_header"},
            )
            counters["coordinate_mismatch_count"] += 1

        prohibited = _prohibited_fact_paths(manifest)
        if prohibited:
            add(
                GROUPING_PHYSICAL_BOUNDARY_FACT_PRESENT,
                evidence={"paths": prohibited},
            )
            counters["prohibited_fact_count"] += len(prohibited)

        fragments = manifest.get("fragments")
        groups = manifest.get("text_groups")
        relations = manifest.get("unresolved_relations")
        fragments = fragments if isinstance(fragments, list) else []
        groups = groups if isinstance(groups, list) else []
        relations = relations if isinstance(relations, list) else []
        counters["fragment_count"] = len(fragments)
        counters["group_count"] = len(groups)
        counters["unresolved_relation_count"] = len(relations)

        fragment_ids = [item.get("fragment_id") for item in fragments if isinstance(item, dict)]
        text_block_ids = [item.get("text_block_id") for item in fragments if isinstance(item, dict)]
        duplicate_fragment_ids = _duplicates(fragment_ids)
        duplicate_text_block_ids = _duplicates(text_block_ids)
        if duplicate_fragment_ids or duplicate_text_block_ids:
            duplicates = sorted(
                {str(item) for item in duplicate_fragment_ids + duplicate_text_block_ids},
                key=_utf8_key,
            )
            add(
                GROUPING_DUPLICATE_IDENTITY,
                evidence={"fragment_or_text_block_ids": duplicates},
            )
            counters["duplicate_identity_count"] += len(duplicates)

        expected_members = set(check_input.stored_detection_member_ids)
        actual_members = {item for item in text_block_ids if isinstance(item, str)}
        missing = sorted(expected_members - actual_members, key=_utf8_key)
        extra = sorted(actual_members - expected_members, key=_utf8_key)
        if missing:
            add(GROUPING_MISSING_FRAGMENT, evidence={"text_block_ids": missing})
            counters["missing_fragment_count"] += len(missing)
        if extra:
            add(GROUPING_EXTRA_FRAGMENT, evidence={"text_block_ids": extra})
            counters["extra_fragment_count"] += len(extra)

        stored_ocr = {item.text_block_id: item for item in candidate.ocr_dependencies}
        manifest_ocr = manifest.get("ocr_dependencies")
        manifest_ocr = manifest_ocr if isinstance(manifest_ocr, list) else []
        top_level_ocr_mismatches = []
        seen_manifest_ocr: set[str] = set()
        for item in manifest_ocr:
            if not isinstance(item, dict) or not isinstance(item.get("text_block_id"), str):
                top_level_ocr_mismatches.append("invalid_entry")
                continue
            text_block_id = item["text_block_id"]
            if text_block_id in seen_manifest_ocr:
                top_level_ocr_mismatches.append(f"duplicate:{text_block_id}")
            seen_manifest_ocr.add(text_block_id)
            bound = stored_ocr.get(text_block_id)
            if bound is None or any(
                item.get(key) != expected
                for key, expected in (
                    ("ocr_result_id", bound.ocr_result_id if bound else None),
                    ("version_number", bound.version_number if bound else None),
                    ("text_hash", bound.text_hash if bound else None),
                    ("geometry_hash", bound.geometry_hash if bound else None),
                    ("input_hash", bound.input_hash if bound else None),
                )
            ):
                top_level_ocr_mismatches.append(text_block_id)
        if seen_manifest_ocr != set(stored_ocr):
            top_level_ocr_mismatches.append("membership")
        if top_level_ocr_mismatches:
            add(
                GROUPING_OCR_DEPENDENCY_MISMATCH,
                evidence={
                    "manifest_ocr_dependencies": sorted(
                        set(top_level_ocr_mismatches), key=_utf8_key
                    )
                },
            )
            counters["dependency_mismatch_count"] += len(
                set(top_level_ocr_mismatches)
            )
        provenance_missing = False
        coordinate_mismatches = []
        ocr_binding_mismatches = []
        for fragment in fragments:
            if not isinstance(fragment, dict):
                counters["missing_provenance_count"] += 1
                provenance_missing = True
                continue
            fragment_id = fragment.get("fragment_id")
            if not isinstance(fragment.get("membership_provenance"), dict) or not fragment.get(
                "membership_provenance"
            ):
                counters["missing_provenance_count"] += 1
                provenance_missing = True
            if fragment.get("coordinate_space") != candidate_coordinate:
                coordinate_mismatches.append(fragment_id)
            text_block_id = fragment.get("text_block_id")
            bound = stored_ocr.get(text_block_id)
            ocr = fragment.get("ocr")
            if bound is None or not isinstance(ocr, dict) or any(
                ocr.get(key) != expected
                for key, expected in (
                    ("ocr_result_id", bound.ocr_result_id if bound else None),
                    ("version_number", bound.version_number if bound else None),
                    ("text_hash", bound.text_hash if bound else None),
                    ("geometry_hash", bound.geometry_hash if bound else None),
                    ("input_hash", bound.input_hash if bound else None),
                )
            ):
                ocr_binding_mismatches.append(text_block_id)
        if provenance_missing:
            add(
                GROUPING_PROVENANCE_INCOMPLETE,
                evidence={"scope": "fragment"},
            )
        if coordinate_mismatches:
            add(
                GROUPING_COORDINATE_SPACE_MISMATCH,
                evidence={"fragment_ids": coordinate_mismatches},
            )
            counters["coordinate_mismatch_count"] += len(coordinate_mismatches)
        if ocr_binding_mismatches:
            add(
                GROUPING_OCR_DEPENDENCY_MISMATCH,
                evidence={"manifest_text_block_ids": ocr_binding_mismatches},
            )
            counters["dependency_mismatch_count"] += len(ocr_binding_mismatches)

        valid_fragment_ids = {item for item in fragment_ids if isinstance(item, str)}
        group_ids = [item.get("group_id") for item in groups if isinstance(item, dict)]
        relation_ids = [
            item.get("relation_id") for item in relations if isinstance(item, dict)
        ]
        duplicate_groups = _duplicates(group_ids)
        duplicate_relations = _duplicates(relation_ids)
        if duplicate_groups or duplicate_relations:
            duplicate_count = len(duplicate_groups) + len(duplicate_relations)
            add(
                GROUPING_DUPLICATE_IDENTITY,
                evidence={
                    "group_ids": duplicate_groups,
                    "relation_ids": duplicate_relations,
                },
            )
            counters["duplicate_identity_count"] += duplicate_count

        valid_group_ids = {item for item in group_ids if isinstance(item, str)}
        valid_relation_ids = {item for item in relation_ids if isinstance(item, str)}
        memberships: dict[str, str] = {}
        unresolved_fragment_ids: set[str] = set()
        dangling: list[str] = []
        duplicate_membership: list[str] = []
        group_orders = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_id = str(group.get("group_id"))
            group_orders.append(group.get("group_order"))
            if not isinstance(group.get("membership_provenance"), dict) or not group.get(
                "membership_provenance"
            ):
                counters["missing_provenance_count"] += 1
                provenance_missing = True
            if not isinstance(group.get("ordering_metadata"), dict) or not group.get(
                "ordering_metadata"
            ):
                counters["missing_provenance_count"] += 1
                provenance_missing = True
            ordered = group.get("ordered_fragment_ids")
            ordered = ordered if isinstance(ordered, list) else []
            counters["membership_count"] += len(ordered)
            for fragment_id in ordered:
                if fragment_id not in valid_fragment_ids:
                    dangling.append(f"group:{group_id}:fragment:{fragment_id}")
                    continue
                if fragment_id in memberships:
                    duplicate_membership.append(str(fragment_id))
                else:
                    memberships[str(fragment_id)] = group_id
            unresolved_refs = group.get("unresolved_relation_ids")
            unresolved_refs = unresolved_refs if isinstance(unresolved_refs, list) else []
            duplicate_unresolved_refs = _duplicates(unresolved_refs)
            if duplicate_unresolved_refs:
                add(
                    GROUPING_DUPLICATE_IDENTITY,
                    evidence={
                        "group_id": group_id,
                        "unresolved_relation_ids": duplicate_unresolved_refs,
                    },
                )
                counters["duplicate_identity_count"] += len(
                    duplicate_unresolved_refs
                )
            for relation_id in unresolved_refs:
                if relation_id not in valid_relation_ids:
                    dangling.append(f"group:{group_id}:relation:{relation_id}")

        if _duplicates(group_orders) or any(
            not isinstance(item, int) or isinstance(item, bool) or item < 0
            for item in group_orders
        ):
            dangling.append("group_order")

        for relation in relations:
            if not isinstance(relation, dict):
                continue
            relation_id = str(relation.get("relation_id"))
            if not isinstance(relation.get("supporting_evidence"), dict) or not relation.get(
                "supporting_evidence"
            ):
                counters["missing_provenance_count"] += 1
                provenance_missing = True
            affected_fragments = relation.get("affected_fragment_ids")
            affected_groups = relation.get("affected_group_ids")
            affected_fragments = (
                affected_fragments if isinstance(affected_fragments, list) else []
            )
            affected_groups = affected_groups if isinstance(affected_groups, list) else []
            duplicate_relation_refs = _duplicates(
                list(affected_fragments) + list(affected_groups)
            )
            if duplicate_relation_refs:
                add(
                    GROUPING_DUPLICATE_IDENTITY,
                    evidence={
                        "relation_id": relation_id,
                        "affected_ids": duplicate_relation_refs,
                    },
                )
                counters["duplicate_identity_count"] += len(
                    duplicate_relation_refs
                )
            if not affected_fragments and not affected_groups:
                dangling.append(f"relation:{relation_id}:no_affected_object")
            if not isinstance(relation.get("reason_code"), str) or not relation.get(
                "reason_code"
            ):
                counters["missing_provenance_count"] += 1
                provenance_missing = True
            for fragment_id in affected_fragments:
                if fragment_id not in valid_fragment_ids:
                    dangling.append(f"relation:{relation_id}:fragment:{fragment_id}")
                elif isinstance(fragment_id, str):
                    unresolved_fragment_ids.add(fragment_id)
            for group_id in affected_groups:
                if group_id not in valid_group_ids:
                    dangling.append(f"relation:{relation_id}:group:{group_id}")

        if dangling:
            add(
                GROUPING_DANGLING_REFERENCE,
                evidence={"references": sorted(set(dangling), key=_utf8_key)},
            )
            counters["dangling_reference_count"] += len(set(dangling))
        if duplicate_membership:
            add(
                GROUPING_DUPLICATE_MEMBERSHIP,
                evidence={
                    "fragment_ids": sorted(set(duplicate_membership), key=_utf8_key)
                },
            )
            counters["incompatible_membership_count"] += len(
                set(duplicate_membership)
            )
        if provenance_missing:
            add(
                GROUPING_PROVENANCE_INCOMPLETE,
                evidence={"scope": "manifest_structure"},
            )

        unassigned = valid_fragment_ids - set(memberships)
        silently_unassigned = unassigned - unresolved_fragment_ids
        if silently_unassigned:
            add(
                GROUPING_MISSING_FRAGMENT,
                evidence={
                    "unassigned_fragment_ids": sorted(silently_unassigned, key=_utf8_key)
                },
            )
            counters["missing_fragment_count"] += len(silently_unassigned)

        return {
            "unresolved": bool(relations or unassigned),
            "unassigned": bool(unassigned),
            "provenance_missing": provenance_missing,
            "relation_ids": tuple(
                sorted(valid_relation_ids, key=_utf8_key)
            ),
        }

    def _check_disposition(self, candidate, structure, counters, add) -> None:
        if candidate.candidate_disposition not in {
            GROUPING_DISPOSITION_PRODUCED,
            GROUPING_DISPOSITION_INCOMPLETE,
        }:
            add(
                GROUPING_INVALID_DISPOSITION,
                evidence={"candidate_disposition": candidate.candidate_disposition},
            )
            return
        unresolved = bool(structure.get("unresolved"))
        provenance_missing = bool(structure.get("provenance_missing"))
        if candidate.candidate_disposition == GROUPING_DISPOSITION_PRODUCED and (
            unresolved or provenance_missing
        ):
            add(
                GROUPING_PRODUCED_WITH_UNRESOLVED_BLOCKER,
                evidence={
                    "unresolved": unresolved,
                    "provenance_missing": provenance_missing,
                },
            )
        if candidate.candidate_disposition == GROUPING_DISPOSITION_INCOMPLETE:
            relation_ids = tuple(structure.get("relation_ids", ()))
            if not unresolved or not relation_ids:
                add(
                    GROUPING_INCOMPLETE_WITHOUT_EVIDENCE,
                    evidence={"relation_ids": list(relation_ids)},
                )
            else:
                for relation_id in relation_ids:
                    add(
                        GROUPING_UNRESOLVED_RELATION,
                        evidence={"relation_id": relation_id},
                        affected_type="grouping_unresolved_relation",
                        affected_id=relation_id,
                        severity="warning",
                        is_blocking=True,
                        suggested_action_key="action.review_grouping_relation",
                    )


def grouping_check_input_fingerprint(check_input: GroupingCheckInput) -> str:
    candidate = check_input.candidate
    current = check_input.current
    payload = {
        "candidate_dependency_fingerprint": candidate.dependency_fingerprint,
        "candidate_manifest_sha256": candidate.manifest_artifact_sha256,
        "check_name": check_input.check_name,
        "check_version": check_input.check_version,
        "current_dependencies": {
            "detection": asdict(current.detection),
            "expected_operation_semantics_version": (
                current.expected_operation_semantics_version
            ),
            "expected_producer": {
                "implementation_hash": current.expected_producer_implementation_hash,
                "name": current.expected_producer_name,
                "version": current.expected_producer_version,
            },
            "ocr_dependencies": [
                asdict(item)
                for item in sorted(
                    current.ocr_dependencies,
                    key=lambda item: _utf8_key(item.text_block_id),
                )
            ],
            "ocr_resolution_status": current.ocr_resolution_status,
            "profile": asdict(current.profile),
            "source_artifact_id": current.source_artifact_id,
            "source_integrity_status": current.source_integrity_status,
            "source_sha256": current.source_sha256,
        },
        "manifest_evidence": {
            "canonical_sha256": check_input.manifest_evidence.canonical_sha256,
            "integrity_status": check_input.manifest_evidence.integrity_status,
            "metadata_matches_snapshot": (
                check_input.manifest_evidence.metadata_matches_snapshot
            ),
            "observed_sha256": check_input.manifest_evidence.observed_sha256,
        },
        "runtime_config_hash": check_input.runtime_config_hash,
        "snapshot_id": candidate.snapshot_id,
        "stored_detection_member_ids": sorted(
            check_input.stored_detection_member_ids, key=_utf8_key
        ),
        "stored_detection_resolution_status": (
            check_input.stored_detection_resolution_status
        ),
    }
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def grouping_check_evidence_bytes(
    evaluation: GroupingCheckEvaluation,
) -> bytes:
    result = evaluation.check_result
    payload = {
        "check_name": result.check_name,
        "check_result_id": result.check_result_id,
        "check_version": result.check_version,
        "finding_codes": list(result.finding_codes),
        "findings": [
            {
                "affected_id": finding.affected_id,
                "affected_type": finding.affected_type,
                "evidence": finding.evidence,
                "is_blocking": finding.is_blocking,
                "issue_type": finding.issue_type,
                "severity": finding.severity,
            }
            for finding in evaluation.findings
        ],
        "input_fingerprint": result.input_fingerprint,
        "metrics": asdict(result.metrics),
        "schema_version": "grouping-check-evidence.v1",
        "snapshot_id": result.snapshot_id,
    }
    return _canonical_json_bytes(payload)


def _issue_draft(
    check_input: GroupingCheckInput,
    result: GroupingCheckResult,
    finding: GroupingCheckFinding,
) -> IssueDraft:
    evidence_identity = sha256(_canonical_json_bytes(finding.evidence)).hexdigest()
    dedupe_key = ":".join(
        (
            "grouping-check",
            result.snapshot_id,
            result.check_name,
            result.check_version,
            result.input_fingerprint,
            finding.issue_type,
            finding.affected_type,
            finding.affected_id,
            evidence_identity,
        )
    )
    return IssueDraft(
        target_type=finding.affected_type,
        target_id=finding.affected_id,
        page_id=result.page_id,
        discovered_stage=GROUPING_ROOT_STAGE,
        root_stage=GROUPING_ROOT_STAGE,
        issue_type=finding.issue_type,
        error_code=finding.issue_type,
        severity=finding.severity,
        is_blocking=finding.is_blocking,
        status="open",
        message_key=finding.message_key,
        suggested_action_key=finding.suggested_action_key,
        message_params=finding.evidence,
        related_artifact_id=check_input.candidate.manifest_artifact_id,
        applies_to_result_id=result.check_result_id,
        input_hash=result.input_fingerprint,
        config_hash=check_input.runtime_config_hash,
        dedupe_key=dedupe_key,
    )


def _duplicates(values: list[object]) -> list[object]:
    seen: set[object] = set()
    duplicates: list[object] = []
    for value in values:
        try:
            duplicate = value in seen
        except TypeError:
            value = json.dumps(value, sort_keys=True, default=str)
            duplicate = value in seen
        if duplicate and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _prohibited_fact_paths(value: object, path: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_").replace(" ", "_")
            child_path = f"{path}.{key}"
            if any(token in normalized for token in _PROHIBITED_FACT_TOKENS):
                paths.append(child_path)
            paths.extend(_prohibited_fact_paths(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_prohibited_fact_paths(item, f"{path}[{index}]"))
    return sorted(set(paths), key=_utf8_key)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _utf8_key(value: object) -> bytes:
    return str(value).encode("utf-8")
