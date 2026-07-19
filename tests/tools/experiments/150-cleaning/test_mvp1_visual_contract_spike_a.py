from __future__ import annotations

import copy

import pytest

from tools.experiments.cleaning_150.visual_contract import spike_a


@pytest.mark.parametrize(
    ("case_id", "expected_count"),
    [
        ("synthetic-contact-n3", 3),
        ("synthetic-multi-column", 1),
        ("synthetic-two-paragraphs", 1),
    ],
)
def test_topology_is_not_hardcoded_to_binary_or_one_segment_per_instance(case_id, expected_count):
    case = spike_a.synthetic_case(case_id)

    result = spike_a.analyze_page(case, spike_a.SpikeAPolicy())

    assert len(result["bubble_instances"]) == expected_count


def test_stable_relationships_do_not_depend_on_input_order():
    case = spike_a.synthetic_case("synthetic-contact-n3")
    reordered = copy.deepcopy(case)
    reordered["segments"].reverse()
    reordered["clusters"].reverse()

    first = spike_a.analyze_page(case, spike_a.SpikeAPolicy())
    second = spike_a.analyze_page(reordered, spike_a.SpikeAPolicy())

    assert spike_a.relationship_digest(first) == spike_a.relationship_digest(second)


def test_cluster_risk_is_not_broadcast_to_safe_member():
    result = spike_a.analyze_page(spike_a.synthetic_case("synthetic-mixed-risk"), spike_a.SpikeAPolicy())
    risks = {item["candidate_risk"] for item in result["eligibility_assessments"]}

    assert "E1" in risks
    assert len(risks) > 1
    assert all("cluster_risk" not in item for item in result["eligibility_assessments"])


def test_e2_e3_evidence_is_complete():
    result = spike_a.analyze_page(spike_a.synthetic_case("synthetic-mixed-risk"), spike_a.SpikeAPolicy())

    for assessment in result["eligibility_assessments"]:
        if assessment["candidate_risk"] in {"E2", "E3"}:
            assert assessment["reason_codes"]
            assert assessment["rules"]
            assert assessment["features"]
            assert assessment["threshold_version"]
            assert assessment["evidence"]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("deliberate_merge", "EXPECTED_DIFFERENT_SEGMENTS_MERGED"),
        ("deliberate_split", "EXPECTED_SAME_SEGMENTS_SPLIT"),
        ("deliberate_unassigned", "SEGMENT_DISPOSITION_INVALID"),
        ("deliberate_wrong_instance", "EXPECTED_ASSIGNMENT_MISMATCH"),
    ],
)
def test_deliberate_negatives_are_rejected(mutation, expected_code):
    snapshot, oracle = spike_a.synthetic_snapshot_and_oracle()
    mutated = spike_a.apply_deliberate_mutation(snapshot, mutation)

    result = spike_a.validate_snapshot(mutated, oracle)

    assert result["passed"] is False
    assert expected_code in result["failure_codes"]


def test_snapshot_declares_single_relationship_truth():
    snapshot, oracle = spike_a.synthetic_snapshot_and_oracle()

    result = spike_a.validate_snapshot(snapshot, oracle)

    assert result["passed"] is True
    assert snapshot["relationship_source"] == {
        "kind": "RUN_LOCAL_VISUAL_CONTRACT_SNAPSHOT",
        "exclusive_for_run": True,
    }
    forbidden = {"parent_bbox_mapping", "directory_order_mapping", "cluster_risk"}
    assert not forbidden.intersection(str(snapshot))


def test_gate_matrix_leaves_only_real_case_72_review_pending():
    snapshot, oracle = spike_a.synthetic_snapshot_and_oracle()
    validation = spike_a.validate_snapshot(snapshot, oracle)
    negatives = {
        "all_rejected": True,
        "results": [],
    }
    # Add real-shape IDs only for exercising the matrix; the real run supplies
    # the actual evidence and remains the authoritative gate result.
    case71 = copy.deepcopy(snapshot["pages"][0])
    case71["page_id"] = "case-71"
    case71["text_segments"] = [
        {"segment_id": "case-71__g002__s01"},
        {"segment_id": "case-71__g002__s02"},
    ]
    case71["bubble_instances"] = [
        {"instance_id": "a", "segment_ids": ["case-71__g002__s01"]},
        {"instance_id": "b", "segment_ids": ["case-71__g002__s02"]},
    ]
    case72 = copy.deepcopy(snapshot["pages"][0])
    case72["page_id"] = "case-72"
    snapshot["pages"].extend([case71, case72])

    matrix = spike_a._gate_matrix(snapshot, validation, negatives)

    assert matrix["automatic_pass_count"] == 9
    assert matrix["pending_human_count"] == 1
    assert matrix["fail_count"] == 0
