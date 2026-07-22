#!/usr/bin/env python3
"""Post-hoc A2 evaluator. This module never invokes the producer."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from shapely.geometry import LineString, shape


EVALUATOR_VERSION = "0.1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _decode_mask(record: dict) -> np.ndarray:
    height, width = record["mask_shape"]
    flat = np.zeros(height * width, dtype=bool)
    for start, length in record["mask_rle"]:
        flat[start:start + length] = True
    return flat.reshape((height, width))


def _verify_mask(candidate_dir: Path, record: dict) -> np.ndarray:
    path = candidate_dir / record["mask_ref"]
    if not path.is_file() or _sha256(path) != record["mask_sha256"]:
        raise ValueError(f"candidate mask missing or hash mismatch: {record['mask_ref']}")
    return _decode_mask(record)


def _raster_line(shape_: tuple[int, int], geometry: dict) -> np.ndarray:
    mask = np.zeros(shape_, dtype=np.uint8)
    coordinates = geometry["coordinates"]
    lines = coordinates if geometry["type"] == "MultiLineString" else [coordinates]
    for line in lines:
        points = np.rint(np.asarray(line)).astype(np.int32)
        if len(points) >= 2:
            cv2.polylines(mask, [points], False, 1, 1)
    return mask.astype(bool)


def _candidate_polygon(instance: dict):
    points = instance["interior"]["points"]
    if len(points) < 3:
        return None
    return shape({"type": "Polygon", "coordinates": [[*points, points[0]]]})


def _oracle_instances(oracle: dict) -> dict[str, dict]:
    result = {}
    for feature in oracle["features"]:
        props = feature["properties"]
        if props["kind"] == "INSTANCE_INTERIOR" and props["status"] == "SUPPORTED":
            for group_id in props.get("text_group_ids", []):
                result[group_id] = {"feature": feature, "geometry": shape(feature["geometry"]), "instance_id": props["instance_id"]}
    return result


def evaluate(candidate_dir: Path, oracle_path: Path, contract_path: Path) -> dict:
    candidate_path = candidate_dir / "candidate.json"
    hash_path = candidate_dir / "candidate.sha256"
    if not hash_path.is_file():
        raise ValueError("candidate is not hash-frozen")
    expected = hash_path.read_text(encoding="ascii").split()[0]
    actual = _sha256(candidate_path)
    if expected != actual:
        raise ValueError("candidate hash mismatch")
    before = {path: _sha256(path) for path in (candidate_path, hash_path, oracle_path)}
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    page_shape = (candidate["page_dimensions"]["height"], candidate["page_dimensions"]["width"])
    for instance in candidate["instances"]:
        _verify_mask(candidate_dir, instance["interior"])
        _verify_mask(candidate_dir, instance["observed_boundary"])
    for item in candidate["typed_boundaries"]:
        if item["kind"] == "TEXT_EXCLUSION":
            _verify_mask(candidate_dir, item)
    oracle_by_group = _oracle_instances(oracle)
    oracle_groups_by_instance = {}
    for group_id, item in oracle_by_group.items():
        oracle_groups_by_instance.setdefault(item["instance_id"], []).append(group_id)
    findings = []
    metrics = []
    seen_groups = set()
    for instance in candidate["instances"]:
        groups = instance["text_group_ids"]
        if len(groups) != 1:
            findings.append({"code": "CROSS_GROUP_MERGE", "classification": "CONFIRMED_CANDIDATE_ERROR", "instance_id": instance["instance_id"]})
            continue
        group_id = groups[0]
        seen_groups.add(group_id)
        oracle_item = oracle_by_group.get(group_id)
        if oracle_item is None:
            findings.append({"code": "BACKGROUND_TEXT_ASSIGNED_TO_BALLOON", "classification": "PROBABLE_CANDIDATE_ERROR", "instance_id": instance["instance_id"], "text_group_id": group_id})
            continue
        candidate_geometry = _candidate_polygon(instance)
        if candidate_geometry is None or candidate_geometry.is_empty:
            findings.append({"code": "MISSING_SUPPORTED_INSTANCE", "classification": "CONFIRMED_CANDIDATE_ERROR", "text_group_id": group_id})
            continue
        oracle_geometry = oracle_item["geometry"]
        union = candidate_geometry.union(oracle_geometry).area
        iou = 0.0 if union == 0 else candidate_geometry.intersection(oracle_geometry).area / union
        metrics.append({"text_group_id": group_id, "instance_interior_iou": round(iou, 8)})
        oracle_boundaries = [
            item for item in oracle["features"]
            if item["properties"]["kind"] == "BUBBLE_BOUNDARY"
            and item["properties"].get("instance_id") == oracle_item["instance_id"]
        ]
        candidate_boundary = _decode_mask(instance["observed_boundary"])
        oracle_boundary = np.zeros(page_shape, dtype=bool)
        for boundary in oracle_boundaries:
            oracle_boundary |= _raster_line(page_shape, boundary["geometry"])
        tolerance_kernel = np.ones((7, 7), np.uint8)
        oracle_tolerance = cv2.dilate(oracle_boundary.astype(np.uint8), tolerance_kernel).astype(bool)
        candidate_tolerance = cv2.dilate(candidate_boundary.astype(np.uint8), tolerance_kernel).astype(bool)
        precision = None if not candidate_boundary.any() else float((candidate_boundary & oracle_tolerance).sum() / candidate_boundary.sum())
        recall = None if not oracle_boundary.any() else float((oracle_boundary & candidate_tolerance).sum() / oracle_boundary.sum())
        metrics[-1].update({"boundary_tolerance_precision": None if precision is None else round(precision, 8), "boundary_tolerance_recall": None if recall is None else round(recall, 8)})
        expected_directions = set()
        for feature in oracle["features"]:
            props = feature["properties"]
            if props["kind"] == "PAGE_EDGE_CLOSURE" and props.get("instance_id") == oracle_item["instance_id"]:
                coordinates = feature["geometry"]["coordinates"]
                xs, ys = [point[0] for point in coordinates], [point[1] for point in coordinates]
                if max(xs) == 0: expected_directions.add("LEFT")
                if min(xs) == max(xs) and min(xs) > 0: expected_directions.add("RIGHT")
                if max(ys) == 0: expected_directions.add("TOP")
                if min(ys) == max(ys) and min(ys) > 0: expected_directions.add("BOTTOM")
        actual_directions = set(instance["page_truncation_directions"])
        if expected_directions - actual_directions:
            findings.append({"code": "MISSING_PAGE_TRUNCATION", "classification": "CONFIRMED_CANDIDATE_ERROR", "text_group_id": group_id, "expected": sorted(expected_directions), "actual": sorted(actual_directions)})
        if actual_directions - expected_directions:
            findings.append({"code": "WRONG_PAGE_TRUNCATION_DIRECTION", "classification": "PROBABLE_CANDIDATE_ERROR", "text_group_id": group_id, "expected": sorted(expected_directions), "actual": sorted(actual_directions)})
    for group_id in sorted(set(oracle_by_group) - seen_groups):
        findings.append({"code": "MISSING_SUPPORTED_INSTANCE", "classification": "CONFIRMED_CANDIDATE_ERROR", "text_group_id": group_id})
    candidate_instance_by_group = {
        item["text_group_ids"][0]: item["instance_id"]
        for item in candidate["instances"] if len(item["text_group_ids"]) == 1
    }
    candidate_relations = {
        frozenset((item["instance_a"], item["instance_b"])): item
        for item in candidate["relations"]
    }
    oracle_exclusions = [
        shape(item["geometry"]) for item in oracle["features"]
        if item["properties"]["kind"] == "TEXT_EXCLUSION"
    ]
    for feature in oracle["features"]:
        props = feature["properties"]
        if props["kind"] != "CONTACT_REGION" or not props.get("separation_required"):
            continue
        groups_a = oracle_groups_by_instance.get(props["instance_a"], [])
        groups_b = oracle_groups_by_instance.get(props["instance_b"], [])
        expected_pair = frozenset(
            candidate_instance_by_group[group_id]
            for group_id in [*groups_a, *groups_b] if group_id in candidate_instance_by_group
        )
        relation = candidate_relations.get(expected_pair)
        if len(expected_pair) != 2 or relation is None or relation["resolution"] != "RESOLVED" or not relation["separator"]:
            findings.append({"code": "SEPARATOR_DOES_NOT_SPLIT_INSTANCES", "classification": "CONFIRMED_CANDIDATE_ERROR", "oracle_relation_id": props["relation_id"], "text_group_ids": [*groups_a, *groups_b]})
            continue
        line = LineString(relation["separator"]["points"])
        if any(line.intersects(exclusion) for exclusion in oracle_exclusions):
            findings.append({"code": "SEPARATOR_INTERSECTS_TEXT_EXCLUSION", "classification": "CONFIRMED_CANDIDATE_ERROR", "relation_id": relation["relation_id"], "oracle_relation_id": props["relation_id"]})
        corridors = [
            shape(item["geometry"]) for item in oracle["features"]
            if item["properties"]["kind"] == "SEPARATOR_CORRIDOR"
            and item["properties"].get("relation_id") == props["relation_id"]
        ]
        if corridors and not any(corridor.buffer(2).covers(line) for corridor in corridors):
            findings.append({"code": "SEPARATOR_OUTSIDE_ADMISSIBLE_CORRIDOR", "classification": "PROBABLE_CANDIDATE_ERROR", "relation_id": relation["relation_id"], "oracle_relation_id": props["relation_id"]})
    for relation in candidate["relations"]:
        separator = relation["separator"]
        if relation["resolution"] == "RESOLVED" and not separator:
            findings.append({"code": "SEPARATOR_DOES_NOT_SPLIT_INSTANCES", "classification": "CONFIRMED_CANDIDATE_ERROR", "relation_id": relation["relation_id"]})
    confirmed = [item for item in findings if item["classification"] == "CONFIRMED_CANDIDATE_ERROR"]
    all_candidate_boundary = np.zeros(page_shape, dtype=bool)
    unknown_pixels = 0
    for instance in candidate["instances"]:
        all_candidate_boundary |= _decode_mask(instance["observed_boundary"])
        if instance["interior"]["evidence"] == "UNKNOWN":
            unknown_pixels += int(_decode_mask(instance["interior"]).sum())
    panel_boundary = np.zeros(page_shape, dtype=bool)
    for feature in oracle["features"]:
        if feature["properties"]["kind"] == "PANEL_BOUNDARY":
            panel_boundary |= _raster_line(page_shape, feature["geometry"])
    panel_tolerance = cv2.dilate(panel_boundary.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    panel_confusion = 0.0 if not all_candidate_boundary.any() else float((all_candidate_boundary & panel_tolerance).sum() / all_candidate_boundary.sum())
    result = {
        "schema": "physical-boundary-a2-evaluation-v0.1",
        "evaluator_version": EVALUATOR_VERSION,
        "candidate_sha256": actual,
        "oracle_sha256": _sha256(oracle_path),
        "evaluation_contract_sha256": _sha256(contract_path),
        "contract_hard_failures": contract["hard_failures"],
        "metrics": {"instances": metrics, "false_positive_instance_count": sum(item["code"] == "BACKGROUND_TEXT_ASSIGNED_TO_BALLOON" for item in findings), "abstention_coverage": 0.0, "unknown_coverage": round(unknown_pixels / (page_shape[0] * page_shape[1]), 8), "panel_bubble_confusion": round(panel_confusion, 8)},
        "findings": findings,
        "confirmed_hard_failure_count": len(confirmed),
        "case_verdict": "PASS" if not confirmed else "FAIL",
    }
    after = {path: _sha256(path) for path in before}
    if before != after:
        raise RuntimeError("evaluator modified candidate or oracle")
    return result


def render_overlay(source_path: Path, candidate_dir: Path, oracle_path: Path, output_path: Path) -> None:
    candidate = json.loads((candidate_dir / "candidate.json").read_text(encoding="utf-8"))
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    with Image.open(source_path) as image:
        canvas = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    for feature in oracle["features"]:
        kind = feature["properties"]["kind"]
        geometry = feature["geometry"]
        if geometry["type"] == "Polygon" and kind in {"INSTANCE_INTERIOR", "SEPARATOR_CORRIDOR"}:
            points = np.rint(np.asarray(geometry["coordinates"][0])).astype(np.int32)
            cv2.polylines(canvas, [points], True, (0, 180, 255) if kind == "SEPARATOR_CORRIDOR" else (0, 255, 255), 2)
    for instance in candidate["instances"]:
        points = np.asarray(instance["interior"]["points"], dtype=np.int32)
        if len(points) >= 3:
            cv2.polylines(canvas, [points], True, (0, 220, 0), 2)
    for relation in candidate["relations"]:
        if relation["separator"]:
            points = np.asarray(relation["separator"]["points"], dtype=np.int32)
            cv2.polylines(canvas, [points], False, (255, 0, 255), 3)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), canvas):
        raise RuntimeError(f"unable to write overlay: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--oracle", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--overlay", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite evaluation")
    result = evaluate(args.candidate_dir, args.oracle, args.contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical(result))
    if bool(args.source) != bool(args.overlay):
        raise ValueError("--source and --overlay must be provided together")
    if args.source and args.overlay:
        render_overlay(args.source, args.candidate_dir, args.oracle, args.overlay)
    print(hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
