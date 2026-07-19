from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT_DIR = Path(__file__).resolve().parents[4]
HARNESS_PATH = (
    ROOT_DIR
    / "tools"
    / "experiments"
    / "120-grouping"
    / "text_seeded_container_association"
    / "harness.py"
)
FOCUSED_CORRECTION_PATH = HARNESS_PATH.with_name("focused_correction.py")


def load_harness(name: str = "text_seeded_container_harness"):
    spec = importlib.util.spec_from_file_location(name, HARNESS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_focused_correction(name: str = "text_seeded_container_focused_correction"):
    spec = importlib.util.spec_from_file_location(name, FOCUSED_CORRECTION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fragment(harness, fragment_id: str, x: int, y: int, width: int, height: int, group_id: str):
    return harness.Fragment(
        fragment_id=fragment_id,
        bbox=(x, y, width, height),
        polygon=((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        upstream_group_id=group_id,
        score=None,
    )


def page(harness, fragments, *, width: int = 180, height: int = 120, image=None):
    if image is None:
        image = np.full((height, width, 3), 255, dtype=np.uint8)
    return harness.PageInput(asset_id="cal-01", image=image, fragments=tuple(fragments))


def test_pair_scorer_uses_frozen_features_and_not_a_label_argument():
    harness = load_harness()
    left = fragment(harness, "p1", 25, 20, 18, 70, "g1")
    right = fragment(harness, "p2", 48, 22, 18, 68, "g1")

    evidence = harness.score_same_container(page(harness, [left, right]), left, right)

    assert set(evidence.features) == {
        "same_upstream_group",
        "orientation_compatibility",
        "scale_similarity",
        "proximity",
        "edge_corridor",
    }
    assert evidence.features["same_upstream_group"] == 1.0
    assert evidence.score >= 0.80
    with pytest.raises(TypeError):
        harness.score_same_container(page(harness, [left, right]), left, right, label="same")


def test_dark_separator_reduces_edge_corridor_score():
    harness = load_harness("text_seeded_container_harness_separator")
    left = fragment(harness, "p1", 35, 20, 18, 70, "g1")
    right = fragment(harness, "p2", 125, 20, 18, 70, "g2")
    blank = np.full((120, 180, 3), 255, dtype=np.uint8)
    separated = blank.copy()
    separated[:, 88:92] = 0

    blank_score = harness.score_same_container(page(harness, [left, right], image=blank), left, right)
    separated_score = harness.score_same_container(page(harness, [left, right], image=separated), left, right)

    assert separated_score.features["edge_corridor"] < blank_score.features["edge_corridor"]
    assert separated_score.score < blank_score.score


def test_calibration_selects_thresholds_only_from_calibration_examples():
    harness = load_harness("text_seeded_container_harness_calibration")
    examples = [
        harness.CalibrationExample("cal-01", "d1", "different", 0.44),
        harness.CalibrationExample("cal-01", "d2", "different", 0.48),
        harness.CalibrationExample("cal-02", "s1", "same", 0.88),
        harness.CalibrationExample("cal-02", "s2", "same", 0.91),
    ]

    result = harness.calibrate_thresholds(examples)

    assert result.status == "FROZEN"
    assert result.thresholds.different == 0.50
    assert result.thresholds.same == 0.85
    assert result.margin == pytest.approx(0.40)


def test_calibration_rejects_r0_or_evaluation_asset_ids():
    harness = load_harness("text_seeded_container_harness_calibration_leak")

    with pytest.raises(harness.HarnessStop, match="calibration asset"):
        harness.calibrate_thresholds(
            [
                harness.CalibrationExample("case-01", "leak", "different", 0.1),
                harness.CalibrationExample("cal-02", "s1", "same", 0.9),
            ]
        )


def test_calibration_without_separation_freezes_all_uncertain():
    harness = load_harness("text_seeded_container_harness_no_separation")
    result = harness.calibrate_thresholds(
        [
            harness.CalibrationExample("cal-01", "d1", "different", 0.74),
            harness.CalibrationExample("cal-02", "s1", "same", 0.72),
        ]
    )

    assert result.status == "ALL_UNCERTAIN"
    assert result.thresholds.classify(0.0) == "uncertain"
    assert result.thresholds.classify(1.0) == "uncertain"


def test_b0_regions_cover_every_input_fragment_and_clip_to_image():
    harness = load_harness("text_seeded_container_harness_b0")
    fragments = [
        fragment(harness, "p1", 0, 0, 20, 70, "g1"),
        fragment(harness, "p2", 150, 50, 25, 65, "g2"),
    ]

    result = harness.run_b0(page(harness, fragments))

    assert result.method_id == "B0"
    assert sorted(fid for region in result.regions for fid in region.fragment_ids) == ["p1", "p2"]
    assert all(region.mask.shape == (120, 180) for region in result.regions)
    assert all(region.mask.dtype == np.bool_ for region in result.regions)
    assert all(region.mask.any() for region in result.regions)


def test_b1_seeded_watershed_returns_disjoint_regions():
    harness = load_harness("text_seeded_container_harness_b1")
    fragments = [
        fragment(harness, "p1", 25, 20, 18, 70, "g1"),
        fragment(harness, "p2", 130, 20, 18, 70, "g2"),
    ]

    result = harness.run_b1(page(harness, fragments))

    assert result.method_id == "B1"
    assert len(result.regions) == 2
    assert not np.logical_and(result.regions[0].mask, result.regions[1].mask).any()
    assert all(region.mask.any() for region in result.regions)


def test_p1_merges_high_same_probability_sources_before_propagation():
    harness = load_harness("text_seeded_container_harness_p1_merge")
    fragments = [
        fragment(harness, "p1", 35, 20, 18, 70, "g1"),
        fragment(harness, "p2", 58, 22, 18, 68, "g1"),
    ]
    thresholds = harness.SameContainerThresholds(different=0.50, same=0.85)

    result = harness.run_p1(page(harness, fragments), thresholds)

    assert result.method_id == "P1"
    assert len(result.regions) == 1
    assert result.regions[0].fragment_ids == ("p1", "p2")
    assert result.same_container_decisions[0].decision == "same"
    assert not result.virtual_boundary.any()


def test_p1_keeps_low_probability_sources_separate_and_emits_virtual_boundary():
    harness = load_harness("text_seeded_container_harness_p1_compete")
    fragments = [
        fragment(harness, "p1", 25, 20, 18, 70, "g1"),
        fragment(harness, "p2", 135, 20, 18, 70, "g2"),
    ]
    thresholds = harness.SameContainerThresholds(different=0.50, same=0.85)

    result = harness.run_p1(page(harness, fragments), thresholds)

    assert len(result.regions) == 2
    assert result.same_container_decisions[0].decision == "different"
    assert result.virtual_boundary.any()
    assert not np.logical_and(result.regions[0].mask, result.regions[1].mask).any()


def test_p1_abstains_when_pair_score_is_between_thresholds():
    harness = load_harness("text_seeded_container_harness_p1_uncertain")
    fragments = [
        fragment(harness, "p1", 25, 20, 18, 70, "g1"),
        fragment(harness, "p2", 80, 20, 18, 70, "g2"),
    ]
    thresholds = harness.SameContainerThresholds(different=0.20, same=0.90)

    result = harness.run_p1(page(harness, fragments), thresholds)

    assert any(item.decision == "uncertain" for item in result.same_container_decisions)
    assert result.recommended_decision == "REVIEW_REQUIRED"
    assert "uncertain_same_container_pair" in result.abstention_reasons


def test_output_json_uses_rle_and_does_not_claim_cleaning_or_pixel_text_mask():
    harness = load_harness("text_seeded_container_harness_output")
    result = harness.run_b0(
        page(harness, [fragment(harness, "p1", 25, 20, 18, 70, "g1")])
    )

    payload = result.to_jsonable()

    assert "mask_rle" in payload["regions"][0]
    assert "mask" not in payload["regions"][0]
    assert "cleaned_image" not in payload
    assert "pixel_text_mask" not in payload
    assert payload["recommended_decision"] in {
        "LOW_RISK_ASSOCIATION_CANDIDATE",
        "REVIEW_REQUIRED",
        "SKIP",
    }


def test_corrected_pair_scorer_can_merge_compatible_cross_upstream_groups():
    harness = load_focused_correction("text_seeded_container_harness_corrected_pair")
    left = fragment(harness, "p1", 50, 30, 18, 80, "g1")
    right = fragment(harness, "p2", 70, 32, 18, 78, "g2")
    blank = np.full((150, 180, 3), 255, dtype=np.uint8)
    separated = blank.copy()
    separated[:, 68:70] = 0

    compatible = harness.score_same_container_v2(
        page(harness, [left, right], width=180, height=150, image=blank),
        left,
        right,
    )
    blocked = harness.score_same_container_v2(
        page(harness, [left, right], width=180, height=150, image=separated),
        left,
        right,
    )

    assert compatible.features["same_upstream_group"] == 0.0
    assert compatible.score >= 0.75
    assert blocked.score < compatible.score


def test_group_scorer_uses_conservative_minimum_member_pair_score():
    harness = load_focused_correction("text_seeded_container_harness_group_pair")
    left_items = (
        fragment(harness, "l1", 20, 25, 18, 70, "g1"),
        fragment(harness, "l2", 42, 25, 18, 70, "g1"),
    )
    right_items = (fragment(harness, "r1", 90, 25, 18, 70, "g2"),)
    image = np.full((120, 140, 3), 255, dtype=np.uint8)
    image[:, 67:70] = 0
    input_page = page(harness, [*left_items, *right_items], width=140, height=120, image=image)

    member_scores = [
        harness.score_same_container_v2(input_page, item, right_items[0]).score
        for item in left_items
    ]
    group_score = harness.score_group_same_container_v2(input_page, left_items, right_items)

    assert group_score.score == min(member_scores)
    assert group_score.features["member_pair_count"] == 2.0


def test_corrected_p1_bounds_free_text_support_without_touching_roi_edges():
    harness = load_focused_correction("text_seeded_container_harness_corrected_support")
    seed = fragment(harness, "p1", 92, 78, 14, 64, "g1")
    policy = harness.CorrectedP1Policy(
        thresholds=harness.SameContainerThresholds(different=0.40, same=0.75),
        max_geodesic_cost=20.0,
        support_padding_scale=2.0,
        max_support_area_ratio=0.20,
        max_merged_support_area_ratio=0.50,
        regionless_uncertain_orientation=True,
        regionless_extreme_span_ratio=0.90,
        regionless_seed_bbox_area_ratio=0.20,
    )

    result = harness.run_corrected_p1(
        page(harness, [seed], width=200, height=220),
        policy,
    )

    assert result.method_id == "P1-corrected-v1"
    assert len(result.regions) == 1
    mask = result.regions[0].mask
    assert mask is not None
    assert mask.mean() <= 0.20
    assert not mask[0, :].any()
    assert not mask[-1, :].any()
    assert not mask[:, 0].any()
    assert not mask[:, -1].any()
    assert result.recommended_decision == "REVIEW_REQUIRED"
    assert "free_text_requires_review" in result.abstention_reasons


def test_corrected_p1_merges_cross_group_sources_before_bounded_propagation():
    harness = load_focused_correction("text_seeded_container_harness_corrected_merge")
    fragments = [
        fragment(harness, "p1", 70, 40, 18, 80, "g1"),
        fragment(harness, "p2", 91, 42, 18, 78, "g2"),
    ]
    policy = harness.CorrectedP1Policy(
        thresholds=harness.SameContainerThresholds(different=0.40, same=0.75),
        max_geodesic_cost=20.0,
        support_padding_scale=2.0,
        max_support_area_ratio=0.40,
        max_merged_support_area_ratio=0.50,
        regionless_uncertain_orientation=True,
        regionless_extreme_span_ratio=0.90,
        regionless_seed_bbox_area_ratio=0.20,
    )

    result = harness.run_corrected_p1(
        page(harness, fragments, width=200, height=180),
        policy,
    )

    assert len(result.regions) == 1
    assert result.regions[0].fragment_ids == ("p1", "p2")
    assert result.same_container_decisions[0].decision == "same"
    assert not result.virtual_boundary.any()


def test_corrected_p1_emits_regionless_abstention_for_isolated_uncertain_seed():
    harness = load_focused_correction("text_seeded_container_harness_regionless")
    uncertain_seed = fragment(harness, "fp1", 80, 70, 32, 34, "g1")
    policy = harness.CorrectedP1Policy(
        thresholds=harness.SameContainerThresholds(different=0.40, same=0.75),
        max_geodesic_cost=20.0,
        support_padding_scale=2.0,
        max_support_area_ratio=0.20,
        max_merged_support_area_ratio=0.50,
        regionless_uncertain_orientation=True,
        regionless_extreme_span_ratio=0.90,
        regionless_seed_bbox_area_ratio=0.20,
    )

    result = harness.run_corrected_p1(
        page(harness, [uncertain_seed], width=200, height=180),
        policy,
    )
    payload = result.to_jsonable()

    assert len(result.regions) == 1
    assert result.regions[0].mask is None
    assert result.recommended_decision == "SKIP"
    assert "regionless_uncertain_isolated_seed" in result.abstention_reasons
    assert payload["regions"][0]["mask_rle"] is None


def test_prepared_corrected_p1_matches_direct_execution():
    harness = load_focused_correction("text_seeded_container_harness_prepared")
    fragments = [
        fragment(harness, "p1", 70, 40, 18, 80, "g1"),
        fragment(harness, "p2", 91, 42, 18, 78, "g2"),
    ]
    policy = harness.CorrectedP1Policy(
        thresholds=harness.SameContainerThresholds(different=0.40, same=0.75),
        max_geodesic_cost=16.0,
        support_padding_scale=1.5,
        max_support_area_ratio=0.40,
        max_merged_support_area_ratio=0.50,
        regionless_uncertain_orientation=True,
        regionless_extreme_span_ratio=0.90,
        regionless_seed_bbox_area_ratio=0.20,
    )
    input_page = page(harness, fragments, width=200, height=180)

    direct = harness.run_corrected_p1(input_page, policy)
    prepared = harness.run_prepared_corrected_p1(
        harness.prepare_corrected_p1(input_page, policy.thresholds),
        policy,
    )

    assert direct.to_jsonable() == prepared.to_jsonable()


def test_corrected_p1_abstains_on_single_extreme_span_seed():
    harness = load_focused_correction("text_seeded_container_harness_extreme_span")
    seed = fragment(harness, "title", 20, 10, 25, 180, "g1")
    policy = harness.CorrectedP1Policy(
        thresholds=harness.SameContainerThresholds(different=0.30, same=0.85),
        max_geodesic_cost=8.0,
        support_padding_scale=0.75,
        max_support_area_ratio=0.50,
        max_merged_support_area_ratio=0.50,
        regionless_uncertain_orientation=True,
        regionless_extreme_span_ratio=0.90,
        regionless_seed_bbox_area_ratio=0.20,
    )

    result = harness.run_corrected_p1(
        page(harness, [seed], width=100, height=200),
        policy,
    )

    assert result.regions[0].mask is None
    assert result.recommended_decision == "SKIP"
    assert "regionless_extreme_span_seed" in result.abstention_reasons
