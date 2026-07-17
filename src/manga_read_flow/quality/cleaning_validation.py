from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class CleaningValidationResult:
    metrics: dict[str, object]
    issue_flags: dict[str, bool]
    evidence_path: Path
    actual_changed_mask_path: Path
    residue_mask_path: Path
    structure_damage_mask_path: Path
    background_difference_mask_path: Path


def validate_cleaning_output(
    *,
    source_image_path: Path,
    cleaned_image_path: Path,
    required_support_path: Path,
    safe_edit_path: Path,
    instance_mask_path: Path,
    protected_mask_path: Path,
    uncertainty_mask_path: Path,
    output_dir: Path,
    background_delta_threshold: float = 12.0,
) -> CleaningValidationResult:
    """Recompute Cleaning evidence from bytes; never trust Provider counters."""
    source = _read_rgb(source_image_path)
    cleaned = _read_rgb(cleaned_image_path)
    required = _read_mask(required_support_path)
    safe = _read_mask(safe_edit_path)
    instance = _read_mask(instance_mask_path)
    protected = _read_mask(protected_mask_path)
    uncertainty = _read_mask(uncertainty_mask_path)
    shape = source.shape[:2]
    if cleaned.shape != source.shape or any(
        mask.shape != shape
        for mask in (required, safe, instance, protected, uncertainty)
    ):
        raise ValueError("Cleaning validator inputs must share full-page dimensions.")

    changed = np.any(source != cleaned, axis=2)
    outside_safe = changed & ~safe
    protected_damage = changed & protected
    uncertainty_damage = changed & uncertainty
    boundary = instance & ~_erode(instance, 1)
    boundary_damage = changed & boundary
    structure_damage = outside_safe | protected_damage | uncertainty_damage | boundary_damage

    sampling_ring = (
        _dilate(required, 5)
        & instance
        & ~_dilate(required, 1)
        & ~protected
        & ~uncertainty
    )
    if int(sampling_ring.sum()) < 16:
        background_rgb = np.array([255, 255, 255], dtype=np.uint8)
        insufficient_background = True
    else:
        background_rgb = np.median(source[sampling_ring], axis=0).astype(np.uint8)
        insufficient_background = False

    background_lab = _rgb_values_to_lab(background_rgb[None, :])[0]
    cleaned_lab = cv2.cvtColor(cleaned, cv2.COLOR_RGB2LAB).astype(np.float32)
    distance = np.linalg.norm(cleaned_lab - background_lab, axis=2)
    residue = required & (distance > background_delta_threshold)
    background_difference = changed & (distance > background_delta_threshold)
    seam_ring = _dilate(changed, 1) & ~changed & instance & ~protected & ~uncertainty
    if seam_ring.any():
        seam_lab_median = np.median(cleaned_lab[seam_ring], axis=0)
        seam_delta = float(np.linalg.norm(seam_lab_median - background_lab))
    else:
        seam_lab_median = background_lab
        seam_delta = 0.0

    required_pixels = int(required.sum())
    changed_required_pixels = int((changed & required).sum())
    metrics = {
        "required_support_pixels": required_pixels,
        "actual_changed_pixels": int(changed.sum()),
        "changed_required_pixels": changed_required_pixels,
        "changed_outside_safe_edit_pixels": int(outside_safe.sum()),
        "changed_inside_protected_pixels": int(protected_damage.sum()),
        "changed_inside_uncertainty_pixels": int(uncertainty_damage.sum()),
        "changed_on_instance_boundary_pixels": int(boundary_damage.sum()),
        "residue_candidate_pixels": int(residue.sum()),
        "background_difference_pixels": int(background_difference.sum()),
        "background_sampling_pixels": int(sampling_ring.sum()),
        "background_rgb_median": background_rgb.tolist(),
        "background_delta_threshold": background_delta_threshold,
        "seam_ring_pixels": int(seam_ring.sum()),
        "seam_lab_median": seam_lab_median.tolist(),
        "seam_delta_to_local_background": seam_delta,
        "insufficient_local_background": insufficient_background,
    }
    issue_flags = {
        "visible_residue": bool(residue.any()),
        "outside_safe_edit": bool(outside_safe.any()),
        "protected_damage": bool(protected_damage.any()) or bool(boundary_damage.any()),
        "uncertainty_damage": bool(uncertainty_damage.any()),
        "background_inconsistency": (
            bool(background_difference.any())
            or seam_delta > background_delta_threshold
            or insufficient_background
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = output_dir / "cleaning-validation-evidence.json"
    actual_changed_path = output_dir / "actual-changed-recomputed.png"
    residue_path = output_dir / "residue-candidate.png"
    structure_path = output_dir / "structure-damage.png"
    background_path = output_dir / "background-difference.png"
    evidence_path.write_text(
        json.dumps(
            {"metrics": metrics, "issue_flags": issue_flags},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_mask(residue_path, residue)
    _write_mask(actual_changed_path, changed)
    _write_mask(structure_path, structure_damage)
    _write_mask(background_path, background_difference)
    return CleaningValidationResult(
        metrics=metrics,
        issue_flags=issue_flags,
        evidence_path=evidence_path,
        actual_changed_mask_path=actual_changed_path,
        residue_mask_path=residue_path,
        structure_damage_mask_path=structure_path,
        background_difference_mask_path=background_path,
    )


def _read_rgb(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unreadable Cleaning image: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def _read_mask(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Unreadable Cleaning mask: {path}")
    return image > 0


def _write_mask(path: Path, mask: np.ndarray) -> None:
    if not cv2.imwrite(str(path), mask.astype(np.uint8) * 255):
        raise ValueError(f"Unable to write Cleaning evidence mask: {path}")


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    kernel = np.ones((radius * 2 + 1, radius * 2 + 1), np.uint8)
    return cv2.dilate(mask.astype(np.uint8), kernel) > 0


def _erode(mask: np.ndarray, radius: int) -> np.ndarray:
    kernel = np.ones((radius * 2 + 1, radius * 2 + 1), np.uint8)
    return cv2.erode(mask.astype(np.uint8), kernel) > 0


def _rgb_values_to_lab(values: np.ndarray) -> np.ndarray:
    image = values.astype(np.uint8).reshape(1, -1, 3)
    return cv2.cvtColor(image, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)


__all__ = ["CleaningValidationResult", "validate_cleaning_output"]
