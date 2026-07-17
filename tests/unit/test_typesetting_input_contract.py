import numpy as np

from tools.spikes import typesetting_input_contract as contract


def _fragment(fragment_id, x, y, width=40, height=120):
    return {"fragment_id": fragment_id, "bbox": {"x": x, "y": y, "width": width, "height": height}}


def test_vertical_baseline_jump_preserves_two_segments():
    fragments = {
        "p1": _fragment("p1", 110, 10),
        "p2": _fragment("p2", 70, 12),
        "p3": _fragment("p3", 30, 180),
    }
    group = {"group_id": "g1", "orientation": "vertical", "ordered_fragment_ids": ["p1", "p2", "p3"]}
    assert contract.split_group_segments(group, fragments) == [["p1", "p2"], ["p3"]]


def test_validator_rejects_overflow_and_boundary_touch():
    region = np.zeros((30, 30), dtype=np.bool_)
    region[5:25, 5:25] = True
    region_hash = contract.mask_sha256(region)
    safe = np.zeros_like(region)
    safe[12:15, 12:15] = True
    assert contract.validate_glyph(region, safe, "r1", region_hash)["passed"] is True

    overflow = safe.copy()
    overflow[0, 0] = True
    assert contract.validate_glyph(region, overflow, "r1", region_hash)["passed"] is False

    touch = np.zeros_like(region)
    touch[5, 10] = True
    result = contract.validate_glyph(region, touch, "r1", region_hash)
    assert result["passed"] is False
    assert result["boundary_touch"] is True


def test_bubble_region_uses_seeded_bright_component():
    image = np.zeros((80, 120, 3), dtype=np.uint8)
    yy, xx = np.ogrid[:80, :120]
    bubble = (xx - 35) ** 2 / 25**2 + (yy - 40) ** 2 / 30**2 <= 1
    other = (xx - 95) ** 2 / 15**2 + (yy - 40) ** 2 / 20**2 <= 1
    image[bubble | other] = 255
    region = contract.extract_bubble_region(image, {"x": 25, "y": 25, "width": 20, "height": 30})
    assert region[40, 35]
    assert not region[40, 95]


def test_bubble_region_does_not_merge_with_white_page_background():
    image = np.full((100, 140, 3), 255, dtype=np.uint8)
    yy, xx = np.ogrid[:100, :140]
    boundary = np.abs(((xx - 45) ** 2 / 28**2 + (yy - 50) ** 2 / 35**2) - 1) < 0.08
    image[boundary] = 0
    region = contract.extract_bubble_region(image, {"x": 35, "y": 35, "width": 20, "height": 30})
    assert region[50, 45]
    assert not region[0, 0]
