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
EXPECTED_CALIBRATION_LOCK_SHA256 = "5ad91445bdf8bc29ba1ba3d4c48ac9f6f4838dd06601a3bc5a80310744e1f1cc"
EXPECTED_HARNESS_SHA256 = "bea1d1ee39200b44729936e05aee4f4ebfd0fa71eeec05212d2ec42d66364f11"
EXPECTED_ASSET_IDS = tuple(f"case-{index:02d}" for index in range(1, 7))
R0_RESULTS_RELATIVE_PATH = Path("s1-runs") / EXPECTED_R0_RUN_ID / "results.json"
R0_SPEC_RELATIVE_PATH = Path("S1-INPUT-SPEC.local.json")
SCHEMA_VERSION = "text-seeded-container-r0-matrix-v1"


class MatrixStop(RuntimeError):
    pass


def _load_harness():
    path = Path(__file__).with_name("harness.py")
    name = "text_seeded_container_association_harness_for_r0"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise MatrixStop(f"cannot load harness: {path}")
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
        raise MatrixStop(f"cannot read JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise MatrixStop(f"JSON root must be an object: {path}")
    return payload


def verify_frozen_inputs(r0_root: Path, calibration_lock_path: Path) -> dict[str, Any]:
    root = r0_root.resolve()
    results_path = root / R0_RESULTS_RELATIVE_PATH
    spec_path = root / R0_SPEC_RELATIVE_PATH
    results_hash = sha256_file(results_path)
    spec_hash = sha256_file(spec_path)
    lock_hash = sha256_file(calibration_lock_path)
    harness_hash = sha256_file(Path(HARNESS.__file__))
    if results_hash != EXPECTED_R0_RESULTS_SHA256:
        raise MatrixStop(f"frozen R0 results hash mismatch: {results_hash}")
    if spec_hash != EXPECTED_R0_SPEC_SHA256:
        raise MatrixStop(f"frozen R0 spec hash mismatch: {spec_hash}")
    if lock_hash != EXPECTED_CALIBRATION_LOCK_SHA256:
        raise MatrixStop(f"Goal 2 calibration lock hash mismatch: {lock_hash}")
    if harness_hash != EXPECTED_HARNESS_SHA256:
        raise MatrixStop(f"Goal 2 harness hash mismatch: {harness_hash}")
    results = _load_json(results_path)
    lock = _load_json(calibration_lock_path)
    if results.get("run_id") != EXPECTED_R0_RUN_ID or results.get("input_hashes_unchanged") is not True:
        raise MatrixStop("R0 S1 run identity or source-integrity flag is invalid")
    assets = results.get("assets")
    if not isinstance(assets, list):
        raise MatrixStop("frozen R0 result has no assets")
    asset_ids = [item.get("asset_id") for item in assets]
    if asset_ids != list(EXPECTED_ASSET_IDS):
        raise MatrixStop(f"R0 asset scope mismatch: {asset_ids}")
    if lock.get("status") != "FROZEN":
        raise MatrixStop(f"Goal 2 thresholds are not frozen: {lock.get('status')}")
    selected = lock.get("selected_thresholds", {})
    if selected.get("different") != 0.40 or selected.get("same") != 0.75:
        raise MatrixStop(f"unexpected Goal 2 thresholds: {selected}")
    if selected.get("force_all_uncertain") is not False:
        raise MatrixStop("Goal 2 lock unexpectedly forces all pairs uncertain")
    if lock.get("scorer", {}).get("harness_sha256") != harness_hash:
        raise MatrixStop("calibration lock does not point to the frozen harness")
    for asset in assets:
        asset_id = asset["asset_id"]
        image_path = root / asset["relative_path"]
        if sha256_file(image_path) != asset.get("sha256"):
            raise MatrixStop(f"R0 image hash mismatch: {asset_id}")
    return {
        "r0_root": root,
        "r0_run_id": EXPECTED_R0_RUN_ID,
        "r0_results_path": results_path,
        "r0_results_sha256": results_hash,
        "r0_spec_sha256": spec_hash,
        "calibration_lock_path": calibration_lock_path.resolve(),
        "calibration_lock_sha256": lock_hash,
        "harness_sha256": harness_hash,
        "runner_sha256": sha256_file(Path(__file__)),
        "asset_ids": asset_ids,
        "results": results,
        "thresholds": HARNESS.SameContainerThresholds(0.40, 0.75),
    }


def page_from_asset(root: Path, asset: dict[str, Any]):
    image = np.asarray(Image.open(root / asset["relative_path"]).convert("RGB"), dtype=np.uint8)
    fragment_groups: dict[str, str] = {}
    for group in asset["groups"]:
        for fragment_id in group["ordered_fragment_ids"]:
            if fragment_id in fragment_groups:
                raise MatrixStop(f"fragment appears in multiple S1 groups: {asset['asset_id']}/{fragment_id}")
            fragment_groups[fragment_id] = group["group_id"]
    fragments = []
    for item in asset["fragments"]:
        fragment_id = item["fragment_id"]
        if fragment_id not in fragment_groups:
            raise MatrixStop(f"fragment has no S1 group: {asset['asset_id']}/{fragment_id}")
        bbox = item["bbox"]
        fragments.append(
            HARNESS.Fragment(
                fragment_id=fragment_id,
                bbox=(bbox["x"], bbox["y"], bbox["width"], bbox["height"]),
                polygon=tuple(tuple(point) for point in item["polygon"]),
                upstream_group_id=fragment_groups[fragment_id],
                score=item.get("score"),
            )
        )
    return HARNESS.PageInput(asset_id=asset["asset_id"], image=image, fragments=tuple(fragments))


def run_methods(page, thresholds) -> dict[str, Any]:
    return {
        "B0": HARNESS.run_b0(page),
        "B1": HARNESS.run_b1(page),
        "P1": HARNESS.run_p1(page, thresholds),
    }


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
        [
            (46, 204, 113),
            (241, 196, 15),
            (155, 89, 182),
            (26, 188, 156),
            (230, 126, 34),
            (52, 152, 219),
        ],
        dtype=np.float32,
    )
    for index, region in enumerate(result.regions):
        color = palette[index % len(palette)]
        canvas[region.mask] = 0.72 * canvas[region.mask] + 0.28 * color
        canvas[_mask_boundary(region.mask)] = color
    canvas[result.virtual_boundary] = np.asarray((30, 80, 255), dtype=np.float32)
    image = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), mode="RGB")
    draw = ImageDraw.Draw(image)
    for fragment in page.fragments:
        x, y, width, height = fragment.bbox
        draw.rectangle((x, y, x + width - 1, y + height - 1), outline=(255, 30, 30), width=2)
    label = f"{page.asset_id} {result.method_id} {result.recommended_decision} regions={len(result.regions)}"
    text_box = draw.textbbox((4, 4), label)
    draw.rectangle((2, 2, text_box[2] + 6, text_box[3] + 6), fill=(255, 255, 255))
    draw.text((4, 4), label, fill=(0, 0, 0))
    return image


def write_page_output(output_root: Path, page, result) -> dict[str, Any]:
    result_path = output_root / "results" / f"{page.asset_id}-{result.method_id}.json"
    overlay_path = output_root / "overlays" / f"{page.asset_id}-{result.method_id}.png"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(result.to_jsonable(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    render_overlay(page, result).save(overlay_path)
    return {
        "asset_id": page.asset_id,
        "method_id": result.method_id,
        "result_relative_path": result_path.relative_to(output_root).as_posix(),
        "result_sha256": sha256_file(result_path),
        "overlay_relative_path": overlay_path.relative_to(output_root).as_posix(),
        "overlay_sha256": sha256_file(overlay_path),
        "region_count": len(result.regions),
        "recommended_decision": result.recommended_decision,
        "abstention_reasons": list(result.abstention_reasons),
    }


def write_matrix(r0_root: Path, calibration_lock_path: Path, output_dir: Path) -> dict[str, Any]:
    partial_dir = output_dir.with_name(output_dir.name + ".partial")
    if output_dir.exists() or partial_dir.exists():
        raise MatrixStop(f"R0 matrix output already exists: {output_dir} or {partial_dir}")
    verified = verify_frozen_inputs(r0_root, calibration_lock_path)
    partial_dir.mkdir(parents=True)
    outputs: list[dict[str, Any]] = []
    for asset in verified["results"]["assets"]:
        page = page_from_asset(verified["r0_root"], asset)
        for result in run_methods(page, verified["thresholds"]).values():
            outputs.append(write_page_output(partial_dir, page, result))
    hashes_after = {
        asset["asset_id"]: sha256_file(verified["r0_root"] / asset["relative_path"])
        for asset in verified["results"]["assets"]
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": "goal3-r0-v0.1",
        "status": "completed",
        "provenance": {
            "r0_s1_run_id": verified["r0_run_id"],
            "r0_results_sha256": verified["r0_results_sha256"],
            "r0_spec_sha256": verified["r0_spec_sha256"],
            "calibration_lock_sha256": verified["calibration_lock_sha256"],
            "harness_sha256": verified["harness_sha256"],
            "runner_sha256": verified["runner_sha256"],
            "thresholds": {"different": 0.40, "same": 0.75},
        },
        "asset_ids": verified["asset_ids"],
        "method_ids": ["B0", "B1", "P1"],
        "outputs": outputs,
        "source_hashes_after": hashes_after,
        "source_hashes_unchanged": all(
            hashes_after[asset["asset_id"]] == asset["sha256"]
            for asset in verified["results"]["assets"]
        ),
        "ground_truth_accessed": False,
        "parameter_updates_after_r0": False,
        "cleaning_performed": False,
    }
    matrix_path = partial_dir / "matrix.json"
    matrix_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    partial_dir.replace(output_dir)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the frozen R0 B0/B1/P1 matrix exactly once.")
    parser.add_argument("--r0-root", required=True, type=Path)
    parser.add_argument("--calibration-lock", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = write_matrix(args.r0_root, args.calibration_lock, args.output_dir)
    except (MatrixStop, HARNESS.HarnessStop) as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
