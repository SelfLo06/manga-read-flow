from __future__ import annotations

import numpy as np

from tools.spikes.text_seeded_container_association import goal6_mask_harness as mask


def _fragment(name: str, x: int, y: int) -> mask.Fragment:
    return mask.Fragment(name, ((x, y), (x + 5, y), (x + 5, y + 9), (x, y + 9)), 0.9)


def test_effective_mask_stays_inside_context_and_protected_is_excluded():
    image = np.full((50, 60, 3), 255, dtype=np.uint8)
    image[15:24, 20:25] = 0
    context_mask = np.zeros((50, 60), dtype=np.bool_)
    context_mask[5:45, 8:52] = True
    result = mask.process_context(
        image,
        mask.Context("container-001", ("f1",), context_mask),
        (_fragment("f1", 20, 15),),
        "COARSE_CONTAINER_SEARCH",
        mask.MaskPolicy(0, 1, 2, 0.95),
    )
    assert result.effective.any()
    assert np.all(~result.effective | context_mask)
    assert not np.any(result.effective & result.protected)
    assert result.fragment_status == {"f1": "assigned_core"}


def test_different_containers_produce_disjoint_effective_masks():
    image = np.full((40, 80, 3), 255, dtype=np.uint8)
    image[14:22, 12:16] = 0
    image[14:22, 60:64] = 0
    left = np.zeros((40, 80), dtype=np.bool_)
    right = np.zeros((40, 80), dtype=np.bool_)
    left[4:34, 4:35] = True
    right[4:34, 45:76] = True
    policy = mask.MaskPolicy(0, 1, 2, 0.95)
    left_result = mask.process_context(image, mask.Context("left", ("a",), left), (_fragment("a", 12, 14),), "COARSE_CONTAINER_SEARCH", policy, (right,))
    right_result = mask.process_context(image, mask.Context("right", ("b",), right), (_fragment("b", 60, 14),), "COARSE_CONTAINER_SEARCH", policy, (left,))
    mask.verify_disjoint((left_result, right_result))


def test_fill_never_changes_pixels_outside_effective_mask():
    image = np.full((20, 20, 3), 210, dtype=np.uint8)
    effective = np.zeros((20, 20), dtype=np.bool_)
    effective[8:12, 8:12] = True
    output = mask.fixed_white(image, effective)
    assert mask.changed_outside(image, output, effective) == 0


def test_bounded_support_is_never_e1_auto_path():
    image = np.full((40, 40, 3), 255, dtype=np.uint8)
    image[15:23, 17:22] = 0
    context = np.zeros((40, 40), dtype=np.bool_)
    context[5:35, 5:35] = True
    result = mask.process_context(
        image,
        mask.Context("support-001", ("f",), context),
        (_fragment("f", 17, 15),),
        "BOUNDED_SUPPORT",
        mask.MaskPolicy(0, 1, 2, 0.95),
    )
    assert result.risk == "E3"
    assert result.decision == "REVIEW_REQUIRED"
