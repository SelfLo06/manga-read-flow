from __future__ import annotations

import numpy as np

from tools.experiments.cleaning_150.visual_contract import spike_b, spike_c


def _mask(shape: tuple[int, int], y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    value = np.zeros(shape, dtype=bool)
    value[y0:y1, x0:x1] = True
    return value


def _scene() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    image = np.full((32, 32, 3), 245, dtype=np.uint8)
    instance = _mask((32, 32), 3, 29, 3, 29)
    core = _mask((32, 32), 13, 19, 14, 18)
    halo = _mask((32, 32), 11, 21, 12, 20) & ~core
    image[core] = (30, 30, 30)
    image[halo] = (220, 220, 220)
    return image, instance, core, halo


def test_a_complete_visible_support_removal_passes() -> None:
    source, instance, core, _ = _scene()
    support, background = spike_c.build_visible_support(source, core, instance)
    output = np.full_like(source, 245)

    result = spike_c.evaluate_visible_residue(source, output, support, background)

    assert result["decision"] == "PASS"
    assert result["residue_component_count"] == 0


def test_b_dark_core_only_removal_with_halo_remaining_blocks() -> None:
    source, instance, core, halo = _scene()
    support, background = spike_c.build_visible_support(source, core, instance)
    output = np.full_like(source, 245)
    output[halo] = source[halo]

    result = spike_c.evaluate_visible_residue(source, output, support, background)

    assert result["decision"] == "BLOCK"
    assert result["issue_code"] == "cleaning_residue"
    assert result["residual_support_pixels"] >= int(halo.sum())


def test_c_near_white_residue_is_detected_relative_to_local_background() -> None:
    source = np.full((24, 24, 3), 238, dtype=np.uint8)
    instance = _mask((24, 24), 2, 22, 2, 22)
    core = _mask((24, 24), 9, 14, 10, 14)
    source[core] = (222, 222, 222)
    support, background = spike_c.build_visible_support(source, core, instance)
    output = np.full_like(source, 238)
    output[support] = 227

    result = spike_c.evaluate_visible_residue(source, output, support, background)

    assert result["decision"] == "BLOCK"
    assert result["max_local_contrast"] >= spike_c.DEFAULT_PROFILE.min_local_contrast


def test_d_connected_character_or_key_stroke_blocks_but_e_noise_passes() -> None:
    source, instance, core, _ = _scene()
    support, background = spike_c.build_visible_support(source, core, instance)
    stroke = _mask(core.shape, 14, 18, 15, 17)
    character = np.full_like(source, 245)
    character[stroke] = (70, 70, 70)
    noise = np.full_like(source, 245)
    noise[5, 5] = (225, 225, 225)  # outside support and a one-pixel background change

    assert spike_c.evaluate_visible_residue(source, character, support, background)["decision"] == "BLOCK"
    assert spike_c.evaluate_visible_residue(source, noise, support, background)["decision"] == "PASS"


def test_f_incomplete_required_safe_never_enters_cleaning_pass() -> None:
    source, instance, core, _ = _scene()
    support, _ = spike_c.build_visible_support(source, core, instance)
    safe = support.copy()
    safe[15:17, 15:17] = False

    completeness = spike_c.required_safe_completeness(support, safe)

    assert completeness["decision"] == "INCOMPLETE_REVIEW"
    assert completeness["issue_code"] == "required_text_not_safely_editable"


def test_issue_draft_contains_qualitycheck_evidence_without_workflow_decision() -> None:
    source, instance, core, halo = _scene()
    support, background = spike_c.build_visible_support(source, core, instance)
    output = np.full_like(source, 245)
    output[halo] = source[halo]
    residue = spike_c.evaluate_visible_residue(source, output, support, background)
    draft = spike_c.cleaning_residue_issue_draft(
        page_id="p", segment_id="s", binding={"instance_id": "i", "region_revision_id": "r", "region_hash": "h"},
        residue=residue, completeness=spike_c.required_safe_completeness(support, support),
        source=source, output=output,
    )

    assert draft["root_issue"] == "cleaning_residue"
    assert draft["affected_segment_id"] == "s"
    assert "retry" not in draft and "fallback" not in draft and "workflow_decision" not in draft
    assert draft["residue_component_count"] >= 1


def test_g_h_spike_b_instance_and_glyph_regressions_remain_rejected() -> None:
    region_a = _mask((16, 16), 2, 14, 2, 14)
    region_b = _mask((16, 16), 2, 14, 0, 1)
    binding_a = spike_b.region_binding("instance-a", "revision-a", region_a)
    binding_b = spike_b.region_binding("instance-b", "revision-b", region_b)
    glyph = _mask((16, 16), 6, 9, 6, 9)
    wrong = spike_b.glyph_evidence("segment-a", binding_b, glyph)

    issues = spike_b.validate_glyph_ledger(
        expected={"segment-a": binding_a},
        glyphs=[wrong],
        region_masks={binding_b["region_hash"]: region_b},
        boundary_masks={binding_b["region_hash"]: np.zeros_like(region_b)},
    )

    assert "wrong_instance_rendering" in issues
    assert all(spike_c._spike_b_regression().values())
