from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from tools.spikes.text_seeded_container_association import calibrate_routed_association as calibration
from tools.spikes.text_seeded_container_association import evaluate_routed_association as evaluator
from tools.spikes.text_seeded_container_association import harness
from tools.spikes.text_seeded_container_association import routed_association as routed


def test_calibration_grid_never_contains_evaluation_specific_policy():
    policies = list(calibration.candidate_policies())

    assert len(policies) == 12
    assert {item.container_boundary_threshold for item in policies} == {0.45, 0.50, 0.55}
    assert {item.support_padding_scale for item in policies} == {0.15, 0.20}


def test_regionless_contract_rejects_nonempty_spatial_output():
    mask = np.zeros((20, 20), dtype=np.bool_)
    mask[5:15, 5:15] = True
    region = routed.SpatialRegion("r", ("p",), mask, {})
    result = routed.RoutedResult(
        "cal-99", "COARSE_CONTAINER_SEARCH", 0.9, ("p",), ("g",),
        (region,), (), "same", (), "REVIEW_REQUIRED", True, (), {},
    )

    checked = calibration.evaluate_contract(
        result,
        {"route": "REGIONLESS_ABSTENTION", "topology": "not_applicable", "container_count": 0},
    )

    assert checked["passed"] is False
    assert "route" in checked["failures"]


def test_evaluator_detects_forbidden_low_risk_decision(tmp_path):
    run_dir = tmp_path / "run"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    labels = {
        "labels": {
            "case-51": {"route": "COARSE_CONTAINER_SEARCH", "topology": "same", "container_count": 1},
            "case-52": {"route": "COARSE_CONTAINER_SEARCH", "topology": "different", "container_count": 2},
            "case-53": {"route": "BOUNDED_SUPPORT", "topology": "not_applicable", "container_count": 0},
            "case-54": {"route": "REGIONLESS_ABSTENTION", "topology": "not_applicable", "container_count": 0},
        }
    }
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(json.dumps(labels), encoding="utf-8")
    outputs = []
    fixtures = {
        "case-51": ("COARSE_CONTAINER_SEARCH", "same", [{}], None, True, "LOW_RISK"),
        "case-52": ("COARSE_CONTAINER_SEARCH", "different", [{}, {}], None, True, "REVIEW_REQUIRED"),
        "case-53": ("BOUNDED_SUPPORT", "not_applicable", None, [{"touches_roi_edge": False}], True, "REVIEW_REQUIRED"),
        "case-54": ("REGIONLESS_ABSTENTION", "not_applicable", None, None, False, "SKIP"),
    }
    for asset_id, (route, topology, regions, supports, eligible, decision) in fixtures.items():
        path = results_dir / f"{asset_id}.json"
        path.write_text(
            json.dumps(
                {
                    "route": route,
                    "topology": topology,
                    "container_regions_or_null": regions,
                    "support_regions_or_null": supports,
                    "goal6_trial_eligible": eligible,
                    "recommended_decision": decision,
                }
            ),
            encoding="utf-8",
        )
        outputs.append(
            {
                "asset_id": asset_id,
                "result_relative_path": f"results/{asset_id}.json",
                "result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    matrix_path = run_dir / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "outputs": outputs,
                "ground_truth_accessed": False,
                "evaluation_labels_accessed": False,
                "source_hashes_unchanged": True,
            }
        ),
        encoding="utf-8",
    )

    result = evaluator.evaluate(matrix_path, labels_path, tmp_path / "evaluation.json")

    assert result["false_low_risk_candidate_count"] == 1
    assert result["passed"] is False
    assert result["cases"][0]["failures"] == ["forbidden_decision"]


def test_evaluator_refuses_to_overwrite_existing_output(tmp_path):
    output = tmp_path / "evaluation.json"
    output.write_text("{}", encoding="utf-8")

    with pytest.raises(harness.HarnessStop, match="already exists"):
        evaluator.evaluate(tmp_path / "matrix.json", tmp_path / "labels.json", output)
