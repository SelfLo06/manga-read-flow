from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[4]
RUNNER_PATH = (
    ROOT_DIR
    / "tools"
    / "experiments"
    / "120-grouping"
    / "text_seeded_container_association"
    / "run_r0_matrix.py"
)
R0_ROOT = (
    ROOT_DIR
    / "data"
    / "local"
    / "reviews"
    / "120-grouping"
    / "association-r0-blind-v0.3"
)
LOCK_PATH = (
    ROOT_DIR
    / "data"
    / "local"
    / "datasets"
    / "120-grouping"
    / "text-seeded-calibration-v0.1"
    / "calibration-runs"
    / "goal2-v0.1"
    / "calibration-lock-v0.1.json"
)


def load_runner(name: str = "text_seeded_container_r0_matrix"):
    spec = importlib.util.spec_from_file_location(name, RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_verifies_exact_frozen_r0_and_goal2_lock():
    runner = load_runner()

    verified = runner.verify_frozen_inputs(R0_ROOT, LOCK_PATH)

    assert verified["r0_run_id"] == "20260715T075811Z-3e9711"
    assert verified["asset_ids"] == [f"case-{index:02d}" for index in range(1, 7)]
    assert verified["thresholds"].different == 0.40
    assert verified["thresholds"].same == 0.75
    assert verified["r0_results_sha256"] == runner.EXPECTED_R0_RESULTS_SHA256
    assert verified["calibration_lock_sha256"] == runner.EXPECTED_CALIBRATION_LOCK_SHA256


def test_algorithm_runner_has_no_evaluator_contract_input():
    runner = load_runner("text_seeded_container_r0_no_gt")
    source = inspect.getsource(runner)

    assert "GOAL3-EVALUATOR-CONTRACT" not in source
    assert "annotator-a" not in source
    assert "expected_topology" not in source
    assert "evaluator" not in inspect.signature(runner.write_matrix).parameters


def test_synthetic_page_runs_all_three_frozen_methods_and_renders_overlay():
    runner = load_runner("text_seeded_container_r0_synthetic")
    fragment = runner.HARNESS.Fragment(
        fragment_id="p1",
        bbox=(20, 10, 15, 35),
        polygon=((20, 10), (35, 10), (35, 45), (20, 45)),
        upstream_group_id="g1",
    )
    page = runner.HARNESS.PageInput(
        asset_id="synthetic",
        image=np.full((60, 80, 3), 255, dtype=np.uint8),
        fragments=(fragment,),
    )
    thresholds = runner.HARNESS.SameContainerThresholds(0.40, 0.75)

    methods = runner.run_methods(page, thresholds)

    assert set(methods) == {"B0", "B1", "P1"}
    for method_id, result in methods.items():
        overlay = runner.render_overlay(page, result)
        assert result.method_id == method_id
        assert overlay.mode == "RGB"
        assert overlay.size == (80, 60)


def test_page_output_contract_contains_hashes_and_no_cleaning_fields(tmp_path: Path):
    runner = load_runner("text_seeded_container_r0_output")
    fragment = runner.HARNESS.Fragment(
        fragment_id="p1",
        bbox=(10, 10, 12, 25),
        polygon=((10, 10), (22, 10), (22, 35), (10, 35)),
        upstream_group_id="g1",
    )
    page = runner.HARNESS.PageInput(
        asset_id="synthetic",
        image=np.full((50, 60, 3), 255, dtype=np.uint8),
        fragments=(fragment,),
    )
    result = runner.HARNESS.run_b0(page)

    record = runner.write_page_output(tmp_path, page, result)

    assert record["asset_id"] == "synthetic"
    assert record["method_id"] == "B0"
    assert len(record["result_sha256"]) == 64
    assert len(record["overlay_sha256"]) == 64
    payload = (tmp_path / record["result_relative_path"]).read_text(encoding="utf-8")
    assert "cleaned_image" not in payload
    assert "pixel_text_mask" not in payload
