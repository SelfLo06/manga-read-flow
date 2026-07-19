#!/usr/bin/env python3
"""Read-only causal trace for the frozen case-72 mark-generation chain.

This harness is diagnostic-only.  It replays the routed seeded-watershed
candidate generation and the downstream Slice 3 mark construction in a
separate ignored output directory.  It never rewrites a frozen run, creates a
Cleaning candidate, or invokes a Cleaner.
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.experiments.cleaning_150.visual_contract import spike_b
from tools.experiments.grouping_120.text_seeded_container_association import harness
from tools.experiments.grouping_120.text_seeded_container_association import routed_association as routed
from tools.experiments.grouping_120.text_seeded_container_association.run_routed_evaluation import policy_from_lock


FULL_PAGE = ROOT / "data/local/reviews/150-cleaning/association-goal6-v0.1/full-page-v0.1"
S1 = FULL_PAGE / "s1-runs/full-page-s1-v0.1/results.json"
GOAL5_LOCK = ROOT / "data/local/reviews/120-grouping/association-goal5-routed-v0.1/calibration-runs/goal5-calibration-v0.1/lock.json"
SNAPSHOT = ROOT / "data/local/reviews/120-grouping/visual-contract-a-v0.1/run-v0.4/visual-contract-snapshot.json"
FROZEN = ROOT / "data/local/runs/150-cleaning/full-page-v0.1/slice-3/run-v0.5/case-72"
DEFAULT_OUTPUT = ROOT / "data/local/runs/150-cleaning/physical-boundary-v0.1/mark-generation-trace-v0.4"
TARGETS = ("case-72__g002__s01", "case-72__g004__s01")


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _save_mask(mask: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.where(mask, 255, 0).astype(np.uint8)).save(path)


def _save_labels(labels: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = np.where(labels < 0, 255, np.clip(labels, 0, 254)).astype(np.uint8)
    Image.fromarray(normalized).save(path)


def _bbox(mask: np.ndarray) -> list[int] | None:
    ys, xs = np.where(mask)
    if not len(xs):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def _components(mask: np.ndarray) -> list[dict[str, object]]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    rows = [
        {
            "pixels": int(stats[index, cv2.CC_STAT_AREA]),
            "bounds_xyxy": [
                int(stats[index, cv2.CC_STAT_LEFT]),
                int(stats[index, cv2.CC_STAT_TOP]),
                int(stats[index, cv2.CC_STAT_LEFT] + stats[index, cv2.CC_STAT_WIDTH]),
                int(stats[index, cv2.CC_STAT_TOP] + stats[index, cv2.CC_STAT_HEIGHT]),
            ],
        }
        for index in range(1, count)
    ]
    return sorted(rows, key=lambda item: (-int(item["pixels"]), item["bounds_xyxy"]))


def _diff(baseline: np.ndarray, variant: np.ndarray) -> dict[str, object]:
    if baseline.shape != variant.shape:
        raise RuntimeError("mask shape mismatch in trace")
    return {
        "baseline_pixels": int(baseline.sum()),
        "variant_pixels": int(variant.sum()),
        "intersection_pixels": int((baseline & variant).sum()),
        "baseline_only_pixels": int((baseline & ~variant).sum()),
        "variant_only_pixels": int((variant & ~baseline).sum()),
        "equal": bool(np.array_equal(baseline, variant)),
    }


def _page_edge_contacts(mask: np.ndarray) -> dict[str, int]:
    return {
        "left": int(mask[:, 0].sum()),
        "right": int(mask[:, -1].sum()),
        "top": int(mask[0, :].sum()),
        "bottom": int(mask[-1, :].sum()),
    }


def _markers(page: harness.PageInput, *, page_background: bool) -> tuple[np.ndarray, list[tuple[str, tuple[harness.Fragment, ...], int]]]:
    markers, seeds = harness._seed_markers(page)
    if page_background:
        return markers, seeds
    markers[0, :] = 0
    markers[-1, :] = 0
    markers[:, 0] = 0
    markers[:, -1] = 0
    return markers, seeds


def _run_b1(page: harness.PageInput, *, page_background: bool) -> tuple[np.ndarray, np.ndarray, dict[frozenset[str], int], dict[str, object]]:
    markers, seeds = _markers(page, page_background=page_background)
    watershed = harness._seeded_watershed(harness._gradient_magnitude(page.image), markers)
    labels = {frozenset(item.fragment_id for item in fragments): label for _group, fragments, label in seeds}
    marker_counts = {
        "page_background_marker_pixels": int((markers == 1).sum()),
        "seed_marker_pixels": {"|".join(sorted(key)): int((markers == label).sum()) for key, label in labels.items()},
        "unmarked_pixels": int((markers == 0).sum()),
    }
    return markers, watershed, labels, marker_counts


def _variant_association(
    page: harness.PageInput,
    policy: routed.RoutedPolicy,
    *,
    page_background: bool,
) -> dict[str, object]:
    """Replay the same route decision, topology and B1 regions with one ablation."""
    preliminary_markers, preliminary_watershed, preliminary_labels, preliminary_counts = _run_b1(page, page_background=page_background)
    preliminary_regions = [preliminary_watershed == label for label in preliminary_labels.values()]
    gradient = harness._gradient_magnitude(page.image)
    preliminary_evidence = tuple(routed._boundary_evidence(mask, gradient) for mask in preliminary_regions)
    best_boundary = max((item["strong_boundary_ratio"] for item in preliminary_evidence), default=0.0)
    if best_boundary < policy.container_boundary_threshold:
        raise RuntimeError("frozen case-72 no longer follows its coarse-container route")
    topology, assignments, topology_evidence = routed._topology(page, policy)
    if topology == "uncertain":
        raise RuntimeError("frozen case-72 topology became uncertain in trace")
    routed_page = routed._page_with_components(page, assignments)
    markers, watershed, labels, marker_counts = _run_b1(routed_page, page_background=page_background)
    return {
        "route": "COARSE_CONTAINER_SEARCH",
        "topology": topology,
        "topology_evidence": list(topology_evidence),
        "preliminary": {
            "markers": preliminary_markers,
            "watershed": preliminary_watershed,
            "labels": preliminary_labels,
            "marker_counts": preliminary_counts,
            "best_boundary_ratio": best_boundary,
        },
        "final": {
            "markers": markers,
            "watershed": watershed,
            "labels": labels,
            "marker_counts": marker_counts,
        },
    }


def _panel_candidate(image: np.ndarray, instance: np.ndarray, bbox: dict[str, int]) -> dict[str, object] | None:
    """Find a long dark horizontal structure outside the candidate basin.

    This is a diagnostic perturbation selector, not a panel-line classifier.
    It avoids all candidate-basin pixels and has no case/target constants.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    x0 = max(0, int(bbox["x"]) - int(bbox["width"]) // 2)
    x1 = min(width, int(bbox["x"]) + int(bbox["width"]) + int(bbox["width"]) // 2)
    y0 = max(0, int(bbox["y"]) - int(bbox["height"]) // 4)
    y1 = min(height, int(bbox["y"]) + int(bbox["height"]) + int(bbox["height"]) // 4)
    def longest_run(row: np.ndarray, offset: int) -> tuple[int, int, int] | None:
        start = 0
        best: tuple[int, int, int] | None = None
        while start < row.size:
            if not row[start]:
                start += 1
                continue
            end = start + 1
            while end < row.size and row[end]:
                end += 1
            candidate = (end - start, offset + start, offset + end)
            if best is None or candidate > best:
                best = candidate
            start = end
        return best

    # Prefer a page-spanning dark run.  A panel separator normally persists
    # on both sides of a bubble, whereas a local border/text stroke does not.
    wide_best: tuple[int, int, int, int] | None = None
    for y in range(y0, y1):
        run = longest_run((gray[y] < 45) & ~instance[y], 0)
        if run is not None:
            candidate = (run[0], y, run[1], run[2])
            if wide_best is None or candidate > wide_best:
                wide_best = candidate
    if wide_best is not None and wide_best[0] >= width // 2:
        length, y, run_x0, run_x1 = wide_best
        return {
            "selection": "page_spanning_dark_horizontal_run",
            "row": y,
            "run_xy": [run_x0, run_x1],
            "run_length": length,
            "search_xyxy": [0, y0, width, y1],
            "suppression_band_y": [max(0, y - 5), min(height, y + 6)],
        }

    best: tuple[int, int, int, int] | None = None
    for y in range(y0, y1):
        run = longest_run((gray[y, x0:x1] < 45) & ~instance[y, x0:x1], x0)
        if run is not None:
            candidate = (run[0], y, run[1], run[2])
            if best is None or candidate > best:
                best = candidate
    if best is None or best[0] < max(32, int(bbox["width"]) // 3):
        return None
    length, y, run_x0, run_x1 = best
    return {
        "selection": "local_dark_horizontal_run_fallback",
        "row": y,
        "run_xy": [run_x0, run_x1],
        "run_length": length,
        "search_xyxy": [x0, y0, x1, y1],
        "suppression_band_y": [max(0, y - 5), min(height, y + 6)],
    }


def _suppress_panel_candidate(image: np.ndarray, instance: np.ndarray, candidate: dict[str, object] | None) -> tuple[np.ndarray, np.ndarray]:
    result = image.copy()
    changed = np.zeros(image.shape[:2], dtype=bool)
    if candidate is None:
        return result, changed
    y0, y1 = (int(value) for value in candidate["suppression_band_y"])
    x0, _unused_y0, x1, _unused_y1 = (int(value) for value in candidate["search_xyxy"])
    source = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    dark = source[y0:y1, x0:x1] < 45
    outside = ~instance[y0:y1, x0:x1]
    selected = dark & outside
    top = max(0, y0 - 6)
    bottom = min(image.shape[0] - 1, y1 + 5)
    replacement = ((image[top, x0:x1].astype(np.uint16) + image[bottom, x0:x1].astype(np.uint16)) // 2).astype(np.uint8)
    patch = result[y0:y1, x0:x1]
    replacement_rows = np.broadcast_to(replacement, patch.shape)
    patch[selected] = replacement_rows[selected]
    result[y0:y1, x0:x1] = patch
    changed[y0:y1, x0:x1] = selected
    return result, changed


def _marks(image: np.ndarray, instance: np.ndarray, bbox: dict[str, int]) -> dict[str, np.ndarray]:
    core = spike_b.text_core_from_bbox(image, bbox, instance, max_text_luminance=180.0)
    required = spike_b.expand_visible_text_support(core, instance, dilation_px=2)
    contour, uncertainty = spike_b.boundary_and_uncertainty(instance, band_px=4)
    safe = spike_b.build_safe_edit_evidence(required, contour, uncertainty)["_safe_edit_mask"]
    return {
        "core": core,
        "required": required,
        "contour": contour,
        "postprocessed_instance": instance.copy(),
        "protected": contour,
        "uncertainty": uncertainty,
        "safe": safe,
        "unsafe": required & ~safe,
    }


def _target_record(
    *,
    target: str,
    target_fragments: frozenset[str],
    bbox: dict[str, int],
    trace: dict[str, object],
    image: np.ndarray,
    baseline_other_instances: np.ndarray,
    frozen_instance: np.ndarray,
) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    final = trace["final"]
    preliminary = trace["preliminary"]
    labels = final["labels"]
    label = labels[target_fragments]
    raw = final["watershed"] == label
    preliminary_label = preliminary["labels"][target_fragments]
    preliminary_basin = preliminary["watershed"] == preliminary_label
    marks = _marks(image, raw, bbox)
    post = marks["postprocessed_instance"]
    contour_components = _components(marks["contour"])
    record = {
        "route": trace["route"],
        "topology": trace["topology"],
        "preliminary_watershed": {
            "marker": preliminary["marker_counts"],
            "basin_label": int(preliminary_label),
            "basin_pixels": int(preliminary_basin.sum()),
            "basin_bbox_xyxy": _bbox(preliminary_basin),
        },
        "watershed_marker": final["marker_counts"],
        "basin_label": int(label),
        "basin_assignment": {
            "raw_basin_pixels": int(raw.sum()),
            "raw_basin_bbox_xyxy": _bbox(raw),
            "raw_basin_page_edge_contacts": _page_edge_contacts(raw),
            "crosses_baseline_other_instance_pixels": int((raw & baseline_other_instances).sum()),
        },
        "raw_instance_mask": {
            "pixels": int(raw.sum()),
            "bbox_xyxy": _bbox(raw),
            "matches_frozen_instance": bool(np.array_equal(raw, frozen_instance)),
            "diff_to_frozen": _diff(frozen_instance, raw),
        },
        "contour_and_closure": {
            "contour_pixels": int(marks["contour"].sum()),
            "contour_components": contour_components,
            "contour_page_edge_contacts": _page_edge_contacts(marks["contour"]),
            "closure_evaluation": "NOT_IMPLEMENTED_IN_FROZEN_CHAIN",
            "component_rejection_reason": "NOT_IMPLEMENTED_IN_FROZEN_CHAIN",
        },
        "postprocessed_instance_mask": {
            "pixels": int(post.sum()),
            "equals_raw_basin": bool(np.array_equal(post, raw)),
            "postprocess": "single-segment Spike-A partition is identity",
        },
        "marks": {
            "core_pixels": int(marks["core"].sum()),
            "required_pixels": int(marks["required"].sum()),
            "safe_pixels": int(marks["safe"].sum()),
            "protected_pixels": int(marks["protected"].sum()),
            "uncertainty_pixels": int(marks["uncertainty"].sum()),
            "required_protected_overlap_pixels": int((marks["required"] & marks["protected"]).sum()),
            "required_uncertainty_overlap_pixels": int((marks["required"] & marks["uncertainty"]).sum()),
            "unsafe_required_pixels": int(marks["unsafe"].sum()),
            "unsafe_components": _components(marks["unsafe"]),
            "text_omitted_from_baseline_is_reported_by_variant_diff": True,
            "boundary_damage": "NOT_APPLICABLE_NO_CLEANER_WRITE",
        },
    }
    masks = {"preliminary_basin": preliminary_basin, "basin": raw, **marks}
    return record, masks


def _write_variant_masks(
    output: Path,
    target: str,
    variant: str,
    masks: dict[str, np.ndarray],
    markers: np.ndarray,
    labels: np.ndarray,
    preliminary_markers: np.ndarray,
    preliminary_labels: np.ndarray,
) -> None:
    root = output / "targets" / target / variant
    _save_labels(markers, root / "watershed-markers.png")
    _save_labels(labels, root / "watershed-labels.png")
    _save_labels(preliminary_markers, root / "preliminary-watershed-markers.png")
    _save_labels(preliminary_labels, root / "preliminary-watershed-labels.png")
    for name, mask in masks.items():
        if name == "markers":
            continue
        _save_mask(mask, root / f"{name}.png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--variant",
        choices=("baseline", "no_page_background_marker", "panel_line_suppression"),
        required=True,
    )
    parser.add_argument("--target", choices=TARGETS)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.variant == "panel_line_suppression" and not args.target:
        parser.error("--target is required for panel_line_suppression")
    if args.variant != "panel_line_suppression" and args.target:
        parser.error("--target is only valid for panel_line_suppression")
    output.mkdir(parents=True, exist_ok=True)

    s1 = _load_json(S1)
    asset = next(item for item in s1["assets"] if item["asset_id"] == "case-72")
    policy = policy_from_lock(_load_json(GOAL5_LOCK))
    page = routed.page_from_s1_asset(FULL_PAGE, asset)
    snapshot = _load_json(SNAPSHOT)
    page_snapshot = next(item for item in snapshot["pages"] if item["page_id"] == "case-72")
    group_fragments = {item["group_id"]: frozenset(item["ordered_fragment_ids"]) for item in asset["groups"]}
    segment_bbox = {item["segment_id"]: item["bbox"] for item in page_snapshot["text_segments"]}

    # Each invocation holds at most a baseline and one comparison trace.  This
    # keeps the diagnostic replay bounded on the full-page image.
    baseline_trace = _variant_association(page, policy, page_background=True)
    baseline_raws = {
        group: baseline_trace["final"]["watershed"] == label
        for group, label in baseline_trace["final"]["labels"].items()
    }
    if args.variant == "baseline":
        selected_targets = TARGETS
        comparison_trace: dict[str, object] | None = None
        comparison_image: np.ndarray | None = None
        comparison_meta: dict[str, object] = {"source_changed_pixels": 0}
    elif args.variant == "no_page_background_marker":
        selected_targets = TARGETS
        comparison_trace = _variant_association(page, policy, page_background=False)
        comparison_image = page.image
        comparison_meta = {"source_changed_pixels": 0}
    else:
        selected_targets = (args.target,)
        target = args.target
        assert target is not None
        group = target.rsplit("__s", 1)[0]
        baseline_raw = baseline_raws[group_fragments[group]]
        candidate = _panel_candidate(page.image, baseline_raw, segment_bbox[target])
        panel_image, source_changed = _suppress_panel_candidate(page.image, baseline_raw, candidate)
        comparison_trace = _variant_association(
            harness.PageInput(page.asset_id, panel_image, page.fragments),
            policy,
            page_background=True,
        )
        comparison_image = panel_image
        comparison_meta = {
            "candidate": candidate,
            "source_changed_pixels": int(source_changed.sum()),
        }

    report: dict[str, object] = {
        "schema": "physical-boundary-mark-generation-trace-v0.1",
        "scope": "read-only diagnostic replay; no frozen artifact mutation and no Cleaner call",
        "chain": [
            "full-page seeded watershed markers",
            "watershed basin label / routed container assignment",
            "raw instance mask",
            "single-segment Spike-A postprocess",
            "morphological contour=protected and 4px uncertainty",
            "dark-core required support, safe subtraction and unsafe components",
        ],
        "known_chain_limits": {
            "roi_crop": "NONE: routed B1 runs on full-page source",
            "contour_closure": "NOT_IMPLEMENTED_IN_FROZEN_CHAIN",
            "component_rejection_reason": "NOT_IMPLEMENTED_IN_FROZEN_CHAIN",
            "panel_line_semantic_class": "NOT_IMPLEMENTED_IN_FROZEN_CHAIN",
        },
        "variant": args.variant,
        "variants": {
            "baseline": "frozen source + page-border background marker",
            "no_page_background_marker": "same source/seeds/policy; only border marker label 1 removed",
            "panel_line_suppression": "same seeds/policy/marker; only source-derived dark horizontal candidate outside baseline basin is interpolated",
        },
        "targets": {},
    }
    for target in selected_targets:
        group = target.rsplit("__s", 1)[0]
        fragments = group_fragments[group]
        frozen = cv2.imread(str(FROZEN / "evidence" / target / "instance.png"), cv2.IMREAD_GRAYSCALE) > 0
        others = np.zeros_like(frozen)
        for other_fragments, raw in baseline_raws.items():
            if other_fragments != fragments:
                others |= raw
        variants = {"baseline": (baseline_trace, page.image, {"source_changed_pixels": 0})}
        if comparison_trace is not None and comparison_image is not None:
            variants[args.variant] = (comparison_trace, comparison_image, comparison_meta)
        target_rows: dict[str, object] = {}
        baseline_masks: dict[str, np.ndarray] | None = None
        for name, (trace, image, variant_meta) in variants.items():
            record, masks = _target_record(
                target=target,
                target_fragments=fragments,
                bbox=segment_bbox[target],
                trace=trace,
                image=image,
                baseline_other_instances=others,
                frozen_instance=frozen,
            )
            record["variant_meta"] = variant_meta
            if baseline_masks is None:
                baseline_masks = masks
                record["diff_from_baseline"] = {name: _diff(mask, mask) for name, mask in masks.items() if name != "markers"}
                record["watershed_marker_diff_from_baseline"] = {
                    "changed_label_pixels": 0,
                    "preliminary_changed_label_pixels": 0,
                    "equal": True,
                }
            else:
                record["diff_from_baseline"] = {
                    mask_name: _diff(baseline_masks[mask_name], mask)
                    for mask_name, mask in masks.items()
                    if mask_name != "markers"
                }
                record["text_omission_vs_baseline_required_pixels"] = int((baseline_masks["required"] & ~masks["required"]).sum())
                baseline_markers = baseline_trace["final"]["markers"]
                variant_markers = trace["final"]["markers"]
                record["watershed_marker_diff_from_baseline"] = {
                    "changed_label_pixels": int((baseline_markers != variant_markers).sum()),
                    "preliminary_changed_label_pixels": int(
                        (baseline_trace["preliminary"]["markers"] != trace["preliminary"]["markers"]).sum()
                    ),
                    "equal": bool(np.array_equal(baseline_markers, variant_markers)),
                }
            _write_variant_masks(
                output,
                target,
                name,
                masks,
                trace["final"]["markers"],
                trace["final"]["watershed"],
                trace["preliminary"]["markers"],
                trace["preliminary"]["watershed"],
            )
            target_rows[name] = record
        report["targets"][target] = target_rows
    report_path = output / f"trace-{args.variant}{'-' + args.target if args.target else ''}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(report_path), "targets": list(report["targets"])}, ensure_ascii=False))
    del baseline_trace, baseline_raws, comparison_trace
    gc.collect()


if __name__ == "__main__":
    main()
