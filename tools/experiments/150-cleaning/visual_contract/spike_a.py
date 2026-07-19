#!/usr/bin/env python3
"""Bounded Spike A: BubbleInstance topology and per-instance eligibility.

This module is deliberately run-local.  It does not access SQLite, active
pointers, product repositories, providers, ArtifactService, or Workflow.
Candidate generation never consumes the evaluation oracle.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import heapq
import json
import math
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


SCHEMA_VERSION = "mvp1-visual-contract-spike-a-snapshot-v1"
THRESHOLD_VERSION = "mvp1-spike-a-topology-eligibility-v1"


class SpikeAStop(RuntimeError):
    """Raised when a frozen input or contract invariant is violated."""


@dataclass(frozen=True)
class SpikeAPolicy:
    """One general policy shared by real and synthetic cases."""

    same_container_saddle_ratio: float = 0.90
    boundary_band_px: int = 4
    segment_exclusion_padding_px: int = 8
    e1_min_luminance: float = 220.0
    e1_max_stddev: float = 36.0
    protected_overlap_ratio_e3: float = 0.05
    negligible_overlap_ratio: float = 0.01
    unsupported_area_ratio: float = 0.10
    min_segment_bbox_overlap_ratio: float = 0.15
    min_background_sample_pixels: int = 32

    def __post_init__(self) -> None:
        if not 0.0 < self.same_container_saddle_ratio <= 1.0:
            raise SpikeAStop("same-container saddle ratio must be in (0, 1]")
        if not 0.0 <= self.negligible_overlap_ratio < self.protected_overlap_ratio_e3 < 1.0:
            raise SpikeAStop("invalid protected-overlap thresholds")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mask_digest(mask: np.ndarray) -> str:
    if mask.dtype != np.bool_ or mask.ndim != 2:
        raise SpikeAStop("mask must be a 2D bool array")
    header = canonical_json({"shape": list(mask.shape), "encoding": "row-major-packed-bool-v1"})
    return hashlib.sha256(header + np.packbits(mask, axis=None).tobytes()).hexdigest()


def _stable_id(kind: str, *parts: Any) -> str:
    return f"{kind}::{digest_value(list(parts))[:20]}"


def _bbox_center(bbox: dict[str, int]) -> tuple[int, int]:
    return (
        int(round(int(bbox["x"]) + int(bbox["width"]) / 2.0)),
        int(round(int(bbox["y"]) + int(bbox["height"]) / 2.0)),
    )


def _snap_to_mask(mask: np.ndarray, point: tuple[int, int]) -> tuple[int, int]:
    x, y = point
    if 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y, x]:
        return y, x
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise SpikeAStop("cannot snap seed to empty mask")
    index = int(np.argmin((xs - x) ** 2 + (ys - y) ** 2))
    return int(ys[index]), int(xs[index])


def _mask_crop(mask: np.ndarray, points: Iterable[tuple[int, int]], padding: int = 32) -> tuple[slice, slice]:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise SpikeAStop("empty cluster mask")
    point_list = list(points)
    y0 = max(0, min(int(ys.min()), *(item[0] for item in point_list)) - padding)
    y1 = min(mask.shape[0], max(int(ys.max()) + 1, *(item[0] + 1 for item in point_list)) + padding)
    x0 = max(0, min(int(xs.min()), *(item[1] for item in point_list)) - padding)
    x1 = min(mask.shape[1], max(int(xs.max()) + 1, *(item[1] + 1 for item in point_list)) + padding)
    return slice(y0, y1), slice(x0, x1)


def _widest_path_saddle(
    mask: np.ndarray,
    distance: np.ndarray,
    first: tuple[int, int],
    second: tuple[int, int],
) -> float:
    """Maximum possible minimum boundary clearance between two marker seeds."""

    if first == second:
        return float(distance[first])
    y_slice, x_slice = _mask_crop(mask, (first, second))
    local_mask = mask[y_slice, x_slice]
    local_distance = distance[y_slice, x_slice]
    start = (first[0] - y_slice.start, first[1] - x_slice.start)
    target = (second[0] - y_slice.start, second[1] - x_slice.start)
    best = np.full(local_mask.shape, -1.0, dtype=np.float32)
    best[start] = local_distance[start]
    queue: list[tuple[float, int, int]] = [(-float(best[start]), start[0], start[1])]
    while queue:
        negative_capacity, y, x = heapq.heappop(queue)
        capacity = -negative_capacity
        if capacity + 1e-6 < float(best[y, x]):
            continue
        if (y, x) == target:
            return capacity
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if not (0 <= ny < local_mask.shape[0] and 0 <= nx < local_mask.shape[1]):
                    continue
                if not local_mask[ny, nx]:
                    continue
                candidate = min(capacity, float(local_distance[ny, nx]))
                if candidate > float(best[ny, nx]):
                    best[ny, nx] = candidate
                    heapq.heappush(queue, (-candidate, ny, nx))
    return 0.0


class _UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, first: str, second: str) -> None:
        left, right = self.find(first), self.find(second)
        if left == right:
            return
        low, high = sorted((left, right))
        self.parent[high] = low


def _segment_partition(
    mask: np.ndarray,
    segments: list[dict[str, Any]],
    policy: SpikeAPolicy,
) -> tuple[list[list[str]], list[dict[str, Any]], dict[str, np.ndarray]]:
    ordered = sorted(segments, key=lambda item: item["segment_id"])
    if not ordered:
        raise SpikeAStop("cluster has no segments")
    distance = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    seeds = {
        item["segment_id"]: _snap_to_mask(mask, _bbox_center(item["bbox"]))
        for item in ordered
    }
    union = _UnionFind(seeds)
    pair_evidence: list[dict[str, Any]] = []
    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1 :]:
            left_id, right_id = left["segment_id"], right["segment_id"]
            saddle = _widest_path_saddle(mask, distance, seeds[left_id], seeds[right_id])
            denominator = max(1e-6, min(float(distance[seeds[left_id]]), float(distance[seeds[right_id]])))
            ratio = min(1.0, saddle / denominator)
            decision = "same" if ratio >= policy.same_container_saddle_ratio else "different"
            if decision == "same":
                union.union(left_id, right_id)
            pair_evidence.append(
                {
                    "left_segment_id": left_id,
                    "right_segment_id": right_id,
                    "left_seed_clearance_px": round(float(distance[seeds[left_id]]), 6),
                    "right_seed_clearance_px": round(float(distance[seeds[right_id]]), 6),
                    "widest_path_saddle_px": round(float(saddle), 6),
                    "saddle_ratio": round(float(ratio), 6),
                    "same_threshold": policy.same_container_saddle_ratio,
                    "decision": decision,
                }
            )

    groups: dict[str, list[str]] = {}
    for segment_id in seeds:
        groups.setdefault(union.find(segment_id), []).append(segment_id)
    partitions = sorted((sorted(items) for items in groups.values()), key=lambda items: items[0])

    ys, xs = np.nonzero(mask)
    centers = [_bbox_center(item["bbox"]) for item in ordered]
    squared = np.stack([(xs - x) ** 2 + (ys - y) ** 2 for x, y in centers], axis=0)
    labels = np.argmin(squared, axis=0)
    seed_masks: dict[str, np.ndarray] = {}
    for index, segment in enumerate(ordered):
        item_mask = np.zeros_like(mask)
        item_mask[ys[labels == index], xs[labels == index]] = True
        seed_masks[segment["segment_id"]] = item_mask
    partition_masks: dict[str, np.ndarray] = {}
    for partition in partitions:
        item_mask = np.zeros_like(mask)
        for segment_id in partition:
            item_mask |= seed_masks[segment_id]
        partition_masks["|".join(partition)] = item_mask
    return partitions, pair_evidence, partition_masks


def _luminance(image: np.ndarray) -> np.ndarray:
    return (0.2126 * image[..., 0] + 0.7152 * image[..., 1] + 0.0722 * image[..., 2]).astype(np.float32)


def _segment_exclusion_mask(shape: tuple[int, int], segments: list[dict[str, Any]], padding: int) -> np.ndarray:
    result = np.zeros(shape, dtype=np.uint8)
    for segment in segments:
        bbox = segment["bbox"]
        x0 = max(0, int(bbox["x"]) - padding)
        y0 = max(0, int(bbox["y"]) - padding)
        x1 = min(shape[1], int(bbox["x"]) + int(bbox["width"]) + padding)
        y1 = min(shape[0], int(bbox["y"]) + int(bbox["height"]) + padding)
        result[y0:y1, x0:x1] = 1
    return result.astype(np.bool_)


def _segment_bbox_overlap_ratio(mask: np.ndarray, segment: dict[str, Any]) -> float:
    bbox = segment["bbox"]
    x0 = max(0, int(bbox["x"]))
    y0 = max(0, int(bbox["y"]))
    x1 = min(mask.shape[1], x0 + int(bbox["width"]))
    y1 = min(mask.shape[0], y0 + int(bbox["height"]))
    area = max(1, int(bbox["width"]) * int(bbox["height"]))
    return float(np.count_nonzero(mask[y0:y1, x0:x1]) / area)


def _eligibility(
    page_id: str,
    image: np.ndarray,
    instance: dict[str, Any],
    segments: list[dict[str, Any]],
    historical: dict[str, Any],
    policy: SpikeAPolicy,
) -> tuple[dict[str, Any], dict[str, Any]]:
    mask = instance["_mask"]
    page_area = max(1, mask.shape[0] * mask.shape[1])
    distance = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    excluded = _segment_exclusion_mask(mask.shape, segments, policy.segment_exclusion_padding_px)
    background = mask & (distance >= policy.boundary_band_px) & ~excluded
    if not np.any(background):
        background = mask & ~excluded
    gray = _luminance(image)
    mean = float(np.mean(gray[background])) if np.any(background) else 0.0
    stddev = float(np.std(gray[background])) if np.any(background) else float("inf")
    center_observations = []
    for segment in segments:
        x, y = _bbox_center(segment["bbox"])
        center_observations.append(bool(0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y, x]))
    overlap_ratios = [_segment_bbox_overlap_ratio(mask, item) for item in segments]
    centers_inside = all(center_observations)
    segment_geometry_grounded = centers_inside and all(
        value >= policy.min_segment_bbox_overlap_ratio for value in overlap_ratios
    )
    core_pixels = historical.get("core_pixels")
    overlap_pixels = historical.get("core_protected_overlap_pixels")
    overlap_localized = len(instance["segment_ids"]) == int(historical.get("parent_segment_count", len(instance["segment_ids"])))
    if overlap_pixels == 0:
        overlap_localized = True
    overlap_ratio = None
    if overlap_localized and isinstance(core_pixels, int) and core_pixels > 0 and isinstance(overlap_pixels, int):
        overlap_ratio = overlap_pixels / core_pixels
    area_ratio = float(mask.sum() / page_area)
    unsupported_candidate = area_ratio > policy.unsupported_area_ratio and stddev > policy.e1_max_stddev
    qualification_status = "QUALIFIED_UNSUPPORTED" if unsupported_candidate else "QUALIFIED_SUPPORTED"
    qualification_reasons = ["MASK_NONEMPTY", "SEGMENT_CENTERS_INSIDE"]
    if not segment_geometry_grounded:
        qualification_status = "NOT_QUALIFIED"
        qualification_reasons = ["SEGMENT_GEOMETRY_NOT_GROUNDED_IN_INSTANCE"]
    elif unsupported_candidate:
        qualification_reasons.append("LARGE_COMPLEX_FREE_TEXT_OR_SFX_CANDIDATE")

    rules = [
        {
            "rule_id": "Q_SEGMENT_INSTANCE_GROUNDING",
            "passed": segment_geometry_grounded,
            "observed": {
                "centers_inside": center_observations,
                "bbox_overlap_ratios": [round(value, 8) for value in overlap_ratios],
            },
            "required": {
                "all_centers_inside": True,
                "min_bbox_overlap_ratio": policy.min_segment_bbox_overlap_ratio,
            },
        },
        {
            "rule_id": "R_PROTECTED_OVERLAP_RATIO",
            "passed": overlap_ratio is not None and overlap_ratio <= policy.protected_overlap_ratio_e3,
            "observed": None if overlap_ratio is None else round(overlap_ratio, 8),
            "e1_negligible_max": policy.negligible_overlap_ratio,
            "e3_threshold": policy.protected_overlap_ratio_e3,
        },
        {
            "rule_id": "R_E1_BACKGROUND",
            "passed": int(background.sum()) >= policy.min_background_sample_pixels
            and mean >= policy.e1_min_luminance
            and stddev <= policy.e1_max_stddev,
            "observed": {
                "sample_pixels": int(background.sum()),
                "mean": round(mean, 6),
                "stddev": round(stddev, 6),
            },
            "required": {
                "sample_pixels_min": policy.min_background_sample_pixels,
                "mean_min": policy.e1_min_luminance,
                "stddev_max": policy.e1_max_stddev,
            },
        },
        {
            "rule_id": "R_SUPPORTED_SCOPE",
            "passed": not unsupported_candidate,
            "observed": {"area_ratio": round(area_ratio, 8), "background_stddev": round(stddev, 6)},
            "unsupported_if": {
                "area_ratio_gt": policy.unsupported_area_ratio,
                "background_stddev_gt": policy.e1_max_stddev,
            },
        },
    ]
    reason_codes: list[str]
    if not segment_geometry_grounded:
        risk, reason_codes = "E3", ["INSTANCE_GROUNDING_FAILED"]
    elif unsupported_candidate:
        risk, reason_codes = "E3", ["UNSUPPORTED_COMPLEX_FREE_TEXT_OR_SFX_CANDIDATE"]
    elif overlap_ratio is None:
        risk, reason_codes = "E3", ["PROTECTED_OVERLAP_NOT_LOCALIZED_PER_INSTANCE"]
    elif overlap_ratio > policy.protected_overlap_ratio_e3:
        risk, reason_codes = "E3", ["PROTECTED_OVERLAP_RATIO_EXCEEDS_LIMIT"]
    elif int(background.sum()) < policy.min_background_sample_pixels:
        risk, reason_codes = "E3", ["BACKGROUND_EVIDENCE_INSUFFICIENT"]
    elif mean >= policy.e1_min_luminance and stddev <= policy.e1_max_stddev:
        risk, reason_codes = "E1", ["LIGHT_LOW_VARIANCE_INSTANCE"]
        if overlap_ratio > 0:
            reason_codes.append("NEGLIGIBLE_PROTECTED_OVERLAP_RETAIN_SAFE_PIXELS_ONLY")
    else:
        risk, reason_codes = "E2", ["NON_UNIFORM_OR_DARK_INSTANCE_BACKGROUND"]

    features = {
        "instance_pixels": int(mask.sum()),
        "instance_area_ratio": round(area_ratio, 8),
        "segment_count": len(segments),
        "fragment_count": sum(len(item.get("fragment_ids", ())) for item in segments),
        "segment_centers_inside": centers_inside,
        "segment_center_observations": center_observations,
        "segment_bbox_overlap_ratios": [round(value, 8) for value in overlap_ratios],
        "segment_geometry_grounded": segment_geometry_grounded,
        "background_sample_pixels": int(background.sum()),
        "background_luminance": round(mean, 6),
        "background_stddev": round(stddev, 6),
        "core_pixels": core_pixels,
        "core_protected_overlap_pixels": overlap_pixels,
        "protected_overlap_ratio": None if overlap_ratio is None else round(overlap_ratio, 8),
        "protected_overlap_localized": overlap_localized,
    }
    evidence = {
        "page_id": page_id,
        "instance_mask_sha256": instance["mask_sha256"],
        "segment_ids": list(instance["segment_ids"]),
        "historical_evidence_sha256": historical.get("evidence_sha256"),
    }
    qualification = {
        "instance_id": instance["instance_id"],
        "status": qualification_status,
        "reason_codes": qualification_reasons,
        "features": features,
        "threshold_version": THRESHOLD_VERSION,
        "evidence": evidence,
    }
    assessment = {
        "instance_id": instance["instance_id"],
        "historical_parent_risk": historical.get("historical_risk"),
        "historical_parent_decision": historical.get("historical_decision"),
        "candidate_risk": risk,
        "changed_from_historical": bool(historical.get("historical_risk") and historical.get("historical_risk") != risk),
        "reason_codes": reason_codes,
        "rules": rules,
        "features": features,
        "threshold_version": THRESHOLD_VERSION,
        "evidence": evidence,
    }
    return qualification, assessment


def analyze_page(case: dict[str, Any], policy: SpikeAPolicy) -> dict[str, Any]:
    image = case["image"]
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3:
        raise SpikeAStop("page image must be RGB ndarray")
    segments = {item["segment_id"]: copy.deepcopy(item) for item in case["segments"]}
    if len(segments) != len(case["segments"]):
        raise SpikeAStop("duplicate segment identity")
    cluster_results: list[dict[str, Any]] = []
    instances: list[dict[str, Any]] = []
    qualifications: list[dict[str, Any]] = []
    assessments: list[dict[str, Any]] = []
    assigned_segments: set[str] = set()
    for source_cluster in case["clusters"]:
        segment_ids = sorted(source_cluster["segment_ids"])
        if not segment_ids or any(item not in segments for item in segment_ids):
            raise SpikeAStop("cluster references unknown or empty segment set")
        if assigned_segments.intersection(segment_ids):
            raise SpikeAStop("segment appears in multiple source clusters")
        assigned_segments.update(segment_ids)
        mask = source_cluster["mask"]
        if mask.dtype != np.bool_ or mask.shape != image.shape[:2] or not np.any(mask):
            raise SpikeAStop("invalid source cluster mask")
        cluster_id = _stable_id("cluster", case["page_id"], sorted(segment_ids), mask_digest(mask))
        cluster_segments = [segments[item] for item in segment_ids]
        partitions, pair_evidence, partition_masks = _segment_partition(mask, cluster_segments, policy)
        cluster_instance_ids: list[str] = []
        cluster_instances: list[dict[str, Any]] = []
        for partition in partitions:
            instance_mask = partition_masks["|".join(partition)]
            instance_id = _stable_id("instance", cluster_id, partition)
            instance = {
                "instance_id": instance_id,
                "cluster_id": cluster_id,
                "segment_ids": partition,
                "mask_sha256": mask_digest(instance_mask),
                "mask_pixel_count": int(instance_mask.sum()),
                "revision_id": _stable_id("instance-revision", instance_id, mask_digest(instance_mask)),
                "_mask": instance_mask,
            }
            historical = copy.deepcopy(source_cluster.get("historical_evidence", {}))
            historical["parent_segment_count"] = len(segment_ids)
            qualification, assessment = _eligibility(
                case["page_id"], image, instance, [segments[item] for item in partition], historical, policy
            )
            cluster_instance_ids.append(instance_id)
            cluster_instances.append(instance)
            instances.append(instance)
            qualifications.append(qualification)
            assessments.append(assessment)
        union_mask = np.zeros_like(mask)
        overlap_pixels = 0
        for instance in cluster_instances:
            overlap_pixels += int(np.count_nonzero(union_mask & instance["_mask"]))
            union_mask |= instance["_mask"]
        if overlap_pixels or not np.array_equal(union_mask, mask):
            raise SpikeAStop("instance masks are not a disjoint complete cluster partition")
        cluster_results.append(
            {
                "cluster_id": cluster_id,
                "source_candidate_ref": source_cluster.get("source_candidate_ref"),
                "segment_ids": segment_ids,
                "instance_ids": sorted(cluster_instance_ids),
                "mask_sha256": mask_digest(mask),
                "mask_pixel_count": int(mask.sum()),
                "instance_union_sha256": mask_digest(union_mask),
                "instance_overlap_pixels": overlap_pixels,
                "topology_evidence": pair_evidence,
                "revision_id": _stable_id("cluster-revision", cluster_id, mask_digest(mask), pair_evidence),
                "_mask": mask,
            }
        )
    missing = sorted(set(segments) - assigned_segments)
    dispositions = [
        {
            "segment_id": segment_id,
            "kind": "ASSIGNED",
            "assigned_instance_id": next(
                item["instance_id"] for item in instances if segment_id in item["segment_ids"]
            ),
            "exclusion": None,
        }
        for segment_id in sorted(assigned_segments)
    ]
    dispositions.extend(
        {
            "segment_id": segment_id,
            "kind": "EXCLUDED",
            "assigned_instance_id": None,
            "exclusion": {"reason_code": "NO_SOURCE_CLUSTER", "evidence": "explicit-run-input-gap"},
        }
        for segment_id in missing
    )
    page_revision = _stable_id(
        "page-visual-revision",
        case["page_id"],
        sorted((item["cluster_id"], item["revision_id"]) for item in cluster_results),
    )
    return {
        "page_id": case["page_id"],
        "source_sha256": case["source_sha256"],
        "page_visual_revision_id": page_revision,
        "text_segments": [segments[item] for item in sorted(segments)],
        "contact_bubble_clusters": sorted(cluster_results, key=lambda item: item["cluster_id"]),
        "bubble_instances": sorted(instances, key=lambda item: item["instance_id"]),
        "segment_dispositions": dispositions,
        "instance_qualifications": sorted(qualifications, key=lambda item: item["instance_id"]),
        "eligibility_assessments": sorted(assessments, key=lambda item: item["instance_id"]),
        "_image": image,
    }


def relationship_digest(page: dict[str, Any]) -> str:
    payload = {
        "page_id": page["page_id"],
        "partitions": sorted(sorted(item["segment_ids"]) for item in page["bubble_instances"]),
        "dispositions": sorted(
            (item["segment_id"], item["kind"], item.get("assigned_instance_id"))
            for item in page["segment_dispositions"]
        ),
    }
    return digest_value(payload)


def _ellipse(shape: tuple[int, int], center: tuple[int, int], axes: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    cv2.ellipse(mask, center, axes, 0, 0, 360, 1, -1)
    return mask.astype(np.bool_)


def _segment(segment_id: str, x: int, y: int, width: int, height: int) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "text_group_id": f"group::{segment_id}",
        "fragment_ids": [f"fragment::{segment_id}"],
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "active": True,
    }


def synthetic_case(case_id: str) -> dict[str, Any]:
    if case_id == "synthetic-contact-n3":
        shape = (430, 260)
        masks = [_ellipse(shape, (130, y), (82, 92)) for y in (100, 215, 330)]
        mask = masks[0] | masks[1] | masks[2]
        segments = [_segment(f"n3-s{i}", 110, y - 30, 40, 60) for i, y in enumerate((100, 215, 330), 1)]
        image = np.full((*shape, 3), 245, dtype=np.uint8)
    elif case_id == "synthetic-multi-column":
        shape = (280, 360)
        mask = _ellipse(shape, (180, 140), (145, 110))
        segments = [
            _segment("columns-left", 105, 95, 40, 90),
            _segment("columns-right", 215, 95, 40, 90),
        ]
        image = np.full((*shape, 3), 248, dtype=np.uint8)
    elif case_id == "synthetic-two-paragraphs":
        shape = (380, 300)
        mask = _ellipse(shape, (150, 190), (110, 165))
        segments = [
            _segment("paragraph-top", 125, 85, 50, 75),
            _segment("paragraph-bottom", 125, 225, 50, 75),
        ]
        image = np.full((*shape, 3), 248, dtype=np.uint8)
    elif case_id == "synthetic-mixed-risk":
        shape = (280, 470)
        left = _ellipse(shape, (145, 140), (115, 105))
        right = _ellipse(shape, (325, 140), (115, 105))
        mask = left | right
        segments = [
            _segment("mixed-safe", 115, 100, 45, 80),
            _segment("mixed-risky", 305, 100, 45, 80),
        ]
        image = np.full((*shape, 3), 246, dtype=np.uint8)
        yy, xx = np.indices(shape)
        texture = ((xx * 13 + yy * 17) % 120).astype(np.uint8)
        risky_pixels = right & (xx >= 235)
        image[risky_pixels] = np.stack(
            (
                60 + texture[risky_pixels],
                45 + texture[risky_pixels] // 2,
                80 + texture[risky_pixels] // 3,
            ),
            axis=1,
        )
    else:
        raise KeyError(case_id)
    return {
        "page_id": case_id,
        "source_sha256": digest_value({"synthetic": case_id}),
        "image": image,
        "segments": segments,
        "clusters": [
            {
                "source_candidate_ref": f"synthetic::{case_id}",
                "segment_ids": [item["segment_id"] for item in segments],
                "mask": mask,
                "historical_evidence": {
                    "historical_risk": None,
                    "historical_decision": None,
                    "core_pixels": 1,
                    "core_protected_overlap_pixels": 0,
                    "evidence_sha256": digest_value({"synthetic-evidence": case_id}),
                },
            }
        ],
    }


def _public_page(page: dict[str, Any]) -> dict[str, Any]:
    def public_item(item: dict[str, Any]) -> dict[str, Any]:
        return {key: copy.deepcopy(value) for key, value in item.items() if not key.startswith("_")}

    return {
        "page_id": page["page_id"],
        "source_sha256": page["source_sha256"],
        "page_visual_revision_id": page["page_visual_revision_id"],
        "text_segments": [public_item(item) for item in page["text_segments"]],
        "contact_bubble_clusters": [public_item(item) for item in page["contact_bubble_clusters"]],
        "bubble_instances": [public_item(item) for item in page["bubble_instances"]],
        "segment_dispositions": copy.deepcopy(page["segment_dispositions"]),
        "instance_qualifications": copy.deepcopy(page["instance_qualifications"]),
        "eligibility_assessments": copy.deepcopy(page["eligibility_assessments"]),
    }


def build_snapshot(
    pages: Iterable[dict[str, Any]],
    policy: SpikeAPolicy,
    input_lock: dict[str, Any] | None = None,
) -> dict[str, Any]:
    public_pages = sorted((_public_page(item) for item in pages), key=lambda item: item["page_id"])
    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": "CANDIDATE_FROZEN_BEFORE_ORACLE",
        "relationship_source": {
            "kind": "RUN_LOCAL_VISUAL_CONTRACT_SNAPSHOT",
            "exclusive_for_run": True,
        },
        "policy": {"threshold_version": THRESHOLD_VERSION, **asdict(policy)},
        "input_lock": copy.deepcopy(input_lock or {"kind": "synthetic-only"}),
        "pages": public_pages,
    }
    snapshot["snapshot_sha256"] = digest_value(snapshot)
    return snapshot


def _snapshot_hash_valid(snapshot: dict[str, Any]) -> bool:
    payload = copy.deepcopy(snapshot)
    observed = payload.pop("snapshot_sha256", None)
    return isinstance(observed, str) and observed == digest_value(payload)


def _partition_sets(page: dict[str, Any]) -> list[frozenset[str]]:
    return [frozenset(item["segment_ids"]) for item in page.get("bubble_instances", ())]


def _semantic_oracle_failures(page: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    actual = _partition_sets(page)
    wanted = [frozenset(item) for item in expected["expected_instance_partitions"]]
    for left_index, left in enumerate(wanted):
        for right in wanted[left_index + 1 :]:
            if any(left.intersection(item) and right.intersection(item) for item in actual):
                failures.append("EXPECTED_DIFFERENT_SEGMENTS_MERGED")
                break
    for expected_partition in wanted:
        holders = {index for index, item in enumerate(actual) if item.intersection(expected_partition)}
        if len(expected_partition) > 1 and len(holders) > 1:
            failures.append("EXPECTED_SAME_SEGMENTS_SPLIT")
    actual_segments = set().union(*actual) if actual else set()
    wanted_segments = set().union(*wanted) if wanted else set()
    if actual_segments != wanted_segments:
        failures.append("EXPECTED_SEGMENT_SET_MISMATCH")
    return failures


def validate_snapshot(snapshot: dict[str, Any], oracle: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        failures.append("SNAPSHOT_SCHEMA_INVALID")
    if snapshot.get("relationship_source") != {
        "kind": "RUN_LOCAL_VISUAL_CONTRACT_SNAPSHOT",
        "exclusive_for_run": True,
    }:
        failures.append("RELATIONSHIP_SOURCE_NOT_EXCLUSIVE")
    forbidden_text = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    for forbidden in ("parent_bbox_mapping", "directory_order_mapping", "cluster_risk"):
        if forbidden in forbidden_text:
            failures.append("FORBIDDEN_RELATIONSHIP_SHORTCUT")
    if not _snapshot_hash_valid(snapshot):
        failures.append("SNAPSHOT_HASH_MISMATCH")

    oracle_cases = oracle.get("cases", {})
    for page in snapshot.get("pages", ()):
        page_id = page.get("page_id")
        segments = {item["segment_id"] for item in page.get("text_segments", ()) if item.get("active", True)}
        instances = {item["instance_id"]: item for item in page.get("bubble_instances", ())}
        if len(instances) != len(page.get("bubble_instances", ())):
            failures.append("DUPLICATE_INSTANCE_ID")
        dispositions = page.get("segment_dispositions", ())
        if {item.get("segment_id") for item in dispositions} != segments or len(dispositions) != len(segments):
            failures.append("SEGMENT_DISPOSITION_INVALID")
        assigned_seen: set[str] = set()
        for disposition in dispositions:
            segment_id = disposition.get("segment_id")
            kind = disposition.get("kind")
            assigned = disposition.get("assigned_instance_id")
            exclusion = disposition.get("exclusion")
            if kind == "ASSIGNED":
                if not assigned or assigned not in instances or exclusion is not None:
                    failures.append("SEGMENT_DISPOSITION_INVALID")
                    continue
                if segment_id not in instances[assigned].get("segment_ids", ()):
                    failures.append("EXPECTED_ASSIGNMENT_MISMATCH")
                if segment_id in assigned_seen:
                    failures.append("SEGMENT_DISPOSITION_INVALID")
                assigned_seen.add(segment_id)
            elif kind == "EXCLUDED":
                if assigned is not None or not isinstance(exclusion, dict) or not exclusion.get("reason_code"):
                    failures.append("SEGMENT_DISPOSITION_INVALID")
            else:
                failures.append("SEGMENT_DISPOSITION_INVALID")

        clusters = {item["cluster_id"]: item for item in page.get("contact_bubble_clusters", ())}
        for instance in instances.values():
            if instance.get("cluster_id") not in clusters or not instance.get("segment_ids"):
                failures.append("INSTANCE_RELATION_INVALID")
        for cluster in clusters.values():
            linked = {item["instance_id"] for item in instances.values() if item["cluster_id"] == cluster["cluster_id"]}
            if linked != set(cluster.get("instance_ids", ())):
                failures.append("CLUSTER_INSTANCE_RELATION_INVALID")
            if cluster.get("instance_overlap_pixels") != 0:
                failures.append("INSTANCE_MASK_OVERLAP")
            if cluster.get("instance_union_sha256") != cluster.get("mask_sha256"):
                failures.append("INSTANCE_MASK_UNION_MISMATCH")

        assessments = {item["instance_id"]: item for item in page.get("eligibility_assessments", ())}
        if set(assessments) != set(instances):
            failures.append("ELIGIBILITY_CARDINALITY_MISMATCH")
        for assessment in assessments.values():
            if assessment.get("candidate_risk") in {"E2", "E3"} and not all(
                assessment.get(field) for field in ("reason_codes", "rules", "features", "threshold_version", "evidence")
            ):
                failures.append("E2_E3_EVIDENCE_INCOMPLETE")

        expected = oracle_cases.get(page_id)
        if expected:
            failures.extend(_semantic_oracle_failures(page, expected))
            if expected.get("require_distinct_candidate_risks") and len(
                {item["candidate_risk"] for item in assessments.values()}
            ) < 2:
                failures.append("CLUSTER_WORST_RISK_BROADCAST")

    unique_failures = sorted(set(failures))
    return {
        "schema_version": "mvp1-spike-a-validation-v1",
        "passed": not unique_failures,
        "failure_codes": unique_failures,
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "oracle_sha256": digest_value(oracle),
    }


def _rehash_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    snapshot.pop("snapshot_sha256", None)
    snapshot["snapshot_sha256"] = digest_value(snapshot)
    return snapshot


def apply_deliberate_mutation(snapshot: dict[str, Any], mutation: str) -> dict[str, Any]:
    result = copy.deepcopy(snapshot)
    by_page = {item["page_id"]: item for item in result["pages"]}
    if mutation == "deliberate_merge":
        page = by_page["synthetic-contact-n3"]
        instances = page["bubble_instances"]
        first, second = instances[0], instances[1]
        first["segment_ids"] = sorted(first["segment_ids"] + second["segment_ids"])
        instances.remove(second)
        cluster = page["contact_bubble_clusters"][0]
        cluster["instance_ids"] = [item for item in cluster["instance_ids"] if item != second["instance_id"]]
        for disposition in page["segment_dispositions"]:
            if disposition["assigned_instance_id"] == second["instance_id"]:
                disposition["assigned_instance_id"] = first["instance_id"]
        page["instance_qualifications"] = [
            item for item in page["instance_qualifications"] if item["instance_id"] != second["instance_id"]
        ]
        page["eligibility_assessments"] = [
            item for item in page["eligibility_assessments"] if item["instance_id"] != second["instance_id"]
        ]
    elif mutation == "deliberate_split":
        page = by_page["synthetic-multi-column"]
        instance = page["bubble_instances"][0]
        moved = instance["segment_ids"].pop()
        clone = copy.deepcopy(instance)
        clone["instance_id"] = _stable_id("deliberate-instance", moved)
        clone["segment_ids"] = [moved]
        page["bubble_instances"].append(clone)
        page["contact_bubble_clusters"][0]["instance_ids"].append(clone["instance_id"])
        for disposition in page["segment_dispositions"]:
            if disposition["segment_id"] == moved:
                disposition["assigned_instance_id"] = clone["instance_id"]
        qualification = copy.deepcopy(page["instance_qualifications"][0])
        assessment = copy.deepcopy(page["eligibility_assessments"][0])
        qualification["instance_id"] = clone["instance_id"]
        assessment["instance_id"] = clone["instance_id"]
        page["instance_qualifications"].append(qualification)
        page["eligibility_assessments"].append(assessment)
    elif mutation == "deliberate_unassigned":
        page = by_page["synthetic-contact-n3"]
        page["segment_dispositions"][0]["assigned_instance_id"] = None
    elif mutation == "deliberate_wrong_instance":
        page = by_page["synthetic-contact-n3"]
        first, second = page["bubble_instances"][:2]
        target_segment = first["segment_ids"][0]
        disposition = next(item for item in page["segment_dispositions"] if item["segment_id"] == target_segment)
        disposition["assigned_instance_id"] = second["instance_id"]
    else:
        raise KeyError(mutation)
    return _rehash_snapshot(result)


def synthetic_snapshot_and_oracle() -> tuple[dict[str, Any], dict[str, Any]]:
    policy = SpikeAPolicy()
    case_ids = (
        "synthetic-contact-n3",
        "synthetic-multi-column",
        "synthetic-two-paragraphs",
        "synthetic-mixed-risk",
    )
    pages = [analyze_page(synthetic_case(case_id), policy) for case_id in case_ids]
    oracle = {
        "schema_version": "mvp1-visual-contract-spike-a-oracle-v1",
        "cases": {
            "synthetic-contact-n3": {
                "expected_instance_partitions": [["n3-s1"], ["n3-s2"], ["n3-s3"]]
            },
            "synthetic-multi-column": {
                "expected_instance_partitions": [["columns-left", "columns-right"]]
            },
            "synthetic-two-paragraphs": {
                "expected_instance_partitions": [["paragraph-top", "paragraph-bottom"]]
            },
            "synthetic-mixed-risk": {
                "expected_instance_partitions": [["mixed-safe"], ["mixed-risky"]],
                "require_distinct_candidate_risks": True,
            },
        },
    }
    return build_snapshot(pages, policy), oracle


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SpikeAStop(f"JSON root must be an object: {path}")
    return value


def _git_value(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _real_cases(
    repository_root: Path,
    source_root: Path,
    s1_path: Path,
    goal5_lock_path: Path,
    provenance_path: Path,
    ocr_path: Path,
    goal6_results_dir: Path,
    context_semantics_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build real candidates without consulting any evaluation oracle."""

    from tools.experiments.grouping_120.text_seeded_container_association import routed_association as routed
    from tools.experiments.grouping_120.text_seeded_container_association.goal6_build_calibration import _contexts
    from tools.experiments.grouping_120.text_seeded_container_association.run_routed_evaluation import policy_from_lock

    s1 = _load_json(s1_path)
    if s1.get("status") != "completed" or s1.get("input_hashes_unchanged") is not True:
        raise SpikeAStop("frozen S1 is not completed and hash-stable")
    provenance = _load_json(provenance_path)
    ocr = _load_json(ocr_path)
    goal5_lock = _load_json(goal5_lock_path)
    policy = policy_from_lock(goal5_lock)
    ledger_pages = {item["asset_id"]: item for item in provenance["pages"]}
    ocr_pages = {item["asset_id"]: item for item in ocr["pages"]}
    cases: list[dict[str, Any]] = []
    source_hashes: dict[str, str] = {}
    evidence_hashes: dict[str, str] = {
        "s1": sha256_file(s1_path),
        "goal5_lock": sha256_file(goal5_lock_path),
        "provenance": sha256_file(provenance_path),
        "ocr": sha256_file(ocr_path),
    }
    for asset in s1["assets"]:
        page_id = asset["asset_id"]
        image_path = source_root / asset["relative_path"]
        observed_source_hash = sha256_file(image_path)
        if observed_source_hash != asset["sha256"]:
            raise SpikeAStop(f"source hash changed: {page_id}")
        source_hashes[page_id] = observed_source_hash
        image = np.asarray(Image.open(image_path).convert("RGB"))
        association = routed.run_routed_association(routed.page_from_s1_asset(source_root, asset), policy)
        association_json = association.to_jsonable()
        contexts = {item.region_id: item for item in _contexts(association_json)}
        association_regions = {
            item["region_id"]: item for item in association_json.get("container_regions_or_null") or ()
        }
        historical_path = goal6_results_dir / page_id / "result.json"
        semantics_path = context_semantics_dir / page_id / "context-writeback-check.json"
        historical = _load_json(historical_path)
        semantics = _load_json(semantics_path)
        historical_contexts = {item["context_id"]: item for item in historical["contexts"]}
        semantic_contexts = {item["context_id"]: item for item in semantics["contexts"]}
        evidence_hashes[f"goal6_result::{page_id}"] = sha256_file(historical_path)
        evidence_hashes[f"context_semantics::{page_id}"] = sha256_file(semantics_path)
        ledger_blocks = {item["segment_id"]: item for item in ledger_pages[page_id]["blocks"]}
        segments: list[dict[str, Any]] = []
        for item in ocr_pages[page_id]["segments"]:
            ledger = ledger_blocks[item["segment_id"]]
            segments.append(
                {
                    "segment_id": item["segment_id"],
                    "text_group_id": item["text_group_id"],
                    "fragment_ids": list(item["fragment_ids"]),
                    "bbox": copy.deepcopy(item["bbox"]),
                    "reading_order": item["reading_order"],
                    "active": True,
                    "historical_status": ledger["status"],
                    "historical_exclusion_reason": ledger["exclusion_reason"],
                }
            )
        clusters: list[dict[str, Any]] = []
        matched_segments: set[str] = set()
        for legacy_id, context in contexts.items():
            owned_fragments = set(context.fragment_ids)
            cluster_segments = [
                item["segment_id"]
                for item in segments
                if set(item["fragment_ids"]).issubset(owned_fragments)
            ]
            if not cluster_segments:
                raise SpikeAStop(f"source cluster has no TextSegment: {page_id}/{legacy_id}")
            if matched_segments.intersection(cluster_segments):
                raise SpikeAStop(f"TextSegment matched multiple source clusters: {page_id}/{legacy_id}")
            matched_segments.update(cluster_segments)
            history = historical_contexts[legacy_id]
            semantic = semantic_contexts[legacy_id]
            region = association_regions[legacy_id]
            clusters.append(
                {
                    "source_candidate_ref": {
                        "kind": "FROZEN_GOAL5_CONTAINER_CANDIDATE",
                        "legacy_evidence_id": legacy_id,
                        "fragment_ids": sorted(context.fragment_ids),
                        "candidate_mask_sha256": mask_digest(context.mask),
                    },
                    "segment_ids": sorted(cluster_segments),
                    "mask": context.mask,
                    "historical_evidence": {
                        "historical_risk": history["risk"],
                        "historical_decision": history["decision"],
                        "historical_application": semantic["application"],
                        "historical_statuses": sorted(
                            {ledger_blocks[item]["status"] for item in cluster_segments}
                        ),
                        "core_pixels": int(history["diagnostics"]["core_pixels"]),
                        "core_protected_overlap_pixels": int(semantic["core_protected_overlap_pixels"]),
                        "association_boundary_ratio": region["evidence"]["strong_boundary_ratio"],
                        "association_mean_boundary_gradient": region["evidence"]["mean_boundary_gradient"],
                        "evidence_sha256": digest_value(
                            {
                                "historical_result_sha256": evidence_hashes[f"goal6_result::{page_id}"],
                                "context_semantics_sha256": evidence_hashes[f"context_semantics::{page_id}"],
                                "legacy_evidence_id": legacy_id,
                            }
                        ),
                    },
                }
            )
        expected_segments = {item["segment_id"] for item in segments}
        if matched_segments != expected_segments:
            raise SpikeAStop(f"real input segment-to-cluster mapping is incomplete: {page_id}")
        cases.append(
            {
                "page_id": page_id,
                "source_sha256": observed_source_hash,
                "image": image,
                "segments": segments,
                "clusters": clusters,
            }
        )
    input_lock = {
        "schema_version": "mvp1-spike-a-input-lock-v1",
        "created_at": utc_now(),
        "branch": _git_value(repository_root, "branch", "--show-current"),
        "git_head": _git_value(repository_root, "rev-parse", "HEAD"),
        "visual_contract_sha256": sha256_file(
            repository_root / "docs/100-stages/150-cleaning/150-40-cleaning-check.md"
        ),
        "spike_a_module_sha256": sha256_file(Path(__file__).resolve()),
        "routed_association_module_sha256": sha256_file(Path(routed.__file__).resolve()),
        "source_hashes": source_hashes,
        "evidence_hashes": evidence_hashes,
        "candidate_generation_oracle_access": False,
    }
    return cases, input_lock


def _safe_artifact_name(identity: str) -> str:
    prefix = identity.split("::", 1)[0]
    return f"{prefix}-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]}.png"


def _save_mask(mask: np.ndarray, path: Path) -> dict[str, Any]:
    Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L").save(path, "PNG")
    return {
        "relative_path": None,
        "file_sha256": sha256_file(path),
        "content_sha256": mask_digest(mask),
        "pixel_count": int(mask.sum()),
        "shape": list(mask.shape),
        "encoding": "png-l8-binary-v1",
        "coordinate_space": "full-page-pixel-v1",
    }


def _materialize_masks(snapshot: dict[str, Any], internal_pages: list[dict[str, Any]], run_dir: Path) -> None:
    public_pages = {item["page_id"]: item for item in snapshot["pages"]}
    for internal in internal_pages:
        page_id = internal["page_id"]
        page_dir = run_dir / "masks" / page_id
        page_dir.mkdir(parents=True)
        public = public_pages[page_id]
        public_clusters = {item["cluster_id"]: item for item in public["contact_bubble_clusters"]}
        public_instances = {item["instance_id"]: item for item in public["bubble_instances"]}
        for cluster in internal["contact_bubble_clusters"]:
            path = page_dir / _safe_artifact_name(cluster["cluster_id"])
            artifact = _save_mask(cluster["_mask"], path)
            artifact["relative_path"] = str(path.relative_to(run_dir))
            public_clusters[cluster["cluster_id"]]["mask_artifact"] = artifact
        for instance in internal["bubble_instances"]:
            path = page_dir / _safe_artifact_name(instance["instance_id"])
            artifact = _save_mask(instance["_mask"], path)
            artifact["relative_path"] = str(path.relative_to(run_dir))
            public_instances[instance["instance_id"]]["mask_artifact"] = artifact


def _color(identity: str) -> tuple[int, int, int]:
    raw = hashlib.sha256(identity.encode("utf-8")).digest()
    return 60 + raw[0] % 160, 60 + raw[1] % 160, 60 + raw[2] % 160


def _outline(mask: np.ndarray) -> np.ndarray:
    return mask & ~cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1).astype(np.bool_)


def _render_overlay(page: dict[str, Any], run_dir: Path) -> str:
    image = page["_image"].astype(np.float32).copy()
    assessments = {item["instance_id"]: item for item in page["eligibility_assessments"]}
    for instance in page["bubble_instances"]:
        color = np.asarray(_color(instance["instance_id"]), dtype=np.float32)
        mask = instance["_mask"]
        image[mask] = image[mask] * 0.72 + color * 0.28
        image[_outline(mask)] = color
    canvas = Image.fromarray(np.clip(image, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    segment_by_id = {item["segment_id"]: item for item in page["text_segments"]}
    for instance in page["bubble_instances"]:
        risk = assessments[instance["instance_id"]]["candidate_risk"]
        for segment_id in instance["segment_ids"]:
            bbox = segment_by_id[segment_id]["bbox"]
            x0, y0 = int(bbox["x"]), int(bbox["y"])
            x1, y1 = x0 + int(bbox["width"]), y0 + int(bbox["height"])
            draw.rectangle((x0, y0, x1, y1), outline=(20, 110, 255), width=2)
            label = f"{segment_id} -> {instance['instance_id'][-8:]} {risk}"
            text_box = draw.textbbox((x0, max(0, y0 - 14)), label, font=font)
            draw.rectangle(text_box, fill=(255, 255, 255))
            draw.text((x0, max(0, y0 - 14)), label, fill=(10, 60, 160), font=font)
    overlay_dir = run_dir / "overlays"
    overlay_dir.mkdir(exist_ok=True)
    path = overlay_dir / f"{page['page_id']}-topology-eligibility.png"
    canvas.save(path, "PNG")
    return str(path.relative_to(run_dir))


def _artifact_validation(snapshot: dict[str, Any], run_dir: Path) -> list[str]:
    failures: list[str] = []
    for page in snapshot["pages"]:
        cluster_masks: dict[str, np.ndarray] = {}
        instance_masks: dict[str, np.ndarray] = {}
        for collection, target, identity_field in (
            (page["contact_bubble_clusters"], cluster_masks, "cluster_id"),
            (page["bubble_instances"], instance_masks, "instance_id"),
        ):
            for item in collection:
                artifact = item.get("mask_artifact", {})
                path = run_dir / str(artifact.get("relative_path", ""))
                if not path.is_file() or sha256_file(path) != artifact.get("file_sha256"):
                    failures.append("MASK_ARTIFACT_HASH_MISMATCH")
                    continue
                mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if mask is None:
                    failures.append("MASK_ARTIFACT_UNREADABLE")
                    continue
                boolean = mask > 0
                if mask_digest(boolean) != item.get("mask_sha256"):
                    failures.append("MASK_CONTENT_HASH_MISMATCH")
                target[item[identity_field]] = boolean
        for cluster in page["contact_bubble_clusters"]:
            cluster_mask = cluster_masks.get(cluster["cluster_id"])
            if cluster_mask is None:
                continue
            union = np.zeros_like(cluster_mask)
            overlap = 0
            for instance_id in cluster["instance_ids"]:
                instance_mask = instance_masks.get(instance_id)
                if instance_mask is None:
                    failures.append("INSTANCE_MASK_ARTIFACT_MISSING")
                    continue
                overlap += int(np.count_nonzero(union & instance_mask))
                union |= instance_mask
            if overlap or not np.array_equal(union, cluster_mask):
                failures.append("INSTANCE_MASK_PARTITION_INVALID")
    return sorted(set(failures))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_form(snapshot: dict[str, Any], validation: dict[str, Any], run_dir: Path) -> None:
    pages = {item["page_id"]: item for item in snapshot["pages"]}
    lines = [
        "# Spike A Human Review FORM",
        "",
        "说明：只审查真实 case-71/72。每题选择一个；不要修改 JSON 或 Mask。",
        "",
        f"自动合同：`{'PASS' if validation['passed'] else 'FAIL'}`",
        "",
        "## case-71 topology",
        "",
        "查看：`overlays/case-71-topology-eligibility.png`",
        "",
        "- [ ] PASS：旧接触区域正确拆为两个 BubbleInstance，每段唯一归属",
        "- [ ] FAIL_MERGE：仍错误合并",
        "- [ ] FAIL_SPLIT：存在错误拆分",
        "- [ ] UNCLEAR",
        "",
        "备注：",
        "",
        "## case-72 topology",
        "",
        "查看：`overlays/case-72-topology-eligibility.png`",
        "",
        "- [ ] PASS：7 BubbleInstance / 8 TextSegment，g007 两段仍属同一实例",
        "- [ ] FAIL",
        "- [ ] UNCLEAR",
        "",
        "备注：",
        "",
        "## case-72 eligibility",
        "",
        "| Segment(s) | Historical | Candidate | Changed | Reasons | 人工裁决 |",
        "|---|---|---|---|---|---|",
    ]
    page = pages["case-72"]
    instances = {item["instance_id"]: item for item in page["bubble_instances"]}
    for assessment in page["eligibility_assessments"]:
        instance = instances[assessment["instance_id"]]
        lines.append(
            "| "
            + ", ".join(instance["segment_ids"])
            + f" | {assessment['historical_parent_risk']} | {assessment['candidate_risk']} | "
            + ("YES" if assessment["changed_from_historical"] else "NO")
            + " | "
            + ", ".join(assessment["reason_codes"])
            + " | `ACCEPT` / `FALSE_NEGATIVE` / `TOO_AGGRESSIVE` / `UNCLEAR` |"
        )
    lines.extend(
        [
            "",
            "重点：普通白色气泡若仅因极少量 protected overlap 被整体 E3，是否应判为历史假阴性？",
            "",
            "备注：",
            "",
            "## Overall",
            "",
            "- [ ] PASS",
            "- [ ] PASS_WITH_CHANGES",
            "- [ ] NO_GO",
            "",
            "备注：",
            "",
        ]
    )
    (run_dir / "FORM.md").write_text("\n".join(lines), encoding="utf-8")


def _gate_matrix(
    snapshot: dict[str, Any],
    validation: dict[str, Any],
    negative_payload: dict[str, Any],
) -> dict[str, Any]:
    pages = {item["page_id"]: item for item in snapshot["pages"]}
    case71_partitions = _partition_sets(pages["case-71"])
    case72 = pages["case-72"]
    n3 = pages["synthetic-contact-n3"]
    columns = pages["synthetic-multi-column"]
    paragraphs = pages["synthetic-two-paragraphs"]
    mixed = pages["synthetic-mixed-risk"]
    e2_e3 = [
        item
        for page in snapshot["pages"]
        for item in page["eligibility_assessments"]
        if item["candidate_risk"] in {"E2", "E3"}
    ]
    forbidden_text = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    items = [
        {
            "gate": 1,
            "requirement": "every active TextSegment is assigned or explicitly excluded exactly once",
            "status": "PASS" if "SEGMENT_DISPOSITION_INVALID" not in validation["failure_codes"] else "FAIL",
            "evidence": "contract-validation.json",
        },
        {
            "gate": 2,
            "requirement": "case-71 contact region yields two independent BubbleInstance",
            "status": "PASS"
            if frozenset({"case-71__g002__s01"}) in case71_partitions
            and frozenset({"case-71__g002__s02"}) in case71_partitions
            else "FAIL",
            "evidence": "visual-contract-snapshot.json + overlays/case-71-topology-eligibility.png",
        },
        {
            "gate": 3,
            "requirement": "N>=3 is not constrained to binary split",
            "status": "PASS" if len(n3["bubble_instances"]) == 3 else "FAIL",
            "evidence": "synthetic-contact-n3",
        },
        {
            "gate": 4,
            "requirement": "single-bubble multi-column and multi-paragraph are not over-split",
            "status": "PASS"
            if len(columns["bubble_instances"]) == 1 and len(paragraphs["bubble_instances"]) == 1
            else "FAIL",
            "evidence": "synthetic-multi-column + synthetic-two-paragraphs",
        },
        {
            "gate": 5,
            "requirement": "merge/split/unassigned/wrong-instance negatives are rejected",
            "status": "PASS" if negative_payload["all_rejected"] else "FAIL",
            "evidence": "negative-validation.json",
        },
        {
            "gate": 6,
            "requirement": "eligibility is per-instance without cluster worst-risk broadcast",
            "status": "PASS"
            if len({item["candidate_risk"] for item in mixed["eligibility_assessments"]}) > 1
            else "FAIL",
            "evidence": "synthetic-mixed-risk eligibility assessments",
        },
        {
            "gate": 7,
            "requirement": "every E2/E3 has rules/features/threshold version/evidence",
            "status": "PASS"
            if all(all(item.get(field) for field in ("reason_codes", "rules", "features", "threshold_version", "evidence")) for item in e2_e3)
            else "FAIL",
            "evidence": "visual-contract-snapshot.json eligibility_assessments",
        },
        {
            "gate": 8,
            "requirement": "case-72 ordinary-bubble exclusions are human-reviewable",
            "status": "PENDING_HUMAN_REVIEW",
            "evidence": {
                "historical_segments": len(case72["text_segments"]),
                "assessment_count": len(case72["eligibility_assessments"]),
                "form": "FORM.md",
                "overlay": "overlays/case-72-topology-eligibility.png",
            },
        },
        {
            "gate": 9,
            "requirement": "snapshot is the run's exclusive relationship source",
            "status": "PASS"
            if snapshot["relationship_source"]["exclusive_for_run"] is True
            and snapshot["status"] == "CANDIDATE_FROZEN_BEFORE_ORACLE"
            else "FAIL",
            "evidence": "visual-contract-snapshot.json + evaluation-lock.json",
        },
        {
            "gate": 10,
            "requirement": "no parent bbox, directory order, or hidden mapping is required",
            "status": "PASS"
            if not any(item in forbidden_text for item in ("parent_bbox_mapping", "directory_order_mapping", "cluster_risk"))
            else "FAIL",
            "evidence": "contract-validation.json + stable-order unit test",
        },
    ]
    return {
        "schema_version": "mvp1-spike-a-gate-matrix-v1",
        "items": items,
        "automatic_pass_count": sum(item["status"] == "PASS" for item in items),
        "pending_human_count": sum(item["status"] == "PENDING_HUMAN_REVIEW" for item in items),
        "fail_count": sum(item["status"] == "FAIL" for item in items),
        "overall": "PENDING_HUMAN_REVIEW"
        if not any(item["status"] == "FAIL" for item in items)
        else "NO_GO",
    }


def run(args: argparse.Namespace) -> Path:
    repository_root = args.repository_root.resolve()
    run_dir = args.output_dir.resolve()
    if run_dir.exists():
        raise SpikeAStop(f"refusing to overwrite run: {run_dir}")
    run_dir.mkdir(parents=True)
    timings: dict[str, int] = {}
    total_start = time.perf_counter()

    stage_start = time.perf_counter()
    real_cases, input_lock = _real_cases(
        repository_root,
        args.source_root.resolve(),
        args.s1.resolve(),
        args.goal5_lock.resolve(),
        args.provenance.resolve(),
        args.ocr.resolve(),
        args.goal6_results_dir.resolve(),
        args.context_semantics_dir.resolve(),
    )
    timings["frozen_input_and_association_ms"] = round((time.perf_counter() - stage_start) * 1000)
    _write_json(run_dir / "input-lock.json", input_lock)

    stage_start = time.perf_counter()
    policy = SpikeAPolicy()
    candidate_cases = real_cases + [
        synthetic_case(case_id)
        for case_id in (
            "synthetic-contact-n3",
            "synthetic-multi-column",
            "synthetic-two-paragraphs",
            "synthetic-mixed-risk",
        )
    ]
    internal_pages = [analyze_page(item, policy) for item in candidate_cases]
    snapshot = build_snapshot(internal_pages, policy, input_lock)
    _materialize_masks(snapshot, internal_pages, run_dir)
    for internal in internal_pages:
        overlay = _render_overlay(internal, run_dir)
        next(item for item in snapshot["pages"] if item["page_id"] == internal["page_id"])[
            "overlay_relative_path"
        ] = overlay
    snapshot = _rehash_snapshot(snapshot)
    snapshot_path = run_dir / "visual-contract-snapshot.json"
    _write_json(snapshot_path, snapshot)
    timings["candidate_snapshot_ms"] = round((time.perf_counter() - stage_start) * 1000)

    # Evaluation starts only after the immutable candidate snapshot exists.
    stage_start = time.perf_counter()
    oracle_path = args.oracle.resolve()
    oracle = _load_json(oracle_path)
    evaluation_lock = {
        "schema_version": "mvp1-spike-a-evaluation-lock-v1",
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "snapshot_file_sha256": sha256_file(snapshot_path),
        "oracle_sha256": sha256_file(oracle_path),
        "oracle_content_sha256": digest_value(oracle),
        "oracle_loaded_after_snapshot_freeze": True,
    }
    _write_json(run_dir / "evaluation-lock.json", evaluation_lock)
    validation = validate_snapshot(snapshot, oracle)
    artifact_failures = _artifact_validation(snapshot, run_dir)
    if artifact_failures:
        validation["failure_codes"] = sorted(set(validation["failure_codes"] + artifact_failures))
        validation["passed"] = False
    _write_json(run_dir / "contract-validation.json", validation)
    negative_results = []
    expected_by_mutation = {
        "deliberate_merge": "EXPECTED_DIFFERENT_SEGMENTS_MERGED",
        "deliberate_split": "EXPECTED_SAME_SEGMENTS_SPLIT",
        "deliberate_unassigned": "SEGMENT_DISPOSITION_INVALID",
        "deliberate_wrong_instance": "EXPECTED_ASSIGNMENT_MISMATCH",
    }
    for mutation, expected_code in expected_by_mutation.items():
        result = validate_snapshot(apply_deliberate_mutation(snapshot, mutation), oracle)
        negative_results.append(
            {
                "mutation": mutation,
                "expected_failure_code": expected_code,
                "accepted": result["passed"],
                "failure_codes": result["failure_codes"],
                "correctly_rejected": not result["passed"] and expected_code in result["failure_codes"],
            }
        )
    negative_payload = {
        "schema_version": "mvp1-spike-a-negative-validation-v1",
        "all_rejected": all(item["correctly_rejected"] for item in negative_results),
        "results": negative_results,
    }
    _write_json(run_dir / "negative-validation.json", negative_payload)
    gate_matrix = _gate_matrix(snapshot, validation, negative_payload)
    _write_json(run_dir / "gate-matrix.json", gate_matrix)
    timings["automatic_validation_ms"] = round((time.perf_counter() - stage_start) * 1000)
    timings["total_ms"] = round((time.perf_counter() - total_start) * 1000)

    auto_pass = validation["passed"] and negative_payload["all_rejected"]
    real_pages = {item["page_id"]: item for item in snapshot["pages"] if item["page_id"] in {"case-71", "case-72"}}
    summary = {
        "schema_version": "mvp1-spike-a-summary-v1",
        "status": "PENDING_HUMAN_REVIEW" if auto_pass else "NO_GO_AUTOMATIC_CONTRACT",
        "candidate_generation_oracle_access": False,
        "automatic_contract_passed": validation["passed"],
        "all_deliberate_negatives_rejected": negative_payload["all_rejected"],
        "real_case_counts": {
            page_id: {
                "segment_count": len(page["text_segments"]),
                "instance_count": len(page["bubble_instances"]),
                "historical_eligible_count": sum(
                    item.get("historical_status") == "eligible" for item in page["text_segments"]
                ),
                "historical_excluded_count": sum(
                    item.get("historical_status") == "excluded" for item in page["text_segments"]
                ),
                "candidate_e1_segment_count": sum(
                    len(next(instance["segment_ids"] for instance in page["bubble_instances"] if instance["instance_id"] == assessment["instance_id"]))
                    for assessment in page["eligibility_assessments"]
                    if assessment["candidate_risk"] == "E1"
                ),
            }
            for page_id, page in real_pages.items()
        },
        "timings_ms": timings,
        "gate": "PENDING_HUMAN_REVIEW" if auto_pass else "NO_GO",
    }
    _write_json(run_dir / "summary.json", summary)
    _write_json(run_dir / "timings.json", {"schema_version": "mvp1-spike-a-timings-v1", **timings})
    _write_form(snapshot, validation, run_dir)
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--s1", type=Path, required=True)
    parser.add_argument("--goal5-lock", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--ocr", type=Path, required=True)
    parser.add_argument("--goal6-results-dir", type=Path, required=True)
    parser.add_argument("--context-semantics-dir", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = run(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, SpikeAStop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": "READY_FOR_HUMAN_REVIEW", "output_dir": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
