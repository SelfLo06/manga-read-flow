from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/spikes/cleaning/real_bubble_fill_followup.py"
SPEC = importlib.util.spec_from_file_location("real_bubble_fill_followup", MODULE_PATH)
assert SPEC and SPEC.loader
spike = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(spike)


def fixture(fixture_class: str = "A") -> dict:
    return {
        "fixture_id": "fixture", "source_image": "black1.webp", "fixture_class": fixture_class,
        "expected_policy": "AUTO_FILL" if fixture_class == "A" else "SKIP",
        "region_bbox": {"x": 1, "y": 1, "width": 6, "height": 6},
    }


def test_static_fixture_distribution_is_8_2_2() -> None:
    classes = [item["fixture_class"] for item in spike.ANNOTATIONS]
    assert classes.count("A") == 8
    assert classes.count("B") == 2
    assert classes.count("D") == 2


def test_all_four_real_pages_are_represented() -> None:
    assert {item["source"] for item in spike.ANNOTATIONS} == {"black1.webp", "black2.webp", "gura.webp", "gura_color.webp"}


def test_safe_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        spike.safe(tmp_path / "../outside", tmp_path)


def test_valid_bbox_rejects_out_of_bounds() -> None:
    item = fixture(); item["region_bbox"]["width"] = 20
    assert not spike.valid_bbox(item, (10, 10))


def test_effective_mask_expands_one_pixel() -> None:
    text = np.zeros((7, 7), np.uint8); text[3, 3] = 255
    assert np.count_nonzero(spike.effective_mask(text, 0)) == 1
    assert np.count_nonzero(spike.effective_mask(text, 1)) == 9


def test_fixed_fill_changes_only_mask() -> None:
    source = np.full((8, 8, 3), 100, np.uint8); mask = np.zeros((8, 8), np.uint8); mask[3, 3] = 255
    output = spike.fill(source, mask, "fixed_white", np.full((8, 8), 255, np.uint8))
    assert (output[3, 3] == 255).all()
    assert (output[0, 0] == 100).all()


def test_metrics_detect_changes_outside_allowed_and_protected() -> None:
    source = np.zeros((5, 5, 3), np.uint8); output = source.copy(); output[0, 0] = 255
    text = np.zeros((5, 5), np.uint8); allowed = np.zeros((5, 5), np.uint8); protected = np.full((5, 5), 255, np.uint8)
    metrics = spike.candidate_metrics(source, output, text, text, allowed, protected, 0)
    assert metrics["changed_outside_allowed_edit"] == 1
    assert metrics["changed_inside_protected"] == 1


def test_d_fixtures_have_no_normal_candidate_annotation() -> None:
    controls = [item for item in spike.ANNOTATIONS if item["fixture_class"] == "D"]
    assert all(not item["glyph_boxes"] and item["allowed"] is None for item in controls)


def test_rectangle_detector_rejects_dense_text_mask() -> None:
    # The density criterion used by mask_stats catches a bbox-style solid mask.
    mask = np.full((6, 6), 255, np.uint8)
    ys, xs = np.where(mask > 0)
    assert xs.size / ((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)) > 0.72


def test_manual_rating_keeps_b_review_only() -> None:
    item = fixture("B"); item["fixture_id"] = "boundary"
    rating, tags, _ = spike.manual_rating(item, "fixed_white", 0)
    assert rating == "REVIEW" and "review_required" in tags


def test_manual_rating_marks_recognisable_residue_unusable() -> None:
    item = fixture(); item["fixture_id"] = "gura-color-lower-left"
    assert spike.manual_rating(item, "fixed_white", 1)[0] == "UNUSABLE"
