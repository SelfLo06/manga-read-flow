from __future__ import annotations

import pytest

from manga_read_flow.application.full_page_cleaning_eligibility import (
    ELIGIBILITY_POLICY_VERSION,
    FullPageEligibilityInput,
    decide_full_page_cleaning_eligibility,
)


def test_old_e3_with_complete_pixel_safe_support_requires_review_not_e3():
    decision = decide_full_page_cleaning_eligibility(
        _input(historical_candidate_risk="E3")
    )

    assert decision.eligibility == "REVIEW"
    assert decision.reason_code == "pixel_level_evidence_requires_review"
    assert decision.evidence_summary["unsafe_required_pixels"] == 0
    assert decision.eligibility_decision_version == ELIGIBILITY_POLICY_VERSION


def test_pixel_guard_conflict_keeps_real_e3_blocker():
    decision = decide_full_page_cleaning_eligibility(
        _input(
            historical_candidate_risk="E3",
            safe_covered_required_pixels=800,
            required_protected_overlap_pixels=109,
            required_uncertainty_overlap_pixels=109,
            support_completeness="INCOMPLETE_REVIEW",
        )
    )

    assert decision.eligibility == "E3"
    assert decision.reason_code == "pixel_level_protected_or_uncertainty_conflict"


@pytest.mark.parametrize(
    ("target_class", "historical_candidate_risk"),
    [
        ("ordinary_dialogue", "E1"),
        ("narration", "E1"),
        ("sign_or_scene_text_review", "E1"),
        ("sfx_or_free_text", "E3"),
    ],
)
def test_target_class_is_an_explicit_policy_input(target_class, historical_candidate_risk):
    decision = decide_full_page_cleaning_eligibility(
        _input(target_class=target_class, historical_candidate_risk=historical_candidate_risk)
    )

    if target_class in {"sign_or_scene_text_review", "sfx_or_free_text"}:
        assert decision.eligibility == "REVIEW"
        assert decision.reason_code == "target_class_requires_review"
    else:
        assert decision.eligibility == "E1"


def test_decision_does_not_depend_on_case_identity():
    first = decide_full_page_cleaning_eligibility(_input())
    second = decide_full_page_cleaning_eligibility(
        _input(text_segment_revision_id="other-case::g003::v9")
    )

    assert first.eligibility == second.eligibility == "REVIEW"
    assert first.reason_code == second.reason_code


def _input(**changes) -> FullPageEligibilityInput:
    values = {
        "target_class": "ordinary_dialogue",
        "historical_candidate_risk": "E3",
        "required_pixels": 909,
        "safe_covered_required_pixels": 909,
        "required_protected_overlap_pixels": 0,
        "required_uncertainty_overlap_pixels": 0,
        "support_completeness": "COMPLETE",
        "bubble_instance_revision_id": "instance-revision::test",
        "text_segment_revision_id": "case-a::g003::v1",
        "evidence_source_revision": "spike-b-pixel-evidence-v0.7",
        "classifier_policy_version": "mvp1-spike-a-topology-eligibility-v1",
        "profile_identity": "profile::slice3",
        "config_identity": "config::slice3",
    }
    values.update(changes)
    return FullPageEligibilityInput(**values)
