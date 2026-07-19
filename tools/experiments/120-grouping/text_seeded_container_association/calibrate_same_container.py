#!/usr/bin/env python3
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


EXPECTED_RUN_ID = "20260715T075556Z-7bb156"
EXPECTED_RESULTS_SHA256 = "195230ecd63191d64621b251b9c1adbc9c6efd6b3366cdfab5bf4438f066a621"
EXPECTED_SPEC_SHA256 = "9162a4314f5b2d71c5bdf80e89a90d02b23852f7d0df2ca85452ae9833074d99"
EXPECTED_ASSET_IDS = ("cal-01", "cal-02")
PAIR_KEY_RELATIVE_PATH = Path("coordinator") / "PAIR-LABELS.local.json"
RESULTS_RELATIVE_PATH = Path("s1-runs") / EXPECTED_RUN_ID / "results.json"
SPEC_RELATIVE_PATH = Path("S1-INPUT-SPEC.local.json")
SCHEMA_VERSION = "text-seeded-container-calibration-lock-v1"


class CalibrationStop(RuntimeError):
    pass


def _load_harness():
    path = Path(__file__).with_name("harness.py")
    name = "text_seeded_container_association_harness_for_calibration"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise CalibrationStop(f"cannot load harness: {path}")
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


HARNESS = _load_harness()


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


def verify_calibration_inputs(calibration_root: Path) -> dict[str, Any]:
    root = calibration_root.resolve()
    results_path = root / RESULTS_RELATIVE_PATH
    spec_path = root / SPEC_RELATIVE_PATH
    results_hash = sha256_file(results_path)
    spec_hash = sha256_file(spec_path)
    if results_hash != EXPECTED_RESULTS_SHA256:
        raise CalibrationStop(f"frozen S1 results hash mismatch: {results_hash}")
    if spec_hash != EXPECTED_SPEC_SHA256:
        raise CalibrationStop(f"frozen calibration spec hash mismatch: {spec_hash}")
    results = _load_json(results_path)
    if results.get("run_id") != EXPECTED_RUN_ID:
        raise CalibrationStop(f"unexpected frozen S1 run: {results.get('run_id')}")
    if results.get("input_hashes_unchanged") is not True:
        raise CalibrationStop("frozen S1 run did not preserve input hashes")
    assets = results.get("assets")
    if not isinstance(assets, list):
        raise CalibrationStop("frozen S1 results have no asset list")
    asset_ids = [item.get("asset_id") for item in assets]
    if asset_ids != list(EXPECTED_ASSET_IDS):
        raise CalibrationStop(f"calibration asset scope mismatch: {asset_ids}")
    for item in assets:
        asset_id = item["asset_id"]
        if not asset_id.startswith("cal-"):
            raise CalibrationStop(f"non-calibration asset in frozen S1 input: {asset_id}")
        image_path = root / item["relative_path"]
        actual_hash = sha256_file(image_path)
        if actual_hash != item.get("sha256"):
            raise CalibrationStop(f"calibration image hash mismatch for {asset_id}: {actual_hash}")
    return {
        "root": root,
        "run_id": results["run_id"],
        "results_path": results_path,
        "results_sha256": results_hash,
        "spec_path": spec_path,
        "spec_sha256": spec_hash,
        "asset_ids": asset_ids,
        "results": results,
    }


def load_pair_key(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload.get("schema_version") != "text-seeded-container-calibration-pairs-v1":
        raise CalibrationStop("unexpected calibration pair-key schema")
    scope = payload.get("asset_scope")
    if not isinstance(scope, list) or not scope:
        raise CalibrationStop("calibration pair key has no asset scope")
    for asset_id in scope:
        if not isinstance(asset_id, str) or not asset_id.startswith("cal-"):
            raise CalibrationStop(f"non-calibration asset in pair key: {asset_id}")
    pairs = payload.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise CalibrationStop("calibration pair key has no pairs")
    seen: set[tuple[str, str, str]] = set()
    for item in pairs:
        asset_id = item.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.startswith("cal-"):
            raise CalibrationStop(f"non-calibration asset in pair key: {asset_id}")
        if asset_id not in scope:
            raise CalibrationStop(f"pair asset is outside pair-key scope: {asset_id}")
        left = item.get("left_fragment_id")
        right = item.get("right_fragment_id")
        if not isinstance(left, str) or not isinstance(right, str) or left == right:
            raise CalibrationStop(f"invalid calibration pair: {item}")
        normalized = (asset_id, *sorted((left, right)))
        if normalized in seen:
            raise CalibrationStop(f"duplicate calibration pair: {normalized}")
        seen.add(normalized)
        if item.get("label") not in {"same", "different"}:
            raise CalibrationStop(f"invalid calibration pair label: {item.get('label')}")
    return payload


def _page_from_asset(root: Path, asset: dict[str, Any]):
    image = np.asarray(Image.open(root / asset["relative_path"]).convert("RGB"), dtype=np.uint8)
    fragment_to_group: dict[str, str] = {}
    for group in asset["groups"]:
        for fragment_id in group["ordered_fragment_ids"]:
            if fragment_id in fragment_to_group:
                raise CalibrationStop(f"fragment appears in multiple S1 groups: {fragment_id}")
            fragment_to_group[fragment_id] = group["group_id"]
    fragments = []
    for item in asset["fragments"]:
        fragment_id = item["fragment_id"]
        if fragment_id not in fragment_to_group:
            raise CalibrationStop(f"fragment has no frozen S1 group: {asset['asset_id']}/{fragment_id}")
        bbox = item["bbox"]
        fragments.append(
            HARNESS.Fragment(
                fragment_id=fragment_id,
                bbox=(bbox["x"], bbox["y"], bbox["width"], bbox["height"]),
                polygon=tuple(tuple(point) for point in item["polygon"]),
                upstream_group_id=fragment_to_group[fragment_id],
                score=item.get("score"),
            )
        )
    return HARNESS.PageInput(asset_id=asset["asset_id"], image=image, fragments=tuple(fragments))


def _candidate_threshold_metrics(examples) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for different_threshold in HARNESS.DIFFERENT_THRESHOLD_GRID:
        for same_threshold in HARNESS.SAME_THRESHOLD_GRID:
            if different_threshold >= same_threshold:
                continue
            thresholds = HARNESS.SameContainerThresholds(different_threshold, same_threshold)
            decisions = [thresholds.classify(item.score) for item in examples]
            rows.append(
                {
                    "different_threshold": different_threshold,
                    "same_threshold": same_threshold,
                    "false_merge_count": sum(
                        item.label == "different" and decision == "same"
                        for item, decision in zip(examples, decisions)
                    ),
                    "false_split_count": sum(
                        item.label == "same" and decision == "different"
                        for item, decision in zip(examples, decisions)
                    ),
                    "decisive_pair_count": sum(decision != "uncertain" for decision in decisions),
                    "uncertain_pair_count": sum(decision == "uncertain" for decision in decisions),
                    "abstention_gap": same_threshold - different_threshold,
                }
            )
    return rows


def score_frozen_pairs(calibration_root: Path) -> dict[str, Any]:
    verified = verify_calibration_inputs(calibration_root)
    pair_path = verified["root"] / PAIR_KEY_RELATIVE_PATH
    pair_key = load_pair_key(pair_path)
    if pair_key["asset_scope"] != list(EXPECTED_ASSET_IDS):
        raise CalibrationStop(f"pair-key asset scope mismatch: {pair_key['asset_scope']}")
    pages = {
        asset["asset_id"]: _page_from_asset(verified["root"], asset)
        for asset in verified["results"]["assets"]
    }
    fragments = {
        asset_id: {item.fragment_id: item for item in page.fragments}
        for asset_id, page in pages.items()
    }
    scored_pairs: list[dict[str, Any]] = []
    examples = []
    for pair in pair_key["pairs"]:
        asset_id = pair["asset_id"]
        try:
            left = fragments[asset_id][pair["left_fragment_id"]]
            right = fragments[asset_id][pair["right_fragment_id"]]
        except KeyError as error:
            raise CalibrationStop(f"pair references unknown frozen fragment: {pair}") from error
        evidence = HARNESS.score_same_container(pages[asset_id], left, right)
        pair_id = f"{asset_id}:{left.fragment_id}:{right.fragment_id}"
        scored_pairs.append(
            {
                "asset_id": asset_id,
                "pair_id": pair_id,
                "left_fragment_id": left.fragment_id,
                "right_fragment_id": right.fragment_id,
                "score": evidence.score,
                "features": evidence.features,
                "label": pair["label"],
            }
        )
        examples.append(
            HARNESS.CalibrationExample(asset_id, pair_id, pair["label"], evidence.score)
        )
    calibration = HARNESS.calibrate_thresholds(examples)
    return {
        "verified": verified,
        "pair_key": pair_key,
        "pair_key_path": pair_path,
        "pair_key_sha256": sha256_file(pair_path),
        "pages": pages,
        "scored_pairs": scored_pairs,
        "examples": tuple(examples),
        "calibration": calibration,
        "candidate_threshold_metrics": _candidate_threshold_metrics(examples),
    }


def _calibration_jsonable(result: dict[str, Any]) -> dict[str, Any]:
    calibration = result["calibration"]
    selected = dataclasses.asdict(calibration.thresholds)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": calibration.status,
        "input": {
            "s1_run_id": result["verified"]["run_id"],
            "s1_results_sha256": result["verified"]["results_sha256"],
            "s1_spec_sha256": result["verified"]["spec_sha256"],
            "asset_ids": result["verified"]["asset_ids"],
            "pair_key_sha256": result["pair_key_sha256"],
        },
        "initial_source_rule": result["pair_key"].get("initial_source_rule"),
        "scorer": {
            "feature_weights": HARNESS.SAME_CONTAINER_WEIGHTS,
            "different_threshold_grid": list(HARNESS.DIFFERENT_THRESHOLD_GRID),
            "same_threshold_grid": list(HARNESS.SAME_THRESHOLD_GRID),
            "minimum_empirical_margin": HARNESS.MIN_CALIBRATION_SCORE_MARGIN,
            "harness_sha256": sha256_file(Path(HARNESS.__file__)),
        },
        "scored_pairs": result["scored_pairs"],
        "candidate_threshold_metrics": result["candidate_threshold_metrics"],
        "selected_thresholds": selected,
        "empirical_score_margin": calibration.margin,
        "selection_reason": (
            "zero false merge/split, then widest abstention gap on the pre-frozen grid"
            if calibration.status == "FROZEN"
            else "no safe empirical separation; all pairs remain uncertain"
        ),
        "evaluation_asset_accessed": False,
        "r0_run_performed": False,
    }


def _write_sanity_outputs(result: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
    if output_dir.exists():
        raise CalibrationStop(f"calibration sanity output already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    thresholds = result["calibration"].thresholds
    summaries: list[dict[str, Any]] = []
    for asset_id, page in result["pages"].items():
        methods = {
            "B0": HARNESS.run_b0(page),
            "B1": HARNESS.run_b1(page),
            "P1": HARNESS.run_p1(page, thresholds),
        }
        for method_id, association in methods.items():
            path = output_dir / f"{asset_id}-{method_id}.json"
            path.write_text(
                json.dumps(association.to_jsonable(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            summaries.append(
                {
                    "asset_id": asset_id,
                    "method_id": method_id,
                    "relative_path": path.name,
                    "sha256": sha256_file(path),
                    "region_count": len(association.regions),
                    "recommended_decision": association.recommended_decision,
                    "abstention_reasons": list(association.abstention_reasons),
                }
            )
    return summaries


def write_calibration_lock(calibration_root: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise CalibrationStop(f"calibration lock already exists: {output_path}")
    result = score_frozen_pairs(calibration_root)
    payload = _calibration_jsonable(result)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sanity_dir = output_path.parent / "harness-sanity"
    payload["calibration_harness_sanity"] = _write_sanity_outputs(result, sanity_dir)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze P_same_container thresholds on calibration-only assets.")
    parser.add_argument("--calibration-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = write_calibration_lock(args.calibration_root, args.output)
    except (CalibrationStop, HARNESS.HarnessStop) as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
