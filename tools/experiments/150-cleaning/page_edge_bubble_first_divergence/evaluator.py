"""Oracle-only, post-execution evaluator for page-edge-bubble runs."""
from __future__ import annotations

from typing import Any

import numpy as np

from core import ExperimentStop, binary_metrics


BOUNDARY_CLASSES = ("bubble_interior", "visible_boundary", "page_truncation", "unknown", "outside")


def support_metrics(predicted: np.ndarray, *, core: np.ndarray, fringe: np.ndarray, visible_boundary: np.ndarray, page_truncation: np.ndarray, bubble_interior: np.ndarray) -> dict[str, Any]:
    if len({predicted.shape, core.shape, fringe.shape, visible_boundary.shape, page_truncation.shape, bubble_interior.shape}) != 1:
        raise ExperimentStop("support evaluator shape mismatch")
    return {
        "core": binary_metrics(predicted, core), "fringe": binary_metrics(predicted, fringe),
        "support_visible_boundary_intersection": int((predicted & visible_boundary).sum()),
        "support_page_truncation_intersection": int((predicted & page_truncation).sum()),
        "outside_bubble_fp": int((predicted & ~bubble_interior).sum()),
        "core_false_negative_count": int((core & ~predicted).sum()),
    }


def boundary_metrics(predicted: dict[str, np.ndarray], expected: dict[str, np.ndarray]) -> dict[str, Any]:
    if set(predicted) != set(BOUNDARY_CLASSES) or set(expected) != set(BOUNDARY_CLASSES):
        raise ExperimentStop("all boundary classes are required")
    shapes = {mask.shape for mask in (*predicted.values(), *expected.values())}
    if len(shapes) != 1 or any(mask.dtype != np.bool_ for mask in (*predicted.values(), *expected.values())):
        raise ExperimentStop("boundary evaluator masks must be same-shaped bool arrays")
    matrix = {actual: {observed: int((expected[actual] & predicted[observed]).sum()) for observed in BOUNDARY_CLASSES} for actual in BOUNDARY_CLASSES}
    return {"confusion_matrix": matrix, "per_class": {name: binary_metrics(predicted[name], expected[name]) for name in BOUNDARY_CLASSES}, "page_edge_as_closed_boundary_pixels": int((expected["page_truncation"] & predicted["visible_boundary"]).sum()), "interior_as_outside_or_unknown_pixels": int((expected["bubble_interior"] & (predicted["outside"] | predicted["unknown"])).sum())}


def grouping_metrics(actual: dict[str, Any] | None, expected: dict[str, Any]) -> dict[str, Any]:
    if actual is None:
        return {"status": "NOT_AVAILABLE"}
    return {"status": "EVALUATED", "automatic_bubble_count": actual.get("bubble_count"), "automatic_text_group_count": actual.get("text_group_count"), "expected_bubble_count": expected.get("bubble_count"), "expected_text_group_count": expected.get("text_group_count"), "unassigned_fragments": actual.get("unassigned_fragments", []), "foreign_assignment": actual.get("foreign_assignment", []), "topology_differences": actual.get("topology_differences", []), "provenance": actual.get("provenance")}


def stable_first_divergence(stages: list[tuple[str, str, list[dict[str, Any]]]]) -> dict[str, Any]:
    for stage, kind, evidence in stages:
        if kind != "MATCH":
            return {"stage": stage, "type": kind, "evidence": evidence}
    return {"stage": "none", "type": "none", "evidence": []}
