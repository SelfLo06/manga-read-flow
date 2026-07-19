from __future__ import annotations

from tools.experiments.grouping_120.text_seeded_container_association import goal7_local_routing as goal7


def fragment(fragment_id: str, x: int, y: int, width: int = 30, height: int = 80) -> dict:
    return {
        "fragment_id": fragment_id,
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "polygon": [[x, y], [x + width, y], [x + width, y + height], [x, y + height]],
        "score": None,
    }


def group(group_id: str, fragment_id: str, x: int, y: int, width: int = 30, height: int = 80) -> dict:
    return {
        "group_id": group_id,
        "asset_id": "case-01",
        "orientation": "vertical",
        "orientation_confidence": 1.0,
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "ordered_fragment_ids": [fragment_id],
        "fragment_count": 1,
        "assembled_raw_text": "",
        "assembled_normalized_text": "",
        "uncertainty_tags": [],
    }


def asset(groups: list[dict], fragments: list[dict], width: int = 1000, height: int = 1000) -> dict:
    return {
        "asset_id": "case-01",
        "relative_path": "images/case-01.jpg",
        "sha256": "unused",
        "width": width,
        "height": height,
        "groups": groups,
        "fragments": fragments,
    }


def test_page_wide_seed_span_does_not_create_page_level_abstention():
    fragments = [fragment("p1", 20, 20), fragment("p2", 930, 900)]
    groups = [group("g1", "p1", 20, 20), group("g2", "p2", 930, 900)]

    result = goal7.route_asset(asset(groups, fragments), goal7.LocalRoutingPolicy())

    assert len(result["clusters"]) == 2
    assert result["page_decision"] == "AGGREGATE_ONLY"
    assert all(item["route"] != "PAGE_ABSTENTION" for item in result["clusters"])


def test_oversized_seed_abstains_only_its_local_cluster():
    fragments = [fragment("huge", 0, 0, 400, 400), fragment("normal", 700, 700)]
    groups = [group("huge-group", "huge", 0, 0, 400, 400), group("normal-group", "normal", 700, 700)]

    result = goal7.route_asset(asset(groups, fragments), goal7.LocalRoutingPolicy())
    by_group = {item["group_ids"][0]: item for item in result["clusters"]}

    assert by_group["huge-group"]["route"] == "LOCAL_ABSTENTION"
    assert by_group["huge-group"]["reason"] == "oversized_local_seed"
    assert by_group["normal-group"]["route"] == "LOCAL_B1_CANDIDATE"


def test_unresolved_pair_does_not_block_unrelated_cluster():
    fragments = [fragment("p1", 100, 100), fragment("p2", 145, 105), fragment("p3", 800, 800)]
    groups = [group("g1", "p1", 100, 100), group("g2", "p2", 145, 105), group("g3", "p3", 800, 800)]

    result = goal7.route_asset(asset(groups, fragments), goal7.LocalRoutingPolicy())

    multi = next(item for item in result["clusters"] if len(item["group_ids"]) == 2)
    single = next(item for item in result["clusters"] if item["group_ids"] == ["g3"])
    assert multi["local_topology"] == "unresolved"
    assert multi["route"] == "LOCAL_REVIEW_REQUIRED"
    assert single["route"] == "LOCAL_B1_CANDIDATE"


def test_local_roi_respects_static_pixel_budget():
    fragments = [fragment("p1", 300, 300, 100, 150)]
    groups = [group("g1", "p1", 300, 300, 100, 150)]

    result = goal7.route_asset(asset(groups, fragments), goal7.LocalRoutingPolicy(max_roi_pixels=50_000))
    cluster = result["clusters"][0]

    assert cluster["estimated_roi_pixels"] <= 50_000
    assert cluster["resource_budget"]["max_roi_pixels"] == 50_000
