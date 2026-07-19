from __future__ import annotations

import numpy as np
import pytest

from tools.experiments.grouping_120.text_seeded_container_association import harness as base
from tools.experiments.grouping_120.text_seeded_container_association import routed_association as routed


def policy(**overrides):
    values = {
        "container_boundary_threshold": 0.50,
        "extreme_seed_span_ratio": 0.85,
        "extreme_seed_area_ratio": 0.65,
        "max_support_group_count": 2,
        "support_padding_scale": 0.15,
        "support_max_area_ratio": 0.20,
        "topology_different_threshold": 0.20,
        "topology_same_threshold": 0.85,
    }
    values.update(overrides)
    return routed.RoutedPolicy(**values)


def fragment(fragment_id="p1", bbox=(40, 40, 20, 50), group="g1"):
    x, y, width, height = bbox
    return base.Fragment(
        fragment_id,
        bbox,
        ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        group,
    )


def test_no_seed_is_regionless_abstention():
    page = base.PageInput("case-99", np.full((120, 120, 3), 255, dtype=np.uint8), ())

    result = routed.run_routed_association(page, policy())

    assert result.route == "REGIONLESS_ABSTENTION"
    assert result.container_regions == result.support_regions == ()
    assert result.recommended_decision == "SKIP"
    assert result.goal6_trial_eligible is False


def test_extreme_seed_is_regionless_before_spatial_search():
    page = base.PageInput(
        "cal-99",
        np.full((100, 100, 3), 255, dtype=np.uint8),
        (fragment(bbox=(0, 0, 100, 90)),),
    )

    result = routed.run_routed_association(page, policy())

    assert result.route == "REGIONLESS_ABSTENTION"
    assert result.abstention_reasons == ("extreme_seed_geometry",)


def test_compact_seed_without_boundary_gets_bounded_support():
    page = base.PageInput(
        "cal-98",
        np.full((160, 200, 3), 255, dtype=np.uint8),
        (fragment(bbox=(80, 60, 30, 40)),),
    )

    result = routed.run_routed_association(page, policy())

    assert result.route == "BOUNDED_SUPPORT"
    assert len(result.support_regions) == 1
    assert result.container_regions == ()
    assert result.support_regions[0].evidence["touches_roi_edge"] is False


def test_pair_aggregate_requires_multiple_members_for_same():
    assert routed.classify_pair_aggregate((0.90,), policy()) == "uncertain"
    assert routed.classify_pair_aggregate((0.10,), policy()) == "different"
    assert routed.classify_pair_aggregate((0.20, 0.88), policy()) == "same"


def test_result_rejects_goal6_eligibility_for_uncertain_topology():
    mask = np.zeros((20, 20), dtype=np.bool_)
    mask[5:15, 5:15] = True
    region = routed.SpatialRegion("r1", ("p1",), mask, {})

    with pytest.raises(base.HarnessStop, match="unsafe Goal 6 eligibility"):
        routed.RoutedResult(
            "case-99", "COARSE_CONTAINER_SEARCH", 0.8, ("p1",), ("g1",),
            (region,), (), "uncertain", (), "REVIEW_REQUIRED", True, (), {},
        )
