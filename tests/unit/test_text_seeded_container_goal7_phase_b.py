from __future__ import annotations

import numpy as np

from tools.spikes.text_seeded_container_association import goal7_phase_b as phase_b


def test_parse_form_reads_frozen_choice_fields():
    content = """## G7-001 — case-10 / case-10__lc001
- ContentRole: `SFX_DECORATIVE`
- ExpectedTask: `LOCAL_SKIP`
- Topology: `N_A`
- PhaseB: `NO`
- Note: control
"""

    labels = phase_b.parse_form(content)

    assert labels["G7-001"] == {
        "content_role": "SFX_DECORATIVE",
        "expected_task": "LOCAL_SKIP",
        "topology": "N_A",
        "phase_b": "NO",
        "note": "control",
    }


def test_l1_shape_never_exceeds_pixel_budget():
    shape, scale = phase_b.l1_shape(2000, 1400, 262_144)

    assert shape[0] * shape[1] <= 262_144
    assert 0.0 < scale < 1.0


def test_markers_include_border_background_and_distinct_group_sources():
    groups = [
        {"group_id": "g1", "fragment_boxes": [(20, 20, 20, 60)]},
        {"group_id": "g2", "fragment_boxes": [(100, 20, 20, 60)]},
    ]

    markers, labels = phase_b.build_markers((120, 160), groups)

    assert np.all(markers[0, :] == 1)
    assert np.all(markers[-1, :] == 1)
    assert labels == {"g1": 2, "g2": 3}
    assert (markers == 2).any()
    assert (markers == 3).any()


def test_watershed_regions_are_nonempty_disjoint_and_bounded_by_background():
    image = np.full((120, 180, 3), 255, dtype=np.uint8)
    image[15:105, 15:75] = 245
    image[15:105, 15] = 0
    image[15:105, 74] = 0
    image[15, 15:75] = 0
    image[104, 15:75] = 0
    image[15:105, 105:165] = 245
    image[15:105, 105] = 0
    image[15:105, 164] = 0
    image[15, 105:165] = 0
    image[104, 105:165] = 0
    groups = [
        {"group_id": "g1", "fragment_boxes": [(35, 35, 15, 50)]},
        {"group_id": "g2", "fragment_boxes": [(125, 35, 15, 50)]},
    ]

    result = phase_b.run_local_watershed(image, groups)
    left = result["labels"] == 2
    right = result["labels"] == 3

    assert left.any() and right.any()
    assert not np.logical_and(left, right).any()
    assert not left[0, :].any() and not right[0, :].any()
    assert result["virtual_boundary"].any()


def test_manual_gate_counts_touching_cluster_by_text_group_not_cluster():
    results = [
        {"review_id": "single-good", "category": "ordinary_dialogue", "execute_b1": True, "candidate_pixels": {"g1": 20}},
        {"review_id": "single-bad", "category": "ordinary_dialogue", "execute_b1": True, "candidate_pixels": {"g2": 20}},
        {"review_id": "touching", "category": "touching_or_adjacent", "execute_b1": True, "candidate_pixels": {"g3": 20, "g4": 20}},
        {"review_id": "control", "category": "negative_control", "execute_b1": False},
    ]
    labels = {
        "single-good": {"candidate_quality": "CORRECT", "container_topology": "N_A", "phase_c": "YES"},
        "single-bad": {"candidate_quality": "WRONG_OR_LEAK", "container_topology": "N_A", "phase_c": "NO"},
        "touching": {"candidate_quality": "PARTIAL", "container_topology": "CORRECT", "phase_c": "YES"},
        "control": {"candidate_quality": "EXPECTED_SKIP", "container_topology": "N_A", "phase_c": "NO"},
    }

    gate = phase_b.evaluate_manual_gate(results, labels)

    assert gate["ordinary_dialogue_group_count"] == 4
    assert gate["confirmed_nonempty_group_count"] == 3
    assert gate["confirmed_nonempty_rate"] == 0.75
    assert gate["visible_coarse_candidate_count"] == 3
    assert not gate["phase_c_authorized"]
