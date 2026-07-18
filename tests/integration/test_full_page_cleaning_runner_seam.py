"""Regression coverage for the real Slice 3 target-construction seam.

The frozen inputs are local evaluation evidence by design.  When they are not
available (for example a source-only checkout), this test is skipped rather
than replacing the real runner path with synthetic target injection.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "tools/mvp1/run_full_page_cleaning_slice3.py"


@pytest.fixture(scope="module")
def runner_module():
    spec = importlib.util.spec_from_file_location("slice3_runner_seam", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = module.IMAGE_ROOT / "case-72.webp"
    if not source.is_file():
        pytest.skip("Slice 3 frozen local case-72 evidence is unavailable.")
    return module


def test_case72_real_target_builder_uses_pixel_eligibility_and_formal_classes(
    runner_module, tmp_path
):
    page = runner_module._page_snapshot("case-72")
    targets, correction = runner_module._build_targets(
        "case-72",
        page,
        runner_module.IMAGE_ROOT / "case-72.webp",
        tmp_path,
    )
    by_segment = {target.text_segment_id: target for target in targets}

    g003 = by_segment["case-72__g003__s01"]
    assert correction is None
    assert g003.eligibility == "REVIEW"
    assert g003.disposition_code == "INCOMPLETE_REVIEW"
    assert g003.reason_code == "pixel_level_evidence_requires_review"
    assert not g003.is_composition_eligible

    # g002/g004 are not routed through the Slice F virtual-boundary planner.
    for segment_id in ("case-72__g002__s01", "case-72__g004__s01"):
        target = by_segment[segment_id]
        assert target.disposition_code == "BLOCKED_UNSAFE_REQUIRED"
        assert target.reason_code == "physical_boundary_capability_requires_review"
        assert not target.is_composition_eligible

    assert by_segment["case-72__g005__s01"].target_class == "sign_or_scene_text_review"
    for segment_id in ("case-72__g007__s01", "case-72__g007__s02"):
        target = by_segment[segment_id]
        assert target.target_class == "sfx_or_free_text"
        assert target.disposition_code == "UNSUPPORTED_FREE_TEXT"


def test_real_e3_and_case_independence_use_the_versioned_policy_interface():
    from manga_read_flow.application.full_page_cleaning_eligibility import (
        FullPageEligibilityInput,
        decide_full_page_cleaning_eligibility,
    )

    shared = {
        "target_class": "ordinary_dialogue",
        "historical_candidate_risk": "E3",
        "required_pixels": 909,
        "safe_covered_required_pixels": 800,
        "required_protected_overlap_pixels": 109,
        "required_uncertainty_overlap_pixels": 109,
        "support_completeness": "INCOMPLETE_REVIEW",
        "bubble_instance_revision_id": "instance-revision::same",
        "evidence_source_revision": "spike-b-pixel-evidence-v0.7",
        "classifier_policy_version": "mvp1-spike-a-topology-eligibility-v1",
        "profile_identity": "profile::slice3",
        "config_identity": "config::slice3",
    }
    first = decide_full_page_cleaning_eligibility(
        FullPageEligibilityInput(text_segment_revision_id="case-a::segment::v1", **shared)
    )
    second = decide_full_page_cleaning_eligibility(
        FullPageEligibilityInput(text_segment_revision_id="case-b::segment::v1", **shared)
    )

    assert first.eligibility == second.eligibility == "E3"
    assert first.reason_code == second.reason_code == "pixel_level_protected_or_uncertainty_conflict"


def test_checkpoint_case_does_not_request_a_human_form(runner_module):
    assert runner_module._requires_human_form("case-71")
    assert not runner_module._requires_human_form("case-72")
