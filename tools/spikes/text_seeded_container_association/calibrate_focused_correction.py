#!/usr/bin/env python3
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import itertools
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


EXPECTED_RUN_ID = "20260715T114410Z-7b216b"
EXPECTED_RESULTS_SHA256 = "1596a7fbd336ab00f3afc949852b8debff2bcb2073f58d5db6bbae52a193b128"
EXPECTED_SPEC_SHA256 = "fec0210c9e7e03f78fa8d93aae157812c472c795a091765bcaf1b5dfa9411ba1"
EXPECTED_FORM_SHA256 = "7cd3ffeff3a632c83d33c4e8592074573c77051489c931917dc9b12f061ec9b7"
EXPECTED_BASE_HARNESS_SHA256 = "bea1d1ee39200b44729936e05aee4f4ebfd0fa71eeec05212d2ec42d66364f11"
EXPECTED_ASSET_IDS = tuple(f"cal-{index}" for index in range(41, 49))
RESULTS_RELATIVE_PATH = Path("s1-runs") / EXPECTED_RUN_ID / "results.json"
SPEC_RELATIVE_PATH = Path("S1-INPUT-SPEC.local.json")
FORM_RELATIVE_PATH = Path("FORM.md")
LABELS_RELATIVE_PATH = Path("coordinator") / "LABELS.local.json"
SCHEMA_VERSION = "text-seeded-container-focused-calibration-lock-v1"

DIFFERENT_THRESHOLD_GRID = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60)
SAME_THRESHOLD_GRID = (0.65, 0.70, 0.75, 0.80, 0.85, 0.90)
MIN_ABSTENTION_GAP = 0.15
MAX_GEODESIC_COST_GRID = (8.0, 12.0, 16.0, 20.0)
SUPPORT_PADDING_SCALE_GRID = (0.15, 0.25, 0.50, 0.75, 1.0, 1.5, 2.0)
MAX_SUPPORT_AREA_RATIO_GRID = (0.15, 0.20, 0.25)
MAX_MERGED_SUPPORT_AREA_RATIO_GRID = (0.35, 0.50, 0.65)
REGIONLESS_EXTREME_SPAN_RATIO_GRID = (0.80, 0.90)
REGIONLESS_SEED_BBOX_AREA_RATIO_GRID = (0.15, 0.20)


class CalibrationStop(RuntimeError):
    pass


def _load_focused_correction():
    path = Path(__file__).with_name("focused_correction.py")
    name = "text_seeded_container_focused_correction_for_calibration"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CalibrationStop(f"cannot load focused correction module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FOCUSED = _load_focused_correction()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CalibrationStop(f"cannot read JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise CalibrationStop(f"JSON root must be an object: {path}")
    return payload


def verify_inputs(calibration_root: Path) -> dict[str, Any]:
    root = calibration_root.resolve()
    results_path = root / RESULTS_RELATIVE_PATH
    spec_path = root / SPEC_RELATIVE_PATH
    form_path = root / FORM_RELATIVE_PATH
    labels_path = root / LABELS_RELATIVE_PATH
    hashes = {
        "s1_results": sha256_file(results_path),
        "s1_spec": sha256_file(spec_path),
        "form": sha256_file(form_path),
        "labels": sha256_file(labels_path),
        "base_harness": sha256_file(Path(FOCUSED.BASE.__file__)),
        "focused_correction": sha256_file(Path(FOCUSED.__file__)),
        "calibration_runner": sha256_file(Path(__file__)),
    }
    expected = {
        "s1_results": EXPECTED_RESULTS_SHA256,
        "s1_spec": EXPECTED_SPEC_SHA256,
        "form": EXPECTED_FORM_SHA256,
        "base_harness": EXPECTED_BASE_HARNESS_SHA256,
    }
    for name, expected_hash in expected.items():
        if hashes[name] != expected_hash:
            raise CalibrationStop(f"frozen {name} hash mismatch: {hashes[name]}")
    results = _load_json(results_path)
    labels = _load_json(labels_path)
    if results.get("run_id") != EXPECTED_RUN_ID or results.get("input_hashes_unchanged") is not True:
        raise CalibrationStop("frozen S1 run identity or source-integrity flag is invalid")
    assets = results.get("assets")
    if not isinstance(assets, list):
        raise CalibrationStop("frozen S1 results have no asset list")
    asset_ids = [item.get("asset_id") for item in assets]
    if asset_ids != list(EXPECTED_ASSET_IDS):
        raise CalibrationStop(f"calibration asset scope mismatch: {asset_ids}")
    if labels.get("schema_version") != "text-seeded-container-focused-calibration-labels-v1":
        raise CalibrationStop("unexpected focused calibration label schema")
    if labels.get("form_sha256") != hashes["form"] or labels.get("confidence") != "high":
        raise CalibrationStop("label key does not point to the frozen high-confidence FORM")
    if labels.get("pixel_accurate_boundary_ground_truth") is not False:
        raise CalibrationStop("focused calibration must not claim pixel-accurate boundary GT")
    for asset in assets:
        if sha256_file(root / asset["relative_path"]) != asset.get("sha256"):
            raise CalibrationStop(f"calibration image hash mismatch: {asset['asset_id']}")
    return {
        "root": root,
        "results": results,
        "labels": labels,
        "hashes": hashes,
        "asset_ids": asset_ids,
    }


def page_from_asset(root: Path, asset: dict[str, Any]):
    image = np.asarray(Image.open(root / asset["relative_path"]).convert("RGB"), dtype=np.uint8)
    fragment_groups: dict[str, str] = {}
    for group in asset["groups"]:
        for fragment_id in group["ordered_fragment_ids"]:
            if fragment_id in fragment_groups:
                raise CalibrationStop(f"fragment appears in multiple groups: {asset['asset_id']}/{fragment_id}")
            fragment_groups[fragment_id] = group["group_id"]
    fragments = []
    for item in asset["fragments"]:
        fragment_id = item["fragment_id"]
        if fragment_id not in fragment_groups:
            raise CalibrationStop(f"fragment has no frozen group: {asset['asset_id']}/{fragment_id}")
        bbox = item["bbox"]
        fragments.append(
            FOCUSED.Fragment(
                fragment_id=fragment_id,
                bbox=(bbox["x"], bbox["y"], bbox["width"], bbox["height"]),
                polygon=tuple(tuple(point) for point in item["polygon"]),
                upstream_group_id=fragment_groups[fragment_id],
                score=item.get("score"),
            )
        )
    return FOCUSED.PageInput(asset["asset_id"], image, tuple(fragments))


def score_pairs(pages: dict[str, Any], labels: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for pair in labels.get("group_pair_labels", []):
        asset_id = pair.get("asset_id")
        if asset_id not in pages or not asset_id.startswith("cal-"):
            raise CalibrationStop(f"pair uses non-calibration asset: {asset_id}")
        left_id, right_id = pair.get("left_group_id"), pair.get("right_group_id")
        normalized = (asset_id, *sorted((left_id, right_id)))
        if normalized in seen:
            raise CalibrationStop(f"duplicate labeled group pair: {normalized}")
        seen.add(normalized)
        if pair.get("label") not in {"same", "different"}:
            raise CalibrationStop(f"invalid pair label: {pair}")
        groups: dict[str, list[Any]] = {}
        for item in pages[asset_id].fragments:
            groups.setdefault(item.upstream_group_id, []).append(item)
        if left_id not in groups or right_id not in groups:
            raise CalibrationStop(f"pair references unknown upstream group: {pair}")
        evidence = FOCUSED.score_group_same_container_v2(
            pages[asset_id], tuple(groups[left_id]), tuple(groups[right_id])
        )
        rows.append(
            {
                "asset_id": asset_id,
                "left_group_id": left_id,
                "right_group_id": right_id,
                "label": pair["label"],
                "score": evidence.score,
                "features": evidence.features,
            }
        )
    if not rows or {row["label"] for row in rows} != {"same", "different"}:
        raise CalibrationStop("focused calibration requires both same and different pair labels")
    return rows


def select_thresholds(scored_pairs: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for different, same in itertools.product(DIFFERENT_THRESHOLD_GRID, SAME_THRESHOLD_GRID):
        if same - different < MIN_ABSTENTION_GAP:
            continue
        decisions = [
            "different" if row["score"] <= different else "same" if row["score"] >= same else "uncertain"
            for row in scored_pairs
        ]
        false_merge = sum(row["label"] == "different" and decision == "same" for row, decision in zip(scored_pairs, decisions))
        false_split = sum(row["label"] == "same" and decision == "different" for row, decision in zip(scored_pairs, decisions))
        correct_decisive = sum(row["label"] == decision for row, decision in zip(scored_pairs, decisions))
        candidates.append(
            {
                "different": different,
                "same": same,
                "false_merge_count": false_merge,
                "false_split_count": false_split,
                "correct_decisive_count": correct_decisive,
                "uncertain_count": decisions.count("uncertain"),
                "abstention_gap": same - different,
            }
        )
    safe = [row for row in candidates if row["false_merge_count"] == 0 and row["false_split_count"] == 0]
    if not safe:
        raise CalibrationStop("no threshold candidate avoids false merge and false split")
    selected = max(
        safe,
        key=lambda row: (
            row["correct_decisive_count"],
            row["abstention_gap"],
            -row["different"],
            row["same"],
        ),
    )
    if selected["correct_decisive_count"] != len(scored_pairs):
        summary = [
            {
                "asset_id": row["asset_id"],
                "group_pair": [row["left_group_id"], row["right_group_id"]],
                "label": row["label"],
                "score": round(float(row["score"]), 6),
                "features": {name: round(float(value), 6) for name, value in row["features"].items()},
            }
            for row in scored_pairs
        ]
        raise CalibrationStop(
            "no threshold candidate classifies every frozen pair decisively and correctly: "
            + json.dumps(summary, ensure_ascii=False)
        )
    return {"selected": selected, "candidates": candidates}


def _component_sets(result) -> set[frozenset[str]]:
    return {frozenset(region.fragment_ids) for region in result.regions}


def evaluate_contract(asset_id: str, result, contract: dict[str, Any]) -> dict[str, Any]:
    kind = contract["kind"]
    masks = [region.mask for region in result.regions]
    failures: list[str] = []
    if kind == "exact_components":
        expected = {frozenset(items) for items in contract["components"]}
        if _component_sets(result) != expected:
            failures.append("component_topology")
    elif kind == "minimum_component_count":
        if len(result.regions) < int(contract["minimum"]):
            failures.append("component_count")
    elif kind == "required_same_component":
        required = set(contract["fragment_ids"])
        if not any(required.issubset(set(region.fragment_ids)) for region in result.regions):
            failures.append("required_same_component")
    elif kind == "regionless_skip":
        if result.recommended_decision != "SKIP" or any(mask is not None for mask in masks):
            failures.append("regionless_skip")
    elif kind == "bounded_support":
        nonnull = [mask for mask in masks if mask is not None]
        if len(nonnull) != 1:
            failures.append("single_nonnull_support")
        else:
            mask = nonnull[0]
            if float(mask.mean()) > float(contract["maximum_area_ratio"]):
                failures.append("support_area_ratio")
            if contract.get("must_not_touch_roi_edge") and (
                mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any()
            ):
                failures.append("support_touches_roi_edge")
        if result.recommended_decision != "REVIEW_REQUIRED":
            failures.append("bounded_support_not_review")
    elif kind == "no_seed_skip":
        if result.recommended_decision != "SKIP" or result.regions or "no_seed" not in result.abstention_reasons:
            failures.append("no_seed_skip")
    else:
        raise CalibrationStop(f"unknown case contract: {asset_id}/{kind}")
    if contract.get("require_nonnull_regions") and any(mask is None for mask in masks):
        failures.append("required_region_is_null")
    return {
        "asset_id": asset_id,
        "kind": kind,
        "passed": not failures,
        "failures": failures,
        "region_count": len(result.regions),
        "nonnull_region_count": sum(mask is not None for mask in masks),
        "component_sets": [sorted(region.fragment_ids) for region in result.regions],
        "area_ratios": [None if mask is None else float(mask.mean()) for mask in masks],
        "recommended_decision": result.recommended_decision,
        "abstention_reasons": list(result.abstention_reasons),
    }


def calibrate(calibration_root: Path) -> dict[str, Any]:
    verified = verify_inputs(calibration_root)
    pages = {
        asset["asset_id"]: page_from_asset(verified["root"], asset)
        for asset in verified["results"]["assets"]
    }
    scored_pairs = score_pairs(pages, verified["labels"])
    threshold_search = select_thresholds(scored_pairs)
    threshold_row = threshold_search["selected"]
    thresholds = FOCUSED.SameContainerThresholds(threshold_row["different"], threshold_row["same"])
    prepared = {
        asset_id: FOCUSED.prepare_corrected_p1(page, thresholds)
        for asset_id, page in pages.items()
        if page.fragments
    }
    contracts = verified["labels"].get("case_contracts", {})
    if set(contracts) != set(EXPECTED_ASSET_IDS):
        raise CalibrationStop(f"case contract scope mismatch: {sorted(contracts)}")
    policy_rows: list[dict[str, Any]] = []
    for max_cost, padding, max_area, max_merged_area, extreme_span, seed_bbox_area in itertools.product(
        MAX_GEODESIC_COST_GRID,
        SUPPORT_PADDING_SCALE_GRID,
        MAX_SUPPORT_AREA_RATIO_GRID,
        MAX_MERGED_SUPPORT_AREA_RATIO_GRID,
        REGIONLESS_EXTREME_SPAN_RATIO_GRID,
        REGIONLESS_SEED_BBOX_AREA_RATIO_GRID,
    ):
        policy = FOCUSED.CorrectedP1Policy(
            thresholds=thresholds,
            max_geodesic_cost=max_cost,
            support_padding_scale=padding,
            max_support_area_ratio=max_area,
            max_merged_support_area_ratio=max_merged_area,
            regionless_uncertain_orientation=True,
            regionless_extreme_span_ratio=extreme_span,
            regionless_seed_bbox_area_ratio=seed_bbox_area,
        )
        results = {
            asset_id: (
                FOCUSED.run_prepared_corrected_p1(prepared[asset_id], policy)
                if asset_id in prepared
                else FOCUSED.run_corrected_p1(page, policy)
            )
            for asset_id, page in pages.items()
        }
        evaluations = [
            evaluate_contract(asset_id, results[asset_id], contracts[asset_id])
            for asset_id in EXPECTED_ASSET_IDS
        ]
        bubble_area = sum(
            sum(0.0 if region.mask is None else float(region.mask.mean()) for region in results[asset_id].regions)
            for asset_id in ("cal-41", "cal-42", "cal-43", "cal-44")
        )
        free_support_area = sum(
            0.0 if region.mask is None else float(region.mask.mean())
            for region in results["cal-46"].regions
        )
        policy_rows.append(
            {
                "policy": dataclasses.asdict(policy),
                "passed": all(item["passed"] for item in evaluations),
                "passed_case_count": sum(item["passed"] for item in evaluations),
                "bubble_support_area_sum": bubble_area,
                "free_support_area_ratio": free_support_area,
                "case_evaluations": evaluations,
            }
        )
    feasible = [row for row in policy_rows if row["passed"]]
    if not feasible:
        best = max(policy_rows, key=lambda row: row["passed_case_count"])
        raise CalibrationStop(
            f"no support policy passes all contracts; best passes {best['passed_case_count']}/8: "
            + json.dumps(
                {
                    "policy": best["policy"],
                    "failed_cases": [
                        item for item in best["case_evaluations"] if not item["passed"]
                    ],
                },
                ensure_ascii=False,
            )
        )
    selected_policy = max(
        feasible,
        key=lambda row: (
            row["bubble_support_area_sum"],
            -row["free_support_area_ratio"],
            -row["policy"]["support_padding_scale"],
            -row["policy"]["max_geodesic_cost"],
            -row["policy"]["max_support_area_ratio"],
            -row["policy"]["max_merged_support_area_ratio"],
            row["policy"]["regionless_extreme_span_ratio"],
            row["policy"]["regionless_seed_bbox_area_ratio"],
        ),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "FROZEN",
        "input": {
            "s1_run_id": EXPECTED_RUN_ID,
            "asset_ids": list(EXPECTED_ASSET_IDS),
            "hashes": verified["hashes"],
            "r0_asset_accessed": False,
            "pixel_accurate_boundary_gt_used": False,
        },
        "scorer": {
            "weights": FOCUSED.SAME_CONTAINER_V2_WEIGHTS,
            "different_threshold_grid": list(DIFFERENT_THRESHOLD_GRID),
            "same_threshold_grid": list(SAME_THRESHOLD_GRID),
            "minimum_abstention_gap": MIN_ABSTENTION_GAP,
            "scored_pairs": scored_pairs,
            "threshold_candidates": threshold_search["candidates"],
            "selected_thresholds": threshold_row,
        },
        "support_search": {
            "max_geodesic_cost_grid": list(MAX_GEODESIC_COST_GRID),
            "support_padding_scale_grid": list(SUPPORT_PADDING_SCALE_GRID),
            "max_support_area_ratio_grid": list(MAX_SUPPORT_AREA_RATIO_GRID),
            "max_merged_support_area_ratio_grid": list(MAX_MERGED_SUPPORT_AREA_RATIO_GRID),
            "regionless_extreme_span_ratio_grid": list(REGIONLESS_EXTREME_SPAN_RATIO_GRID),
            "regionless_seed_bbox_area_ratio_grid": list(REGIONLESS_SEED_BBOX_AREA_RATIO_GRID),
            "candidate_count": len(policy_rows),
            "feasible_count": len(feasible),
            "selected": selected_policy,
            "candidates": policy_rows,
        },
        "selection_rule": (
            "require 8/8 case contracts; then maximize bubble-case bounded support, "
            "minimize free-text support, and prefer the tighter policy on ties"
        ),
        "cleaning_performed": False,
        "benchmark_manifest_created": False,
        "parameter_updates_after_r0": False,
    }


def write_lock(calibration_root: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise CalibrationStop(f"calibration lock already exists: {output_path}")
    payload = calibrate(calibration_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze corrected P1 using Goal 4 calibration assets only.")
    parser.add_argument("--calibration-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = write_lock(args.calibration_root, args.output)
    except (CalibrationStop, FOCUSED.HarnessStop) as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
