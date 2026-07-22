from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from hashlib import sha256
import inspect
import json

import pytest

from manga_read_flow.domain.grouping import (
    GROUPING_DISPOSITION_INCOMPLETE,
    GROUPING_DISPOSITION_PRODUCED,
    GROUPING_SNAPSHOT_ID_PREFIX,
    GroupingDependencyFingerprintInput,
    GroupingFingerprintOcrDependency,
    GroupingProducerIdentity,
    grouping_dependency_fingerprint_from_bindings,
)
from manga_read_flow.quality.grouping_check import (
    CurrentDetectionCheckBinding,
    CurrentProfileCheckBinding,
    GROUPING_COORDINATE_SPACE_MISMATCH,
    GROUPING_DANGLING_REFERENCE,
    GROUPING_DEPENDENCY_FINGERPRINT_MISMATCH,
    GROUPING_DETECTION_DEPENDENCY_MISMATCH,
    GROUPING_DUPLICATE_IDENTITY,
    GROUPING_DUPLICATE_MEMBERSHIP,
    GROUPING_EXTRA_FRAGMENT,
    GROUPING_INCOMPLETE_WITHOUT_EVIDENCE,
    GROUPING_INVALID_DISPOSITION,
    GROUPING_MANIFEST_HASH_MISMATCH,
    GROUPING_MANIFEST_MISSING,
    GROUPING_MISSING_FRAGMENT,
    GROUPING_OCR_DEPENDENCY_MISMATCH,
    GROUPING_PHYSICAL_BOUNDARY_FACT_PRESENT,
    GROUPING_PRODUCED_WITH_UNRESOLVED_BLOCKER,
    GROUPING_PROFILE_DEPENDENCY_MISMATCH,
    GROUPING_PROVENANCE_INCOMPLETE,
    GROUPING_SOURCE_BINDING_MISMATCH,
    GROUPING_UNRESOLVED_RELATION,
    GROUPING_UNSUPPORTED_SCHEMA,
    GroupingCandidateCheckFact,
    GroupingCheck,
    GroupingCheckGenerationFact,
    GroupingCheckInput,
    GroupingCheckOcrBinding,
    GroupingCheckResult,
    GroupingCurrentUsability,
    GroupingManifestEvidence,
)


def test_valid_produced_candidate_has_explainable_zero_metrics_and_no_issues():
    evaluation = GroupingCheck().evaluate(_valid_input())

    assert evaluation.issue_drafts == ()
    assert evaluation.findings == ()
    assert evaluation.check_result.metrics.fragment_count == 2
    assert evaluation.check_result.metrics.group_count == 1
    assert evaluation.check_result.metrics.membership_count == 2
    assert evaluation.check_result.metrics.dependency_mismatch_count == 0
    assert not hasattr(evaluation.check_result, "accepted")
    assert not hasattr(evaluation.check_result, "workflow_recommendation")


def test_valid_incomplete_candidate_persists_review_required_blocking_issue():
    check_input, manifest = _incomplete_input(disposition=GROUPING_DISPOSITION_INCOMPLETE)

    evaluation = GroupingCheck().evaluate(check_input)

    issue = next(
        item
        for item in evaluation.issue_drafts
        if item.issue_type == GROUPING_UNRESOLVED_RELATION
    )
    assert issue.severity == "warning"
    assert issue.is_blocking is True
    assert issue.root_stage == "grouping"
    assert issue.message_params == {"relation_id": "relation-1"}
    assert evaluation.check_result.metrics.unresolved_relation_count == 1
    assert manifest["candidate_disposition"] == GROUPING_DISPOSITION_INCOMPLETE


def test_produced_candidate_with_unresolved_fact_is_blocking():
    check_input, _ = _incomplete_input(disposition=GROUPING_DISPOSITION_PRODUCED)

    assert GROUPING_PRODUCED_WITH_UNRESOLVED_BLOCKER in _issue_types(check_input)


def test_source_artifact_mismatch_is_blocking():
    check_input = _valid_input()
    current = replace(
        check_input.current,
        source_artifact_id="artifact-other",
        source_sha256="f" * 64,
    )

    assert GROUPING_SOURCE_BINDING_MISMATCH in _issue_types(
        replace(check_input, current=current)
    )


def test_manifest_missing_is_blocking():
    check_input = _valid_input()
    evidence = replace(
        check_input.manifest_evidence,
        integrity_status="missing",
        observed_sha256=None,
        canonical_sha256=None,
        manifest=None,
    )

    assert GROUPING_MANIFEST_MISSING in _issue_types(
        replace(check_input, manifest_evidence=evidence)
    )


def test_manifest_hash_mismatch_is_blocking():
    check_input = _valid_input()
    evidence = replace(
        check_input.manifest_evidence,
        observed_sha256="f" * 64,
        canonical_sha256="f" * 64,
    )

    assert GROUPING_MANIFEST_HASH_MISMATCH in _issue_types(
        replace(check_input, manifest_evidence=evidence)
    )


def test_unsupported_schema_is_blocking():
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    manifest["schema_version"] = "frozen-grouping-evidence-manifest.v99"

    assert GROUPING_UNSUPPORTED_SCHEMA in _issue_types(
        _with_manifest(check_input, manifest)
    )


def test_detection_dependency_mismatch_is_blocking():
    check_input = _valid_input()
    current = replace(
        check_input.current,
        detection=CurrentDetectionCheckBinding(
            resolution_status="valid",
            dependency_id=f"detection-set-v1:{'e' * 64}",
            dependency_hash="e" * 64,
            source_artifact_id=check_input.candidate.source_artifact_id,
            source_sha256=check_input.candidate.source_sha256,
            member_ids=("tb-a", "tb-b"),
        ),
    )

    assert GROUPING_DETECTION_DEPENDENCY_MISMATCH in _issue_types(
        replace(check_input, current=current)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("ocr_result_id", "ocr-v2"),
        ("text_hash", "b" * 64),
        ("geometry_hash", "c" * 64),
    ],
)
def test_exact_ocr_identity_text_and_geometry_mismatch_are_blocking(field, value):
    check_input = _valid_input()
    first = replace(check_input.current.ocr_dependencies[0], **{field: value})
    current = replace(
        check_input.current,
        ocr_dependencies=(first, check_input.current.ocr_dependencies[1]),
    )

    assert GROUPING_OCR_DEPENDENCY_MISMATCH in _issue_types(
        replace(check_input, current=current)
    )


def test_profile_dependency_mismatch_is_blocking():
    check_input = _valid_input()
    current = replace(
        check_input.current,
        profile=CurrentProfileCheckBinding(
            resolution_status="valid",
            profile_snapshot_id="profile-v2",
            settings_hash="e" * 64,
        ),
    )

    assert GROUPING_PROFILE_DEPENDENCY_MISMATCH in _issue_types(
        replace(check_input, current=current)
    )


def test_dependency_fingerprint_mismatch_is_blocking():
    check_input = _valid_input()
    candidate = replace(
        check_input.candidate,
        snapshot_id=f"{GROUPING_SNAPSHOT_ID_PREFIX}{'f' * 64}",
        dependency_fingerprint="f" * 64,
        generation_facts=(
            replace(
                check_input.candidate.generation_facts[0],
                snapshot_id=f"{GROUPING_SNAPSHOT_ID_PREFIX}{'f' * 64}",
            ),
        ),
    )

    assert GROUPING_DEPENDENCY_FINGERPRINT_MISMATCH in _issue_types(
        replace(check_input, candidate=candidate)
    )


def test_missing_fragment_is_reported():
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    manifest["fragments"] = manifest["fragments"][:1]
    manifest["text_groups"][0]["ordered_fragment_ids"] = ["fragment-a"]

    assert GROUPING_MISSING_FRAGMENT in _issue_types(_with_manifest(check_input, manifest))


def test_extra_fragment_is_reported():
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    extra = deepcopy(manifest["fragments"][0])
    extra.update(fragment_id="fragment-extra", text_block_id="tb-extra")
    extra["ocr"].update(ocr_result_id="ocr-extra")
    manifest["fragments"].append(extra)

    assert GROUPING_EXTRA_FRAGMENT in _issue_types(_with_manifest(check_input, manifest))


@pytest.mark.parametrize("kind", ["fragment", "group", "relation"])
def test_dangling_fragment_group_and_relation_references_are_reported(kind):
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    if kind == "fragment":
        manifest["text_groups"][0]["ordered_fragment_ids"].append("missing-fragment")
    elif kind == "relation":
        manifest["text_groups"][0]["unresolved_relation_ids"] = ["missing-relation"]
    else:
        manifest["unresolved_relations"] = [
            {
                "affected_fragment_ids": [],
                "affected_group_ids": ["missing-group"],
                "reason_code": "uncertain",
                "relation_id": "relation-1",
                "supporting_evidence": {"kind": "test"},
            }
        ]

    assert GROUPING_DANGLING_REFERENCE in _issue_types(
        _with_manifest(check_input, manifest)
    )


def test_duplicate_identity_is_reported():
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    manifest["fragments"].append(deepcopy(manifest["fragments"][0]))

    assert GROUPING_DUPLICATE_IDENTITY in _issue_types(
        _with_manifest(check_input, manifest)
    )


def test_incompatible_duplicate_membership_is_reported():
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    manifest["text_groups"].append(
        {
            "group_id": "group-2",
            "group_order": 1,
            "membership_provenance": {"kind": "test"},
            "ordered_fragment_ids": ["fragment-a"],
            "ordering_metadata": {"basis": "m1"},
            "supporting_geometry_references": {},
            "unresolved_relation_ids": [],
        }
    )

    assert GROUPING_DUPLICATE_MEMBERSHIP in _issue_types(
        _with_manifest(check_input, manifest)
    )


def test_incomplete_provenance_is_reported():
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    manifest["fragments"][0]["membership_provenance"] = {}

    assert GROUPING_PROVENANCE_INCOMPLETE in _issue_types(
        _with_manifest(check_input, manifest)
    )


def test_missing_generation_outcome_provenance_is_reported():
    check_input = _valid_input()
    candidate = replace(check_input.candidate, generation_facts=())

    assert GROUPING_PROVENANCE_INCOMPLETE in _issue_types(
        replace(check_input, candidate=candidate)
    )


def test_coordinate_space_mismatch_is_reported():
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    manifest["fragments"][0]["coordinate_space"]["width"] = 99

    assert GROUPING_COORDINATE_SPACE_MISMATCH in _issue_types(
        _with_manifest(check_input, manifest)
    )


def test_physical_boundary_fact_is_reported():
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    manifest["text_groups"][0]["physical_boundary"] = {"closed": True}

    assert GROUPING_PHYSICAL_BOUNDARY_FACT_PRESENT in _issue_types(
        _with_manifest(check_input, manifest)
    )


def test_invalid_candidate_disposition_is_reported():
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    manifest["candidate_disposition"] = "ACCEPTED"
    invalid = _with_manifest(
        check_input,
        manifest,
        candidate_disposition="ACCEPTED",
    )

    assert GROUPING_INVALID_DISPOSITION in _issue_types(invalid)


def test_incomplete_without_explicit_evidence_is_reported():
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    manifest["candidate_disposition"] = GROUPING_DISPOSITION_INCOMPLETE

    assert GROUPING_INCOMPLETE_WITHOUT_EVIDENCE in _issue_types(
        _with_manifest(
            check_input,
            manifest,
            candidate_disposition=GROUPING_DISPOSITION_INCOMPLETE,
        )
    )


def test_grouping_check_is_state_neutral_and_has_no_producer_or_workflow_contract():
    check_input = _valid_input()
    original = deepcopy(check_input)

    evaluation = GroupingCheck().evaluate(check_input)
    check_source = inspect.getsource(GroupingCheck)
    result_fields = {field.name for field in fields(GroupingCheckResult)}

    assert check_input == original
    assert "produce(" not in check_source
    assert "repository" not in check_source.lower()
    assert "workflow" not in result_fields
    assert "accepted" not in result_fields
    assert "blocked" not in result_fields
    assert evaluation.check_result.finding_codes == ()


def _valid_input() -> GroupingCheckInput:
    coordinate = {"height": 24, "origin": "top_left", "width": 32}
    coordinate_json = _canonical_json(coordinate)
    ocr = (
        GroupingCheckOcrBinding("tb-a", "ocr-a", 1, "5" * 64, "7" * 64, "9" * 64),
        GroupingCheckOcrBinding("tb-b", "ocr-b", 1, "6" * 64, "8" * 64, "a" * 64),
    )
    fragments = [
        _fragment("fragment-a", "tb-a", "ocr-a", "5" * 64, "7" * 64, "9" * 64, coordinate),
        _fragment("fragment-b", "tb-b", "ocr-b", "6" * 64, "8" * 64, "a" * 64, coordinate),
    ]
    manifest = {
        "candidate_disposition": GROUPING_DISPOSITION_PRODUCED,
        "coordinate_space": coordinate,
        "detection_dependency": {
            "dependency_hash": "2" * 64,
            "dependency_id": f"detection-set-v1:{'2' * 64}",
        },
        "fragments": fragments,
        "ocr_dependencies": [
            {
                "geometry_hash": item.geometry_hash,
                "input_hash": item.input_hash,
                "ocr_result_id": item.ocr_result_id,
                "text_block_id": item.text_block_id,
                "text_hash": item.text_hash,
                "version_number": item.version_number,
            }
            for item in ocr
        ],
        "operation_semantics_version": "grouping-op.v1",
        "page_id": "page-1",
        "producer": {
            "implementation_hash": "4" * 64,
            "name": "producer",
            "version": "1",
        },
        "profile_snapshot": {
            "profile_snapshot_id": "profile-v1",
            "settings_hash": "3" * 64,
        },
        "project_id": "project-1",
        "schema_version": "frozen-grouping-evidence-manifest.v1",
        "source_artifact_id": "artifact-source",
        "source_sha256": "1" * 64,
        "text_groups": [
            {
                "group_id": "group-1",
                "group_order": 0,
                "membership_provenance": {"kind": "test"},
                "ordered_fragment_ids": ["fragment-a", "fragment-b"],
                "ordering_metadata": {"basis": "m1"},
                "supporting_geometry_references": {},
                "unresolved_relation_ids": [],
            }
        ],
        "unresolved_relations": [],
    }
    manifest_sha = sha256(_canonical_bytes(manifest)).hexdigest()
    fingerprint = _dependency_fingerprint(manifest_sha, coordinate_json, ocr)
    snapshot_id = f"{GROUPING_SNAPSHOT_ID_PREFIX}{fingerprint}"
    candidate = GroupingCandidateCheckFact(
        snapshot_id=snapshot_id,
        project_id="project-1",
        page_id="page-1",
        source_artifact_id="artifact-source",
        source_sha256="1" * 64,
        coordinate_space_json=coordinate_json,
        detection_dependency_id=f"detection-set-v1:{'2' * 64}",
        detection_dependency_hash="2" * 64,
        manifest_artifact_id="artifact-manifest",
        manifest_artifact_sha256=manifest_sha,
        manifest_schema_version="frozen-grouping-evidence-manifest.v1",
        profile_snapshot_id="profile-v1",
        profile_settings_hash="3" * 64,
        producer_name="producer",
        producer_version="1",
        producer_implementation_hash="4" * 64,
        operation_semantics_version="grouping-op.v1",
        dependency_fingerprint=fingerprint,
        candidate_disposition=GROUPING_DISPOSITION_PRODUCED,
        ocr_dependencies=ocr,
        generation_facts=(
            GroupingCheckGenerationFact(
                "run-1", "SUCCEEDED", "MATERIALIZED", snapshot_id
            ),
        ),
    )
    current = GroupingCurrentUsability(
        source_integrity_status="valid",
        source_artifact_id="artifact-source",
        source_sha256="1" * 64,
        detection=CurrentDetectionCheckBinding(
            resolution_status="valid",
            dependency_id=f"detection-set-v1:{'2' * 64}",
            dependency_hash="2" * 64,
            source_artifact_id="artifact-source",
            source_sha256="1" * 64,
            member_ids=("tb-a", "tb-b"),
        ),
        ocr_resolution_status="valid",
        ocr_dependencies=ocr,
        profile=CurrentProfileCheckBinding("valid", "profile-v1", "3" * 64),
        expected_producer_name="producer",
        expected_producer_version="1",
        expected_producer_implementation_hash="4" * 64,
        expected_operation_semantics_version="grouping-op.v1",
    )
    return GroupingCheckInput(
        project_id="project-1",
        page_id="page-1",
        candidate=candidate,
        stored_detection_resolution_status="valid",
        stored_detection_member_ids=("tb-a", "tb-b"),
        manifest_evidence=GroupingManifestEvidence(
            integrity_status="valid",
            observed_sha256=manifest_sha,
            canonical_sha256=manifest_sha,
            metadata_matches_snapshot=True,
            manifest=manifest,
        ),
        current=current,
        completed_at="2026-07-19T00:00:00+00:00",
        runtime_config_hash=sha256(b"{}").hexdigest(),
    )


def _incomplete_input(*, disposition: str):
    check_input = _valid_input()
    manifest = deepcopy(check_input.manifest_evidence.manifest)
    manifest["candidate_disposition"] = disposition
    manifest["text_groups"][0]["ordered_fragment_ids"] = ["fragment-a"]
    manifest["text_groups"][0]["unresolved_relation_ids"] = ["relation-1"]
    manifest["unresolved_relations"] = [
        {
            "affected_fragment_ids": ["fragment-b"],
            "affected_group_ids": [],
            "reason_code": "membership_uncertain",
            "relation_id": "relation-1",
            "supporting_evidence": {"kind": "test"},
        }
    ]
    return (
        _with_manifest(
            check_input,
            manifest,
            candidate_disposition=disposition,
        ),
        manifest,
    )


def _with_manifest(
    check_input: GroupingCheckInput,
    manifest: dict,
    *,
    candidate_disposition: str | None = None,
) -> GroupingCheckInput:
    manifest_sha = sha256(_canonical_bytes(manifest)).hexdigest()
    candidate = check_input.candidate
    fingerprint = _dependency_fingerprint(
        manifest_sha,
        candidate.coordinate_space_json,
        candidate.ocr_dependencies,
    )
    snapshot_id = f"{GROUPING_SNAPSHOT_ID_PREFIX}{fingerprint}"
    candidate = replace(
        candidate,
        snapshot_id=snapshot_id,
        manifest_artifact_sha256=manifest_sha,
        dependency_fingerprint=fingerprint,
        candidate_disposition=(
            candidate_disposition
            if candidate_disposition is not None
            else candidate.candidate_disposition
        ),
        generation_facts=(
            replace(candidate.generation_facts[0], snapshot_id=snapshot_id),
        ),
    )
    return replace(
        check_input,
        candidate=candidate,
        manifest_evidence=GroupingManifestEvidence(
            integrity_status="valid",
            observed_sha256=manifest_sha,
            canonical_sha256=manifest_sha,
            metadata_matches_snapshot=True,
            manifest=manifest,
        ),
    )


def _dependency_fingerprint(manifest_sha, coordinate_space_json, ocr):
    return grouping_dependency_fingerprint_from_bindings(
        input_data=GroupingDependencyFingerprintInput(
            source_artifact_id="artifact-source",
            source_sha256="1" * 64,
            coordinate_space_json=coordinate_space_json,
            detection_dependency_id=f"detection-set-v1:{'2' * 64}",
            detection_dependency_hash="2" * 64,
            profile_snapshot_id="profile-v1",
            profile_settings_hash="3" * 64,
            producer=GroupingProducerIdentity("producer", "1", "4" * 64),
            operation_semantics_version="grouping-op.v1",
            ocr_dependencies=tuple(
                GroupingFingerprintOcrDependency(
                    item.text_block_id,
                    item.ocr_result_id,
                    item.version_number,
                    item.text_hash,
                    item.geometry_hash,
                    item.input_hash,
                )
                for item in ocr
            ),
        ),
        canonical_manifest_sha256=manifest_sha,
    )


def _fragment(fragment_id, text_block_id, ocr_id, text_hash, geometry_hash, input_hash, coordinate):
    return {
        "bbox": {"height": 4, "width": 8, "x": 1, "y": 2},
        "coordinate_space": deepcopy(coordinate),
        "fragment_id": fragment_id,
        "geometry_hash": geometry_hash,
        "membership_provenance": {"kind": "test"},
        "ocr": {
            "geometry_hash": geometry_hash,
            "input_hash": input_hash,
            "ocr_result_id": ocr_id,
            "text_hash": text_hash,
            "version_number": 1,
        },
        "polygon": [],
        "reading_order": 0,
        "supporting_geometry_references": {},
        "text_block_id": text_block_id,
    }


def _issue_types(check_input):
    return {
        item.issue_type for item in GroupingCheck().evaluate(check_input).issue_drafts
    }


def _canonical_bytes(value):
    return _canonical_json(value).encode("utf-8")


def _canonical_json(value):
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
