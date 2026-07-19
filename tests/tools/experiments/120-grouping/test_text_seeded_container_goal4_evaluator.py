from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
EVALUATOR_PATH = (
    ROOT
    / "tools"
    / "experiments"
    / "120-grouping"
    / "text_seeded_container_association"
    / "evaluate_goal4_r0.py"
)


def load_evaluator(name: str = "text_seeded_container_goal4_evaluator_test"):
    spec = importlib.util.spec_from_file_location(name, EVALUATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_not_text_regionless_skip_is_a_type_pass():
    evaluator = load_evaluator("goal4_evaluator_regionless")
    case = {
        "asset_id": "case-01",
        "expected_container_type": "not_text",
        "expected_container_count": 0,
        "expected_topology": "not_applicable",
        "target_fragment_groups": [],
        "excluded_or_false_seed_fragments": ["p1"],
        "required_safety_decisions": ["SKIP", "REVIEW_REQUIRED"],
    }
    result = {
        "method_id": "P1-corrected-v1",
        "recommended_decision": "SKIP",
        "abstention_reasons": ["regionless_uncertain_isolated_seed"],
        "regions": [
            {
                "region_id": "r1",
                "fragment_ids": ["p1"],
                "container_type": "uncertain",
                "mask_rle": None,
            }
        ],
    }

    record = evaluator.evaluate_result(case, result)

    assert record["container_type_assessment"] == "PASS"
    assert record["excluded_or_false_seed_nonnull_region_ids"] == []
    assert record["safety_decision_assessment"] == "PASS"


def test_missing_target_region_mask_cannot_pass_container_type():
    evaluator = load_evaluator("goal4_evaluator_missing_target")
    case = {
        "asset_id": "case-04",
        "expected_container_type": "free_text",
        "expected_container_count": 0,
        "expected_topology": "not_applicable",
        "target_fragment_groups": [["p1"], ["p2"]],
        "excluded_or_false_seed_fragments": [],
        "required_safety_decisions": ["SKIP", "REVIEW_REQUIRED"],
    }
    result = {
        "method_id": "P1-corrected-v1",
        "recommended_decision": "REVIEW_REQUIRED",
        "abstention_reasons": ["regionless_support_area_limit"],
        "regions": [
            {
                "region_id": "r1",
                "fragment_ids": ["p1"],
                "container_type": "free_text",
                "mask_rle": {"shape": [1, 1], "starts_with": 1, "counts": [1]},
            },
            {
                "region_id": "r2",
                "fragment_ids": ["p2"],
                "container_type": "uncertain",
                "mask_rle": None,
            },
        ],
    }

    record = evaluator.evaluate_result(case, result)

    assert record["target_region_availability_assessment"] == "FAIL"
    assert record["container_type_assessment"] == "FAIL"
