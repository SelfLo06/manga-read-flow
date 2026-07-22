#!/usr/bin/env python3
"""Oracle-free experimental Physical Boundary producer for A2."""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


PRODUCER_NAME = "physical-boundary-a2-constrained"
PRODUCER_VERSION = "0.1"
CANDIDATE_SCHEMA = "physical-boundary-a2-candidate-v0.1"


@dataclass(frozen=True)
class ProducerConfig:
    text_exclusion_margin: int = 10
    roi_scale_x: float = 2.15
    roi_scale_y: float = 1.75
    minimum_roi_margin: int = 28
    edge_low_threshold: int = 45
    edge_high_threshold: int = 135
    boundary_support_threshold: float = 0.08
    contact_dilation: int = 5


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def implementation_hash() -> str:
    return sha256_file(Path(__file__))


def config_hash(config: ProducerConfig) -> str:
    return sha256_bytes(canonical_bytes(asdict(config)))


def mask_hash(mask: np.ndarray) -> str:
    packed = np.packbits(mask.astype(np.uint8), axis=None).tobytes()
    return sha256_bytes(packed)


def encode_mask_rle(mask: np.ndarray) -> list[list[int]]:
    indices = np.flatnonzero(mask.ravel())
    if not len(indices):
        return []
    runs: list[list[int]] = []
    start = previous = int(indices[0])
    for value in map(int, indices[1:]):
        if value != previous + 1:
            runs.append([start, previous - start + 1])
            start = value
        previous = value
    runs.append([start, previous - start + 1])
    return runs


def decode_mask_rle(shape: tuple[int, int], runs: list[list[int]]) -> np.ndarray:
    flat = np.zeros(shape[0] * shape[1], dtype=bool)
    for start, length in runs:
        flat[start:start + length] = True
    return flat.reshape(shape)


def _polygon_mask(shape: tuple[int, int], points: list[list[float]]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    cv2.fillPoly(mask, [np.rint(np.asarray(points)).astype(np.int32)], 1)
    return mask.astype(bool)


def _group_bounds(group: dict[str, object]) -> tuple[int, int, int, int]:
    points = np.concatenate(
        [np.asarray(item["points"], dtype=np.float64) for item in group["fragment_geometries"]]
    )
    return tuple(map(int, (points[:, 0].min(), points[:, 1].min(), points[:, 0].max(), points[:, 1].max())))


def _ellipse_proposal(
    shape: tuple[int, int], bounds: tuple[int, int, int, int], config: ProducerConfig
) -> tuple[np.ndarray, list[list[int]]]:
    height, width = shape
    x0, y0, x1, y1 = bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx = max(config.minimum_roi_margin, (x1 - x0) * config.roi_scale_x / 2)
    ry = max(config.minimum_roi_margin, (y1 - y0) * config.roi_scale_y / 2)
    points = []
    for index in range(96):
        angle = 2 * math.pi * index / 96
        points.append(
            [
                int(np.clip(round(cx + rx * math.cos(angle)), 0, width - 1)),
                int(np.clip(round(cy + ry * math.sin(angle)), 0, height - 1)),
            ]
        )
    return _polygon_mask(shape, points), points


def _mask_to_polygon(mask: np.ndarray) -> list[list[int]]:
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    contour = max(contours, key=cv2.contourArea)
    epsilon = max(1.0, cv2.arcLength(contour, True) * 0.004)
    return [[int(x), int(y)] for [[x, y]] in cv2.approxPolyDP(contour, epsilon, True)]


def _boundary_support(mask: np.ndarray, edges: np.ndarray) -> tuple[float, np.ndarray]:
    eroded = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    perimeter = mask & ~eroded
    nearby_edges = cv2.dilate(edges.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    denominator = int(perimeter.sum())
    return (0.0 if denominator == 0 else float((perimeter & nearby_edges).sum() / denominator), perimeter & nearby_edges)


def _text_exclusion(shape: tuple[int, int], group: dict[str, object], margin: int) -> np.ndarray:
    core = np.zeros(shape, dtype=bool)
    for fragment in group["fragment_geometries"]:
        core |= _polygon_mask(shape, fragment["points"])
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (margin * 2 + 1, margin * 2 + 1))
    return cv2.dilate(core.astype(np.uint8), kernel).astype(bool)


def _separator(
    first: dict[str, object], second: dict[str, object], exclusions: np.ndarray, shape: tuple[int, int]
) -> list[list[int]] | None:
    ax, ay = first["seed"]
    bx, by = second["seed"]
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length == 0:
        return None
    mx, my = (ax + bx) / 2, (ay + by) / 2
    ux, uy = -dy / length, dx / length
    span = max(10.0, min(length * 0.45, min(first["radius"], second["radius"]) * 0.5))
    height, width = shape
    # Search only the local contact corridor. Offsets are global config-derived
    # candidates, never case-specific coordinates, and remain text-safe.
    for offset_ratio in (0.0, -0.08, 0.08, -0.16, 0.16, -0.24, 0.24, -0.32, 0.32):
        ox, oy = mx + dx * offset_ratio, my + dy * offset_ratio
        points = [
            [int(np.clip(round(ox - ux * span), 0, width - 1)), int(np.clip(round(oy - uy * span), 0, height - 1))],
            [int(np.clip(round(ox + ux * span), 0, width - 1)), int(np.clip(round(oy + uy * span), 0, height - 1))],
        ]
        line = np.zeros(shape, dtype=np.uint8)
        cv2.line(line, tuple(points[0]), tuple(points[1]), 1, 2)
        if not np.any(line.astype(bool) & exclusions):
            return points
    return None


def _frontier_separator(first: dict[str, object], second: dict[str, object], exclusions: np.ndarray) -> list[list[int]] | None:
    kernel = np.ones((5, 5), np.uint8)
    frontier = (
        cv2.dilate(first["mask"].astype(np.uint8), kernel).astype(bool)
        & cv2.dilate(second["mask"].astype(np.uint8), kernel).astype(bool)
        & ~exclusions
    )
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(frontier.astype(np.uint8), 8)
    if count <= 1:
        return None
    midpoint = np.asarray([(first["seed"][0] + second["seed"][0]) / 2, (first["seed"][1] + second["seed"][1]) / 2])
    eligible = [index for index in range(1, count) if stats[index, cv2.CC_STAT_AREA] >= 8]
    if not eligible:
        return None
    component_id = min(eligible, key=lambda index: float(np.linalg.norm(centroids[index] - midpoint)))
    component = labels == component_id
    y0, x0 = np.argwhere(component)[0]

    def farthest(start: tuple[int, int], keep_parents: bool = False):
        queue = deque([start])
        distance = {start: 0}
        parents = {} if keep_parents else None
        last = start
        while queue:
            current = queue.popleft()
            last = current if distance[current] >= distance[last] else last
            cy, cx = current
            for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
                neighbor = (cy + dy, cx + dx)
                ny, nx = neighbor
                if ny < 0 or nx < 0 or ny >= component.shape[0] or nx >= component.shape[1]:
                    continue
                if not component[neighbor] or neighbor in distance:
                    continue
                distance[neighbor] = distance[current] + 1
                if parents is not None:
                    parents[neighbor] = current
                queue.append(neighbor)
        return last, parents

    endpoint_a, _ = farthest((int(y0), int(x0)))
    endpoint_b, parents = farthest(endpoint_a, keep_parents=True)
    assert parents is not None
    path = [endpoint_b]
    while path[-1] != endpoint_a:
        path.append(parents[path[-1]])
    path.reverse()
    points = np.asarray([[x, y] for y, x in path], dtype=np.int32).reshape((-1, 1, 2))
    simplified = cv2.approxPolyDP(points, 1.5, False)
    result = [[int(x), int(y)] for [[x, y]] in simplified]
    return result if len(result) >= 2 else None


def produce(source_path: Path, input_path: Path, config: ProducerConfig = ProducerConfig()) -> tuple[dict, dict]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("split") not in {"development", "holdout"}:
        raise ValueError("unsupported split")
    source_bytes = source_path.read_bytes()
    source_hash = sha256_bytes(source_bytes)
    if source_hash != payload["source"]["sha256"]:
        raise ValueError("source hash mismatch")
    with Image.open(source_path) as image:
        rgb = np.asarray(image.convert("RGB"))
    if [rgb.shape[1], rgb.shape[0]] != [payload["source"]["width"], payload["source"]["height"]]:
        raise ValueError("source dimensions mismatch")
    shape = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, config.edge_low_threshold, config.edge_high_threshold).astype(bool)
    groups = payload["grouping_input"]["text_groups"]
    exclusions = np.zeros(shape, dtype=bool)
    for group in groups:
        exclusions |= _text_exclusion(shape, group, config.text_exclusion_margin)

    instances = []
    internal = []
    exclusion_records = []
    any_incomplete = False
    for ordinal, group in enumerate(groups, 1):
        exclusion = _text_exclusion(shape, group, config.text_exclusion_margin)
        exclusion_records.append({
            "kind": "TEXT_EXCLUSION",
            "evidence": "INFERRED",
            "text_group_id": group["text_group_id"],
            "mask_ref": f"masks/text-exclusion-{ordinal:03d}.bin",
            "mask_sha256": mask_hash(exclusion),
            "mask_shape": list(shape),
            "mask_rle": encode_mask_rle(exclusion),
            "geometry": {"geometry_type": "polygon", "points": _mask_to_polygon(exclusion)},
        })
        bounds = _group_bounds(group)
        proposal, proposal_points = _ellipse_proposal(shape, bounds, config)
        score, observed = _boundary_support(proposal, edges)
        x0, y0, x1, y1 = bounds
        seed = [round((x0 + x1) / 2, 3), round((y0 + y1) / 2, 3)]
        supported = score >= config.boundary_support_threshold
        any_incomplete |= not supported
        instance_id = f"candidate-i{ordinal:03d}"
        closures = []
        directions = []
        for direction, touches in (
            ("LEFT", np.any(proposal[:, 0])), ("RIGHT", np.any(proposal[:, -1])),
            ("TOP", np.any(proposal[0, :])), ("BOTTOM", np.any(proposal[-1, :])),
        ):
            if touches:
                directions.append(direction)
        for direction in directions:
            ys, xs = np.where(proposal)
            if direction == "LEFT": points = [[0, int(ys.min())], [0, int(ys.max())]]
            elif direction == "RIGHT": points = [[shape[1] - 1, int(ys.min())], [shape[1] - 1, int(ys.max())]]
            elif direction == "TOP": points = [[int(xs.min()), 0], [int(xs.max()), 0]]
            else: points = [[int(xs.min()), shape[0] - 1], [int(xs.max()), shape[0] - 1]]
            closures.append({"kind": "PAGE_EDGE_CLOSURE", "evidence": "VIRTUAL", "direction": direction, "points": points})
        instances.append({
            "instance_id": instance_id,
            "text_group_ids": [group["text_group_id"]],
            "resolution": "RESOLVED" if supported else "INCOMPLETE",
            "interior": {"geometry_type": "polygon", "points": _mask_to_polygon(proposal), "evidence": "INFERRED" if supported else "UNKNOWN", "mask_ref": f"masks/instance-{ordinal:03d}.bin", "mask_sha256": mask_hash(proposal), "mask_shape": list(shape), "mask_rle": encode_mask_rle(proposal)},
            "observed_boundary": {"geometry_type": "pixel_mask", "pixel_count": int(observed.sum()), "evidence": "OBSERVED", "support_ratio": round(score, 8), "mask_ref": f"masks/observed-boundary-{ordinal:03d}.bin", "mask_sha256": mask_hash(observed), "mask_shape": list(shape), "mask_rle": encode_mask_rle(observed)},
            "appearance_diagnostics": {"edge_support_ratio": round(score, 8), "proposal_kind": "ellipse_roi", "panel_relation": "UNKNOWN"},
            "page_truncation_directions": directions,
            "closures": closures,
        })
        internal.append({"instance_id": instance_id, "mask": proposal, "seed": seed, "radius": math.sqrt(float(proposal.sum()) / math.pi)})

    # Resolve shared proposal pixels by nearest immutable text-group seed. This
    # preserves identity without treating connected visual support as a merge.
    for first_index, first in enumerate(internal):
        for second in internal[first_index + 1:]:
            overlap = first["mask"] & second["mask"]
            if not np.any(overlap):
                continue
            ys, xs = np.where(overlap)
            first_distance = (xs - first["seed"][0]) ** 2 + (ys - first["seed"][1]) ** 2
            second_distance = (xs - second["seed"][0]) ** 2 + (ys - second["seed"][1]) ** 2
            first_loses = first_distance > second_distance
            second_loses = ~first_loses
            first["mask"][ys[first_loses], xs[first_loses]] = False
            second["mask"][ys[second_loses], xs[second_loses]] = False
    for instance, item in zip(instances, internal, strict=True):
        instance["interior"]["points"] = _mask_to_polygon(item["mask"])
        instance["interior"]["mask_sha256"] = mask_hash(item["mask"])
        instance["interior"]["mask_rle"] = encode_mask_rle(item["mask"])

    relations = []
    typed_boundaries = list(exclusion_records)
    for instance in instances:
        typed_boundaries.append({"kind": "BUBBLE_BOUNDARY", "evidence": "OBSERVED", "instance_id": instance["instance_id"], "mask_ref": instance["observed_boundary"]["mask_ref"], "mask_sha256": instance["observed_boundary"]["mask_sha256"], "support_ratio": instance["observed_boundary"]["support_ratio"]})
        for closure in instance["closures"]:
            typed_boundaries.append({**closure, "instance_id": instance["instance_id"]})
    kernel = np.ones((config.contact_dilation * 2 + 1, config.contact_dilation * 2 + 1), np.uint8)
    for index, first in enumerate(internal):
        for second in internal[index + 1:]:
            overlap = first["mask"] & second["mask"]
            near = cv2.dilate(first["mask"].astype(np.uint8), kernel).astype(bool) & second["mask"]
            if not np.any(overlap | near):
                continue
            separator = _separator(first, second, exclusions, shape)
            if separator is None:
                separator = _frontier_separator(first, second, exclusions)
            any_incomplete |= separator is None
            relations.append({
                "relation_id": f"relation-{len(relations) + 1:03d}",
                "instance_a": first["instance_id"], "instance_b": second["instance_id"],
                "contact": {"evidence": "OBSERVED", "pixel_count": int((overlap | near).sum())},
                "separator": None if separator is None else {"evidence": "VIRTUAL", "points": separator, "endpoint_evidence": [{"evidence": "VIRTUAL", "point": separator[0]}, {"evidence": "VIRTUAL", "point": separator[-1]}]},
                "resolution": "UNRESOLVED" if separator is None else "RESOLVED",
            })
            typed_boundaries.append({"kind": "CONTACT_REGION", "evidence": "OBSERVED", "relation_id": relations[-1]["relation_id"], "pixel_count": relations[-1]["contact"]["pixel_count"]})
            if separator is not None:
                typed_boundaries.append({"kind": "SEPARATOR", "evidence": "VIRTUAL", "relation_id": relations[-1]["relation_id"], "points": separator})

    candidate = {
        "schema": CANDIDATE_SCHEMA,
        "case_id": payload["case_id"],
        "page_dimensions": {"width": shape[1], "height": shape[0]},
        "source_sha256": source_hash,
        "grouping_input_sha256": sha256_file(input_path),
        "producer": {"name": PRODUCER_NAME, "version": PRODUCER_VERSION, "implementation_sha256": implementation_hash()},
        "config": {"values": asdict(config), "sha256": config_hash(config)},
        "run_outcome": "SUCCEEDED",
        "candidate_disposition": "INCOMPLETE" if any_incomplete else "PRODUCED",
        "instances": instances,
        "relations": relations,
        "typed_boundaries": typed_boundaries,
        "panel_boundary_proposals": [],
        "unknown_evidence": [{"reason": "insufficient_boundary_support", "instance_id": item["instance_id"]} for item in instances if item["resolution"] == "INCOMPLETE"],
    }
    provenance = {
        "schema": "physical-boundary-a2-provenance-v0.1",
        "case_id": payload["case_id"],
        "stages": [
            "INPUT_BINDING", "TEXT_EXCLUSION", "PROPOSAL_GENERATION", "INSTANCE_SEEDING",
            "PARTITION", "CONTACT_DETECTION", "SEPARATOR_SEARCH", "PAGE_OR_VIRTUAL_CLOSURE",
            "TYPED_EVIDENCE_ASSEMBLY",
        ],
        "proposal_policy": "text-seeded ellipse ROI plus image-edge support; proposals are never serialized as observed truth",
        "text_exclusion_pixel_count": int(exclusions.sum()),
        "text_exclusion_mask_sha256": mask_hash(exclusions),
        "edge_pixel_count": int(edges.sum()),
        "derived_mask_policy": "mask references are run-local packed-bit hashes; no mask is promoted to product truth",
        "instance_mask_sha256": {item["instance_id"]: item["interior"]["mask_sha256"] for item in instances},
    }
    return candidate, provenance


def write_candidate(output: Path, candidate: dict, provenance: dict) -> str:
    output.mkdir(parents=True, exist_ok=False)
    mask_records = []
    for instance in candidate["instances"]:
        mask_records.extend((instance["interior"], instance["observed_boundary"]))
    mask_records.extend(item for item in candidate["typed_boundaries"] if item["kind"] == "TEXT_EXCLUSION")
    for record in mask_records:
        mask = decode_mask_rle(tuple(record["mask_shape"]), record["mask_rle"])
        packed = np.packbits(mask.astype(np.uint8), axis=None).tobytes()
        if sha256_bytes(packed) != record["mask_sha256"]:
            raise ValueError(f"derived mask hash mismatch: {record['mask_ref']}")
        path = output / record["mask_ref"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(packed)
    candidate_bytes = canonical_bytes(candidate)
    candidate_hash = sha256_bytes(candidate_bytes)
    (output / "candidate.json").write_bytes(candidate_bytes)
    (output / "provenance.json").write_bytes(canonical_bytes(provenance))
    (output / "candidate.sha256").write_text(candidate_hash + "  candidate.json\n", encoding="ascii")
    return candidate_hash


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    candidate, provenance = produce(args.source, args.input)
    print(write_candidate(args.output, candidate, provenance))


if __name__ == "__main__":
    main()
