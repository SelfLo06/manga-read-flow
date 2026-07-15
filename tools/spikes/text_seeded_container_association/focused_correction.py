#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import heapq
import importlib.util
import itertools
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


BASE_MODULE_NAME = "text_seeded_container_association_goal2_harness"
BASE_PATH = Path(__file__).with_name("harness.py")
if BASE_MODULE_NAME in sys.modules:
    BASE = sys.modules[BASE_MODULE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(BASE_MODULE_NAME, BASE_PATH)
    if _spec is None or _spec.loader is None:
        raise RuntimeError(f"cannot load frozen base harness: {BASE_PATH}")
    BASE = importlib.util.module_from_spec(_spec)
    sys.modules[BASE_MODULE_NAME] = BASE
    _spec.loader.exec_module(BASE)


SCHEMA_VERSION = "text-seeded-container-association-focused-correction-v1"
SAME_CONTAINER_V2_WEIGHTS = {
    "same_upstream_group": 0.10,
    "orientation_compatibility": 0.05,
    "scale_similarity": 0.05,
    "proximity": 0.05,
    "local_background_similarity": 0.05,
    "group_or_clear_corridor": 0.70,
}

HarnessStop = BASE.HarnessStop
Fragment = BASE.Fragment
PageInput = BASE.PageInput
PairEvidence = BASE.PairEvidence
SameContainerThresholds = BASE.SameContainerThresholds
SameContainerDecision = BASE.SameContainerDecision


@dataclass(frozen=True)
class CorrectedP1Policy:
    thresholds: SameContainerThresholds
    max_geodesic_cost: float
    support_padding_scale: float
    max_support_area_ratio: float
    max_merged_support_area_ratio: float
    regionless_uncertain_orientation: bool
    regionless_extreme_span_ratio: float
    regionless_seed_bbox_area_ratio: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_geodesic_cost) or self.max_geodesic_cost <= 0:
            raise HarnessStop("max_geodesic_cost must be positive and finite")
        if not math.isfinite(self.support_padding_scale) or self.support_padding_scale <= 0:
            raise HarnessStop("support_padding_scale must be positive and finite")
        if not 0.0 < self.max_support_area_ratio <= 1.0:
            raise HarnessStop("max_support_area_ratio must be in (0, 1]")
        if not 0.0 < self.max_merged_support_area_ratio <= 1.0:
            raise HarnessStop("max_merged_support_area_ratio must be in (0, 1]")
        if not 0.0 < self.regionless_extreme_span_ratio <= 1.0:
            raise HarnessStop("regionless_extreme_span_ratio must be in (0, 1]")
        if not 0.0 < self.regionless_seed_bbox_area_ratio <= 1.0:
            raise HarnessStop("regionless_seed_bbox_area_ratio must be in (0, 1]")


@dataclass(frozen=True)
class RegionResult:
    region_id: str
    fragment_ids: tuple[str, ...]
    mask: np.ndarray | None
    container_type: str
    confidence: float

    def __post_init__(self) -> None:
        if self.mask is not None and (self.mask.dtype != np.bool_ or self.mask.ndim != 2):
            raise HarnessStop("region mask must be a two-dimensional bool array or null")


@dataclass(frozen=True)
class AssociationResult:
    asset_id: str
    method_id: str
    regions: tuple[RegionResult, ...]
    same_container_decisions: tuple[SameContainerDecision, ...]
    virtual_boundary: np.ndarray
    recommended_decision: str
    abstention_reasons: tuple[str, ...]
    diagnostics: dict[str, Any]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "asset_id": self.asset_id,
            "method_id": self.method_id,
            "regions": [
                {
                    "region_id": item.region_id,
                    "fragment_ids": list(item.fragment_ids),
                    "container_type": item.container_type,
                    "confidence": item.confidence,
                    "mask_rle": BASE.encode_bool_rle(item.mask) if item.mask is not None else None,
                }
                for item in self.regions
            ],
            "same_container_decisions": [dataclasses.asdict(item) for item in self.same_container_decisions],
            "virtual_boundary_rle": BASE.encode_bool_rle(self.virtual_boundary),
            "recommended_decision": self.recommended_decision,
            "abstention_reasons": list(self.abstention_reasons),
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class PreparedAssociation:
    page: PageInput
    thresholds: SameContainerThresholds
    decisions: tuple[SameContainerDecision, ...]
    components: tuple[tuple[Fragment, ...], ...]
    labels: np.ndarray
    superpixel_count: int
    region_size: int
    graph: list[list[tuple[int, float]]]
    seed_nodes: tuple[set[int], ...]
    centers: np.ndarray
    gradient: np.ndarray


def _fragment_context_tone(image: np.ndarray, fragment: Fragment) -> float:
    height, width = image.shape[:2]
    x, y, box_width, box_height = fragment.bbox
    padding = max(2, int(round(0.35 * fragment.scale)))
    x1, y1 = max(0, x - padding), max(0, y - padding)
    x2, y2 = min(width, x + box_width + padding), min(height, y + box_height + padding)
    patch = image[y1:y2, x1:x2].astype(np.float32) / 255.0
    if patch.size == 0:
        return 0.5
    gray = 0.299 * patch[:, :, 0] + 0.587 * patch[:, :, 1] + 0.114 * patch[:, :, 2]
    ring = np.ones(gray.shape, dtype=np.bool_)
    inner_x1, inner_y1 = x - x1, y - y1
    inner_x2, inner_y2 = inner_x1 + box_width, inner_y1 + box_height
    ring[inner_y1:inner_y2, inner_x1:inner_x2] = False
    values = gray[ring]
    if not values.size:
        values = gray.ravel()
    return float(np.median(values))


def _clear_interbox_corridor(
    image: np.ndarray,
    left: Fragment,
    right: Fragment,
) -> float:
    """Return zero when a continuous dark separator crosses the inter-box corridor."""
    rgb = image.astype(np.float32) / 255.0
    gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    height, width = gray.shape
    left_x, left_y = left.center
    right_x, right_y = right.center
    length = max(16, int(round(math.hypot(right_x - left_x, right_y - left_y))) * 2)
    xs = np.clip(np.rint(np.linspace(left_x, right_x, length)).astype(int), 0, width - 1)
    ys = np.clip(np.rint(np.linspace(left_y, right_y, length)).astype(int), 0, height - 1)

    def inside_expanded_box(fragment: Fragment) -> np.ndarray:
        x, y, box_width, box_height = fragment.bbox
        return (
            (xs >= x)
            & (xs < x + box_width)
            & (ys >= y)
            & (ys < y + box_height)
        )

    valid = ~(inside_expanded_box(left) | inside_expanded_box(right))
    dark = (gray[ys, xs] < 0.55) & valid
    if not dark.any():
        return 1.0
    run = 0
    for is_dark in dark:
        run = run + 1 if is_dark else 0
        if run >= 3:
            return 0.0
    return 0.5


def score_same_container_v2(page: PageInput, left: Fragment, right: Fragment) -> PairEvidence:
    """Upstream grouping is weak evidence and never a cross-group merge prerequisite."""
    if left.fragment_id == right.fragment_id:
        raise HarnessStop("cannot score a fragment against itself")
    if left.orientation == right.orientation:
        orientation = 1.0
    elif "uncertain" in {left.orientation, right.orientation}:
        orientation = 0.5
    else:
        orientation = 0.0
    scale_similarity = min(left.scale, right.scale) / max(left.scale, right.scale)
    normalized_gap = BASE._bbox_gap(left, right) / max(1.0, (left.scale + right.scale) / 2.0)
    proximity = math.exp(-normalized_gap)
    left_tone = _fragment_context_tone(page.image, left)
    right_tone = _fragment_context_tone(page.image, right)
    same_upstream_group = 1.0 if left.upstream_group_id == right.upstream_group_id else 0.0
    features = {
        "same_upstream_group": same_upstream_group,
        "orientation_compatibility": float(orientation),
        "scale_similarity": float(scale_similarity),
        "proximity": float(proximity),
        "local_background_similarity": float(math.exp(-4.0 * abs(left_tone - right_tone))),
        "group_or_clear_corridor": max(
            same_upstream_group,
            _clear_interbox_corridor(page.image, left, right),
        ),
    }
    score = sum(SAME_CONTAINER_V2_WEIGHTS[name] * value for name, value in features.items())
    return PairEvidence(
        left_fragment_id=left.fragment_id,
        right_fragment_id=right.fragment_id,
        score=float(np.clip(score, 0.0, 1.0)),
        features=features,
    )


def score_group_same_container_v2(
    page: PageInput,
    left_items: tuple[Fragment, ...],
    right_items: tuple[Fragment, ...],
) -> PairEvidence:
    if not left_items or not right_items:
        raise HarnessStop("cannot score an empty upstream group")
    member_evidence = [
        score_same_container_v2(page, left, right)
        for left, right in itertools.product(left_items, right_items)
        if BASE._candidate_pair(left, right)
    ]
    if not member_evidence:
        raise HarnessStop("upstream groups have no candidate member pair")
    scores = [item.score for item in member_evidence]
    left_group = left_items[0].upstream_group_id
    right_group = right_items[0].upstream_group_id
    return PairEvidence(
        left_fragment_id=f"group:{left_group}",
        right_fragment_id=f"group:{right_group}",
        score=float(min(scores)),
        features={
            "minimum_member_pair_score": float(min(scores)),
            "mean_member_pair_score": float(np.mean(scores)),
            "maximum_member_pair_score": float(max(scores)),
            "member_pair_count": float(len(scores)),
        },
    )


def _superpixel_centroids(labels: np.ndarray, count: int) -> np.ndarray:
    yy, xx = np.indices(labels.shape)
    sizes = np.bincount(labels.ravel(), minlength=count).astype(np.float64)
    centers = np.zeros((count, 2), dtype=np.float64)
    centers[:, 0] = np.bincount(labels.ravel(), weights=xx.ravel(), minlength=count)
    centers[:, 1] = np.bincount(labels.ravel(), weights=yy.ravel(), minlength=count)
    centers /= np.maximum(sizes[:, None], 1.0)
    return centers


def _support_envelope(
    shape: tuple[int, int],
    items: tuple[Fragment, ...],
    padding_scale: float,
) -> np.ndarray:
    height, width = shape
    median_scale = float(np.median([item.scale for item in items]))
    padding = max(2, int(round(padding_scale * median_scale)))
    x1 = max(0, min(item.bbox[0] for item in items) - padding)
    y1 = max(0, min(item.bbox[1] for item in items) - padding)
    x2 = min(width, max(item.bbox[0] + item.bbox[2] for item in items) + padding)
    y2 = min(height, max(item.bbox[1] + item.bbox[3] for item in items) + padding)
    mask = np.zeros(shape, dtype=np.bool_)
    mask[y1:y2, x1:x2] = True
    return mask


def _bounded_propagate(
    graph: list[list[tuple[int, float]]],
    seeds: list[set[int]],
    allowed_nodes: list[np.ndarray],
    max_cost: float,
):
    count = len(graph)
    distances = np.full(count, np.inf, dtype=np.float64)
    owners = np.full(count, -1, dtype=np.int32)
    queue: list[tuple[float, int, int]] = []
    contested: set[int] = set()
    for owner, node_ids in enumerate(seeds):
        for node in node_ids:
            if owners[node] not in {-1, owner}:
                contested.add(node)
                continue
            distances[node] = 0.0
            owners[node] = owner
            heapq.heappush(queue, (0.0, owner, node))
    while queue:
        distance, owner, node = heapq.heappop(queue)
        if distance != distances[node] or owner != owners[node]:
            continue
        for neighbor, cost in graph[node]:
            if not allowed_nodes[owner][neighbor]:
                continue
            candidate = distance + cost
            if candidate > max_cost:
                continue
            if candidate + 1e-9 < distances[neighbor]:
                distances[neighbor] = candidate
                owners[neighbor] = owner
                heapq.heappush(queue, (candidate, owner, neighbor))
            elif owners[neighbor] != owner and abs(candidate - distances[neighbor]) <= 0.5:
                contested.add(neighbor)
    return owners, distances, contested


def _virtual_boundary_from_masks(shape: tuple[int, int], masks: list[np.ndarray | None]) -> np.ndarray:
    owner_image = np.full(shape, -1, dtype=np.int32)
    for owner, mask in enumerate(masks):
        if mask is not None:
            owner_image[mask] = owner
    boundary = np.zeros(shape, dtype=np.bool_)
    horizontal = (owner_image[:, :-1] >= 0) & (owner_image[:, 1:] >= 0) & (
        owner_image[:, :-1] != owner_image[:, 1:]
    )
    vertical = (owner_image[:-1, :] >= 0) & (owner_image[1:, :] >= 0) & (
        owner_image[:-1, :] != owner_image[1:, :]
    )
    boundary[:, :-1] |= horizontal
    boundary[:, 1:] |= horizontal
    boundary[:-1, :] |= vertical
    boundary[1:, :] |= vertical
    return boundary


def prepare_corrected_p1(
    page: PageInput,
    thresholds: SameContainerThresholds,
) -> PreparedAssociation:
    if not page.fragments:
        raise HarnessStop("cannot prepare a page without seeds")
    decisions: list[SameContainerDecision] = []
    disjoint = BASE._DisjointSet(item.fragment_id for item in page.fragments)
    groups = {
        group_id: tuple(sorted(items, key=lambda item: item.fragment_id))
        for group_id, items in BASE._group_fragments(page).items()
    }
    for items in groups.values():
        for left, right in itertools.combinations(items, 2):
            disjoint.union(left.fragment_id, right.fragment_id)
    for (left_group, left_items), (right_group, right_items) in itertools.combinations(
        sorted(groups.items()), 2
    ):
        if not any(
            BASE._candidate_pair(left, right)
            for left, right in itertools.product(left_items, right_items)
        ):
            continue
        evidence = score_group_same_container_v2(page, left_items, right_items)
        decision = thresholds.classify(evidence.score)
        decisions.append(
            SameContainerDecision(
                f"group:{left_group}",
                f"group:{right_group}",
                evidence.score,
                decision,
                evidence.features,
            )
        )
        if decision == "same":
            disjoint.union(left_items[0].fragment_id, right_items[0].fragment_id)

    components_by_root: dict[str, list[Fragment]] = {}
    for item in page.fragments:
        components_by_root.setdefault(disjoint.find(item.fragment_id), []).append(item)
    components = tuple(
        tuple(sorted(items, key=lambda item: item.fragment_id))
        for _root, items in sorted(components_by_root.items())
    )

    labels, superpixel_count, region_size = BASE._slic_labels(page)
    graph, _boundaries = BASE._superpixel_graph(page, labels, superpixel_count)
    seed_nodes = BASE._seed_superpixels(labels, components)
    centers = _superpixel_centroids(labels, superpixel_count)
    return PreparedAssociation(
        page=page,
        thresholds=thresholds,
        decisions=tuple(decisions),
        components=components,
        labels=labels,
        superpixel_count=superpixel_count,
        region_size=region_size,
        graph=graph,
        seed_nodes=tuple(seed_nodes),
        centers=centers,
        gradient=BASE._gradient_magnitude(page.image),
    )


def run_prepared_corrected_p1(
    prepared: PreparedAssociation,
    policy: CorrectedP1Policy,
) -> AssociationResult:
    if prepared.thresholds != policy.thresholds:
        raise HarnessStop("prepared thresholds do not match policy thresholds")
    page = prepared.page
    decisions = prepared.decisions
    components = prepared.components
    labels = prepared.labels
    graph = prepared.graph
    seed_nodes = prepared.seed_nodes
    centers = prepared.centers
    envelopes = [
        _support_envelope(page.image.shape[:2], items, policy.support_padding_scale)
        for items in components
    ]
    center_x = np.clip(np.rint(centers[:, 0]).astype(int), 0, page.image.shape[1] - 1)
    center_y = np.clip(np.rint(centers[:, 1]).astype(int), 0, page.image.shape[0] - 1)
    allowed_nodes: list[np.ndarray] = []
    for owner, envelope in enumerate(envelopes):
        allowed = envelope[center_y, center_x]
        if seed_nodes[owner]:
            allowed[np.fromiter(seed_nodes[owner], dtype=np.int32)] = True
        allowed_nodes.append(allowed)

    owners, distances, contested = _bounded_propagate(
        graph,
        seed_nodes,
        allowed_nodes,
        policy.max_geodesic_cost,
    )
    gradient = prepared.gradient
    regions: list[RegionResult] = []
    masks: list[np.ndarray | None] = []
    reasons: set[str] = set()
    if any(item.decision == "uncertain" for item in decisions):
        reasons.add("uncertain_same_container_pair")

    for owner, items in enumerate(components):
        candidate_mask = ((owners[labels] == owner) & envelopes[owner]).astype(np.bool_)
        regionless_reason: str | None = None
        x1 = min(item.bbox[0] for item in items)
        y1 = min(item.bbox[1] for item in items)
        x2 = max(item.bbox[0] + item.bbox[2] for item in items)
        y2 = max(item.bbox[1] + item.bbox[3] for item in items)
        seed_bbox_area_ratio = ((x2 - x1) * (y2 - y1)) / float(page.image.shape[0] * page.image.shape[1])
        seed_span_ratio = max(
            (x2 - x1) / float(page.image.shape[1]),
            (y2 - y1) / float(page.image.shape[0]),
        )
        if not candidate_mask.any():
            regionless_reason = "regionless_unassigned_seed_component"
        elif (
            len(items) == 1
            and seed_span_ratio >= policy.regionless_extreme_span_ratio
            and seed_bbox_area_ratio >= policy.regionless_seed_bbox_area_ratio
        ):
            regionless_reason = "regionless_extreme_span_seed"
        elif (
            policy.regionless_uncertain_orientation
            and len(items) == 1
            and items[0].orientation == "uncertain"
        ):
            regionless_reason = "regionless_uncertain_isolated_seed"
        elif float(np.mean(candidate_mask)) > (
            policy.max_merged_support_area_ratio if len(items) > 1 else policy.max_support_area_ratio
        ):
            regionless_reason = "regionless_support_area_limit"

        if regionless_reason is not None:
            mask = None
            container_type, confidence = "uncertain", 0.0
            reasons.add(regionless_reason)
        else:
            mask = candidate_mask
            container_type, confidence = BASE._classify_region(mask, gradient)
            if container_type == "free_text":
                reasons.add("free_text_requires_review")
            elif container_type == "implicit_container":
                reasons.add("implicit_boundary_requires_review")
        masks.append(mask)
        regions.append(
            RegionResult(
                region_id=f"P1C-r{owner + 1:03d}",
                fragment_ids=tuple(item.fragment_id for item in items),
                mask=mask,
                container_type=container_type,
                confidence=confidence,
            )
        )

    if all(mask is None for mask in masks):
        recommendation = "SKIP"
    elif reasons:
        recommendation = "REVIEW_REQUIRED"
    elif all(item.container_type == "explicit_container" for item in regions):
        recommendation = "LOW_RISK_ASSOCIATION_CANDIDATE"
    else:
        recommendation = "REVIEW_REQUIRED"

    finite_distances = distances[np.isfinite(distances)]
    return AssociationResult(
        asset_id=page.asset_id,
        method_id="P1-corrected-v1",
        regions=tuple(regions),
        same_container_decisions=tuple(decisions),
        virtual_boundary=_virtual_boundary_from_masks(page.image.shape[:2], masks),
        recommended_decision=recommendation,
        abstention_reasons=tuple(sorted(reasons)),
        diagnostics={
            "policy": dataclasses.asdict(policy),
            "superpixel_count": prepared.superpixel_count,
            "slic_region_size": prepared.region_size,
            "source_component_count": len(components),
            "regionless_component_count": sum(mask is None for mask in masks),
            "unassigned_superpixel_count": int(np.count_nonzero(owners < 0)),
            "contested_superpixel_count": len(contested),
                "max_finite_geodesic_cost": float(np.max(finite_distances)) if finite_distances.size else None,
        },
    )


def run_corrected_p1(page: PageInput, policy: CorrectedP1Policy) -> AssociationResult:
    method_id = "P1-corrected-v1"
    if not page.fragments:
        return AssociationResult(
            page.asset_id,
            method_id,
            (),
            (),
            np.zeros(page.image.shape[:2], dtype=np.bool_),
            "SKIP",
            ("no_seed",),
            {"policy": dataclasses.asdict(policy)},
        )
    return run_prepared_corrected_p1(
        prepare_corrected_p1(page, policy.thresholds),
        policy,
    )
