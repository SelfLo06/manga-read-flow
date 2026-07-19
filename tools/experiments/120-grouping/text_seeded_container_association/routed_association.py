#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import itertools
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from tools.experiments.grouping_120.text_seeded_container_association import focused_correction as focused
from tools.experiments.grouping_120.text_seeded_container_association import harness as base


SCHEMA_VERSION = "text-seeded-container-routed-association-v1"
ROUTES = {
    "COARSE_CONTAINER_SEARCH",
    "BOUNDED_SUPPORT",
    "REGIONLESS_ABSTENTION",
}


@dataclass(frozen=True)
class RoutedPolicy:
    container_boundary_threshold: float
    extreme_seed_span_ratio: float
    extreme_seed_area_ratio: float
    max_support_group_count: int
    support_padding_scale: float
    support_max_area_ratio: float
    topology_different_threshold: float
    topology_same_threshold: float
    topology_same_min_member_pairs: int = 2

    def __post_init__(self) -> None:
        if not 0.0 < self.container_boundary_threshold < 1.0:
            raise base.HarnessStop("invalid container boundary threshold")
        if not 0.0 < self.extreme_seed_span_ratio <= 1.0:
            raise base.HarnessStop("invalid extreme span threshold")
        if not 0.0 < self.extreme_seed_area_ratio <= 1.0:
            raise base.HarnessStop("invalid extreme area threshold")
        if self.max_support_group_count < 1:
            raise base.HarnessStop("max support group count must be positive")
        if not 0.0 < self.support_padding_scale <= 1.0:
            raise base.HarnessStop("invalid support padding scale")
        if not 0.0 < self.support_max_area_ratio <= 1.0:
            raise base.HarnessStop("invalid support area ratio")
        if not 0.0 <= self.topology_different_threshold < self.topology_same_threshold <= 1.0:
            raise base.HarnessStop("invalid topology thresholds")
        if self.topology_same_min_member_pairs < 1:
            raise base.HarnessStop("topology pair minimum must be positive")


@dataclass(frozen=True)
class SpatialRegion:
    region_id: str
    fragment_ids: tuple[str, ...]
    mask: np.ndarray
    evidence: dict[str, Any]

    def __post_init__(self) -> None:
        if self.mask.dtype != np.bool_ or self.mask.ndim != 2:
            raise base.HarnessStop("spatial region mask must be a 2-D bool array")
        if not self.mask.any():
            raise base.HarnessStop("spatial region mask must be non-empty")


@dataclass(frozen=True)
class RoutedResult:
    asset_id: str
    route: str
    route_confidence: float
    input_fragment_ids: tuple[str, ...]
    input_group_ids: tuple[str, ...]
    container_regions: tuple[SpatialRegion, ...]
    support_regions: tuple[SpatialRegion, ...]
    topology: str
    topology_evidence: tuple[dict[str, Any], ...]
    recommended_decision: str
    goal6_trial_eligible: bool
    abstention_reasons: tuple[str, ...]
    diagnostics: dict[str, Any]

    def __post_init__(self) -> None:
        if self.route not in ROUTES:
            raise base.HarnessStop(f"unknown route: {self.route}")
        if self.recommended_decision not in {"REVIEW_REQUIRED", "SKIP"}:
            raise base.HarnessStop("Goal 5 has no low-risk or auto-accept decision")
        if self.container_regions and self.support_regions:
            raise base.HarnessStop("container and support outputs are mutually exclusive")
        if self.route == "COARSE_CONTAINER_SEARCH" and not self.container_regions:
            raise base.HarnessStop("container route requires a coarse region")
        if self.route == "BOUNDED_SUPPORT" and not self.support_regions:
            raise base.HarnessStop("support route requires a support region")
        if self.route == "REGIONLESS_ABSTENTION" and (self.container_regions or self.support_regions):
            raise base.HarnessStop("abstention must be regionless")
        if self.route == "REGIONLESS_ABSTENTION" and self.recommended_decision != "SKIP":
            raise base.HarnessStop("regionless abstention must skip")
        if self.goal6_trial_eligible and (
            self.route == "REGIONLESS_ABSTENTION" or self.topology == "uncertain"
        ):
            raise base.HarnessStop("unsafe Goal 6 eligibility")

    def to_jsonable(self) -> dict[str, Any]:
        def encode(items: tuple[SpatialRegion, ...]) -> list[dict[str, Any]]:
            return [
                {
                    "region_id": item.region_id,
                    "fragment_ids": list(item.fragment_ids),
                    "mask_rle": base.encode_bool_rle(item.mask),
                    "area_ratio": float(np.mean(item.mask)),
                    "touches_roi_edge": _touches_edge(item.mask),
                    "evidence": item.evidence,
                }
                for item in items
            ]

        return {
            "schema_version": SCHEMA_VERSION,
            "asset_id": self.asset_id,
            "route": self.route,
            "route_confidence": self.route_confidence,
            "input_fragment_ids": list(self.input_fragment_ids),
            "input_group_ids": list(self.input_group_ids),
            "container_regions_or_null": encode(self.container_regions) or None,
            "support_regions_or_null": encode(self.support_regions) or None,
            "topology": self.topology,
            "topology_evidence": list(self.topology_evidence),
            "recommended_decision": self.recommended_decision,
            "goal6_trial_eligible": self.goal6_trial_eligible,
            "abstention_reasons": list(self.abstention_reasons),
            "diagnostics": self.diagnostics,
        }


def _touches_edge(mask: np.ndarray) -> bool:
    return bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())


def _mask_boundary(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    eroded = np.ones_like(mask)
    dilated = np.zeros_like(mask)
    for dy in range(3):
        for dx in range(3):
            view = padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
            eroded &= view
            dilated |= view
    return dilated != eroded


def _boundary_evidence(mask: np.ndarray, gradient: np.ndarray) -> dict[str, Any]:
    edge = _mask_boundary(mask)
    strength = float(np.mean(gradient[edge] >= 0.45)) if edge.any() else 0.0
    return {
        "strong_boundary_ratio": strength,
        "mean_boundary_gradient": float(np.mean(gradient[edge])) if edge.any() else 0.0,
        "area_ratio": float(np.mean(mask)),
        "touches_roi_edge": _touches_edge(mask),
    }


def _input_geometry(page: base.PageInput) -> dict[str, float]:
    if not page.fragments:
        return {"seed_span_ratio": 0.0, "seed_bbox_area_ratio": 0.0}
    x1 = min(item.bbox[0] for item in page.fragments)
    y1 = min(item.bbox[1] for item in page.fragments)
    x2 = max(item.bbox[0] + item.bbox[2] for item in page.fragments)
    y2 = max(item.bbox[1] + item.bbox[3] for item in page.fragments)
    height, width = page.image.shape[:2]
    return {
        "seed_span_ratio": max((x2 - x1) / width, (y2 - y1) / height),
        "seed_bbox_area_ratio": ((x2 - x1) * (y2 - y1)) / float(width * height),
    }


def classify_pair_aggregate(
    member_scores: tuple[float, ...],
    policy: RoutedPolicy,
) -> str:
    if not member_scores:
        return "different"
    maximum = max(member_scores)
    if len(member_scores) >= policy.topology_same_min_member_pairs and maximum >= policy.topology_same_threshold:
        return "same"
    if maximum <= policy.topology_different_threshold:
        return "different"
    return "uncertain"


def _topology(page: base.PageInput, policy: RoutedPolicy) -> tuple[str, dict[str, str], tuple[dict[str, Any], ...]]:
    groups = {
        group_id: tuple(sorted(items, key=lambda item: item.fragment_id))
        for group_id, items in base._group_fragments(page).items()
    }
    if len(groups) <= 1:
        only = next(iter(groups), "group-001")
        return "same", {only: "component-001"}, ()
    disjoint = base._DisjointSet(groups)
    evidence_items: list[dict[str, Any]] = []
    uncertain = False
    for (left_id, left), (right_id, right) in itertools.combinations(sorted(groups.items()), 2):
        member = tuple(
            focused.score_same_container_v2(page, left_item, right_item).score
            for left_item, right_item in itertools.product(left, right)
            if base._candidate_pair(left_item, right_item)
        )
        decision = classify_pair_aggregate(member, policy)
        if decision == "same":
            disjoint.union(left_id, right_id)
        elif decision == "uncertain":
            uncertain = True
        evidence_items.append(
            {
                "left_group_id": left_id,
                "right_group_id": right_id,
                "member_pair_count": len(member),
                "maximum_member_score": max(member) if member else None,
                "mean_member_score": float(np.mean(member)) if member else None,
                "decision": decision,
            }
        )
    roots = {group_id: disjoint.find(group_id) for group_id in groups}
    root_ids = {root: f"component-{index:03d}" for index, root in enumerate(sorted(set(roots.values())), 1)}
    assignments = {group_id: root_ids[root] for group_id, root in roots.items()}
    if uncertain:
        topology = "uncertain"
    elif len(root_ids) == 1:
        topology = "same"
    else:
        topology = "different"
    return topology, assignments, tuple(evidence_items)


def _page_with_components(page: base.PageInput, assignments: dict[str, str]) -> base.PageInput:
    return base.PageInput(
        page.asset_id,
        page.image,
        tuple(
            base.Fragment(
                item.fragment_id,
                item.bbox,
                item.polygon,
                assignments.get(item.upstream_group_id, item.upstream_group_id),
                item.score,
            )
            for item in page.fragments
        ),
    )


def _support_mask(page: base.PageInput, items: tuple[base.Fragment, ...], policy: RoutedPolicy) -> np.ndarray:
    height, width = page.image.shape[:2]
    scale = float(np.median([item.scale for item in items]))
    gradient = base._gradient_magnitude(page.image)
    x1 = max(0, min(item.bbox[0] for item in items) - max(2, int(round(scale * 0.5))))
    y1 = max(0, min(item.bbox[1] for item in items) - max(2, int(round(scale * 0.5))))
    x2 = min(width, max(item.bbox[0] + item.bbox[2] for item in items) + max(2, int(round(scale * 0.5))))
    y2 = min(height, max(item.bbox[1] + item.bbox[3] for item in items) + max(2, int(round(scale * 0.5))))
    texture = float(np.median(gradient[y1:y2, x1:x2])) if x2 > x1 and y2 > y1 else 0.0
    adaptive_scale = policy.support_padding_scale * (1.0 - 0.5 * min(texture, 1.0))
    padding = max(2, int(round(scale * adaptive_scale)))
    x1 = max(0, min(item.bbox[0] for item in items) - padding)
    y1 = max(0, min(item.bbox[1] for item in items) - padding)
    x2 = min(width, max(item.bbox[0] + item.bbox[2] for item in items) + padding)
    y2 = min(height, max(item.bbox[1] + item.bbox[3] for item in items) + padding)
    mask = np.zeros((height, width), dtype=np.bool_)
    mask[y1:y2, x1:x2] = True
    return mask


def run_routed_association(page: base.PageInput, policy: RoutedPolicy) -> RoutedResult:
    fragment_ids = tuple(sorted(item.fragment_id for item in page.fragments))
    group_ids = tuple(sorted({item.upstream_group_id for item in page.fragments}))
    geometry = _input_geometry(page)
    common = {
        "policy": dataclasses.asdict(policy),
        "seed_geometry": geometry,
        "fragment_count": len(page.fragments),
        "group_count": len(group_ids),
    }
    if not page.fragments:
        return RoutedResult(
            page.asset_id, "REGIONLESS_ABSTENTION", 1.0, (), (), (), (), "not_applicable", (),
            "SKIP", False, ("no_seed",), common,
        )
    if (
        geometry["seed_span_ratio"] >= policy.extreme_seed_span_ratio
        or geometry["seed_bbox_area_ratio"] >= policy.extreme_seed_area_ratio
    ):
        return RoutedResult(
            page.asset_id, "REGIONLESS_ABSTENTION", 1.0, fragment_ids, group_ids, (), (),
            "not_applicable", (), "SKIP", False, ("extreme_seed_geometry",), common,
        )

    preliminary = base.run_b1(page)
    gradient = base._gradient_magnitude(page.image)
    preliminary_evidence = tuple(_boundary_evidence(item.mask, gradient) for item in preliminary.regions)
    best_boundary = max((item["strong_boundary_ratio"] for item in preliminary_evidence), default=0.0)
    common["preliminary_b1_regions"] = list(preliminary_evidence)
    common["best_boundary_ratio"] = best_boundary

    if best_boundary >= policy.container_boundary_threshold:
        topology, assignments, topology_evidence = _topology(page, policy)
        routed_page = page if topology == "uncertain" else _page_with_components(page, assignments)
        coarse = base.run_b1(routed_page)
        regions = tuple(
            SpatialRegion(
                f"container-{index:03d}",
                item.fragment_ids,
                item.mask,
                _boundary_evidence(item.mask, gradient),
            )
            for index, item in enumerate(coarse.regions, 1)
        )
        eligible = topology != "uncertain" and bool(regions)
        return RoutedResult(
            page.asset_id,
            "COARSE_CONTAINER_SEARCH",
            float(best_boundary),
            fragment_ids,
            group_ids,
            regions,
            (),
            topology,
            topology_evidence,
            "REVIEW_REQUIRED",
            eligible,
            ("topology_uncertain",) if topology == "uncertain" else (),
            common,
        )

    if len(group_ids) > policy.max_support_group_count:
        return RoutedResult(
            page.asset_id, "REGIONLESS_ABSTENTION", 1.0 - best_boundary, fragment_ids, group_ids,
            (), (), "not_applicable", (), "SKIP", False, ("too_many_groups_without_container",), common,
        )
    groups = base._group_fragments(page)
    support_regions: list[SpatialRegion] = []
    for index, (group_id, items_list) in enumerate(sorted(groups.items()), 1):
        items = tuple(items_list)
        mask = _support_mask(page, items, policy)
        if _touches_edge(mask) or float(np.mean(mask)) > policy.support_max_area_ratio:
            return RoutedResult(
                page.asset_id, "REGIONLESS_ABSTENTION", 1.0 - best_boundary, fragment_ids, group_ids,
                (), (), "not_applicable", (), "SKIP", False,
                ("bounded_support_contract_failed",), common,
            )
        support_regions.append(
            SpatialRegion(
                f"support-{index:03d}",
                tuple(sorted(item.fragment_id for item in items)),
                mask,
                {"group_id": group_id, "area_ratio": float(np.mean(mask)), "touches_roi_edge": False},
            )
        )
    return RoutedResult(
        page.asset_id,
        "BOUNDED_SUPPORT",
        float(1.0 - best_boundary),
        fragment_ids,
        group_ids,
        (),
        tuple(support_regions),
        "not_applicable",
        (),
        "REVIEW_REQUIRED",
        True,
        (),
        common,
    )


def page_from_s1_asset(root: Path, asset: dict[str, Any]) -> base.PageInput:
    image = np.asarray(Image.open(root / asset["relative_path"]).convert("RGB"), dtype=np.uint8)
    fragment_groups = {
        fragment_id: group["group_id"]
        for group in asset["groups"]
        for fragment_id in group["ordered_fragment_ids"]
    }
    fragments = tuple(
        base.Fragment(
            item["fragment_id"],
            (item["bbox"]["x"], item["bbox"]["y"], item["bbox"]["width"], item["bbox"]["height"]),
            tuple(tuple(point) for point in item["polygon"]),
            fragment_groups[item["fragment_id"]],
            item.get("score"),
        )
        for item in asset["fragments"]
    )
    return base.PageInput(asset["asset_id"], image, fragments)
