from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np


MODULE_PATH = Path("tools/experiments/150-cleaning/physical_boundary/evidence.py")
SPEC = importlib.util.spec_from_file_location("physical_boundary_evidence", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
classify_a1 = MODULE.classify_a1
classify_a2 = MODULE.classify_a2
classify_a5 = MODULE.classify_a5
components = MODULE.components


def _inputs():
    source = np.full((12, 12, 3), 245, dtype=np.uint8)
    source[5:7, 4:8] = 40
    required = np.zeros((12, 12), dtype=bool); required[4:8, 3:9] = True
    instance = np.ones((12, 12), dtype=bool)
    protected = np.zeros((12, 12), dtype=bool); protected[4:8, 3] = True
    uncertainty = np.zeros((12, 12), dtype=bool); uncertainty[4:8, 4] = True
    return source, required, instance, protected, uncertainty


def test_classifications_are_partitioned_and_protected_never_required():
    values = _inputs()
    for classify in (classify_a1, classify_a2, classify_a5):
        outcome = classify(*values)
        outcome.validate(values[1])
        assert not np.any(outcome.required_text & values[3])
        assert not np.any(outcome.required_text & values[4])


def test_replay_and_component_identity_are_deterministic():
    values = _inputs()
    assert np.array_equal(classify_a1(*values).unresolved_uncertain, classify_a1(*values).unresolved_uncertain)
    mask = np.zeros((6, 6), dtype=bool); mask[1, 1] = True; mask[3:5, 3:5] = True
    assert [int(item.sum()) for _, item in components(mask)] == [4, 1]


def test_algorithm_has_no_case_or_target_identifier_branch():
    tree = ast.parse(Path("tools/experiments/150-cleaning/physical_boundary/evidence.py").read_text(encoding="utf-8"))
    forbidden = {"case_id", "target_id", "filename"}
    assert not any(isinstance(node, ast.Name) and node.id in forbidden for node in ast.walk(tree))


def test_positive_interior_and_negative_boundary_controls_remain_fail_closed():
    source = np.full((16, 16, 3), 245, dtype=np.uint8)
    source[6:10, 6:10] = (10, 30, 170)  # interior deep-blue text control
    required = np.zeros((16, 16), dtype=bool); required[5:11, 5:11] = True
    instance = np.ones((16, 16), dtype=bool)
    protected = np.zeros((16, 16), dtype=bool)
    uncertainty = np.zeros((16, 16), dtype=bool)
    for classify in (classify_a1, classify_a2, classify_a5):
        positive = classify(source, required, instance, protected, uncertainty)
        assert not np.any(positive.required_text & ~required)
        # Negative: a true physical outline must stay non-writable even when it
        # is dark enough to look like text-core evidence.
        boundary = protected.copy(); boundary[5:11, 5] = True
        source[5:11, 5] = 0
        negative = classify(source, required, instance, boundary, uncertainty)
        assert not np.any(negative.required_text & boundary)
        assert np.any(negative.unresolved_uncertain & boundary)


def test_color_controls_use_one_algorithm_path_not_named_color_rules():
    required = np.zeros((12, 12), dtype=bool); required[3:9, 3:9] = True
    instance = np.ones((12, 12), dtype=bool)
    protected = np.zeros((12, 12), dtype=bool)
    uncertainty = np.zeros((12, 12), dtype=bool)
    outcomes = []
    for color in ((0, 20, 170), (220, 90, 0)):  # blue/orange only test inputs
        source = np.full((12, 12, 3), 245, dtype=np.uint8)
        source[4:8, 4:8] = color
        outcome = classify_a5(source, required, instance, protected, uncertainty)
        outcomes.append((outcome.required_text.shape, outcome.unresolved_uncertain.shape))
        assert not np.any(outcome.required_text & protected)
    assert outcomes == [((12, 12), (12, 12)), ((12, 12), (12, 12))]


def test_frozen_case71_controls_cannot_expand_or_cross_hard_barriers():
    """Real frozen controls are evidence-only; no output is a write candidate."""
    case_root = Path("data/local/runs/150-cleaning/full-page-v0.1/slice-3/run-v0.2/case-71")
    summary = json.loads((case_root / "summary.json").read_text(encoding="utf-8"))
    historical_source = Path(summary["source"]["path"])
    source_path = (
        historical_source
        if historical_source.is_file()
        else Path("data/local/reviews/150-cleaning/association-goal6-v0.1/full-page-v0.1/images")
        / historical_source.name
    )
    bgr = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    assert bgr is not None
    source = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    # These are frozen fixture controls only: simple interior and previously
    # accepted support variants.  They never select an algorithm policy.
    for target in ("case-71__g001__s01", "case-71__g002__s01", "case-71__g002__s02"):
        evidence = case_root / "evidence" / target
        masks = {
            name: cv2.imread(str(evidence / f"{name}.png"), cv2.IMREAD_GRAYSCALE) > 0
            for name in ("visible", "instance", "protected", "uncertainty")
        }
        for classify in (classify_a1, classify_a2, classify_a5):
            outcome = classify(source, masks["visible"], masks["instance"], masks["protected"], masks["uncertainty"])
            outcome.validate(masks["visible"])
            assert not np.any(outcome.required_text & ~masks["visible"])
            assert not np.any(outcome.required_text & (masks["protected"] | masks["uncertainty"]))
