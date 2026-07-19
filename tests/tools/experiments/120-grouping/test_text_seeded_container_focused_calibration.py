from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[4]
RUNNER_PATH = (
    ROOT
    / "tools"
    / "experiments"
    / "120-grouping"
    / "text_seeded_container_association"
    / "calibrate_focused_correction.py"
)


def load_runner(name: str = "text_seeded_container_focused_calibration_test"):
    spec = importlib.util.spec_from_file_location(name, RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_threshold_selection_requires_all_frozen_pairs_to_be_correct_and_decisive():
    runner = load_runner("focused_calibration_thresholds")
    scored = [
        {"asset_id": "cal-41", "label": "different", "score": 0.43},
        {"asset_id": "cal-44", "label": "same", "score": 0.82},
    ]

    selected = runner.select_thresholds(scored)["selected"]

    assert selected["false_merge_count"] == 0
    assert selected["false_split_count"] == 0
    assert selected["correct_decisive_count"] == 2
    assert selected["uncertain_count"] == 0
    assert selected["same"] - selected["different"] >= runner.MIN_ABSTENTION_GAP


def test_regionless_contract_rejects_a_nonnull_region():
    runner = load_runner("focused_calibration_regionless")
    region = runner.FOCUSED.RegionResult(
        region_id="r1",
        fragment_ids=("p1",),
        mask=np.ones((10, 10), dtype=np.bool_),
        container_type="free_text",
        confidence=0.0,
    )
    result = runner.FOCUSED.AssociationResult(
        asset_id="cal-45",
        method_id="P1-corrected-v1",
        regions=(region,),
        same_container_decisions=(),
        virtual_boundary=np.zeros((10, 10), dtype=np.bool_),
        recommended_decision="REVIEW_REQUIRED",
        abstention_reasons=("free_text_requires_review",),
        diagnostics={},
    )

    evaluation = runner.evaluate_contract(
        "cal-45", result, {"kind": "regionless_skip", "reason": "title_or_decoration_risk"}
    )

    assert evaluation["passed"] is False
    assert evaluation["failures"] == ["regionless_skip"]


def test_topology_contract_rejects_null_container_region():
    runner = load_runner("focused_calibration_null_container")
    region = runner.FOCUSED.RegionResult(
        region_id="r1",
        fragment_ids=("p1", "p2"),
        mask=None,
        container_type="uncertain",
        confidence=0.0,
    )
    result = runner.FOCUSED.AssociationResult(
        asset_id="cal-44",
        method_id="P1-corrected-v1",
        regions=(region,),
        same_container_decisions=(),
        virtual_boundary=np.zeros((10, 10), dtype=np.bool_),
        recommended_decision="SKIP",
        abstention_reasons=("regionless_support_area_limit",),
        diagnostics={},
    )

    evaluation = runner.evaluate_contract(
        "cal-44",
        result,
        {
            "kind": "exact_components",
            "components": [["p1", "p2"]],
            "require_nonnull_regions": True,
        },
    )

    assert evaluation["passed"] is False
    assert evaluation["failures"] == ["required_region_is_null"]


def test_prepared_policy_rejects_threshold_mismatch():
    runner = load_runner("focused_calibration_policy_mismatch")
    focused = runner.FOCUSED
    page = focused.PageInput(
        "cal-41",
        np.full((80, 80, 3), 255, dtype=np.uint8),
        (
            focused.Fragment("p1", (20, 15, 10, 40), ((20, 15), (30, 15), (30, 55), (20, 55)), "g1"),
        ),
    )
    prepared = focused.prepare_corrected_p1(
        page, focused.SameContainerThresholds(0.40, 0.75)
    )
    policy = focused.CorrectedP1Policy(
        thresholds=focused.SameContainerThresholds(0.45, 0.80),
        max_geodesic_cost=12.0,
        support_padding_scale=1.0,
        max_support_area_ratio=0.25,
        max_merged_support_area_ratio=0.50,
        regionless_uncertain_orientation=True,
        regionless_extreme_span_ratio=0.90,
        regionless_seed_bbox_area_ratio=0.20,
    )

    with pytest.raises(focused.HarnessStop, match="thresholds do not match"):
        focused.run_prepared_corrected_p1(prepared, policy)
