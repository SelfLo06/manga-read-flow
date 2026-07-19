from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
RUNNER_PATH = (
    ROOT
    / "tools"
    / "experiments"
    / "120-grouping"
    / "text_seeded_container_association"
    / "run_goal4_r0.py"
)


def load_runner(name: str = "text_seeded_container_goal4_r0_test"):
    spec = importlib.util.spec_from_file_location(name, RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_goal4_r0_runner_has_no_evaluator_or_ground_truth_input():
    runner = load_runner("goal4_r0_signature")

    assert tuple(inspect.signature(runner.run_once).parameters) == (
        "r0_root",
        "calibration_lock_path",
        "output_dir",
    )


def test_goal4_r0_overlay_accepts_regionless_abstention():
    runner = load_runner("goal4_r0_regionless_overlay")
    focused = runner.FOCUSED
    image = np.full((80, 100, 3), 255, dtype=np.uint8)
    fragment = focused.Fragment(
        "p1", (30, 20, 15, 40), ((30, 20), (45, 20), (45, 60), (30, 60)), "g1"
    )
    page = focused.PageInput("case-01", image, (fragment,))
    result = focused.AssociationResult(
        asset_id="case-01",
        method_id="P1-corrected-v1",
        regions=(focused.RegionResult("r1", ("p1",), None, "uncertain", 0.0),),
        same_container_decisions=(),
        virtual_boundary=np.zeros((80, 100), dtype=np.bool_),
        recommended_decision="SKIP",
        abstention_reasons=("regionless_uncertain_isolated_seed",),
        diagnostics={},
    )

    overlay = runner.render_overlay(page, result)

    assert overlay.size == (100, 80)
