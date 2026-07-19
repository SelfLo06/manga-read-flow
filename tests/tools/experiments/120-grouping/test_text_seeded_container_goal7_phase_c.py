from __future__ import annotations

from tools.experiments.grouping_120.text_seeded_container_association import goal7_phase_c as phase_c


def test_phase_c_selection_contains_only_frozen_local_b1_candidates():
    matrix = {
        "pages": [
            {
                "page_id": "case-01",
                "clusters": [
                    {"cluster_id": "c1", "page_id": "case-01", "route": "LOCAL_B1_CANDIDATE"},
                    {"cluster_id": "c2", "page_id": "case-01", "route": "LOCAL_REVIEW_REQUIRED"},
                    {"cluster_id": "c3", "page_id": "case-01", "route": "LOCAL_ABSTENTION"},
                ],
            }
        ]
    }

    items = phase_c.build_phase_c_selection(matrix)

    assert len(items) == 1
    assert items[0]["cluster"]["cluster_id"] == "c1"
    assert items[0]["execute_b1"]
    assert items[0]["category"] == "frozen_local_candidate"
