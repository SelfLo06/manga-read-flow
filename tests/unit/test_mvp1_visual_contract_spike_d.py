from __future__ import annotations

import numpy as np

from tools.spikes.mvp1_visual_contract import spike_d


def _mask(shape: tuple[int, int], y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    mask[y0:y1, x0:x1] = True
    return mask


def _scene() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    source = np.full((32, 32, 3), 245, dtype=np.uint8)
    instance = _mask((32, 32), 2, 30, 2, 30)
    candidate = _mask((32, 32), 13, 19, 14, 18)
    protected = _mask((32, 32), 3, 5, 3, 5)
    uncertainty = _mask((32, 32), 27, 29, 27, 29)
    source[candidate] = (30, 30, 30)
    return source, instance, candidate, protected, uncertainty


def test_real_cleaner_writes_only_candidate_and_is_safe_bounded() -> None:
    source, instance, candidate, protected, uncertainty = _scene()
    output, evidence = spike_d.border_sampled_fill(source, candidate, instance, protected, uncertainty)
    changed = spike_d.actual_changed_mask(source, output)

    assert np.array_equal(changed, candidate)
    assert evidence["sampling_region_pixels"] > 0
    assert not np.any(changed & protected)
    assert not np.any(changed & uncertainty)


def test_structure_gate_rejects_outside_safe_and_protected_changes() -> None:
    source, _, candidate, protected, uncertainty = _scene()
    output = source.copy()
    output[candidate] = (245, 245, 245)
    output[0, 0] = (0, 0, 0)
    output[protected] = (0, 0, 0)
    result = spike_d.evaluate_structure_damage(source, output, candidate, protected, uncertainty)

    assert result["decision"] == "BLOCK"
    assert "outside_safe_edit" in result["reason_codes"]
    assert "protected_structure_damage" in result["reason_codes"]


def test_background_gate_rejects_obvious_wrong_fill_and_allows_local_fill() -> None:
    source, instance, candidate, protected, uncertainty = _scene()
    correct, background = spike_d.border_sampled_fill(source, candidate, instance, protected, uncertainty)
    wrong = source.copy()
    wrong[candidate] = (20, 20, 20)

    correct_result = spike_d.evaluate_background_consistency(correct, candidate, background)
    wrong_result = spike_d.evaluate_background_consistency(wrong, candidate, background)

    assert correct_result["decision"] == "PASS"
    assert correct_result["seam_delta_to_local_background"] <= spike_d.BACKGROUND_DELTA_MAX
    assert wrong_result["decision"] == "BLOCK"
    assert wrong_result["issue_code"] == "background_inconsistency"


def test_actual_changed_mask_is_recomputed_from_images() -> None:
    source, _, candidate, _, _ = _scene()
    output = source.copy()
    output[candidate] = (245, 245, 245)

    assert np.array_equal(spike_d.actual_changed_mask(source, output), candidate)
