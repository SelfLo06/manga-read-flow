from tools.experiments.grouping_120.text_seeded_container_association import goal6_run_evaluation as evaluation


def test_review_form_forces_regionless_control_to_skip():
    form = evaluation.build_review_form(
        [
            {"asset_id": "case-51", "route": "COARSE_CONTAINER_SEARCH", "has_candidate": True},
            {"asset_id": "case-54", "route": "REGIONLESS_ABSTENTION", "has_candidate": False},
        ]
    )

    assert "| case-51 |" in form
    assert "| case-54 | `SKIP（固定）`" in form
    assert "AUTO_ACCEPT" in form
