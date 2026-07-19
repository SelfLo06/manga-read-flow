#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


EXPECTED_R0_RUN_ID = "20260715T075811Z-3e9711"
EXPECTED_R0_RESULTS_SHA256 = "33f1061aac43e5b4ca4b86d66c8aec262d19eb33151a965aaf81e656d406da0a"
EXPECTED_R0_SPEC_SHA256 = "95d7d627eefb2b8d7c119364c6e362528848399e5b06a6de7f3c28a1bd7995e7"
EXPECTED_CALIBRATION_LOCK_SHA256 = "2daf93a246b971e36c59b6cdde182b91927d16673843e2098cca25fe9c30248c"
EXPECTED_FOCUSED_CORRECTION_SHA256 = "585c88828b53809fd3f6bdd2e0cdacc4701f733ec7333ee8224c26b002280bf4"
EXPECTED_BASE_HARNESS_SHA256 = "bea1d1ee39200b44729936e05aee4f4ebfd0fa71eeec05212d2ec42d66364f11"
EXPECTED_ASSET_IDS = tuple(f"case-{index:02d}" for index in range(1, 7))
R0_RESULTS_RELATIVE_PATH = Path("s1-runs") / EXPECTED_R0_RUN_ID / "results.json"
R0_SPEC_RELATIVE_PATH = Path("S1-INPUT-SPEC.local.json")
SCHEMA_VERSION = "text-seeded-container-goal4-r0-v1"


class R0Stop(RuntimeError):
    pass


def _load_focused_correction():
    path = Path(__file__).with_name("focused_correction.py")
    name = "text_seeded_container_focused_correction_for_goal4_r0"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise R0Stop(f"cannot load focused correction module: {path}")
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
        raise R0Stop(f"cannot read JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise R0Stop(f"JSON root must be an object: {path}")
    return payload


def _policy_from_lock(lock: dict[str, Any]):
    selected = lock.get("support_search", {}).get("selected", {})
    if selected.get("passed") is not True:
        raise R0Stop("calibration lock has no passing selected policy")
    raw = selected.get("policy")
    if not isinstance(raw, dict):
        raise R0Stop("calibration lock selected policy is missing")
    thresholds = raw.get("thresholds", {})
    expected = {
        "different": 0.30,
        "same": 0.85,
        "max_geodesic_cost": 12.0,
        "support_padding_scale": 0.25,
        "max_support_area_ratio": 0.20,
        "max_merged_support_area_ratio": 0.35,
        "regionless_uncertain_orientation": True,
        "regionless_extreme_span_ratio": 0.90,
        "regionless_seed_bbox_area_ratio": 0.20,
    }
    actual = {name: raw.get(name) for name in expected if name not in {"different", "same"}}
    actual.update({"different": thresholds.get("different"), "same": thresholds.get("same")})
    if actual != expected or thresholds.get("force_all_uncertain") is not False:
        raise R0Stop(f"unexpected frozen policy: {actual}")
    return FOCUSED.CorrectedP1Policy(
        thresholds=FOCUSED.SameContainerThresholds(0.30, 0.85),
        max_geodesic_cost=12.0,
        support_padding_scale=0.25,
        max_support_area_ratio=0.20,
        max_merged_support_area_ratio=0.35,
        regionless_uncertain_orientation=True,
        regionless_extreme_span_ratio=0.90,
        regionless_seed_bbox_area_ratio=0.20,
    )


def verify_inputs(r0_root: Path, calibration_lock_path: Path) -> dict[str, Any]:
    root = r0_root.resolve()
    results_path = root / R0_RESULTS_RELATIVE_PATH
    spec_path = root / R0_SPEC_RELATIVE_PATH
    hashes = {
        "r0_results": sha256_file(results_path),
        "r0_spec": sha256_file(spec_path),
        "calibration_lock": sha256_file(calibration_lock_path),
        "focused_correction": sha256_file(Path(FOCUSED.__file__)),
        "base_harness": sha256_file(Path(FOCUSED.BASE.__file__)),
        "runner": sha256_file(Path(__file__)),
    }
    expected = {
        "r0_results": EXPECTED_R0_RESULTS_SHA256,
        "r0_spec": EXPECTED_R0_SPEC_SHA256,
        "calibration_lock": EXPECTED_CALIBRATION_LOCK_SHA256,
        "focused_correction": EXPECTED_FOCUSED_CORRECTION_SHA256,
        "base_harness": EXPECTED_BASE_HARNESS_SHA256,
    }
    for name, value in expected.items():
        if hashes[name] != value:
            raise R0Stop(f"frozen {name} hash mismatch: {hashes[name]}")
    results = _load_json(results_path)
    lock = _load_json(calibration_lock_path)
    if results.get("run_id") != EXPECTED_R0_RUN_ID or results.get("input_hashes_unchanged") is not True:
        raise R0Stop("R0 S1 identity or source-integrity flag is invalid")
    assets = results.get("assets")
    if not isinstance(assets, list) or [item.get("asset_id") for item in assets] != list(EXPECTED_ASSET_IDS):
        raise R0Stop("R0 asset scope mismatch")
    if lock.get("status") != "FROZEN":
        raise R0Stop("Goal 4 calibration lock is not frozen")
    lock_hashes = lock.get("input", {}).get("hashes", {})
    if lock.get("input", {}).get("r0_asset_accessed") is not False:
        raise R0Stop("calibration lock reports R0 access")
    if lock_hashes.get("focused_correction") != hashes["focused_correction"]:
        raise R0Stop("calibration lock points to another correction module")
    if lock_hashes.get("base_harness") != hashes["base_harness"]:
        raise R0Stop("calibration lock points to another base harness")
    policy = _policy_from_lock(lock)
    for asset in assets:
        if sha256_file(root / asset["relative_path"]) != asset.get("sha256"):
            raise R0Stop(f"R0 image hash mismatch: {asset['asset_id']}")
    return {
        "root": root,
        "results": results,
        "policy": policy,
        "hashes": hashes,
    }


def page_from_asset(root: Path, asset: dict[str, Any]):
    image = np.asarray(Image.open(root / asset["relative_path"]).convert("RGB"), dtype=np.uint8)
    fragment_groups = {
        fragment_id: group["group_id"]
        for group in asset["groups"]
        for fragment_id in group["ordered_fragment_ids"]
    }
    fragments = []
    for item in asset["fragments"]:
        fragment_id = item["fragment_id"]
        if fragment_id not in fragment_groups:
            raise R0Stop(f"fragment has no frozen S1 group: {asset['asset_id']}/{fragment_id}")
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


def _mask_boundary(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    eroded = np.ones_like(mask)
    for dy in range(3):
        for dx in range(3):
            eroded &= padded[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
    return mask & ~eroded


def render_overlay(page, result) -> Image.Image:
    canvas = page.image.astype(np.float32).copy()
    palette = np.asarray(
        [(46, 204, 113), (241, 196, 15), (155, 89, 182), (26, 188, 156)],
        dtype=np.float32,
    )
    for index, region in enumerate(result.regions):
        if region.mask is None:
            continue
        color = palette[index % len(palette)]
        canvas[region.mask] = 0.72 * canvas[region.mask] + 0.28 * color
        canvas[_mask_boundary(region.mask)] = color
    canvas[result.virtual_boundary] = np.asarray((30, 80, 255), dtype=np.float32)
    image = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), mode="RGB")
    draw = ImageDraw.Draw(image)
    for fragment in page.fragments:
        x, y, width, height = fragment.bbox
        draw.rectangle((x, y, x + width - 1, y + height - 1), outline=(255, 30, 30), width=2)
    null_count = sum(region.mask is None for region in result.regions)
    label = (
        f"{page.asset_id} {result.method_id} {result.recommended_decision} "
        f"regions={len(result.regions)} null={null_count}"
    )
    text_box = draw.textbbox((4, 4), label)
    draw.rectangle((2, 2, text_box[2] + 6, text_box[3] + 6), fill=(255, 255, 255))
    draw.text((4, 4), label, fill=(0, 0, 0))
    return image


def run_once(r0_root: Path, calibration_lock_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise R0Stop(f"Goal 4 R0 output already exists: {output_dir}")
    verified = verify_inputs(r0_root, calibration_lock_path)
    output_dir.mkdir(parents=True)
    (output_dir / "results").mkdir()
    (output_dir / "overlays").mkdir()
    outputs = []
    for asset in verified["results"]["assets"]:
        page = page_from_asset(verified["root"], asset)
        result = FOCUSED.run_corrected_p1(page, verified["policy"])
        result_path = output_dir / "results" / f"{page.asset_id}-P1-corrected-v1.json"
        overlay_path = output_dir / "overlays" / f"{page.asset_id}-P1-corrected-v1.png"
        result_path.write_text(
            json.dumps(result.to_jsonable(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        render_overlay(page, result).save(overlay_path)
        outputs.append(
            {
                "asset_id": page.asset_id,
                "method_id": result.method_id,
                "result_relative_path": result_path.relative_to(output_dir).as_posix(),
                "result_sha256": sha256_file(result_path),
                "overlay_relative_path": overlay_path.relative_to(output_dir).as_posix(),
                "overlay_sha256": sha256_file(overlay_path),
                "region_count": len(result.regions),
                "nonnull_region_count": sum(region.mask is not None for region in result.regions),
                "recommended_decision": result.recommended_decision,
                "abstention_reasons": list(result.abstention_reasons),
            }
        )
    source_hashes_after = {
        asset["asset_id"]: sha256_file(verified["root"] / asset["relative_path"])
        for asset in verified["results"]["assets"]
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": "goal4-r0-corrected-v0.1",
        "status": "completed",
        "provenance": verified["hashes"],
        "asset_ids": list(EXPECTED_ASSET_IDS),
        "method_ids": ["P1-corrected-v1"],
        "outputs": outputs,
        "source_hashes_after": source_hashes_after,
        "source_hashes_unchanged": all(
            source_hashes_after[asset["asset_id"]] == asset["sha256"]
            for asset in verified["results"]["assets"]
        ),
        "ground_truth_accessed": False,
        "evaluator_contract_accessed": False,
        "parameter_updates_after_r0": False,
        "cleaning_performed": False,
    }
    matrix_path = output_dir / "matrix.json"
    matrix_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run corrected P1 on frozen R0 exactly once.")
    parser.add_argument("--r0-root", required=True, type=Path)
    parser.add_argument("--calibration-lock", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = run_once(args.r0_root, args.calibration_lock, args.output_dir)
    except (R0Stop, FOCUSED.HarnessStop) as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
