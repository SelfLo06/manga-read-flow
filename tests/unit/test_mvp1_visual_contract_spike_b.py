from __future__ import annotations

import numpy as np
import pytest

from tools.spikes.mvp1_visual_contract import spike_b


def _square(shape: tuple[int, int], y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    mask[y0:y1, x0:x1] = True
    return mask


def test_changed_pixel_mask_is_recomputed_from_input_and_output() -> None:
    source = np.full((8, 8, 3), 240, dtype=np.uint8)
    output = source.copy()
    output[2:4, 3:6] = 250

    changed = spike_b.actual_changed_pixel_mask(source, output)

    assert changed.sum() == 6
    assert spike_b.validate_changed_mask(changed, _square((8, 8), 2, 4, 3, 6)) == []
    assert spike_b.validate_changed_mask(changed, _square((8, 8), 2, 3, 3, 6)) == [
        "ACTUAL_CHANGED_MASK_MISMATCH"
    ]


def test_required_text_residue_negative_and_positive_controls_are_distinguished() -> None:
    required = _square((12, 12), 3, 8, 4, 7)
    clean = np.full((12, 12, 3), 245, dtype=np.uint8)
    residual = clean.copy()
    residual[4:6, 5:7] = 20

    clean_report = spike_b.evaluate_residue(required, clean, max_residual_luminance=180)
    positive_report = spike_b.evaluate_residue(required, residual, max_residual_luminance=180)

    assert clean_report["decision"] == "PASS"
    assert clean_report["residual_required_pixels"] == 0
    assert positive_report["decision"] == "BLOCK"
    assert positive_report["issue_code"] == "cleaning_residue"
    assert positive_report["residual_required_pixels"] == 4


def test_safe_edit_evidence_keeps_protected_and_uncertainty_separate() -> None:
    text = _square((15, 15), 4, 11, 4, 11)
    protected = _square((15, 15), 4, 6, 4, 11)
    uncertainty = _square((15, 15), 9, 11, 4, 11)

    evidence = spike_b.build_safe_edit_evidence(text, protected, uncertainty)

    assert evidence["text_core_pixels"] == 49
    assert evidence["protected_overlap_pixels"] == 14
    assert evidence["uncertainty_overlap_pixels"] == 14
    assert evidence["safe_edit_pixels"] == 21
    assert evidence["decision_basis"] == "PIXEL_INTERSECTION_NOT_INSTANCE_RATIO"


def test_required_text_completeness_blocks_a_cleaning_pass_when_safe_edit_is_smaller() -> None:
    """Regression: safe-edit pixels are not the same thing as required text."""

    required = _square((12, 12), 3, 8, 4, 8)
    protected = _square((12, 12), 3, 4, 4, 8)
    safe = spike_b.build_safe_edit_evidence(required, protected, np.zeros_like(required))
    output = np.full((12, 12, 3), 245, dtype=np.uint8)
    output[protected] = 20  # The controlled writeback deliberately cannot touch it.

    completeness = spike_b.evaluate_required_text_completeness(required, safe["_safe_edit_mask"])
    residue = spike_b.evaluate_residue(required, output, max_residual_luminance=180)

    assert completeness["decision"] == "INCOMPLETE_REVIEW"
    assert completeness["unsafe_required_pixels"] == 4
    assert residue["decision"] == "BLOCK"
    assert residue["issue_code"] == "cleaning_residue"


def test_visible_glyph_support_detects_a_light_halo_left_after_dark_core_is_removed() -> None:
    """Regression: a dark core is not the complete visible glyph domain."""

    instance = _square((16, 16), 2, 14, 2, 14)
    core = _square((16, 16), 7, 9, 7, 9)
    support = spike_b.expand_visible_text_support(core, instance, dilation_px=2)
    output = np.full((16, 16, 3), 245, dtype=np.uint8)
    output[support & ~core] = 220  # Light antialias/stroke remains recognizable.

    report = spike_b.evaluate_residue(support, output, max_residual_luminance=240)

    assert int(support.sum()) > int(core.sum())
    assert report["decision"] == "BLOCK"
    assert report["residual_required_pixels"] == int((support & ~core).sum())


def test_glyph_validator_rejects_missing_duplicate_wrong_instance_overflow_and_wrong_region() -> None:
    region_a = _square((20, 20), 3, 17, 3, 17)
    region_b = _square((20, 20), 3, 17, 0, 2)
    glyph = _square((20, 20), 7, 10, 7, 10)
    binding_a = spike_b.region_binding("instance-a", "revision-a", region_a)
    binding_b = spike_b.region_binding("instance-b", "revision-b", region_b)

    normal = spike_b.validate_glyph_ledger(
        expected={"s1": binding_a},
        glyphs=[spike_b.glyph_evidence("s1", binding_a, glyph)],
        region_masks={binding_a["region_hash"]: region_a},
        boundary_masks={binding_a["region_hash"]: np.zeros_like(region_a)},
    )
    assert normal == []

    assert "segment_missing" in spike_b.validate_glyph_ledger(
        expected={"s1": binding_a}, glyphs=[], region_masks={}, boundary_masks={}
    )
    assert "segment_rendered_multiple_times" in spike_b.validate_glyph_ledger(
        expected={"s1": binding_a},
        glyphs=[spike_b.glyph_evidence("s1", binding_a, glyph)] * 2,
        region_masks={binding_a["region_hash"]: region_a},
        boundary_masks={binding_a["region_hash"]: np.zeros_like(region_a)},
    )
    assert "wrong_instance_rendering" in spike_b.validate_glyph_ledger(
        expected={"s1": binding_a},
        glyphs=[spike_b.glyph_evidence("s1", binding_b, glyph)],
        region_masks={binding_b["region_hash"]: region_b},
        boundary_masks={binding_b["region_hash"]: np.zeros_like(region_b)},
    )
    outside = glyph.copy()
    outside[1, 1] = True
    assert "glyph_overflow" in spike_b.validate_glyph_ledger(
        expected={"s1": binding_a},
        glyphs=[spike_b.glyph_evidence("s1", binding_a, outside)],
        region_masks={binding_a["region_hash"]: region_a},
        boundary_masks={binding_a["region_hash"]: np.zeros_like(region_a)},
    )
    wrong_validator = spike_b.glyph_evidence("s1", binding_a, glyph)
    wrong_validator["validator_binding"] = binding_b
    assert "validator_region_binding_mismatch" in spike_b.validate_glyph_ledger(
        expected={"s1": binding_a},
        glyphs=[wrong_validator],
        region_masks={binding_a["region_hash"]: region_a},
        boundary_masks={binding_a["region_hash"]: np.zeros_like(region_a)},
    )


def test_glyph_validator_never_accepts_preclipped_empty_evidence() -> None:
    region = _square((10, 10), 2, 8, 2, 8)
    binding = spike_b.region_binding("instance-a", "revision-a", region)
    empty = spike_b.glyph_evidence("s1", binding, np.zeros_like(region))

    issues = spike_b.validate_glyph_ledger(
        expected={"s1": binding},
        glyphs=[empty],
        region_masks={binding["region_hash"]: region},
        boundary_masks={binding["region_hash"]: np.zeros_like(region)},
    )

    assert "missing_glyph" in issues


def test_correction_reservation_is_exactly_once_and_replay_safe() -> None:
    first = spike_b.reserve_correction([], root_issue="glyph_overflow", idempotency_key="k1")
    replay = spike_b.reserve_correction([first], root_issue="glyph_overflow", idempotency_key="k1")
    second = spike_b.reserve_correction([first], root_issue="glyph_overflow", idempotency_key="k2")

    assert first["decision"] == "RESERVED"
    assert first["ordinal"] == 1
    assert replay["decision"] == "REPLAY"
    assert replay["reservation_id"] == first["reservation_id"]
    assert second["decision"] == "REJECTED_SECOND_AUTOMATIC_CORRECTION"


def test_mask_shape_mismatch_is_a_hard_contract_error() -> None:
    with pytest.raises(spike_b.SpikeBStop, match="shape"):
        spike_b.build_safe_edit_evidence(
            np.zeros((2, 2), dtype=bool),
            np.zeros((2, 3), dtype=bool),
            np.zeros((2, 2), dtype=bool),
        )
