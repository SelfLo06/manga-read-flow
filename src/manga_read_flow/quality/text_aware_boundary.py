from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import cv2
import numpy as np


@dataclass(frozen=True)
class TextAwareBoundaryInputs:
    """Immutable, instance-scoped inputs for one bounded correction."""

    primary_instance: np.ndarray
    neighbor_instance: np.ndarray
    current_virtual_boundary: np.ndarray
    visible_boundary: np.ndarray
    required_support: np.ndarray
    protected: np.ndarray
    uncertainty: np.ndarray
    source_sha256: str = ""
    guard_margin_px: int = 1
    corridor_radius_px: int = 6
    uncertainty_radius_px: int = 2
    policy_version: str = "text-aware-boundary-v0.1"


@dataclass(frozen=True)
class TextAwareBoundaryResult:
    status: str
    reason_code: str
    correction_ordinal: int
    budget_after: int
    corridor: np.ndarray
    guarded_required: np.ndarray
    virtual_boundary: np.ndarray
    uncertainty: np.ndarray
    primary_instance: np.ndarray
    neighbor_instance: np.ndarray
    primary_protected: np.ndarray
    primary_safe_edit: np.ndarray
    unsafe_required_pixels: int
    dependency_fingerprint: str


def correct_text_aware_virtual_boundary(
    inputs: TextAwareBoundaryInputs,
    *,
    correction_ordinal: int,
) -> TextAwareBoundaryResult:
    """Perform exactly one local virtual-boundary correction.

    The function never changes visible/protected pixels or the required evidence.
    It only removes virtual-boundary uncertainty where a guarded required support
    proves that the inferred boundary is locally misplaced.  The result's safe
    edit mask is always derived from the returned instance/protected/uncertainty
    masks, never grown from required support.
    """
    if correction_ordinal != 1:
        raise ValueError("Only correction ordinal 1 is permitted.")
    masks = tuple(_bool(mask) for mask in (
        inputs.primary_instance,
        inputs.neighbor_instance,
        inputs.current_virtual_boundary,
        inputs.visible_boundary,
        inputs.required_support,
        inputs.protected,
        inputs.uncertainty,
    ))
    if len({mask.shape for mask in masks}) != 1:
        raise ValueError("Boundary correction masks must share dimensions.")
    primary, neighbor, current_virtual, visible, required, protected, uncertainty = masks
    if (primary & neighbor).any():
        raise ValueError("BubbleInstance masks must be mutually exclusive.")

    shared_domain = primary | neighbor
    corridor_seed = current_virtual | uncertainty
    corridor = _dilate(corridor_seed, inputs.corridor_radius_px) & shared_domain
    guarded_required = _dilate(required, inputs.guard_margin_px) & corridor
    hard_structure = visible | protected
    conflict = guarded_required & hard_structure
    required_outside_primary = required & ~primary
    if conflict.any() or required_outside_primary.any():
        return _blocked(
            inputs,
            primary,
            neighbor,
            current_virtual,
            uncertainty,
            corridor,
            guarded_required,
            "guard_conflicts_visible_or_protected"
            if conflict.any()
            else "required_support_crosses_primary_instance",
        )

    # The virtual boundary is an inferred separator, not a visible structure.
    # A fixed guard around confirmed text forbids that separator and its
    # uncertainty band from occupying this local corridor.  No pixels outside
    # the corridor are changed and no protected/visible pixel is reclassified.
    protected_guard = _dilate(guarded_required, inputs.uncertainty_radius_px)
    new_virtual = current_virtual & ~(protected_guard & corridor)
    new_uncertainty = uncertainty & ~(protected_guard & corridor)
    primary_protected = protected | visible | new_virtual
    primary_safe = primary & ~primary_protected & ~new_uncertainty
    unsafe = int((required & ~primary_safe).sum())
    status = "COMPLETE" if unsafe == 0 else "INCOMPLETE_REVIEW"
    return TextAwareBoundaryResult(
        status=status,
        reason_code=("text_aware_virtual_boundary_corrected" if unsafe == 0 else "required_text_not_safely_editable"),
        correction_ordinal=1,
        budget_after=0,
        corridor=corridor,
        guarded_required=guarded_required,
        virtual_boundary=new_virtual,
        uncertainty=new_uncertainty,
        primary_instance=primary.copy(),
        neighbor_instance=neighbor.copy(),
        primary_protected=primary_protected,
        primary_safe_edit=primary_safe,
        unsafe_required_pixels=unsafe,
        dependency_fingerprint=_fingerprint(inputs, new_virtual, new_uncertainty, primary_safe),
    )


def _blocked(inputs, primary, neighbor, current_virtual, uncertainty, corridor, guarded_required, reason):
    safe = primary & ~(inputs.visible_boundary.astype(bool) | inputs.protected.astype(bool) | current_virtual | uncertainty)
    return TextAwareBoundaryResult(
        status="INCOMPLETE_REVIEW",
        reason_code=reason,
        correction_ordinal=1,
        budget_after=0,
        corridor=corridor,
        guarded_required=guarded_required,
        virtual_boundary=current_virtual,
        uncertainty=uncertainty,
        primary_instance=primary.copy(),
        neighbor_instance=neighbor.copy(),
        primary_protected=inputs.protected.astype(bool) | inputs.visible_boundary.astype(bool) | current_virtual,
        primary_safe_edit=safe,
        unsafe_required_pixels=int((inputs.required_support.astype(bool) & ~safe).sum()),
        dependency_fingerprint=_fingerprint(inputs, current_virtual, uncertainty, safe),
    )


def _bool(mask: np.ndarray) -> np.ndarray:
    return np.asarray(mask, dtype=bool)


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius < 0:
        raise ValueError("Mask radius must be non-negative.")
    return cv2.dilate(mask.astype(np.uint8), np.ones((radius * 2 + 1, radius * 2 + 1), np.uint8)) > 0


def _fingerprint(inputs, virtual, uncertainty, safe) -> str:
    digest = sha256()
    digest.update(inputs.policy_version.encode("utf-8"))
    digest.update(inputs.source_sha256.encode("ascii"))
    digest.update(f"{inputs.guard_margin_px}:{inputs.corridor_radius_px}:{inputs.uncertainty_radius_px}".encode("ascii"))
    for mask in (inputs.primary_instance, inputs.neighbor_instance, inputs.required_support, inputs.visible_boundary, inputs.protected, virtual, uncertainty, safe):
        digest.update(np.ascontiguousarray(mask.astype(np.uint8)).tobytes())
    return digest.hexdigest()


__all__ = ["TextAwareBoundaryInputs", "TextAwareBoundaryResult", "correct_text_aware_virtual_boundary"]
