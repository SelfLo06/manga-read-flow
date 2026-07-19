from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest
from PIL import Image


MODULE_PATH = Path("tools/experiments/150-cleaning/page_edge_bubble_first_divergence/core.py")
SPEC = importlib.util.spec_from_file_location("page_edge_core", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
sys.modules["core"] = MODULE
SPEC.loader.exec_module(MODULE)

EVALUATOR_PATH = Path("tools/experiments/150-cleaning/page_edge_bubble_first_divergence/evaluator.py")
EVALUATOR_SPEC = importlib.util.spec_from_file_location("page_edge_evaluator", EVALUATOR_PATH)
assert EVALUATOR_SPEC and EVALUATOR_SPEC.loader
EVALUATOR = importlib.util.module_from_spec(EVALUATOR_SPEC)
sys.modules[EVALUATOR_SPEC.name] = EVALUATOR
EVALUATOR_SPEC.loader.exec_module(EVALUATOR)

ADAPTER_PATH = Path("tools/experiments/150-cleaning/page_edge_bubble_first_divergence/paddle_detection_adapter.py")
ADAPTER_SPEC = importlib.util.spec_from_file_location("paddle_detection_adapter", ADAPTER_PATH)
assert ADAPTER_SPEC and ADAPTER_SPEC.loader
ADAPTER = importlib.util.module_from_spec(ADAPTER_SPEC)
sys.modules[ADAPTER_SPEC.name] = ADAPTER
ADAPTER_SPEC.loader.exec_module(ADAPTER)

RUNNER_PATH = Path("tools/experiments/150-cleaning/page_edge_bubble_first_divergence/run_paddle_detection_baseline.py")
RUNNER_SPEC = importlib.util.spec_from_file_location("paddle_detection_baseline", RUNNER_PATH)
assert RUNNER_SPEC and RUNNER_SPEC.loader
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
sys.modules[RUNNER_SPEC.name] = RUNNER
RUNNER_SPEC.loader.exec_module(RUNNER)

GROUPING_ADAPTER_PATH = Path("tools/experiments/150-cleaning/page_edge_bubble_first_divergence/grouping_adapter.py")
GROUPING_ADAPTER_SPEC = importlib.util.spec_from_file_location("grouping_adapter", GROUPING_ADAPTER_PATH)
assert GROUPING_ADAPTER_SPEC and GROUPING_ADAPTER_SPEC.loader
GROUPING_ADAPTER = importlib.util.module_from_spec(GROUPING_ADAPTER_SPEC)
sys.modules[GROUPING_ADAPTER_SPEC.name] = GROUPING_ADAPTER
GROUPING_ADAPTER_SPEC.loader.exec_module(GROUPING_ADAPTER)

GROUPING_RUNNER_PATH = Path("tools/experiments/150-cleaning/page_edge_bubble_first_divergence/run_grouping_baseline.py")
GROUPING_RUNNER_SPEC = importlib.util.spec_from_file_location("grouping_baseline", GROUPING_RUNNER_PATH)
assert GROUPING_RUNNER_SPEC and GROUPING_RUNNER_SPEC.loader
GROUPING_RUNNER = importlib.util.module_from_spec(GROUPING_RUNNER_SPEC)
sys.modules[GROUPING_RUNNER_SPEC.name] = GROUPING_RUNNER
GROUPING_RUNNER_SPEC.loader.exec_module(GROUPING_RUNNER)


def test_binary_metrics_reports_single_pixel_core_false_negative():
    expected = np.array([[True, True], [False, False]])
    predicted = np.array([[True, False], [False, False]])
    assert MODULE.binary_metrics(predicted, expected) == {"tp": 1, "fp": 0, "fn": 1, "precision": 1.0, "recall": 0.5, "iou": 0.5}


def test_authorization_never_writes_visible_or_page_truncation():
    masks = {name: np.zeros((7, 7), dtype=bool) for name in ("bubble_interior", "visible_boundary", "page_truncation", "text_required", "text_fringe")}
    masks["bubble_interior"][:] = True
    masks["visible_boundary"][0, :] = True
    masks["page_truncation"][:, 0] = True
    masks["text_required"][3, 3] = True
    oracle = type("Oracle", (), {"masks": masks})()
    derived = MODULE.derive_authorization(oracle, boundary_radius=1, fringe_radius=1)
    assert not np.any(derived["write"] & masks["visible_boundary"])
    assert not np.any(derived["write"] & masks["page_truncation"])
    assert np.any(derived["write"])


def test_full_page_and_roi_coordinate_conversion_is_reversible():
    case = type("Case", (), {"roi": (2, 3, 5, 6)})()
    roi = np.array([[True, False, True], [False, True, False], [True, True, False]])
    full = MODULE.roi_to_full(roi, case, (9, 8))
    assert np.array_equal(MODULE.full_to_roi(full, case), roi)


def test_support_and_boundary_evaluator_cover_hard_diagnostic_cases():
    core = np.zeros((3, 3), dtype=bool); core[1, 1] = True
    fringe = core.copy(); fringe[1, 2] = True
    visible = np.zeros((3, 3), dtype=bool); visible[0, 1] = True
    truncation = np.zeros((3, 3), dtype=bool); truncation[:, 0] = True
    interior = np.ones((3, 3), dtype=bool)
    predicted = core | visible
    support = EVALUATOR.support_metrics(predicted, core=core, fringe=fringe, visible_boundary=visible, page_truncation=truncation, bubble_interior=interior)
    assert support["core_false_negative_count"] == 0
    assert support["support_visible_boundary_intersection"] == 1
    classes = {"bubble_interior": interior & ~visible & ~truncation, "visible_boundary": visible, "page_truncation": truncation, "unknown": np.zeros((3, 3), dtype=bool), "outside": np.zeros((3, 3), dtype=bool)}
    observed = {**classes, "page_truncation": np.zeros((3, 3), dtype=bool), "visible_boundary": visible | truncation}
    boundary = EVALUATOR.boundary_metrics(observed, classes)
    assert boundary["page_edge_as_closed_boundary_pixels"] == 3
    assert EVALUATOR.stable_first_divergence([("input", "MATCH", []), ("text_support", "core_false_negative", [])])["stage"] == "text_support"


def test_first_divergence_is_detection_and_never_claims_causality():
    case = type("Case", (), {"case_id": "case"})()
    oracle = type("Oracle", (), {"masks": {"text_required": np.ones((2, 2), dtype=bool)}})()
    value = MODULE.first_divergence_for_unavailable_detection(case, oracle)
    assert value["first_observed_divergence"] is None
    assert value["earliest_execution_gap"]["stage"] == "detection"
    assert value["causality"]["established"] is False


def test_auto_execution_function_has_no_oracle_parameter_or_loader_call():
    tree = ast.parse(Path("tools/experiments/150-cleaning/page_edge_bubble_first_divergence/run_experiment.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_auto_execution")
    assert [arg.arg for arg in function.args.args] == ["case", "run_dir"]
    assert not any(isinstance(node, ast.Name) and node.id == "load_accepted_oracle" for node in ast.walk(function))


def test_existing_accepted_oracle_is_never_overwritten(tmp_path: Path):
    case = type("Case", (), {})()
    candidate = tmp_path / "candidate"; candidate.mkdir()
    accepted = tmp_path / "accepted"; accepted.mkdir()
    with pytest.raises(MODULE.ExperimentStop, match="already exists"):
        MODULE.freeze_candidate_as_accepted(case, candidate, accepted)


def test_case_loader_rejects_tampered_source_before_run_creation(tmp_path: Path):
    source = tmp_path / "data/local/sources/110-detection/source.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(source)
    case_path = tmp_path / "data/local/datasets/150-cleaning/cases.json"
    case_path.parent.mkdir(parents=True)
    case_path.write_text(json.dumps({"schema_version": "page-edge-bubble-case-v1", "case_id": "case", "source_path": "data/local/sources/110-detection/source.png", "source_sha256": "0" * 64, "roi_xyxy": [0, 0, 4, 4], "algorithm_input": "full_page"}), encoding="utf-8")
    with pytest.raises(MODULE.ExperimentStop, match="source hash mismatch"):
        MODULE.load_case(case_path, tmp_path)


def test_detection_adapter_normalizes_only_full_page_in_bounds_boxes():
    assert ADAPTER.normalize_bbox({"x": 1, "y": 2, "width": 6, "height": 6}, width=8, height=9) == {"x": 1.0, "y": 2.0, "width": 6.0, "height": 6.0}
    with pytest.raises(ADAPTER.DetectionAdapterError, match="out-of-bounds"):
        ADAPTER.normalize_bbox({"x": -1, "y": 2, "width": 6, "height": 6}, width=8, height=9)


def test_detection_adapter_rejects_out_of_bounds_polygon_without_clipping():
    with pytest.raises(ADAPTER.DetectionAdapterError, match="out-of-bounds"):
        ADAPTER.normalize_polygon([[0, 0], [9, 0], [0, 1]], width=8, height=9)


def test_detection_execution_adapter_has_no_oracle_input_or_loader_dependency():
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run")
    assert "oracle" not in [arg.arg for arg in function.args.args]
    assert not any(isinstance(node, ast.Name) and "oracle" in node.id.lower() for node in ast.walk(function))


def test_runner_freezes_detection_artifacts_before_loading_oracle():
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert source.index("execution_artifacts = artifact_inventory(run)") < source.index("oracle = load_accepted_oracle")
    assert "oracle_injection\": False" in source


def test_detection_miss_is_divergence_but_complete_geometry_is_grouping_gap():
    first, gap = RUNNER.classify_detection_outcome({"target_candidate_count": 0, "unmatched_required_pixels": 12})
    assert first["stage"] == "detection" and gap is None
    first, gap = RUNNER.classify_detection_outcome({"target_candidate_count": 2, "unmatched_required_pixels": 0})
    assert first is None and gap["stage"] == "grouping"


def test_grouping_adapter_rejects_nonintegral_or_out_of_bounds_detection_geometry():
    with pytest.raises(GROUPING_ADAPTER.GroupingAdapterError, match="integer bbox"):
        GROUPING_ADAPTER._integer_bbox({"x": 0.5, "y": 0, "width": 3, "height": 4}, width=8, height=9)
    with pytest.raises(GROUPING_ADAPTER.GroupingAdapterError, match="out of full-page bounds"):
        GROUPING_ADAPTER._integer_bbox({"x": 7, "y": 0, "width": 3, "height": 4}, width=8, height=9)


def test_grouping_execution_adapter_has_no_oracle_input_or_loader_dependency():
    tree = ast.parse(GROUPING_ADAPTER_PATH.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run")
    assert "oracle" not in [arg.arg for arg in function.args.args]
    assert not any(isinstance(node, ast.Name) and "oracle" in node.id.lower() for node in ast.walk(function))


def test_grouping_runner_freezes_assignments_before_loading_oracle():
    source = GROUPING_RUNNER_PATH.read_text(encoding="utf-8")
    assert source.index("execution_artifacts = artifact_inventory(run)") < source.index("oracle = load_accepted_oracle")
    assert "oracle_injection\": False" in source


def test_grouping_membership_miss_is_divergence_but_missing_bubble_assignment_is_gap():
    failing = {"association_comparison": {"text_group_membership_assessment": "FAIL"}}
    first, gap = GROUPING_RUNNER.classify_grouping_outcome(failing)
    assert first["stage"] == "grouping" and gap is None
    passing = {"association_comparison": {"text_group_membership_assessment": "PASS"}}
    first, gap = GROUPING_RUNNER.classify_grouping_outcome(passing)
    assert first is None and gap["component"] == "bubble_instance_assignment"
