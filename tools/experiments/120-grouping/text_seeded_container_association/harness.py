#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import heapq
import itertools
import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np


SCHEMA_VERSION = "text-seeded-container-association-harness-v1"

SAME_CONTAINER_WEIGHTS = {
    "same_upstream_group": 0.40,
    "orientation_compatibility": 0.15,
    "scale_similarity": 0.15,
    "proximity": 0.15,
    "edge_corridor": 0.15,
}
DIFFERENT_THRESHOLD_GRID = (0.40, 0.45, 0.50, 0.55, 0.60)
SAME_THRESHOLD_GRID = (0.70, 0.75, 0.80, 0.85, 0.90)
MIN_CALIBRATION_SCORE_MARGIN = 0.20

SLIC_ITERATIONS = 5
SLIC_MIN_ELEMENT_RATIO = 25
P1_MAX_GEODESIC_COST = 24.0
P1_HARD_BARRIER = 0.85


class HarnessStop(RuntimeError):
    pass


@dataclass(frozen=True)
class Fragment:
    fragment_id: str
    bbox: tuple[int, int, int, int]
    polygon: tuple[tuple[float, float], ...]
    upstream_group_id: str
    score: float | None = None

    @property
    def center(self) -> tuple[float, float]:
        x, y, width, height = self.bbox
        return x + width / 2.0, y + height / 2.0

    @property
    def scale(self) -> float:
        return float(max(1, min(self.bbox[2], self.bbox[3])))

    @property
    def orientation(self) -> str:
        width, height = self.bbox[2], self.bbox[3]
        if height >= 1.25 * width:
            return "vertical"
        if width >= 1.25 * height:
            return "horizontal"
        return "uncertain"


@dataclass(frozen=True)
class PageInput:
    asset_id: str
    image: np.ndarray
    fragments: tuple[Fragment, ...]

    def __post_init__(self) -> None:
        if self.image.ndim != 3 or self.image.shape[2] != 3 or self.image.dtype != np.uint8:
            raise HarnessStop("image must be uint8 RGB with shape HxWx3")
        seen: set[str] = set()
        height, width = self.image.shape[:2]
        for item in self.fragments:
            if item.fragment_id in seen:
                raise HarnessStop(f"duplicate fragment_id: {item.fragment_id}")
            seen.add(item.fragment_id)
            x, y, box_width, box_height = item.bbox
            if box_width <= 0 or box_height <= 0:
                raise HarnessStop(f"invalid bbox for {item.fragment_id}")
            if x < 0 or y < 0 or x + box_width > width or y + box_height > height:
                raise HarnessStop(f"bbox outside image for {item.fragment_id}")


@dataclass(frozen=True)
class PairEvidence:
    left_fragment_id: str
    right_fragment_id: str
    score: float
    features: dict[str, float]


@dataclass(frozen=True)
class SameContainerThresholds:
    different: float
    same: float
    force_all_uncertain: bool = False

    def __post_init__(self) -> None:
        if not self.force_all_uncertain and self.different >= self.same:
            raise HarnessStop("different threshold must be lower than same threshold")

    def classify(self, score: float) -> str:
        if self.force_all_uncertain:
            return "uncertain"
        if score <= self.different:
            return "different"
        if score >= self.same:
            return "same"
        return "uncertain"


@dataclass(frozen=True)
class CalibrationExample:
    asset_id: str
    pair_id: str
    label: str
    score: float


@dataclass(frozen=True)
class CalibrationResult:
    status: str
    thresholds: SameContainerThresholds
    margin: float
    examples: tuple[CalibrationExample, ...]


@dataclass(frozen=True)
class SameContainerDecision:
    left_fragment_id: str
    right_fragment_id: str
    probability: float
    decision: str
    features: dict[str, float]


@dataclass(frozen=True)
class RegionResult:
    region_id: str
    fragment_ids: tuple[str, ...]
    mask: np.ndarray
    container_type: str
    confidence: float

    def __post_init__(self) -> None:
        if self.mask.dtype != np.bool_ or self.mask.ndim != 2:
            raise HarnessStop("region mask must be a two-dimensional bool array")


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
                    "mask_rle": encode_bool_rle(item.mask),
                }
                for item in self.regions
            ],
            "same_container_decisions": [dataclasses.asdict(item) for item in self.same_container_decisions],
            "virtual_boundary_rle": encode_bool_rle(self.virtual_boundary),
            "recommended_decision": self.recommended_decision,
            "abstention_reasons": list(self.abstention_reasons),
            "diagnostics": self.diagnostics,
        }


def encode_bool_rle(mask: np.ndarray) -> dict[str, Any]:
    flat = mask.astype(np.uint8, copy=False).ravel(order="C")
    if flat.size == 0:
        return {"shape": list(mask.shape), "starts_with": 0, "counts": []}
    counts: list[int] = []
    current = int(flat[0])
    run_length = 1
    for value in flat[1:]:
        actual = int(value)
        if actual == current:
            run_length += 1
        else:
            counts.append(run_length)
            current = actual
            run_length = 1
    counts.append(run_length)
    return {"shape": list(mask.shape), "starts_with": int(flat[0]), "counts": counts}


def _bbox_gap(left: Fragment, right: Fragment) -> float:
    lx, ly, lw, lh = left.bbox
    rx, ry, rw, rh = right.bbox
    dx = max(lx - (rx + rw), rx - (lx + lw), 0)
    dy = max(ly - (ry + rh), ry - (ly + lh), 0)
    return math.hypot(dx, dy)


def _gradient_magnitude(image: np.ndarray) -> np.ndarray:
    rgb = image.astype(np.float32) / 255.0
    gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    grad_x = np.zeros_like(gray)
    grad_y = np.zeros_like(gray)
    grad_x[:, 1:-1] = (gray[:, 2:] - gray[:, :-2]) / 2.0
    grad_y[1:-1, :] = (gray[2:, :] - gray[:-2, :]) / 2.0
    magnitude = np.hypot(grad_x, grad_y)
    scale = float(np.percentile(magnitude, 99.0))
    if scale <= 1e-8:
        return np.zeros_like(magnitude)
    return np.clip(magnitude / scale, 0.0, 1.0)


def _edge_corridor(image: np.ndarray, left: Fragment, right: Fragment) -> float:
    gradient = _gradient_magnitude(image)
    height, width = gradient.shape
    left_x, left_y = left.center
    right_x, right_y = right.center
    length = max(16, int(round(math.hypot(right_x - left_x, right_y - left_y))))
    xs = np.clip(np.rint(np.linspace(left_x, right_x, length)).astype(int), 0, width - 1)
    ys = np.clip(np.rint(np.linspace(left_y, right_y, length)).astype(int), 0, height - 1)
    return float(np.clip(1.0 - float(np.max(gradient[ys, xs], initial=0.0)), 0.0, 1.0))


def score_same_container(page: PageInput, left: Fragment, right: Fragment) -> PairEvidence:
    if left.fragment_id == right.fragment_id:
        raise HarnessStop("cannot score a fragment against itself")
    if left.orientation == right.orientation:
        orientation = 1.0
    elif "uncertain" in {left.orientation, right.orientation}:
        orientation = 0.5
    else:
        orientation = 0.0
    scale_similarity = min(left.scale, right.scale) / max(left.scale, right.scale)
    normalized_gap = _bbox_gap(left, right) / max(1.0, (left.scale + right.scale) / 2.0)
    proximity = math.exp(-normalized_gap)
    features = {
        "same_upstream_group": 1.0 if left.upstream_group_id == right.upstream_group_id else 0.0,
        "orientation_compatibility": float(orientation),
        "scale_similarity": float(scale_similarity),
        "proximity": float(proximity),
        "edge_corridor": _edge_corridor(page.image, left, right),
    }
    score = sum(SAME_CONTAINER_WEIGHTS[name] * value for name, value in features.items())
    return PairEvidence(
        left_fragment_id=left.fragment_id,
        right_fragment_id=right.fragment_id,
        score=float(np.clip(score, 0.0, 1.0)),
        features=features,
    )


def calibrate_thresholds(examples: Iterable[CalibrationExample]) -> CalibrationResult:
    items = tuple(examples)
    if not items:
        raise HarnessStop("calibration examples are required")
    for item in items:
        if not item.asset_id.startswith("cal-"):
            raise HarnessStop(f"non-calibration asset in calibration set: {item.asset_id}")
        if item.label not in {"same", "different"}:
            raise HarnessStop(f"invalid calibration label: {item.label}")
        if not 0.0 <= item.score <= 1.0:
            raise HarnessStop(f"invalid calibration score: {item.score}")
    same_scores = [item.score for item in items if item.label == "same"]
    different_scores = [item.score for item in items if item.label == "different"]
    if not same_scores or not different_scores:
        raise HarnessStop("calibration requires both same and different examples")
    empirical_margin = min(same_scores) - max(different_scores)
    feasible: list[tuple[float, float]] = []
    for different_threshold in DIFFERENT_THRESHOLD_GRID:
        for same_threshold in SAME_THRESHOLD_GRID:
            if different_threshold >= same_threshold:
                continue
            if max(different_scores) <= different_threshold and min(same_scores) >= same_threshold:
                if same_threshold - different_threshold >= MIN_CALIBRATION_SCORE_MARGIN:
                    feasible.append((different_threshold, same_threshold))
    if not feasible or empirical_margin < MIN_CALIBRATION_SCORE_MARGIN:
        return CalibrationResult(
            status="ALL_UNCERTAIN",
            thresholds=SameContainerThresholds(-1.0, 2.0, force_all_uncertain=True),
            margin=float(empirical_margin),
            examples=items,
        )
    different_threshold, same_threshold = max(
        feasible,
        key=lambda pair: (pair[1] - pair[0], -pair[0], pair[1]),
    )
    return CalibrationResult(
        status="FROZEN",
        thresholds=SameContainerThresholds(different_threshold, same_threshold),
        margin=float(empirical_margin),
        examples=items,
    )


def _group_fragments(page: PageInput) -> dict[str, list[Fragment]]:
    grouped: dict[str, list[Fragment]] = {}
    for item in page.fragments:
        grouped.setdefault(item.upstream_group_id, []).append(item)
    return grouped


def _bbox_mask(shape: tuple[int, int], fragments: Iterable[Fragment], padding: int) -> np.ndarray:
    height, width = shape
    items = tuple(fragments)
    x1 = max(0, min(item.bbox[0] for item in items) - padding)
    y1 = max(0, min(item.bbox[1] for item in items) - padding)
    x2 = min(width, max(item.bbox[0] + item.bbox[2] for item in items) + padding)
    y2 = min(height, max(item.bbox[1] + item.bbox[3] for item in items) + padding)
    mask = np.zeros((height, width), dtype=np.bool_)
    mask[y1:y2, x1:x2] = True
    return mask


def run_b0(page: PageInput) -> AssociationResult:
    groups = _group_fragments(page)
    regions: list[RegionResult] = []
    for index, (group_id, items) in enumerate(sorted(groups.items()), start=1):
        padding = max(2, int(round(0.75 * float(np.median([item.scale for item in items])))))
        regions.append(
            RegionResult(
                region_id=f"B0-r{index:03d}",
                fragment_ids=tuple(sorted(item.fragment_id for item in items)),
                mask=_bbox_mask(page.image.shape[:2], items, padding),
                container_type="uncertain",
                confidence=0.0,
            )
        )
    overlap = any(
        np.logical_and(left.mask, right.mask).any()
        for left, right in itertools.combinations(regions, 2)
    )
    reasons = ("bbox_overlap",) if overlap else ("baseline_has_no_container_evidence",)
    return AssociationResult(
        asset_id=page.asset_id,
        method_id="B0",
        regions=tuple(regions),
        same_container_decisions=(),
        virtual_boundary=np.zeros(page.image.shape[:2], dtype=np.bool_),
        recommended_decision="SKIP" if not regions else "REVIEW_REQUIRED",
        abstention_reasons=reasons if regions else ("no_seed",),
        diagnostics={"group_count": len(groups)},
    )


def _seed_markers(page: PageInput) -> tuple[np.ndarray, list[tuple[str, tuple[Fragment, ...], int]]]:
    height, width = page.image.shape[:2]
    markers = np.zeros((height, width), dtype=np.int32)
    markers[0, :] = 1
    markers[-1, :] = 1
    markers[:, 0] = 1
    markers[:, -1] = 1
    seeds: list[tuple[str, tuple[Fragment, ...], int]] = []
    for label, (group_id, items) in enumerate(sorted(_group_fragments(page).items()), start=2):
        frozen_items = tuple(items)
        for item in frozen_items:
            x, y, box_width, box_height = item.bbox
            inset_x = max(1, box_width // 5)
            inset_y = max(1, box_height // 5)
            markers[y + inset_y : y + box_height - inset_y, x + inset_x : x + box_width - inset_x] = label
        seeds.append((group_id, frozen_items, label))
    return markers, seeds


def run_b1(page: PageInput) -> AssociationResult:
    if not page.fragments:
        return AssociationResult(
            page.asset_id,
            "B1",
            (),
            (),
            np.zeros(page.image.shape[:2], dtype=np.bool_),
            "SKIP",
            ("no_seed",),
            {},
        )
    markers, seeds = _seed_markers(page)
    watershed = _seeded_watershed(_gradient_magnitude(page.image), markers)
    regions = tuple(
        RegionResult(
            region_id=f"B1-r{index:03d}",
            fragment_ids=tuple(sorted(item.fragment_id for item in items)),
            mask=(watershed == label),
            container_type="uncertain",
            confidence=0.0,
        )
        for index, (_group_id, items, label) in enumerate(seeds, start=1)
    )
    return AssociationResult(
        asset_id=page.asset_id,
        method_id="B1",
        regions=regions,
        same_container_decisions=(),
        virtual_boundary=(watershed == -1),
        recommended_decision="REVIEW_REQUIRED",
        abstention_reasons=("watershed_has_no_same_container_model",),
        diagnostics={"seed_count": len(seeds)},
    )


class _DisjointSet:
    def __init__(self, ids: Iterable[str]) -> None:
        self.parent = {item: item for item in ids}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def _candidate_pair(left: Fragment, right: Fragment) -> bool:
    normalized_gap = _bbox_gap(left, right) / max(1.0, (left.scale + right.scale) / 2.0)
    return normalized_gap <= 8.0


def _seeded_watershed(gradient: np.ndarray, markers: np.ndarray) -> np.ndarray:
    """Deterministic priority-flood seeded watershed; -1 denotes competition ridge."""
    height, width = gradient.shape
    owners = markers.copy()
    levels = np.full((height, width), np.inf, dtype=np.float32)
    queue: list[tuple[float, int, int, int]] = []
    for y, x in np.argwhere(markers > 0):
        owner = int(markers[y, x])
        levels[y, x] = 0.0
        heapq.heappush(queue, (0.0, owner, int(y), int(x)))
    while queue:
        level, owner, y, x = heapq.heappop(queue)
        if level > float(levels[y, x]) + 1e-9 or owners[y, x] not in {owner, -1}:
            continue
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if ny < 0 or nx < 0 or ny >= height or nx >= width:
                continue
            candidate = max(level, float(gradient[ny, nx]))
            if candidate + 1e-9 < float(levels[ny, nx]):
                levels[ny, nx] = candidate
                owners[ny, nx] = owner
                heapq.heappush(queue, (candidate, owner, ny, nx))
            elif owners[ny, nx] not in {owner, 0, -1} and abs(candidate - float(levels[ny, nx])) <= 1e-6:
                owners[ny, nx] = -1
    return owners


def _slic_labels(page: PageInput) -> tuple[np.ndarray, int, int]:
    """Small dependency-free SLIC implementation in RGBXY space for the Spike."""
    median_scale = float(np.median([item.scale for item in page.fragments])) if page.fragments else 16.0
    region_size = int(np.clip(round(0.5 * median_scale), 8, 32))
    image = page.image.astype(np.float32) / 255.0
    height, width = image.shape[:2]
    centers: list[list[float]] = []
    for y in range(region_size // 2, height, region_size):
        for x in range(region_size // 2, width, region_size):
            color = image[min(y, height - 1), min(x, width - 1)]
            centers.append([float(color[0]), float(color[1]), float(color[2]), float(y), float(x)])
    if not centers:
        centers = [[*map(float, image[height // 2, width // 2]), height / 2.0, width / 2.0]]
    centers_array = np.asarray(centers, dtype=np.float32)
    labels = np.full((height, width), -1, dtype=np.int32)
    compactness = 10.0
    for _ in range(SLIC_ITERATIONS):
        distances = np.full((height, width), np.inf, dtype=np.float32)
        for index, center in enumerate(centers_array):
            y, x = float(center[3]), float(center[4])
            y1, y2 = max(0, int(y - region_size)), min(height, int(y + region_size + 1))
            x1, x2 = max(0, int(x - region_size)), min(width, int(x + region_size + 1))
            patch = image[y1:y2, x1:x2]
            yy, xx = np.mgrid[y1:y2, x1:x2]
            color_distance = np.sum((patch - center[:3]) ** 2, axis=2)
            spatial_distance = (yy - y) ** 2 + (xx - x) ** 2
            distance = color_distance + (compactness / region_size) ** 2 * spatial_distance
            current = distances[y1:y2, x1:x2]
            improve = distance < current
            current[improve] = distance[improve]
            labels[y1:y2, x1:x2][improve] = index
        flat_labels = labels.ravel()
        for index in range(len(centers_array)):
            selected = flat_labels == index
            if not selected.any():
                continue
            yy, xx = np.nonzero(labels == index)
            colors = image.reshape(-1, 3)[selected]
            centers_array[index, :3] = colors.mean(axis=0)
            centers_array[index, 3] = float(yy.mean())
            centers_array[index, 4] = float(xx.mean())
    return labels, len(centers_array), region_size


def _superpixel_graph(page: PageInput, labels: np.ndarray, count: int):
    colors = page.image.astype(np.float32) / 255.0
    flat_labels = labels.ravel()
    sizes = np.bincount(flat_labels, minlength=count).astype(np.float32)
    means = np.zeros((count, 3), dtype=np.float32)
    for channel in range(3):
        means[:, channel] = np.bincount(flat_labels, weights=colors[:, :, channel].ravel(), minlength=count)
    means /= np.maximum(sizes[:, None], 1.0)
    gradient = _gradient_magnitude(page.image)
    boundaries: dict[tuple[int, int], float] = {}

    def add_edges(left_labels, right_labels, edge_strength):
        different = left_labels != right_labels
        for left, right, strength in zip(
            left_labels[different].ravel(),
            right_labels[different].ravel(),
            edge_strength[different].ravel(),
        ):
            key = (int(min(left, right)), int(max(left, right)))
            boundaries[key] = max(boundaries.get(key, 0.0), float(strength))

    add_edges(labels[:, :-1], labels[:, 1:], np.maximum(gradient[:, :-1], gradient[:, 1:]))
    add_edges(labels[:-1, :], labels[1:, :], np.maximum(gradient[:-1, :], gradient[1:, :]))
    graph: list[list[tuple[int, float]]] = [[] for _ in range(count)]
    for (left, right), strength in boundaries.items():
        if strength >= P1_HARD_BARRIER:
            continue
        color_distance = float(np.linalg.norm(means[left] - means[right]))
        cost = 1.0 + 2.0 * color_distance + 4.0 * strength
        graph[left].append((right, cost))
        graph[right].append((left, cost))
    return graph, boundaries


def _polygon_mask(shape: tuple[int, int], polygon: tuple[tuple[float, float], ...]) -> np.ndarray:
    height, width = shape
    points = np.asarray(polygon, dtype=np.float64)
    if len(points) < 3:
        return np.zeros(shape, dtype=np.bool_)
    x1 = max(0, int(math.floor(float(points[:, 0].min()))))
    x2 = min(width, int(math.ceil(float(points[:, 0].max()))) + 1)
    y1 = max(0, int(math.floor(float(points[:, 1].min()))))
    y2 = min(height, int(math.ceil(float(points[:, 1].max()))) + 1)
    yy, xx = np.mgrid[y1:y2, x1:x2]
    px = xx.astype(np.float64) + 0.5
    py = yy.astype(np.float64) + 0.5
    inside = np.zeros(px.shape, dtype=np.bool_)
    previous = points[-1]
    for current in points:
        x_a, y_a = previous
        x_b, y_b = current
        crosses = ((y_a > py) != (y_b > py)) & (
            px < (x_b - x_a) * (py - y_a) / ((y_b - y_a) + 1e-12) + x_a
        )
        inside ^= crosses
        previous = current
    mask = np.zeros(shape, dtype=np.bool_)
    mask[y1:y2, x1:x2] = inside
    return mask


def _seed_superpixels(labels: np.ndarray, components: list[tuple[Fragment, ...]]) -> list[set[int]]:
    height, width = labels.shape
    seeds: list[set[int]] = []
    for items in components:
        node_ids: set[int] = set()
        for item in items:
            mask = _polygon_mask((height, width), item.polygon)
            node_ids.update(int(value) for value in np.unique(labels[mask]))
        seeds.append(node_ids)
    return seeds


def _propagate(graph: list[list[tuple[int, float]]], seeds: list[set[int]]):
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
            candidate = distance + cost
            if candidate > P1_MAX_GEODESIC_COST:
                continue
            if candidate + 1e-9 < distances[neighbor]:
                distances[neighbor] = candidate
                owners[neighbor] = owner
                heapq.heappush(queue, (candidate, owner, neighbor))
            elif owners[neighbor] != owner and abs(candidate - distances[neighbor]) <= 0.5:
                contested.add(neighbor)
    return owners, distances, contested


def _virtual_boundary(labels: np.ndarray, owners: np.ndarray, contested: set[int]) -> np.ndarray:
    owner_image = owners[labels]
    boundary = np.isin(labels, np.fromiter(contested, dtype=np.int32)) if contested else np.zeros_like(labels, dtype=bool)
    horizontal = (owner_image[:, :-1] >= 0) & (owner_image[:, 1:] >= 0) & (owner_image[:, :-1] != owner_image[:, 1:])
    vertical = (owner_image[:-1, :] >= 0) & (owner_image[1:, :] >= 0) & (owner_image[:-1, :] != owner_image[1:, :])
    boundary[:, :-1] |= horizontal
    boundary[:, 1:] |= horizontal
    boundary[:-1, :] |= vertical
    boundary[1:, :] |= vertical
    return boundary.astype(np.bool_)


def _classify_region(mask: np.ndarray, gradient: np.ndarray) -> tuple[str, float]:
    if not mask.any():
        return "uncertain", 0.0
    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    dilated = np.zeros_like(mask)
    eroded = np.ones_like(mask)
    for dy in range(3):
        for dx in range(3):
            view = padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
            dilated |= view
            eroded &= view
    edge = dilated != eroded
    strong_ratio = float(np.mean(gradient[edge] >= 0.45)) if edge.any() else 0.0
    touches_border = bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())
    if strong_ratio >= 0.55 and not touches_border:
        return "explicit_container", strong_ratio
    if strong_ratio >= 0.25 or touches_border:
        return "implicit_container", max(0.25, strong_ratio)
    return "free_text", max(0.0, 1.0 - strong_ratio)


def run_p1(page: PageInput, thresholds: SameContainerThresholds) -> AssociationResult:
    if not page.fragments:
        return AssociationResult(
            page.asset_id,
            "P1",
            (),
            (),
            np.zeros(page.image.shape[:2], dtype=np.bool_),
            "SKIP",
            ("no_seed",),
            {},
        )
    decisions: list[SameContainerDecision] = []
    disjoint = _DisjointSet(item.fragment_id for item in page.fragments)
    for left, right in itertools.combinations(page.fragments, 2):
        if not _candidate_pair(left, right):
            continue
        evidence = score_same_container(page, left, right)
        decision = thresholds.classify(evidence.score)
        decisions.append(
            SameContainerDecision(
                left.fragment_id,
                right.fragment_id,
                evidence.score,
                decision,
                evidence.features,
            )
        )
        if decision == "same":
            disjoint.union(left.fragment_id, right.fragment_id)

    components_by_root: dict[str, list[Fragment]] = {}
    for item in page.fragments:
        components_by_root.setdefault(disjoint.find(item.fragment_id), []).append(item)
    components = [tuple(sorted(items, key=lambda item: item.fragment_id)) for _root, items in sorted(components_by_root.items())]

    labels, superpixel_count, region_size = _slic_labels(page)
    graph, _boundaries = _superpixel_graph(page, labels, superpixel_count)
    seed_nodes = _seed_superpixels(labels, components)
    owners, distances, contested = _propagate(graph, seed_nodes)
    virtual_boundary = _virtual_boundary(labels, owners, contested)
    gradient = _gradient_magnitude(page.image)
    regions: list[RegionResult] = []
    for owner, items in enumerate(components):
        mask = (owners[labels] == owner)
        container_type, confidence = _classify_region(mask, gradient)
        regions.append(
            RegionResult(
                region_id=f"P1-r{owner + 1:03d}",
                fragment_ids=tuple(item.fragment_id for item in items),
                mask=mask.astype(np.bool_),
                container_type=container_type,
                confidence=confidence,
            )
        )

    reasons: set[str] = set()
    if any(item.decision == "uncertain" for item in decisions):
        reasons.add("uncertain_same_container_pair")
    if any(not item.mask.any() for item in regions):
        reasons.add("unassigned_seed_component")
    if any(item.container_type == "free_text" for item in regions):
        reasons.add("free_text_requires_review")
    if any(item.container_type == "implicit_container" for item in regions):
        reasons.add("implicit_boundary_requires_review")
    if reasons:
        recommendation = "REVIEW_REQUIRED"
    elif regions and all(item.container_type == "explicit_container" for item in regions):
        recommendation = "LOW_RISK_ASSOCIATION_CANDIDATE"
    else:
        recommendation = "REVIEW_REQUIRED"
    finite_distances = distances[np.isfinite(distances)]
    return AssociationResult(
        asset_id=page.asset_id,
        method_id="P1",
        regions=tuple(regions),
        same_container_decisions=tuple(decisions),
        virtual_boundary=virtual_boundary,
        recommended_decision=recommendation,
        abstention_reasons=tuple(sorted(reasons)),
        diagnostics={
            "superpixel_count": superpixel_count,
            "slic_region_size": region_size,
            "source_component_count": len(components),
            "unassigned_superpixel_count": int(np.count_nonzero(owners < 0)),
            "max_finite_geodesic_cost": float(np.max(finite_distances)) if finite_distances.size else None,
        },
    )
