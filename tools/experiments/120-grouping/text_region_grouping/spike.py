#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_RESULTS = ROOT_DIR / "data/local/runs/130-ocr/detection-ocr-v0.1/results.json"
DEFAULT_GROUND_TRUTH = ROOT_DIR / "data/local/datasets/110-detection/detection-ocr-ground-truth-v0.1.json"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "data/local/runs/120-grouping/text-region-grouping-v0.1"
SCHEMA_VERSION = "text-region-grouping-spike-v1"

ORIENTATION_RATIO = 1.25
PROJECTION_OVERLAP_RATIO = 0.15
GAP_RELATIVE_LIMIT = 0.35
GAP_MIN_PX = 16.0


class SpikeStop(Exception):
    pass


@dataclass(frozen=True)
class FragmentInput:
    fragment_id: str
    asset_id: str
    bbox: dict[str, int]
    polygon: list[Any]
    score: float | None = None
    ocr_text: str = ""
    ocr_error: str | None = None


@dataclass(frozen=True)
class PageGroupingInput:
    asset_id: str
    width: int
    height: int
    fragments: list[FragmentInput]


@dataclass(frozen=True)
class PredictedGroup:
    group_id: str
    asset_id: str
    orientation: str
    orientation_confidence: float
    bbox: dict[str, int]
    ordered_fragment_ids: list[str]
    fragment_count: int
    assembled_raw_text: str
    assembled_normalized_text: str
    uncertainty_tags: list[str]


@dataclass(frozen=True)
class EvaluationRegion:
    region_id: str
    asset_id: str
    split: str
    bbox: dict[str, int]
    direction: str
    expected: str
    normalized_expected: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(3).hex()


def normalize_ocr_text(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace(" ", "").replace("\n", "")


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + (left_char != right_char)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def character_error_rate(expected: str | None, actual: str | None) -> float:
    expected_norm = normalize_ocr_text(expected)
    actual_norm = normalize_ocr_text(actual)
    if not expected_norm:
        return 0.0 if not actual_norm else 1.0
    return levenshtein_distance(expected_norm, actual_norm) / len(expected_norm)


def dumps_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SpikeStop(f"JSON root must be an object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_json(data), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def safe_run_path(run_dir: Path, *parts: str) -> Path:
    base = run_dir.resolve()
    candidate = base.joinpath(*parts).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise ValueError(f"output path would escape run directory: {candidate}") from error
    return candidate


def bbox_edges(bbox: dict[str, Any]) -> tuple[float, float, float, float]:
    x = float(bbox["x"])
    y = float(bbox["y"])
    return x, y, x + float(bbox["width"]), y + float(bbox["height"])


def bbox_center(bbox: dict[str, Any]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox_edges(bbox)
    return (x1 + x2) / 2, (y1 + y2) / 2


def union_bbox(bboxes: list[dict[str, Any]], *, image_width: int, image_height: int) -> dict[str, int]:
    if not bboxes:
        raise ValueError("cannot union empty bbox list")
    min_x = min(float(bbox["x"]) for bbox in bboxes)
    min_y = min(float(bbox["y"]) for bbox in bboxes)
    max_x = max(float(bbox["x"]) + float(bbox["width"]) for bbox in bboxes)
    max_y = max(float(bbox["y"]) + float(bbox["height"]) for bbox in bboxes)
    x1 = max(0, int(min_x // 1))
    y1 = max(0, int(min_y // 1))
    x2 = min(image_width, int(max_x + 0.999999))
    y2 = min(image_height, int(max_y + 0.999999))
    return {"x": x1, "y": y1, "width": max(0, x2 - x1), "height": max(0, y2 - y1)}


def bbox_orientation(bbox: dict[str, Any]) -> tuple[str, float]:
    width = max(1.0, float(bbox["width"]))
    height = max(1.0, float(bbox["height"]))
    ratio = max(width, height) / min(width, height)
    confidence = min(1.0, max(0.0, (ratio - 1.0) / 2.0))
    if width >= height * ORIENTATION_RATIO:
        return "horizontal", confidence
    if height >= width * ORIENTATION_RATIO:
        return "vertical", confidence
    return "uncertain", confidence


def polygon_orientation(polygon: list[Any]) -> tuple[str, float]:
    if len(polygon) < 4:
        return "uncertain", 0.0
    try:
        points = [(float(point[0]), float(point[1])) for point in polygon[:4]]
    except (TypeError, ValueError, IndexError):
        return "uncertain", 0.0

    def dist(left: tuple[float, float], right: tuple[float, float]) -> float:
        return ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2) ** 0.5

    horizontal_len = (dist(points[0], points[1]) + dist(points[2], points[3])) / 2
    vertical_len = (dist(points[1], points[2]) + dist(points[3], points[0])) / 2
    if min(horizontal_len, vertical_len) <= 0:
        return "uncertain", 0.0
    ratio = max(horizontal_len, vertical_len) / min(horizontal_len, vertical_len)
    confidence = min(1.0, max(0.0, (ratio - 1.0) / 2.0))
    if horizontal_len >= vertical_len * ORIENTATION_RATIO:
        return "horizontal", confidence
    if vertical_len >= horizontal_len * ORIENTATION_RATIO:
        return "vertical", confidence
    return "uncertain", confidence


def infer_fragment_orientation(fragment: FragmentInput) -> tuple[str, float]:
    bbox_vote, bbox_confidence = bbox_orientation(fragment.bbox)
    polygon_vote, polygon_confidence = polygon_orientation(fragment.polygon)
    if bbox_vote == polygon_vote:
        return bbox_vote, max(bbox_confidence, polygon_confidence)
    if bbox_vote == "uncertain":
        return polygon_vote, polygon_confidence
    if polygon_vote == "uncertain":
        return bbox_vote, bbox_confidence
    return bbox_vote if bbox_confidence >= polygon_confidence else polygon_vote, max(bbox_confidence, polygon_confidence)


def projection_features(left: dict[str, Any], right: dict[str, Any]) -> dict[str, float]:
    left_x1, left_y1, left_x2, left_y2 = bbox_edges(left)
    right_x1, right_y1, right_x2, right_y2 = bbox_edges(right)
    x_overlap = max(0.0, min(left_x2, right_x2) - max(left_x1, right_x1))
    y_overlap = max(0.0, min(left_y2, right_y2) - max(left_y1, right_y1))
    x_gap = max(0.0, max(left_x1, right_x1) - min(left_x2, right_x2))
    y_gap = max(0.0, max(left_y1, right_y1) - min(left_y2, right_y2))
    min_width = max(1.0, min(float(left["width"]), float(right["width"])))
    min_height = max(1.0, min(float(left["height"]), float(right["height"])))
    return {
        "x_overlap": x_overlap,
        "y_overlap": y_overlap,
        "x_gap": x_gap,
        "y_gap": y_gap,
        "x_overlap_ratio": x_overlap / min_width,
        "y_overlap_ratio": y_overlap / min_height,
        "horizontal_gap_limit": max(GAP_MIN_PX, GAP_RELATIVE_LIMIT * min_width),
        "vertical_gap_limit": max(GAP_MIN_PX, GAP_RELATIVE_LIMIT * min_height),
    }


def should_link_fragments(
    left: FragmentInput,
    right: FragmentInput,
    left_orientation: str,
    right_orientation: str,
) -> bool:
    if left_orientation != right_orientation and "uncertain" not in {left_orientation, right_orientation}:
        return False

    features = projection_features(left.bbox, right.bbox)
    horizontal_line_link = (
        features["x_overlap_ratio"] >= PROJECTION_OVERLAP_RATIO
        and features["y_gap"] <= features["vertical_gap_limit"]
    )
    vertical_column_link = (
        features["y_overlap_ratio"] >= PROJECTION_OVERLAP_RATIO
        and features["x_gap"] <= features["horizontal_gap_limit"]
    )
    return horizontal_line_link or vertical_column_link


class UnionFind:
    def __init__(self, items: list[str]) -> None:
        self.parents = {item: item for item in items}

    def find(self, item: str) -> str:
        parent = self.parents[item]
        while parent != self.parents[parent]:
            self.parents[parent] = self.parents[self.parents[parent]]
            parent = self.parents[parent]
        self.parents[item] = parent
        return parent

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parents[right_root] = left_root


def infer_group_orientation(members: list[FragmentInput], orientations: dict[str, tuple[str, float]]) -> tuple[str, float, list[str]]:
    tags: list[str] = []
    votes = [orientations[member.fragment_id][0] for member in members]
    confident_votes = [vote for vote in votes if vote != "uncertain"]
    if any(vote == "uncertain" for vote in votes):
        tags.append("uncertain_orientation")
    if confident_votes:
        horizontal_count = confident_votes.count("horizontal")
        vertical_count = confident_votes.count("vertical")
        if horizontal_count > vertical_count:
            confidence = horizontal_count / len(votes)
            return "horizontal", confidence, tags
        if vertical_count > horizontal_count:
            confidence = vertical_count / len(votes)
            return "vertical", confidence, tags

    group_bbox = union_bbox([member.bbox for member in members], image_width=10**9, image_height=10**9)
    orientation, confidence = bbox_orientation(group_bbox)
    if orientation == "uncertain":
        tags.append("uncertain_group_orientation")
        orientation = "horizontal"
    return orientation, confidence, tags


def sort_group_members(members: list[FragmentInput], *, orientation: str) -> list[FragmentInput]:
    if orientation == "vertical":
        return sorted(members, key=lambda item: (-float(item.bbox["x"]), float(item.bbox["y"]), item.fragment_id))
    return sorted(members, key=lambda item: (float(item.bbox["y"]), float(item.bbox["x"]), item.fragment_id))


def group_fragments(page: PageGroupingInput) -> list[PredictedGroup]:
    fragments = sorted(page.fragments, key=lambda item: item.fragment_id)
    if not fragments:
        return []

    orientations = {fragment.fragment_id: infer_fragment_orientation(fragment) for fragment in fragments}
    union_find = UnionFind([fragment.fragment_id for fragment in fragments])
    for left_index, left in enumerate(fragments):
        for right in fragments[left_index + 1 :]:
            if should_link_fragments(left, right, orientations[left.fragment_id][0], orientations[right.fragment_id][0]):
                union_find.union(left.fragment_id, right.fragment_id)

    components: dict[str, list[FragmentInput]] = {}
    for fragment in fragments:
        components.setdefault(union_find.find(fragment.fragment_id), []).append(fragment)

    groups: list[PredictedGroup] = []
    sorted_components = sorted(
        components.values(),
        key=lambda members: (
            min(float(member.bbox["y"]) for member in members),
            min(float(member.bbox["x"]) for member in members),
            min(member.fragment_id for member in members),
        ),
    )
    for index, members in enumerate(sorted_components, start=1):
        orientation, confidence, tags = infer_group_orientation(members, orientations)
        ordered_members = sort_group_members(members, orientation=orientation)
        bbox = union_bbox([member.bbox for member in members], image_width=page.width, image_height=page.height)
        raw_text = "\n".join(member.ocr_text for member in ordered_members)
        if any(member.ocr_error for member in members):
            tags.append("fragment_ocr_error")
        groups.append(
            PredictedGroup(
                group_id=f"{safe_name(page.asset_id)}__g{index:03d}",
                asset_id=page.asset_id,
                orientation=orientation,
                orientation_confidence=round(confidence, 4),
                bbox=bbox,
                ordered_fragment_ids=[member.fragment_id for member in ordered_members],
                fragment_count=len(members),
                assembled_raw_text=raw_text,
                assembled_normalized_text=normalize_ocr_text(raw_text),
                uncertainty_tags=sorted(set(tags)),
            )
        )
    return groups


def to_jsonable_group(group: PredictedGroup) -> dict[str, Any]:
    return {
        "group_id": group.group_id,
        "asset_id": group.asset_id,
        "orientation": group.orientation,
        "orientation_confidence": group.orientation_confidence,
        "bbox": group.bbox,
        "ordered_fragment_ids": group.ordered_fragment_ids,
        "fragment_count": group.fragment_count,
        "assembled_raw_text": group.assembled_raw_text,
        "assembled_normalized_text": group.assembled_normalized_text,
        "uncertainty_tags": group.uncertainty_tags,
    }


def is_scored_region(asset: dict[str, Any], region: dict[str, Any]) -> bool:
    if region.get("bbox") is None:
        return False
    if asset.get("source_type") == "synthetic":
        return True
    return asset.get("source_type") == "real" and region.get("include_in_core_ocr_score") is True


def load_asset_dimensions(ground_truth: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for asset in ground_truth.get("assets", []):
        asset_id = asset.get("file_name")
        if not isinstance(asset_id, str):
            continue
        result[asset_id] = {
            "width": int(asset["width"]),
            "height": int(asset["height"]),
            "split": asset.get("source_type", ""),
        }
    return result


def load_evaluation_regions(ground_truth: dict[str, Any]) -> list[EvaluationRegion]:
    regions: list[EvaluationRegion] = []
    for asset in ground_truth.get("assets", []):
        for region in asset.get("regions", []):
            if not is_scored_region(asset, region):
                continue
            expected = region.get("normalized_text") or region.get("expected_text", "")
            regions.append(
                EvaluationRegion(
                    region_id=region["region_id"],
                    asset_id=asset["file_name"],
                    split=asset["source_type"],
                    bbox=region["bbox"],
                    direction=region.get("text_orientation", "unknown"),
                    expected=region.get("expected_text", ""),
                    normalized_expected=normalize_ocr_text(expected),
                )
            )
    return sorted(regions, key=lambda item: (item.asset_id, item.region_id))


def select_cycle(results: dict[str, Any], cycle_name: str) -> dict[str, Any]:
    for cycle in results.get("cycles", []):
        if cycle.get("cycle") == cycle_name:
            return cycle
    raise SpikeStop(f"cycle not found: {cycle_name}")


def build_fragment_ocr_index(cycle: dict[str, Any]) -> dict[tuple[str, str], dict[str, str | None]]:
    index: dict[tuple[str, str], dict[str, str | None]] = {}
    for region in cycle.get("regions", []):
        asset_id = region.get("asset_id")
        native = region.get("b2_native_fragments") or {}
        for fragment in native.get("fragments", []):
            prediction_id = fragment.get("prediction_id")
            if isinstance(asset_id, str) and isinstance(prediction_id, str):
                index[(asset_id, prediction_id)] = {
                    "text": str(fragment.get("actual_raw") or ""),
                    "error": fragment.get("error"),
                }
    return index


def build_grouping_inputs(cycle: dict[str, Any], asset_dimensions: dict[str, dict[str, Any]]) -> list[PageGroupingInput]:
    ocr_index = build_fragment_ocr_index(cycle)
    pages: list[PageGroupingInput] = []
    assets = cycle.get("assets")
    if not isinstance(assets, dict):
        raise SpikeStop("cycle assets must be an object")

    for asset_id, asset in sorted(assets.items()):
        dimensions = asset_dimensions.get(asset_id)
        if dimensions is None:
            raise SpikeStop(f"missing page dimensions for asset: {asset_id}")
        fragments: list[FragmentInput] = []
        for prediction in sorted(asset.get("predictions", []), key=lambda item: str(item.get("prediction_id"))):
            prediction_id = prediction.get("prediction_id")
            bbox = prediction.get("bbox")
            if not isinstance(prediction_id, str) or not isinstance(bbox, dict):
                continue
            ocr = ocr_index.get((asset_id, prediction_id), {})
            fragments.append(
                FragmentInput(
                    fragment_id=prediction_id,
                    asset_id=asset_id,
                    bbox={
                        "x": int(bbox["x"]),
                        "y": int(bbox["y"]),
                        "width": int(bbox["width"]),
                        "height": int(bbox["height"]),
                    },
                    polygon=prediction.get("polygon") or [],
                    score=prediction.get("score"),
                    ocr_text=str(ocr.get("text") or ""),
                    ocr_error=ocr.get("error") if isinstance(ocr.get("error"), str) else None,
                )
            )
        pages.append(
            PageGroupingInput(
                asset_id=asset_id,
                width=int(dimensions["width"]),
                height=int(dimensions["height"]),
                fragments=fragments,
            )
        )
    return pages


def cycle_region_index(cycle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {region["region_id"]: region for region in cycle.get("regions", []) if isinstance(region.get("region_id"), str)}


def region_fragment_ids(source_region: dict[str, Any] | None) -> list[str]:
    if source_region is None:
        return []
    native = source_region.get("b2_native_fragments") or {}
    return [
        fragment["prediction_id"]
        for fragment in native.get("fragments", [])
        if isinstance(fragment.get("prediction_id"), str)
    ]


def group_fragment_id_set(group: PredictedGroup) -> set[str]:
    return set(group.ordered_fragment_ids)


def evaluate_groups(
    groups: list[PredictedGroup],
    regions: list[EvaluationRegion],
    source_regions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    groups_by_id = {group.group_id: group for group in groups}
    groups_by_asset: dict[str, list[PredictedGroup]] = {}
    for group in groups:
        groups_by_asset.setdefault(group.asset_id, []).append(group)

    prediction_to_region: dict[tuple[str, str], str] = {}
    gt_fragment_ids: dict[str, list[str]] = {}
    for region in regions:
        fragment_ids = region_fragment_ids(source_regions.get(region.region_id))
        gt_fragment_ids[region.region_id] = fragment_ids
        for prediction_id in fragment_ids:
            prediction_to_region[(region.asset_id, prediction_id)] = region.region_id

    group_core_regions: dict[str, set[str]] = {}
    group_unassigned_fragments: dict[str, list[str]] = {}
    for group in groups:
        assigned_regions: set[str] = set()
        unassigned: list[str] = []
        for prediction_id in group.ordered_fragment_ids:
            assigned_region = prediction_to_region.get((group.asset_id, prediction_id))
            if assigned_region is None:
                unassigned.append(prediction_id)
            else:
                assigned_regions.add(assigned_region)
        group_core_regions[group.group_id] = assigned_regions
        group_unassigned_fragments[group.group_id] = unassigned

    group_id_by_prediction: dict[tuple[str, str], str] = {}
    for group in groups:
        for prediction_id in group.ordered_fragment_ids:
            group_id_by_prediction[(group.asset_id, prediction_id)] = group.group_id

    rows: list[dict[str, Any]] = []
    for region in regions:
        expected_fragment_ids = gt_fragment_ids[region.region_id]
        containing_group_ids = sorted(
            {
                group_id_by_prediction.get((region.asset_id, prediction_id))
                for prediction_id in expected_fragment_ids
                if group_id_by_prediction.get((region.asset_id, prediction_id)) is not None
            }
        )
        matched_group_id = ""
        if containing_group_ids:
            matched_group_id = max(
                containing_group_ids,
                key=lambda group_id: (
                    len(group_fragment_id_set(groups_by_id[group_id]) & set(expected_fragment_ids)),
                    group_id,
                ),
            )
        matched_group = groups_by_id.get(matched_group_id)
        split_error = len(containing_group_ids) > 1
        group_miss = not expected_fragment_ids or not containing_group_ids
        merge_error = bool(matched_group and (group_core_regions[matched_group.group_id] - {region.region_id}))
        full_fragment_match = bool(
            matched_group
            and set(expected_fragment_ids).issubset(group_fragment_id_set(matched_group))
            and not split_error
        )
        contains_unassigned_fragments = bool(matched_group and group_unassigned_fragments[matched_group.group_id])
        group_hit = full_fragment_match and not group_miss and not split_error and not merge_error

        matched_fragment_count = (
            len(set(expected_fragment_ids) & group_fragment_id_set(matched_group))
            if matched_group is not None
            else 0
        )
        orphan_fragment = max(0, len(expected_fragment_ids) - matched_fragment_count)

        source_region = source_regions.get(region.region_id) or {}
        native = source_region.get("b2_native_fragments") or {}
        gt_assisted_b2_raw = str(native.get("actual_raw") or "")
        gt_assisted_b2_cer = native.get("cer")
        gt_assisted_b2_exact = native.get("exact")
        actual = matched_group.assembled_raw_text if matched_group is not None else ""
        exact = normalize_ocr_text(actual) == region.normalized_expected
        cer = character_error_rate(region.normalized_expected, actual)
        b2_cer_value = float(gt_assisted_b2_cer) if gt_assisted_b2_cer is not None else None
        cer_delta = cer - b2_cer_value if b2_cer_value is not None else None

        order_correct: bool | None = None
        order_not_evaluable = False
        if len(expected_fragment_ids) < 2 or not matched_group or group_miss or split_error or merge_error:
            order_not_evaluable = True
        else:
            ordered_core_ids = [
                prediction_id
                for prediction_id in matched_group.ordered_fragment_ids
                if prediction_id in set(expected_fragment_ids)
            ]
            order_correct = ordered_core_ids == expected_fragment_ids

        grouping_issue = group_miss or split_error or merge_error or orphan_fragment > 0
        order_issue = order_correct is False
        existing_ocr_issue = bool(gt_assisted_b2_exact is False)
        if grouping_issue and (order_issue or existing_ocr_issue):
            failure_source = "mixed_error"
        elif grouping_issue:
            failure_source = "grouping_error"
        elif order_issue:
            failure_source = "reading_order_error" if not existing_ocr_issue else "mixed_error"
        elif existing_ocr_issue:
            failure_source = "existing_ocr_error"
        else:
            failure_source = "none"

        rows.append(
            {
                "asset_id": region.asset_id,
                "split": region.split,
                "region_id": region.region_id,
                "predicted_group_id": matched_group_id,
                "matched_gt_region_id": region.region_id if matched_group_id else "",
                "orientation": matched_group.orientation if matched_group else "",
                "fragment_ids": ";".join(matched_group.ordered_fragment_ids) if matched_group else "",
                "fragment_count": matched_group.fragment_count if matched_group else 0,
                "gt_fragment_ids": ";".join(expected_fragment_ids),
                "gt_fragment_count": len(expected_fragment_ids),
                "group_hit": group_hit,
                "group_miss": group_miss,
                "split_error": split_error,
                "merge_error": merge_error,
                "orphan_fragment": orphan_fragment,
                "contains_unassigned_fragments": contains_unassigned_fragments,
                "order_correct": order_correct,
                "order_not_evaluable": order_not_evaluable,
                "expected": region.expected,
                "actual": actual,
                "normalized_expected": region.normalized_expected,
                "normalized_actual": normalize_ocr_text(actual),
                "exact": exact,
                "cer": cer,
                "gt_assisted_b2_actual": gt_assisted_b2_raw,
                "gt_assisted_b2_cer": b2_cer_value,
                "cer_delta": cer_delta,
                "exact_changed_vs_gt_assisted_b2": exact != gt_assisted_b2_exact if gt_assisted_b2_exact is not None else None,
                "failure_source": failure_source,
                "uncertainty_tags": ";".join(matched_group.uncertainty_tags) if matched_group else "",
            }
        )

    summary = summarize_evaluation(rows, groups, group_core_regions)
    return {
        "regions": rows,
        "groups": summarize_groups_for_evaluation(groups, group_core_regions, group_unassigned_fragments),
        "summary": summary,
    }


def summarize_groups_for_evaluation(
    groups: list[PredictedGroup],
    group_core_regions: dict[str, set[str]],
    group_unassigned_fragments: dict[str, list[str]],
) -> list[dict[str, Any]]:
    summaries = []
    for group in groups:
        summaries.append(
            {
                "group_id": group.group_id,
                "asset_id": group.asset_id,
                "core_region_ids": sorted(group_core_regions[group.group_id]),
                "unassigned_fragment_ids": group_unassigned_fragments[group.group_id],
                "is_extra_group": not group_core_regions[group.group_id],
                "is_cross_container_merge": len(group_core_regions[group.group_id]) > 1,
            }
        )
    return summaries


def summarize_ocr_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cers = [float(row["cer"]) for row in rows]
    deltas = [float(row["cer_delta"]) for row in rows if row["cer_delta"] is not None]
    return {
        "regions": len(rows),
        "exact": sum(1 for row in rows if row["exact"] is True),
        "exact_rate": sum(1 for row in rows if row["exact"] is True) / len(rows) if rows else 0.0,
        "median_cer": statistics.median(cers) if cers else None,
        "mean_cer": statistics.mean(cers) if cers else None,
        "cer_lte_0.30": sum(1 for value in cers if value <= 0.30),
        "mean_cer_delta_vs_gt_assisted_b2": statistics.mean(deltas) if deltas else 0.0,
        "exact_changed_vs_gt_assisted_b2": sum(1 for row in rows if row["exact_changed_vs_gt_assisted_b2"] is True),
    }


def summarize_evaluation(
    rows: list[dict[str, Any]],
    groups: list[PredictedGroup],
    group_core_regions: dict[str, set[str]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    asset_split_by_row = {row["asset_id"]: row["split"] for row in rows}
    for split in ("synthetic", "real"):
        split_rows = [row for row in rows if row["split"] == split]
        split_groups = [group for group in groups if asset_split_by_row.get(group.asset_id) == split]
        gt_container_count = len(split_rows)
        group_hit = sum(1 for row in split_rows if row["group_hit"] is True)
        split_error = sum(1 for row in split_rows if row["split_error"] is True)
        group_miss = sum(1 for row in split_rows if row["group_miss"] is True)
        merge_error = sum(
            1
            for group in split_groups
            if len(group_core_regions.get(group.group_id, set())) > 1
        )
        extra_group = sum(
            1
            for group in split_groups
            if not group_core_regions.get(group.group_id, set())
        )
        order_evaluable_rows = [row for row in split_rows if row["order_not_evaluable"] is False]
        result[split] = {
            "grouping": {
                "gt_container_count": gt_container_count,
                "predicted_group_count": len(split_groups),
                "group_hit": group_hit,
                "group_miss": group_miss,
                "split_error": split_error,
                "merge_error": merge_error,
                "orphan_fragment": sum(int(row["orphan_fragment"]) for row in split_rows),
                "extra_group": extra_group,
                "group_recall": group_hit / gt_container_count if gt_container_count else 0.0,
            },
            "reading_order": {
                "order_correct": sum(1 for row in order_evaluable_rows if row["order_correct"] is True),
                "order_error": sum(1 for row in order_evaluable_rows if row["order_correct"] is False),
                "order_not_evaluable": sum(1 for row in split_rows if row["order_not_evaluable"] is True),
            },
            "ocr": summarize_ocr_rows(split_rows),
        }

    result["overall"] = {
        "grouping": {
            "gt_container_count": sum(result[split]["grouping"]["gt_container_count"] for split in ("synthetic", "real")),
            "predicted_group_count": len(groups),
            "group_hit": sum(result[split]["grouping"]["group_hit"] for split in ("synthetic", "real")),
            "group_miss": sum(result[split]["grouping"]["group_miss"] for split in ("synthetic", "real")),
            "split_error": sum(result[split]["grouping"]["split_error"] for split in ("synthetic", "real")),
            "merge_error": sum(result[split]["grouping"]["merge_error"] for split in ("synthetic", "real")),
            "orphan_fragment": sum(result[split]["grouping"]["orphan_fragment"] for split in ("synthetic", "real")),
            "extra_group": sum(result[split]["grouping"]["extra_group"] for split in ("synthetic", "real")),
        },
        "reading_order": {
            "order_correct": sum(result[split]["reading_order"]["order_correct"] for split in ("synthetic", "real")),
            "order_error": sum(result[split]["reading_order"]["order_error"] for split in ("synthetic", "real")),
            "order_not_evaluable": sum(
                result[split]["reading_order"]["order_not_evaluable"] for split in ("synthetic", "real")
            ),
        },
    }
    return result


def decide_verdict(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    synthetic = summary["synthetic"]["grouping"]
    real = summary["real"]["grouping"]
    real_ocr = summary["real"]["ocr"]
    order = summary["overall"]["reading_order"]
    black2_r02 = next((row for row in rows if row["region_id"] == "black2_r02"), None)
    no_black2_merge = bool(black2_r02 and not black2_r02["merge_error"])
    vertical_order_ok = order["order_error"] == 0

    pass_gate = (
        synthetic["group_hit"] >= 10
        and real["group_hit"] >= 14
        and summary["overall"]["grouping"]["merge_error"] <= 1
        and real_ocr["cer_lte_0.30"] >= 12
        and vertical_order_ok
        and no_black2_merge
    )
    if not pass_gate:
        if real["group_hit"] < 14 or summary["overall"]["grouping"]["merge_error"] > 1 or order["order_error"] > 0:
            return "FAIL"
        return "PASS_WITH_LIMITATIONS"

    has_limits = (
        synthetic["group_miss"] > 0
        or summary["overall"]["grouping"]["extra_group"] > 0
        or real_ocr["exact_changed_vs_gt_assisted_b2"] > 0
        or real_ocr["exact_rate"] < 1.0
    )
    return "PASS_WITH_LIMITATIONS" if has_limits else "PASS"


def collect_git_state() -> dict[str, Any]:
    def run(command: list[str]) -> str:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        return completed.stdout.strip()

    return {
        "branch": run(["git", "branch", "--show-current"]),
        "head": run(["git", "rev-parse", "--short", "HEAD"]),
        "status_short": run(["git", "status", "--short", "--untracked-files=all"]),
    }


def validate_inputs(results: dict[str, Any], ground_truth: dict[str, Any], cycle_name: str | None = None) -> dict[str, Any]:
    cycles = results.get("cycles")
    if not isinstance(cycles, list) or not cycles:
        raise SpikeStop("results must contain at least one cycle")
    if cycle_name is not None:
        select_cycle(results, cycle_name)

    assets = ground_truth.get("assets")
    if not isinstance(assets, list) or len(assets) != 8:
        raise SpikeStop("ground truth must contain 8 assets")
    scored_regions = 0
    synthetic_scored = 0
    real_core = 0
    for asset in assets:
        for region in asset.get("regions", []):
            if is_scored_region(asset, region):
                scored_regions += 1
                if asset.get("source_type") == "synthetic":
                    synthetic_scored += 1
                else:
                    real_core += 1
    if scored_regions != 27 or synthetic_scored != 11 or real_core != 16:
        raise SpikeStop("expected 11 synthetic + 16 real core scored regions")
    return {
        "assets": len(assets),
        "scored_regions": scored_regions,
        "synthetic_scored_regions": synthetic_scored,
        "real_core_regions": real_core,
        "available_cycles": [cycle.get("cycle") for cycle in cycles],
    }


def input_hashes(results_path: Path, ground_truth_path: Path) -> dict[str, str]:
    return {
        str(results_path.relative_to(ROOT_DIR)): sha256_file(results_path),
        str(ground_truth_path.relative_to(ROOT_DIR)): sha256_file(ground_truth_path),
    }


def create_run_dir(output_root: Path, run_id: str | None) -> tuple[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    actual_run_id = run_id or make_run_id()
    run_dir = output_root / actual_run_id
    if run_dir.exists():
        raise SpikeStop(f"run directory already exists: {run_dir}")
    safe_run_path(run_dir).mkdir(parents=True, exist_ok=False)
    safe_run_path(run_dir, "visualizations").mkdir(parents=True, exist_ok=False)
    return actual_run_id, run_dir


def write_groups_csv(run_dir: Path, rows: list[dict[str, Any]]) -> None:
    path = safe_run_path(run_dir, "groups.csv")
    fieldnames = [
        "asset_id",
        "predicted_group_id",
        "matched_gt_region_id",
        "orientation",
        "fragment_ids",
        "fragment_count",
        "group_hit",
        "split_error",
        "merge_error",
        "order_correct",
        "expected",
        "actual",
        "exact",
        "cer",
        "gt_assisted_b2_cer",
        "cer_delta",
        "failure_source",
        "uncertainty_tags",
    ]
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def render_visualizations(
    run_dir: Path,
    pages: list[PageGroupingInput],
    groups: list[PredictedGroup],
    regions: list[EvaluationRegion],
) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return

    groups_by_asset: dict[str, list[PredictedGroup]] = {}
    for group in groups:
        groups_by_asset.setdefault(group.asset_id, []).append(group)
    regions_by_asset: dict[str, list[EvaluationRegion]] = {}
    for region in regions:
        regions_by_asset.setdefault(region.asset_id, []).append(region)

    palette = [
        (220, 60, 60),
        (40, 120, 220),
        (50, 160, 90),
        (190, 90, 210),
        (225, 145, 35),
        (30, 150, 170),
    ]
    for page in pages:
        scale = min(1.0, 1600 / max(page.width, page.height))
        canvas = Image.new("RGB", (max(1, int(page.width * scale)), max(1, int(page.height * scale))), "white")
        draw = ImageDraw.Draw(canvas)

        def box_tuple(bbox: dict[str, Any]) -> tuple[int, int, int, int]:
            x1, y1, x2, y2 = bbox_edges(bbox)
            return int(x1 * scale), int(y1 * scale), int(x2 * scale), int(y2 * scale)

        for region in regions_by_asset.get(page.asset_id, []):
            draw.rectangle(box_tuple(region.bbox), outline=(0, 140, 0), width=max(1, int(3 * scale)))
            x1, y1, _, _ = box_tuple(region.bbox)
            draw.text((x1 + 3, y1 + 3), region.region_id, fill=(0, 100, 0))

        fragments_by_id = {fragment.fragment_id: fragment for fragment in page.fragments}
        for group_index, group in enumerate(groups_by_asset.get(page.asset_id, [])):
            color = palette[group_index % len(palette)]
            draw.rectangle(box_tuple(group.bbox), outline=color, width=max(1, int(4 * scale)))
            gx, gy, _, _ = box_tuple(group.bbox)
            draw.text((gx + 4, gy + 16), group.group_id.rsplit("__", 1)[-1], fill=color)
            for order_index, fragment_id in enumerate(group.ordered_fragment_ids, start=1):
                fragment = fragments_by_id.get(fragment_id)
                if fragment is None:
                    continue
                draw.rectangle(box_tuple(fragment.bbox), outline=(40, 40, 40), width=max(1, int(1 * scale)))
                cx, cy = bbox_center(fragment.bbox)
                draw.text((int(cx * scale), int(cy * scale)), str(order_index), fill=color)

        out_path = safe_run_path(run_dir, "visualizations", f"{safe_name(page.asset_id)}.png")
        canvas.save(out_path, "PNG")


def run_grouping(args: argparse.Namespace) -> int:
    results_path = args.results.resolve()
    ground_truth_path = args.ground_truth.resolve()
    results = load_json(results_path)
    ground_truth = load_json(ground_truth_path)
    stats = validate_inputs(results, ground_truth, args.cycle)
    before_hashes = input_hashes(results_path, ground_truth_path)
    run_id, run_dir = create_run_dir(args.output_root.resolve(), getattr(args, "run_id", None))

    cycle = select_cycle(results, args.cycle)
    asset_dimensions = load_asset_dimensions(ground_truth)
    pages = build_grouping_inputs(cycle, asset_dimensions)
    groups = [group for page in pages for group in group_fragments(page)]
    evaluation_regions = load_evaluation_regions(ground_truth)
    source_regions = cycle_region_index(cycle)
    evaluation = evaluate_groups(groups, evaluation_regions, source_regions)
    verdict = decide_verdict(evaluation["summary"], evaluation["regions"])
    after_hashes = input_hashes(results_path, ground_truth_path)

    predicted_groups = [to_jsonable_group(group) for group in sorted(groups, key=lambda item: item.group_id)]
    output = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "source_detection_ocr_run_id": results.get("run_id"),
        "source_results": str(results_path.relative_to(ROOT_DIR)),
        "ground_truth": str(ground_truth_path.relative_to(ROOT_DIR)),
        "git_head": collect_git_state(),
        "cycle": args.cycle,
        "parameters": {
            "orientation_ratio": ORIENTATION_RATIO,
            "projection_overlap_ratio": PROJECTION_OVERLAP_RATIO,
            "gap_relative_limit": GAP_RELATIVE_LIMIT,
            "gap_min_px": GAP_MIN_PX,
        },
        "stats": stats,
        "input_hashes_before": before_hashes,
        "input_hashes_after": after_hashes,
        "input_hashes_unchanged": before_hashes == after_hashes,
        "assets": [
            {
                "asset_id": page.asset_id,
                "width": page.width,
                "height": page.height,
                "fragment_count": len(page.fragments),
                "predicted_group_count": sum(1 for group in groups if group.asset_id == page.asset_id),
            }
            for page in pages
        ],
        "predicted_groups": predicted_groups,
        "evaluation": evaluation,
        "summary": evaluation["summary"],
        "verdict": verdict,
        "started_at": utc_now(),
        "finished_at": utc_now(),
    }
    if not output["input_hashes_unchanged"]:
        output["verdict"] = "FAIL"
        output["fatal_error"] = {"stage": "verify_inputs", "error": "input hash changed"}

    write_json(safe_run_path(run_dir, "results.json"), output)
    write_json(safe_run_path(run_dir, "summary.json"), output["summary"])
    write_groups_csv(run_dir, evaluation["regions"])
    render_visualizations(run_dir, pages, groups, evaluation_regions)

    print(f"run_id={run_id}")
    print(f"output_dir={run_dir}")
    print(f"verdict={output['verdict']}")
    return 0 if output["input_hashes_unchanged"] else 2


def validate_command(args: argparse.Namespace) -> int:
    results = load_json(args.results.resolve())
    ground_truth = load_json(args.ground_truth.resolve())
    stats = validate_inputs(results, ground_truth, None)
    print(
        "Validation passed: "
        f"{stats['assets']} assets, "
        f"{stats['synthetic_scored_regions']} synthetic scored regions, "
        f"{stats['real_core_regions']} real core regions, "
        f"cycles={','.join(str(cycle) for cycle in stats['available_cycles'])}"
    )
    return 0


def verify_command(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    results_path = safe_run_path(run_dir, "results.json")
    summary_path = safe_run_path(run_dir, "summary.json")
    groups_path = safe_run_path(run_dir, "groups.csv")
    if not results_path.exists() or not summary_path.exists() or not groups_path.exists():
        raise SpikeStop("run directory is missing required output files")
    results = load_json(results_path)
    summary = load_json(summary_path)
    if results.get("schema_version") != SCHEMA_VERSION:
        raise SpikeStop("unexpected schema_version")
    if results.get("summary") != summary:
        raise SpikeStop("summary.json does not match results.json")
    if results.get("input_hashes_unchanged") is not True:
        raise SpikeStop("input hashes changed")
    if results.get("verdict") not in {"PASS", "PASS_WITH_LIMITATIONS", "FAIL"}:
        raise SpikeStop("invalid verdict")
    print(f"Verification passed: {run_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline text region grouping spike")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    validate_parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    validate_parser.set_defaults(func=validate_command)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    run_parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    run_parser.add_argument("--cycle", default="cold")
    run_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    run_parser.add_argument("--run-id", default=None)
    run_parser.set_defaults(func=run_grouping)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--run-dir", type=Path, required=True)
    verify_parser.set_defaults(func=verify_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SpikeStop as error:
        print(f"Spike stopped: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
