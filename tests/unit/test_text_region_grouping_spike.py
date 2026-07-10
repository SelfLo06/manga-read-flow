from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
SPIKE_PATH = ROOT_DIR / "tools" / "spikes" / "text_region_grouping" / "spike.py"


def load_spike_module():
    spec = importlib.util.spec_from_file_location("text_region_grouping_spike", SPIKE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fragment(spike, fragment_id: str, x: int, y: int, width: int, height: int, text: str = ""):
    return spike.FragmentInput(
        fragment_id=fragment_id,
        asset_id="page.webp",
        bbox={"x": x, "y": y, "width": width, "height": height},
        polygon=[[x, y], [x + width, y], [x + width, y + height], [x, y + height]],
        ocr_text=text or fragment_id,
    )


def group_page(spike, fragments):
    page = spike.PageGroupingInput(asset_id="page.webp", width=1000, height=1000, fragments=fragments)
    return spike.group_fragments(page)


def test_single_fragment_becomes_independent_group():
    spike = load_spike_module()

    groups = group_page(spike, [fragment(spike, "p1", 10, 10, 120, 24, "hello")])

    assert len(groups) == 1
    assert groups[0].ordered_fragment_ids == ["p1"]
    assert groups[0].assembled_normalized_text == "hello"


def test_horizontal_multiline_fragments_merge_and_sort_top_to_bottom_left_to_right():
    spike = load_spike_module()
    fragments = [
        fragment(spike, "p3", 70, 64, 80, 24, "C"),
        fragment(spike, "p1", 10, 10, 160, 26, "A"),
        fragment(spike, "p2", 10, 34, 160, 24, "B"),
    ]

    groups = group_page(spike, fragments)

    assert len(groups) == 1
    assert groups[0].orientation == "horizontal"
    assert groups[0].ordered_fragment_ids == ["p1", "p2", "p3"]
    assert groups[0].assembled_raw_text == "A\nB\nC"


def test_vertical_multicolumn_fragments_merge_and_sort_right_to_left_top_to_bottom():
    spike = load_spike_module()
    fragments = [
        fragment(spike, "left", 24, 16, 30, 130, "C"),
        fragment(spike, "right", 100, 10, 30, 120, "A"),
        fragment(spike, "middle", 62, 12, 30, 128, "B"),
    ]

    groups = group_page(spike, fragments)

    assert len(groups) == 1
    assert groups[0].orientation == "vertical"
    assert groups[0].ordered_fragment_ids == ["right", "middle", "left"]
    assert groups[0].assembled_raw_text == "A\nB\nC"


def test_adjacent_containers_do_not_merge_when_gap_is_too_large():
    spike = load_spike_module()
    fragments = [
        fragment(spike, "top_right", 100, 10, 30, 120),
        fragment(spike, "top_left", 62, 12, 30, 128),
        fragment(spike, "lower", 96, 260, 30, 120),
    ]

    groups = group_page(spike, fragments)

    assert sorted(group.fragment_count for group in groups) == [1, 2]


def test_uncertain_orientation_can_link_by_projection_and_is_tagged():
    spike = load_spike_module()
    fragments = [
        fragment(spike, "p1", 10, 10, 30, 30, "A"),
        fragment(spike, "p2", 45, 12, 30, 30, "B"),
    ]

    groups = group_page(spike, fragments)

    assert len(groups) == 1
    assert "uncertain_orientation" in groups[0].uncertainty_tags


def test_group_bbox_union_clips_to_page_bounds():
    spike = load_spike_module()

    bbox = spike.union_bbox(
        [
            {"x": -5, "y": 5, "width": 20, "height": 20},
            {"x": 90, "y": 80, "width": 40, "height": 40},
        ],
        image_width=100,
        image_height=100,
    )

    assert bbox == {"x": 0, "y": 5, "width": 100, "height": 95}


def test_grouping_input_builder_does_not_read_gt_region_fields():
    spike = load_spike_module()

    class PoisonRegion(dict):
        forbidden = {"region_id", "bbox", "direction", "expected", "normalized_expected"}

        def get(self, key, default=None):
            if key in self.forbidden:
                raise AssertionError(f"read forbidden GT field: {key}")
            return super().get(key, default)

        def __getitem__(self, key):
            if key in self.forbidden:
                raise AssertionError(f"read forbidden GT field: {key}")
            return super().__getitem__(key)

    cycle = {
        "assets": {
            "page.webp": {
                "predictions": [
                    {
                        "prediction_id": "p1",
                        "bbox": {"x": 10, "y": 10, "width": 100, "height": 30},
                        "polygon": [[10, 10], [110, 10], [110, 40], [10, 40]],
                        "score": None,
                    }
                ]
            }
        },
        "regions": [
            PoisonRegion(
                {
                    "asset_id": "page.webp",
                    "region_id": "poison",
                    "bbox": "poison",
                    "direction": "poison",
                    "expected": "poison",
                    "normalized_expected": "poison",
                    "b2_native_fragments": {
                        "fragments": [{"prediction_id": "p1", "actual_raw": "OCR", "error": None}]
                    },
                }
            )
        ],
    }

    pages = spike.build_grouping_inputs(cycle, {"page.webp": {"width": 200, "height": 200, "split": "synthetic"}})

    assert pages[0].fragments[0].ocr_text == "OCR"


def test_evaluation_counts_split_as_orphan_and_not_order_evaluable():
    spike = load_spike_module()
    groups = [
        spike.PredictedGroup("g1", "page.webp", "horizontal", 1.0, {"x": 0, "y": 0, "width": 10, "height": 10}, ["p1"], 1, "A", "A", []),
        spike.PredictedGroup("g2", "page.webp", "horizontal", 1.0, {"x": 0, "y": 20, "width": 10, "height": 10}, ["p2"], 1, "B", "B", []),
    ]
    regions = [
        spike.EvaluationRegion(
            "r1",
            "page.webp",
            "synthetic",
            {"x": 0, "y": 0, "width": 20, "height": 40},
            "horizontal",
            "AB",
            "AB",
        )
    ]
    source_regions = {
        "r1": {
            "b2_native_fragments": {
                "fragments": [{"prediction_id": "p1"}, {"prediction_id": "p2"}],
                "actual_raw": "A\nB",
                "cer": 0.0,
                "exact": True,
            }
        }
    }

    evaluation = spike.evaluate_groups(groups, regions, source_regions)
    row = evaluation["regions"][0]

    assert row["split_error"] is True
    assert row["orphan_fragment"] == 1
    assert row["order_not_evaluable"] is True
    assert evaluation["summary"]["synthetic"]["grouping"]["split_error"] == 1


def test_evaluation_reports_reading_order_error_without_grouping_error():
    spike = load_spike_module()
    groups = [
        spike.PredictedGroup(
            "g1",
            "page.webp",
            "vertical",
            1.0,
            {"x": 0, "y": 0, "width": 40, "height": 100},
            ["p2", "p1"],
            2,
            "B\nA",
            "BA",
            [],
        )
    ]
    regions = [
        spike.EvaluationRegion(
            "r1",
            "page.webp",
            "real",
            {"x": 0, "y": 0, "width": 40, "height": 100},
            "vertical",
            "AB",
            "AB",
        )
    ]
    source_regions = {
        "r1": {
            "b2_native_fragments": {
                "fragments": [{"prediction_id": "p1"}, {"prediction_id": "p2"}],
                "actual_raw": "A\nB",
                "cer": 0.0,
                "exact": True,
            }
        }
    }

    evaluation = spike.evaluate_groups(groups, regions, source_regions)
    row = evaluation["regions"][0]

    assert row["group_hit"] is True
    assert row["order_correct"] is False
    assert row["failure_source"] == "reading_order_error"
    assert evaluation["summary"]["real"]["reading_order"]["order_error"] == 1


def test_safe_run_path_cannot_escape_run_directory(tmp_path):
    spike = load_spike_module()
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    assert spike.safe_run_path(run_dir, "visualizations", "page.png") == run_dir / "visualizations" / "page.png"

    with pytest.raises(ValueError, match="escape"):
        spike.safe_run_path(run_dir, "..", "outside.json")

    with pytest.raises(ValueError, match="escape"):
        spike.safe_run_path(run_dir, str(tmp_path / "outside.json"))


def test_results_serialization_is_stable_and_sorted():
    spike = load_spike_module()

    assert spike.dumps_json({"b": 1, "a": 2}) == '{\n  "a": 2,\n  "b": 1\n}\n'
