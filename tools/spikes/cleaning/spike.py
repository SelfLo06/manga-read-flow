#!/usr/bin/env python3
"""Local-only Cleaning Real Tool Spike; never touches production artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[3]
CLEANING_DIR = ROOT / "local_samples" / "cleaning"
MANIFEST_PATH = CLEANING_DIR / "manifest.json"
OUTPUT_ROOT = ROOT / "local_samples" / "spike_outputs" / "cleaning"
RATINGS_PATH = CLEANING_DIR / "ratings" / "ratings.csv"
DECISIONS_PATH = CLEANING_DIR / "ratings" / "manual_decisions.json"
FILL_METHODS = ("fixed_white", "border_sampled_fill")
INPAINT_METHODS = ("telea", "navier_stokes")
RATING_VALUES = {"ACCEPTABLE", "REVIEW", "UNUSABLE"}
POLICIES = {"AUTO_FILL", "AUTO_INPAINT", "REVIEW_REQUIRED", "SKIP"}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def inside_root(path: Path) -> Path:
    resolved = path.resolve()
    if resolved != ROOT and ROOT not in resolved.parents:
        raise ValueError(f"path escapes repository: {path}")
    return resolved


def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema_version") != "1.0" or not isinstance(manifest.get("fixtures"), list):
        raise ValueError("invalid cleaning manifest schema")
    return manifest


def source_path(fixture: dict[str, Any]) -> Path:
    return inside_root(CLEANING_DIR / fixture["source_image"])


def mask_path(fixture: dict[str, Any]) -> Path:
    return inside_root(CLEANING_DIR / fixture["mask_image"])


def image_bgr(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot read image: {path}")
    return image


def binary_mask(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"cannot read mask: {path}")
    return (image > 0).astype(np.uint8) * 255


def rect_to_bounds(rect: list[int]) -> tuple[int, int, int, int]:
    x, y, width, height = rect
    return x, y, x + width, y + height


def validate_fixture(fixture: dict[str, Any], require_mask: bool = True) -> dict[str, Any]:
    required = {"fixture_id", "source_image", "mask_image", "region_bbox", "scenario", "expected_policy", "evaluation_tags", "source_kind"}
    missing = required - fixture.keys()
    if missing:
        raise ValueError(f"{fixture.get('fixture_id', '<unknown>')} missing {sorted(missing)}")
    if fixture["expected_policy"] not in POLICIES:
        raise ValueError(f"invalid expected policy: {fixture['expected_policy']}")
    if fixture["source_kind"] not in {"real", "synthetic"}:
        raise ValueError("source_kind must be real or synthetic")
    src = source_path(fixture)
    if not src.is_file():
        raise ValueError(f"missing source: {src}")
    source = image_bgr(src)
    height, width = source.shape[:2]
    bbox = fixture["region_bbox"]
    if set(bbox) != {"x", "y", "width", "height"}:
        raise ValueError(f"invalid bbox fields for {fixture['fixture_id']}")
    x, y, box_width, box_height = (bbox[key] for key in ("x", "y", "width", "height"))
    if min(x, y, box_width, box_height) < 0 or box_width == 0 or box_height == 0 or x + box_width > width or y + box_height > height:
        raise ValueError(f"invalid bbox for {fixture['fixture_id']}")
    info = {"source_hash": sha256_path(src), "width": width, "height": height}
    if require_mask:
        mask_file = mask_path(fixture)
        if not mask_file.is_file():
            raise ValueError(f"missing mask: {mask_file}")
        mask = binary_mask(mask_file)
        if mask.shape != source.shape[:2]:
            raise ValueError(f"mask dimensions mismatch: {fixture['fixture_id']}")
        active = mask > 0
        if not active.any():
            raise ValueError(f"empty mask: {fixture['fixture_id']}")
        yy, xx = np.where(active)
        if xx.min() < x or yy.min() < y or xx.max() >= x + box_width or yy.max() >= y + box_height:
            raise ValueError(f"mask outside region bbox: {fixture['fixture_id']}")
        info["mask_hash"] = sha256_path(mask_file)
        info["masked_pixel_count"] = int(active.sum())
    return info


def prepare_masks() -> None:
    manifest = load_manifest()
    masks_dir = CLEANING_DIR / "masks"
    if manifest.get("freeze", {}).get("state") == "FROZEN":
        raise ValueError("manifest already frozen; masks must not be regenerated")
    masks_dir.mkdir(parents=True, exist_ok=True)
    for fixture in manifest["fixtures"]:
        source = image_bgr(source_path(fixture))
        height, width = source.shape[:2]
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        for rect in fixture.get("mask_rectangles", []):
            x1, y1, x2, y2 = rect_to_bounds(rect)
            draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=255)
        target = mask_path(fixture)
        target.parent.mkdir(parents=True, exist_ok=True)
        mask.save(target, format="PNG")
    print(f"prepared {len(manifest['fixtures'])} oracle masks")


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def freeze_inputs() -> None:
    manifest = load_manifest()
    if manifest.get("freeze", {}).get("state") == "FROZEN":
        raise ValueError("inputs already frozen")
    records = {fixture["fixture_id"]: validate_fixture(fixture) for fixture in manifest["fixtures"]}
    fixture_hash = canonical_hash(manifest["fixtures"])
    source_hashes = {fixture_id: record["source_hash"] for fixture_id, record in records.items()}
    mask_hashes = {fixture_id: record["mask_hash"] for fixture_id, record in records.items()}
    manifest["freeze"] = {
        "state": "FROZEN",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head(),
        "fixture_set_sha256": fixture_hash,
        "source_hashes": source_hashes,
        "mask_hashes": mask_hashes,
        "mask_set_sha256": canonical_hash(mask_hashes),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"frozen fixture set {fixture_hash}")


def supersede_mask_freeze() -> None:
    """Preserve a pre-verdict run's masks before correcting a visually invalid mask."""
    manifest = load_manifest()
    freeze = manifest.get("freeze", {})
    if freeze.get("state") != "FROZEN":
        raise ValueError("only a frozen input set can be superseded")
    old_id = freeze.get("fixture_set_sha256", "unknown")[:12]
    archive = CLEANING_DIR / "masks_history" / old_id
    if archive.exists():
        raise ValueError(f"mask archive already exists: {archive}")
    shutil.copytree(CLEANING_DIR / "masks", archive)
    history = manifest.setdefault("freeze_history", [])
    history.append({"state": "SUPERSEDED_BEFORE_VERDICT", "reason": "visual mask undercoverage found before verdict", "freeze": freeze, "mask_archive": str(archive.relative_to(CLEANING_DIR))})
    manifest["freeze"] = {"state": "PREPARED_NOT_FROZEN", "supersedes": old_id}
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"archived pre-correction masks to {archive.relative_to(ROOT)}")


def frozen_records(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    freeze = manifest.get("freeze", {})
    if freeze.get("state") != "FROZEN":
        raise ValueError("run requires frozen manifest and masks")
    records = {fixture["fixture_id"]: validate_fixture(fixture) for fixture in manifest["fixtures"]}
    if canonical_hash(manifest["fixtures"]) != freeze.get("fixture_set_sha256"):
        raise ValueError("fixture set changed after freeze")
    if {key: value["source_hash"] for key, value in records.items()} != freeze.get("source_hashes"):
        raise ValueError("source changed after freeze")
    if {key: value["mask_hash"] for key, value in records.items()} != freeze.get("mask_hashes"):
        raise ValueError("mask changed after freeze")
    return records


def validate() -> None:
    manifest = load_manifest()
    ids = [fixture["fixture_id"] for fixture in manifest["fixtures"]]
    if len(ids) != 10 or len(set(ids)) != len(ids):
        raise ValueError("manifest must contain exactly 10 unique core fixtures")
    policies = Counter(fixture["expected_policy"] for fixture in manifest["fixtures"])
    if policies["AUTO_FILL"] != 4 or policies["AUTO_INPAINT"] != 3 or policies["REVIEW_REQUIRED"] + policies["SKIP"] != 3:
        raise ValueError("fixture policy distribution must be 4 fill / 3 inpaint / 3 review-skip")
    if sum(fixture["source_kind"] == "real" for fixture in manifest["fixtures"]) < 3:
        raise ValueError("at least three fixtures must use real samples")
    records = frozen_records(manifest)
    print(json.dumps({"valid": True, "fixture_count": len(records), "freeze": manifest["freeze"]}, ensure_ascii=False, indent=2))


def rgb(image: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def crop(image: np.ndarray, bbox: dict[str, int], padding: int = 16) -> np.ndarray:
    x, y, width, height = (bbox[key] for key in ("x", "y", "width", "height"))
    top, left = max(0, y - padding), max(0, x - padding)
    bottom, right = min(image.shape[0], y + height + padding), min(image.shape[1], x + width + padding)
    return image[top:bottom, left:right]


def preview() -> None:
    manifest = load_manifest()
    frozen_records(manifest)
    target_dir = CLEANING_DIR / "previews"
    target_dir.mkdir(parents=True, exist_ok=True)
    for fixture in manifest["fixtures"]:
        source = image_bgr(source_path(fixture))
        mask = binary_mask(mask_path(fixture))
        overlay = source.copy()
        overlay[mask > 0] = (0, 0, 255)
        overlay = cv2.addWeighted(source, 0.65, overlay, 0.35, 0)
        bbox = fixture["region_bbox"]
        x, y, width, height = (bbox[key] for key in ("x", "y", "width", "height"))
        cv2.rectangle(overlay, (x, y), (x + width, y + height), (0, 255, 0), 2)
        full = rgb(overlay)
        region = rgb(crop(overlay, bbox, 24))
        canvas = Image.new("RGB", (full.width + region.width, max(full.height, region.height)), "white")
        canvas.paste(full, (0, 0))
        canvas.paste(region, (full.width, 0))
        canvas.save(target_dir / f"{fixture['fixture_id']}.png")
    print(f"wrote previews to {target_dir.relative_to(ROOT)}")


def dilate(mask: np.ndarray, pixels: int) -> np.ndarray:
    if pixels == 0:
        return mask
    return cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=pixels)


def border_color(source: np.ndarray, mask: np.ndarray) -> tuple[int, int, int]:
    ring = (cv2.dilate(mask, np.ones((7, 7), np.uint8), iterations=1) > 0) & (mask == 0)
    samples = source[ring]
    if samples.size == 0:
        samples = source.reshape(-1, 3)
    median = np.median(samples, axis=0).astype(np.uint8)
    return int(median[0]), int(median[1]), int(median[2])


def clean(source: np.ndarray, mask: np.ndarray, method: str, radius: int | None) -> np.ndarray:
    if method == "fixed_white":
        output = source.copy()
        output[mask > 0] = (255, 255, 255)
        return output
    if method == "border_sampled_fill":
        output = source.copy()
        output[mask > 0] = border_color(source, mask)
        return output
    if method == "telea":
        return cv2.inpaint(source, mask, float(radius), cv2.INPAINT_TELEA)
    if method == "navier_stokes":
        return cv2.inpaint(source, mask, float(radius), cv2.INPAINT_NS)
    raise ValueError(f"unsupported method: {method}")


def metrics(source: np.ndarray, output: np.ndarray, active_mask: np.ndarray) -> dict[str, Any]:
    active = active_mask > 0
    changed = np.any(source != output, axis=2)
    outside = changed & ~active
    boundary = (cv2.dilate(active_mask, np.ones((3, 3), np.uint8), iterations=1) > 0) & ~active
    return {
        "masked_pixel_count": int(active.sum()),
        "changed_inside_mask": int((changed & active).sum()),
        "changed_outside_mask": int(outside.sum()),
        "outside_mask_change_ratio": float(outside.sum() / max(1, (~active).sum())),
        "boundary_change_ratio": float((changed & boundary).sum() / max(1, boundary.sum())),
    }


def candidate_id(fixture_id: str, method: str, radius: int | None, dilation_px: int) -> str:
    radius_value = "na" if radius is None else str(radius)
    return f"{fixture_id}__{method}__r{radius_value}__d{dilation_px}"


def run_candidate(run_dir: Path, fixture: dict[str, Any], source_info: dict[str, Any], method: str, radius: int | None, dilation_px: int, comparison_only: bool = False) -> dict[str, Any]:
    source = image_bgr(source_path(fixture))
    mask = dilate(binary_mask(mask_path(fixture)), dilation_px)
    started = time.perf_counter()
    output = clean(source, mask, method, radius)
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    candidate = candidate_id(fixture["fixture_id"], method, radius, dilation_px)
    output_path = run_dir / "candidates" / f"{candidate}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), output):
        raise ValueError(f"cannot write output: {output_path}")
    return {
        "candidate_id": candidate,
        "fixture_id": fixture["fixture_id"],
        "method": method,
        "radius": radius,
        "dilation": dilation_px,
        "comparison_only": comparison_only,
        "source_hash": source_info["source_hash"],
        "mask_hash": source_info["mask_hash"],
        "output_hash": sha256_path(output_path),
        "processing_time_ms": elapsed,
        "output_path": str(output_path.relative_to(ROOT)),
        "error": None,
        **metrics(source, output, mask),
    }


def contact_sheet(run_dir: Path, fixture: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    source = image_bgr(source_path(fixture))
    mask = binary_mask(mask_path(fixture))
    source_crop = crop(source, fixture["region_bbox"])
    overlay = source.copy()
    overlay[mask > 0] = (0, 0, 255)
    overlay = cv2.addWeighted(source, 0.65, overlay, 0.35, 0)
    tiles: list[tuple[str, Image.Image]] = [("source", rgb(source_crop)), ("oracle mask", rgb(crop(overlay, fixture["region_bbox"]))) ]
    for candidate in candidates:
        output = image_bgr(ROOT / candidate["output_path"])
        label = f"{candidate['method']} r{candidate['radius']} d{candidate['dilation']}"
        tiles.append((label, rgb(crop(output, fixture["region_bbox"]))))
    tile_width, tile_height = 220, 160
    columns = 4
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile_width, rows * (tile_height + 24)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, tile) in enumerate(tiles):
        tile.thumbnail((tile_width - 8, tile_height - 8))
        x = (index % columns) * tile_width + 4
        y = (index // columns) * (tile_height + 24) + 20
        sheet.paste(tile, (x, y))
        draw.text((x, y - 17), label, fill="black")
    path = run_dir / "comparisons" / f"{fixture['fixture_id']}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def write_rating_template(results: list[dict[str, Any]]) -> None:
    RATINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RATINGS_PATH.open("w", newline="", encoding="utf-8") as handle:
        fields = ["candidate_id", "fixture_id", "method", "radius", "dilation", "rating", "policy", "failure_tags", "review_note"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow({
                "candidate_id": result["candidate_id"], "fixture_id": result["fixture_id"], "method": result["method"],
                "radius": "" if result["radius"] is None else result["radius"], "dilation": result["dilation"],
                "rating": "PENDING", "policy": "", "failure_tags": "", "review_note": "awaiting visual review",
            })


def run() -> None:
    manifest = load_manifest()
    records = frozen_records(manifest)
    seed = canonical_hash({"freeze": manifest["freeze"], "matrix": {"fill": [0, 1], "inpaint": [0, 1, 2]}})[:6]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + seed
    run_dir = OUTPUT_ROOT / run_id
    if run_dir.exists():
        raise ValueError(f"run directory exists: {run_dir}")
    run_dir.mkdir(parents=True)
    results: list[dict[str, Any]] = []
    skip_records: list[dict[str, Any]] = []
    for fixture in manifest["fixtures"]:
        policy = fixture["expected_policy"]
        if policy in {"REVIEW_REQUIRED", "SKIP"}:
            skip_records.append({
                "fixture_id": fixture["fixture_id"], "expected_policy": policy, "status": "SKIPPED_NO_ACCEPTABLE_CANDIDATE",
                "risk_tags": fixture["evaluation_tags"], "skip_reason": fixture["scenario"], "source_hash": records[fixture["fixture_id"]]["source_hash"],
                "mask_hash": records[fixture["fixture_id"]]["mask_hash"],
            })
            contact_sheet(run_dir, fixture, [])
            continue
        fixture_results: list[dict[str, Any]] = []
        if policy == "AUTO_FILL":
            for method in FILL_METHODS:
                for dilation_px in (0, 1):
                    fixture_results.append(run_candidate(run_dir, fixture, records[fixture["fixture_id"]], method, None, dilation_px))
        else:
            for method in FILL_METHODS:
                fixture_results.append(run_candidate(run_dir, fixture, records[fixture["fixture_id"]], method, None, 0, comparison_only=True))
            for method in INPAINT_METHODS:
                for radius in (2, 3, 5):
                    for dilation_px in (0, 1, 2):
                        fixture_results.append(run_candidate(run_dir, fixture, records[fixture["fixture_id"]], method, radius, dilation_px))
        results.extend(fixture_results)
        contact_sheet(run_dir, fixture, fixture_results)
    metadata = {
        "run_id": run_id, "git_head": git_head(), "created_at": datetime.now(timezone.utc).isoformat(),
        "opencv_version": cv2.__version__, "pillow_version": Image.__version__, "python": sys.version,
        "platform": platform.platform(), "manifest_sha256": sha256_path(MANIFEST_PATH), "freeze": manifest["freeze"],
        "matrix": {"fill": {"dilation": [0, 1]}, "inpaint": {"methods": list(INPAINT_METHODS), "radius": [2, 3, 5], "dilation": [0, 1, 2]}},
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run_dir / "results.json").write_text(json.dumps({"run_id": run_id, "candidates": results, "skipped": skip_records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_rating_template(results)
    (CLEANING_DIR / "ratings" / "run_id.txt").write_text(run_id + "\n", encoding="utf-8")
    print(json.dumps({"run_id": run_id, "candidate_count": len(results), "skipped": len(skip_records), "run_dir": str(run_dir.relative_to(ROOT))}, ensure_ascii=False))


def latest_run_dir() -> Path:
    run_id_file = CLEANING_DIR / "ratings" / "run_id.txt"
    if not run_id_file.is_file():
        raise ValueError("no cleaning run recorded")
    return inside_root(OUTPUT_ROOT / run_id_file.read_text(encoding="utf-8").strip())


def load_results(run_dir: Path) -> dict[str, Any]:
    with (run_dir / "results.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def verify() -> None:
    manifest = load_manifest()
    records = frozen_records(manifest)
    run_dir = latest_run_dir()
    data = load_results(run_dir)
    fixture_map = {fixture["fixture_id"]: fixture for fixture in manifest["fixtures"]}
    for candidate in data["candidates"]:
        fixture = fixture_map[candidate["fixture_id"]]
        output = inside_root(ROOT / candidate["output_path"])
        if not output.is_file() or sha256_path(output) != candidate["output_hash"]:
            raise ValueError(f"missing or changed output: {candidate['candidate_id']}")
        if image_bgr(output).shape != image_bgr(source_path(fixture)).shape:
            raise ValueError(f"output dimensions mismatch: {candidate['candidate_id']}")
        if candidate["source_hash"] != records[candidate["fixture_id"]]["source_hash"] or candidate["mask_hash"] != records[candidate["fixture_id"]]["mask_hash"]:
            raise ValueError(f"provenance mismatch: {candidate['candidate_id']}")
        if fixture["expected_policy"] in {"REVIEW_REQUIRED", "SKIP"}:
            raise ValueError("dangerous fixture generated a candidate")
    if len(data["skipped"]) != 3:
        raise ValueError("expected exactly three skipped/review fixtures")
    print(json.dumps({"verified": True, "run_id": data["run_id"], "candidate_count": len(data["candidates"]), "source_hashes_unchanged": True}, ensure_ascii=False))


def apply_ratings() -> None:
    if not DECISIONS_PATH.is_file():
        raise ValueError("manual_decisions.json is required after visual review")
    raw_decisions = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    run_dir = latest_run_dir()
    candidates = {candidate["candidate_id"]: candidate for candidate in load_results(run_dir)["candidates"]}
    if "fixture_defaults" in raw_decisions:
        defaults = raw_decisions["fixture_defaults"]
        overrides = raw_decisions.get("overrides", {})
        decisions = {}
        for candidate_id, candidate in candidates.items():
            if candidate["fixture_id"] not in defaults:
                raise ValueError(f"missing manual fixture decision: {candidate['fixture_id']}")
            decision = {**defaults[candidate["fixture_id"]], **overrides.get(candidate_id, {})}
            decisions[candidate_id] = decision
        extra = set(overrides) - set(candidates)
        if extra:
            raise ValueError(f"unknown rating overrides: {sorted(extra)}")
    else:
        decisions = raw_decisions
        if set(decisions) != set(candidates):
            missing, extra = set(candidates) - set(decisions), set(decisions) - set(candidates)
            raise ValueError(f"rating decisions mismatch; missing={len(missing)} extra={len(extra)}")
    with RATINGS_PATH.open("w", newline="", encoding="utf-8") as handle:
        fields = ["candidate_id", "fixture_id", "method", "radius", "dilation", "rating", "policy", "failure_tags", "review_note"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for candidate_id in sorted(candidates):
            candidate, decision = candidates[candidate_id], decisions[candidate_id]
            if decision["rating"] not in RATING_VALUES or decision["policy"] not in POLICIES:
                raise ValueError(f"invalid rating decision: {candidate_id}")
            writer.writerow({
                "candidate_id": candidate_id, "fixture_id": candidate["fixture_id"], "method": candidate["method"],
                "radius": "" if candidate["radius"] is None else candidate["radius"], "dilation": candidate["dilation"],
                **decision,
            })
    print(f"applied {len(decisions)} reviewed ratings")


def ratings_by_candidate() -> dict[str, dict[str, str]]:
    if not RATINGS_PATH.is_file():
        raise ValueError("ratings.csv missing")
    with RATINGS_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or any(row["rating"] not in RATING_VALUES for row in rows):
        raise ValueError("all candidates require completed visual ratings")
    return {row["candidate_id"]: row for row in rows}


def summarize() -> None:
    manifest = load_manifest()
    frozen_records(manifest)
    run_dir = latest_run_dir()
    data, ratings = load_results(run_dir), ratings_by_candidate()
    if {candidate["candidate_id"] for candidate in data["candidates"]} != set(ratings):
        raise ValueError("ratings do not cover all candidates")
    method_summary: dict[str, Counter[str]] = defaultdict(Counter)
    failures: Counter[str] = Counter()
    fixture_decisions: list[dict[str, Any]] = []
    rank = {"ACCEPTABLE": 0, "REVIEW": 1, "UNUSABLE": 2}
    fixture_map = {fixture["fixture_id"]: fixture for fixture in manifest["fixtures"]}
    by_fixture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in data["candidates"]:
        rating = ratings[candidate["candidate_id"]]
        candidate["review"] = rating
        method_summary[candidate["method"]][rating["rating"]] += 1
        for tag in filter(None, rating["failure_tags"].split(";")):
            failures[tag] += 1
        by_fixture[candidate["fixture_id"]].append(candidate)
    for fixture in manifest["fixtures"]:
        policy = fixture["expected_policy"]
        if policy in {"REVIEW_REQUIRED", "SKIP"}:
            fixture_decisions.append({"fixture_id": fixture["fixture_id"], "best_candidate": None, "rating": "REVIEW", "final_policy": policy, "reason": "risk fixture intentionally generated no acceptable candidate"})
            failures["unsafe_to_clean"] += 1
            continue
        formal = [candidate for candidate in by_fixture[fixture["fixture_id"]] if not candidate["comparison_only"]]
        best = min(formal, key=lambda candidate: (rank[candidate["review"]["rating"]], candidate["processing_time_ms"]))
        final_policy = policy if best["review"]["rating"] == "ACCEPTABLE" else "REVIEW_REQUIRED"
        fixture_decisions.append({"fixture_id": fixture["fixture_id"], "best_candidate": best["candidate_id"], "rating": best["review"]["rating"], "final_policy": final_policy, "reason": best["review"]["review_note"]})
    fill_decisions = [decision for decision in fixture_decisions if fixture_map[decision["fixture_id"]]["expected_policy"] == "AUTO_FILL"]
    inpaint_decisions = [decision for decision in fixture_decisions if fixture_map[decision["fixture_id"]]["expected_policy"] == "AUTO_INPAINT"]
    fill_ok = sum(decision["rating"] == "ACCEPTABLE" for decision in fill_decisions) >= 4
    inpaint_supported = sum(decision["rating"] in {"ACCEPTABLE", "REVIEW"} for decision in inpaint_decisions) >= 2
    inpaint_better_than_fill = False
    for fixture_id, candidates in by_fixture.items():
        fixture = fixture_map[fixture_id]
        if fixture["expected_policy"] != "AUTO_INPAINT":
            continue
        formal_ranks = [rank[candidate["review"]["rating"]] for candidate in candidates if not candidate["comparison_only"]]
        baseline_ranks = [rank[candidate["review"]["rating"]] for candidate in candidates if candidate["comparison_only"]]
        if formal_ranks and baseline_ranks and min(formal_ranks) < min(baseline_ranks):
            inpaint_better_than_fill = True
    inpaint_ok = inpaint_supported and inpaint_better_than_fill
    dangerous_safe = all(decision["final_policy"] in {"REVIEW_REQUIRED", "SKIP"} for decision in fixture_decisions if fixture_map[decision["fixture_id"]]["expected_policy"] in {"REVIEW_REQUIRED", "SKIP"})
    severe_tags = {
        "bubble_border_damage",
        "line_art_damage",
        "character_detail_damage",
        "unsafe_to_clean",
    }
    severe_accepted = any(
        ratings[candidate["candidate_id"]]["rating"] == "ACCEPTABLE"
        and severe_tags.intersection(filter(None, ratings[candidate["candidate_id"]]["failure_tags"].split(";")))
        for candidate in data["candidates"]
    )
    verdict = "CONDITIONAL_GO" if fill_ok and inpaint_ok and dangerous_safe and not severe_accepted else "FURTHER_SPIKE" if fill_ok else "NO_GO"
    timings = [candidate["processing_time_ms"] for candidate in data["candidates"]]
    summary = {
        "run_id": data["run_id"], "method_summary": {method: dict(counter) for method, counter in method_summary.items()},
        "failure_taxonomy": dict(failures), "fixture_decisions": fixture_decisions,
        "performance_ms": {"candidate_count": len(data["candidates"]), "median": float(np.median(timings)), "max": max(timings)},
        "safety": {"source_files_unchanged": True, "dangerous_fixtures_not_auto_accepted": dangerous_safe, "severe_damage_accepted": severe_accepted},
        "harness_gates": {"light_bubble_fill": fill_ok, "inpaint_supported": inpaint_supported, "inpaint_better_than_fill": inpaint_better_than_fill, "inpaint_value": inpaint_ok, "dangerous_fixtures": dangerous_safe}, "verdict": verdict,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare-masks", "freeze", "supersede-mask-freeze", "validate", "preview", "run", "verify", "apply-ratings", "summarize"))
    command = parser.parse_args().command
    commands = {"prepare-masks": prepare_masks, "freeze": freeze_inputs, "supersede-mask-freeze": supersede_mask_freeze, "validate": validate, "preview": preview, "run": run, "verify": verify, "apply-ratings": apply_ratings, "summarize": summarize}
    try:
        commands[command]()
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
