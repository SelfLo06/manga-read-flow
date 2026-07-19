from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[4]
EVALUATOR_PATH = (
    ROOT_DIR
    / "tools"
    / "experiments"
    / "120-grouping"
    / "text_seeded_container_association"
    / "evaluate_r0_matrix.py"
)
R0_ROOT = (
    ROOT_DIR
    / "data"
    / "local"
    / "reviews"
    / "120-grouping"
    / "association-r0-blind-v0.3"
)
MATRIX_ROOT = R0_ROOT / "goal3-runs" / "goal3-r0-v0.1"
CONTRACT_PATH = R0_ROOT / "coordinator" / "GOAL3-EVALUATOR-CONTRACT.local.json"


def load_evaluator(name: str = "text_seeded_container_r0_evaluator"):
    spec = importlib.util.spec_from_file_location(name, EVALUATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_verifies_frozen_matrix_and_evaluator_contract_hashes():
    evaluator = load_evaluator()

    verified = evaluator.verify_inputs(MATRIX_ROOT, CONTRACT_PATH)

    assert verified["matrix_sha256"] == evaluator.EXPECTED_MATRIX_SHA256
    assert verified["contract_sha256"] == evaluator.EXPECTED_CONTRACT_SHA256
    assert len(verified["matrix"]["outputs"]) == 18
    assert verified["matrix"]["ground_truth_accessed"] is False


def test_topology_assessment_requires_integral_groups_and_expected_relation():
    evaluator = load_evaluator("text_seeded_container_r0_topology")
    regions = [
        {"region_id": "r1", "fragment_ids": ["a", "b"]},
        {"region_id": "r2", "fragment_ids": ["c", "d"]},
    ]

    same_fail = evaluator.assess_topology([["a", "b"], ["c", "d"]], "same_container", regions)
    different_pass = evaluator.assess_topology(
        [["a", "b"], ["c", "d"]], "different_containers", regions
    )

    assert same_fail["assessment"] == "FAIL"
    assert different_pass["assessment"] == "PASS"
    assert different_pass["target_region_count"] == 2


def test_actual_evaluation_is_topology_and_safety_only_not_pixel_accuracy():
    evaluator = load_evaluator("text_seeded_container_r0_actual_eval")

    payload = evaluator.evaluate_matrix(MATRIX_ROOT, CONTRACT_PATH)
    serialized = json.dumps(payload)

    assert len(payload["records"]) == 18
    assert {record["method_id"] for record in payload["records"]} == {"B0", "B1", "P1"}
    assert "pixel_accurate" not in serialized
    assert "boundary_f1" not in serialized
    assert "pixel_iou" not in serialized
    assert payload["limitations"]["coarse_reference_only"] is True
