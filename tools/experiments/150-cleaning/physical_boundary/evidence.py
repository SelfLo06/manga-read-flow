"""Deterministic Stage A evidence derivation; deliberately has no case identity input."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import cv2
import numpy as np


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class Classification:
    required_text: np.ndarray
    proven_non_text_boundary: np.ndarray
    unresolved_uncertain: np.ndarray
    evidence_error: np.ndarray
    boundary_ridge: np.ndarray

    def validate(self, old_required: np.ndarray) -> None:
        masks = (self.required_text, self.proven_non_text_boundary, self.unresolved_uncertain, self.evidence_error)
        if any(mask.dtype != np.bool_ or mask.shape != old_required.shape for mask in masks):
            raise EvidenceError("classification masks must be bool and match required")
        if np.any(sum(mask.astype(np.uint8) for mask in masks) != old_required.astype(np.uint8)):
            raise EvidenceError("every old required pixel must receive exactly one classification")


def mask_hash(mask: np.ndarray) -> str:
    _mask(mask, "mask")
    return sha256(str(mask.shape).encode() + np.packbits(mask).tobytes()).hexdigest()


def text_core(source_rgb: np.ndarray, old_required: np.ndarray, *, luminance_max: float = 180.0) -> np.ndarray:
    _image(source_rgb)
    _mask(old_required, "old_required")
    if old_required.shape != source_rgb.shape[:2]:
        raise EvidenceError("source/mask shape mismatch")
    luminance = 0.2126 * source_rgb[..., 0] + 0.7152 * source_rgb[..., 1] + 0.0722 * source_rgb[..., 2]
    return old_required & (luminance <= luminance_max)


def gradient_ridge(source_rgb: np.ndarray, instance: np.ndarray, protected: np.ndarray, *, percentile: float = 92.0) -> np.ndarray:
    _image(source_rgb); _same(instance, protected)
    if instance.shape != source_rgb.shape[:2]:
        raise EvidenceError("source/mask shape mismatch")
    gray = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2GRAY)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(grad_x, grad_y)
    values = magnitude[instance]
    threshold = float(np.percentile(values, percentile)) if values.size else float("inf")
    return (magnitude >= threshold) & instance | protected


def classify_a1(source_rgb: np.ndarray, old_required: np.ndarray, instance: np.ndarray, protected: np.ndarray, uncertainty: np.ndarray) -> Classification:
    """Core-connected support under hard physical structure barriers.

    It only certifies clearly core-connected pixels as `required_text`; hard
    protected, ridge, and uncertainty barriers remain outside that support.
    Every contested/non-core result abstains, so it never proves a boundary
    removable.
    """
    _all_same(old_required, instance, protected, uncertainty, source_rgb[..., 0])
    core = text_core(source_rgb, old_required)
    ridge = gradient_ridge(source_rgb, instance, protected)
    traversable = old_required & instance & ~protected & ~uncertainty & ~ridge
    labels_count, labels = cv2.connectedComponents(traversable.astype(np.uint8), connectivity=8)
    owned = np.zeros_like(old_required)
    for label in range(1, labels_count):
        component = labels == label
        if np.any(component & core):
            owned |= component
    unresolved = old_required & ~owned
    result = Classification(owned, np.zeros_like(old_required), unresolved, np.zeros_like(old_required), ridge)
    result.validate(old_required)
    return result


def classify_a2(source_rgb: np.ndarray, old_required: np.ndarray, instance: np.ndarray, protected: np.ndarray, uncertainty: np.ndarray) -> Classification:
    """Gradient-barrier reachability; ambiguity remains unresolved rather than shrunk away."""
    _all_same(old_required, instance, protected, uncertainty, source_rgb[..., 0])
    core = text_core(source_rgb, old_required)
    ridge = gradient_ridge(source_rgb, instance, protected)
    barrier = protected | ridge
    reachable = _geodesic_reachable(core & ~barrier, old_required & instance & ~barrier)
    # Pixels in uncertainty are retained only if they have unambiguous direct seed support.
    required_text = reachable & ~uncertainty
    unresolved = old_required & ~required_text
    result = Classification(required_text, np.zeros_like(old_required), unresolved, np.zeros_like(old_required), ridge)
    result.validate(old_required)
    return result


def classify_a5(source_rgb: np.ndarray, old_required: np.ndarray, instance: np.ndarray, protected: np.ndarray, uncertainty: np.ndarray) -> Classification:
    """Color-aware, seed-connected support with one adaptive Lab-distance policy.

    The policy has no knowledge of a color name, case, target, or coordinate.
    Color only supplies evidence that a candidate differs from the locally
    sampled bubble background; physical ridges/protected pixels remain barriers.
    """
    _all_same(old_required, instance, protected, uncertainty, source_rgb[..., 0])
    core = text_core(source_rgb, old_required)
    ridge = gradient_ridge(source_rgb, instance, protected)
    exclusion = cv2.dilate(old_required.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    background = instance & ~exclusion & ~protected & ~uncertainty
    if int(background.sum()) < 16 or not core.any():
        unresolved = old_required.copy()
        result = Classification(np.zeros_like(old_required), np.zeros_like(old_required), unresolved, np.zeros_like(old_required), ridge)
        result.validate(old_required)
        return result
    lab = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    background_lab = np.median(lab[background], axis=0)
    distance = np.linalg.norm(lab - background_lab, axis=2)
    core_distance = distance[core]
    threshold = max(4.0, float(np.percentile(core_distance, 20)))
    candidate = old_required & instance & ~protected & ~ridge & (distance >= threshold)
    required_text = _geodesic_reachable(core & candidate, candidate) & ~uncertainty
    unresolved = old_required & ~required_text
    result = Classification(required_text, np.zeros_like(old_required), unresolved, np.zeros_like(old_required), ridge)
    result.validate(old_required)
    return result


def color_evidence(source_rgb: np.ndarray, old_required: np.ndarray, instance: np.ndarray, protected: np.ndarray, uncertainty: np.ndarray) -> dict[str, object]:
    """Report-only local Lab evidence; it cannot affect A5's policy path."""
    _all_same(old_required, instance, protected, uncertainty, source_rgb[..., 0])
    lab = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    background = instance & ~old_required & ~protected & ~uncertainty
    core = text_core(source_rgb, old_required)
    if int(background.sum()) < 16 or not core.any():
        return {"status": "INSUFFICIENT_LOCAL_COLOR_EVIDENCE", "precision_recall": "PENDING_HUMAN_LABELS"}
    bg = np.median(lab[background], axis=0)
    distance = np.linalg.norm(lab - bg, axis=2)
    return {"status": "OBSERVED", "background_lab_median": [round(float(value), 4) for value in bg], "core_distance_p20_p50_p80": [round(float(np.percentile(distance[core], p)), 4) for p in (20, 50, 80)], "requested_strata": {"deep_blue": "PENDING_HUMAN_LABELS", "orange": "PENDING_HUMAN_LABELS", "antialias_edge": "PENDING_HUMAN_LABELS"}}


def components(mask: np.ndarray) -> list[tuple[int, np.ndarray]]:
    _mask(mask, "mask")
    count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    values = [(label, labels == label) for label in range(1, count)]
    return sorted(values, key=lambda entry: (-int(entry[1].sum()), int(entry[0])))


def _geodesic_reachable(seeds: np.ndarray, traversable: np.ndarray) -> np.ndarray:
    _same(seeds, traversable)
    count, labels = cv2.connectedComponents(traversable.astype(np.uint8), connectivity=8)
    result = np.zeros_like(seeds)
    for label in range(1, count):
        component = labels == label
        if np.any(component & seeds):
            result |= component
    return result


def _mask(value: np.ndarray, name: str) -> None:
    if not isinstance(value, np.ndarray) or value.dtype != np.bool_ or value.ndim != 2:
        raise EvidenceError(f"{name} must be a 2D bool mask")


def _image(value: np.ndarray) -> None:
    if not isinstance(value, np.ndarray) or value.ndim != 3 or value.shape[2] != 3:
        raise EvidenceError("source must be RGB")


def _same(*values: np.ndarray) -> None:
    first = values[0].shape
    for value in values:
        if value.shape != first:
            raise EvidenceError("mask shape mismatch")
        if value.ndim == 2:
            _mask(value, "mask")


def _all_same(*values: np.ndarray) -> None:
    first = values[0].shape
    if any(value.shape != first for value in values):
        raise EvidenceError("mask shape mismatch")
    for value in values[:-1]:
        _mask(value, "mask")
