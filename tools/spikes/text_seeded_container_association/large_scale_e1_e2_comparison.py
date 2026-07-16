#!/usr/bin/env python3
"""Isolated 40-page E1-only vs aggressive E1+E2 comparison runner.

This writes review artifacts only.  It does not change the frozen Goal 6
policy, does not overwrite sources, and deliberately keeps E3/abstentions out
of both candidates.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from tools.spikes.text_seeded_container_association import freeze_s1_inputs as s1
from tools.spikes.text_seeded_container_association import goal6_mask_harness as mask
from tools.spikes.text_seeded_container_association import routed_association as routed
from tools.spikes.text_seeded_container_association.goal6_build_calibration import POLICIES, _contexts, _fragments
from tools.spikes.text_seeded_container_association.goal6_full_page_trial import (
    context_risk_overlay,
    semantic_overlay,
    sha256,
    union_effective,
)
from tools.spikes.text_seeded_container_association.run_routed_evaluation import policy_from_lock


ROOT = Path(__file__).resolve().parents[3]
BOOK_SOURCE = ROOT / "data" / "local" / "(C80) [蒼空市場 (蒼)] 東奔西走ブレイカー (東方Project)" / "(C80) [蒼空市場 (蒼)] 東奔西走ブレイカー (東方Project)"
GOAL5_LOCK = ROOT / "data" / "local" / "text-seeded-container-association" / "goal5-routed-v0.1" / "calibration-runs" / "goal5-calibration-v0.1" / "lock.json"
EXPECTED_PAGE_COUNT = 40
MAX_SINGLE_SEED_AREA_RATIO = 0.10


class ComparisonStop(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ComparisonStop(f"JSON root must be an object: {path}")
    return value


def book_pages(source: Path = BOOK_SOURCE) -> tuple[Path, ...]:
    pages = tuple(sorted(source.glob("*.jpg")))
    if len(pages) != EXPECTED_PAGE_COUNT:
        raise ComparisonStop(f"expected {EXPECTED_PAGE_COUNT} JPG pages, got {len(pages)}")
    return pages


def materialize(output_root: Path, source: Path = BOOK_SOURCE) -> dict[str, Any]:
    output_root = output_root.resolve()
    images = output_root / "images"
    if output_root.exists():
        raise ComparisonStop(f"output root already exists: {output_root}")
    pages = book_pages(source)
    images.mkdir(parents=True)
    assets: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    for index, page in enumerate(pages, 1):
        asset_id = f"case-{index:02d}"
        target = images / f"{asset_id}.jpg"
        shutil.copyfile(page, target)
        with Image.open(target) as image:
            width, height = image.size
        source_hash = sha256(page)
        copied_hash = sha256(target)
        if source_hash != copied_hash:
            raise ComparisonStop(f"copy hash mismatch: {page.name}")
        assets.append({"asset_id": asset_id, "relative_path": f"images/{target.name}", "sha256": copied_hash, "width": width, "height": height})
        sources.append({"asset_id": asset_id, "source_filename": page.name, "source_relative_path": str(page.relative_to(ROOT)), "source_sha256": source_hash, "copied_sha256": copied_hash})
    (output_root / "S1-INPUT-SPEC.local.json").write_text(json.dumps({"schema_version": s1.SPEC_SCHEMA_VERSION, "assets": assets}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_root / "SOURCE-MANIFEST.local.json").write_text(json.dumps({"source_page_count": len(sources), "pages": sources}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_root / "MASK-POLICY-LOCK.local.json").write_text(json.dumps({
        "schema_version": "large-scale-e1-e2-mask-policy-lock-v1",
        "status": "FROZEN_FOR_AGGRESSIVE_COMPARISON_ONLY",
        "selected_policy": "P0_conservative",
        "policy": POLICIES["P0_conservative"].__dict__,
        "e2_authorization": "user-authorized only for this isolated comparison; not product policy",
        "no_auto_accept": True,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"asset_count": len(assets), "output_root": str(output_root)}


def freeze(output_root: Path, run_id: str = "s1-book-40-v0.1") -> dict[str, Any]:
    output_root = output_root.resolve()
    detector_module = s1.load_python_module(s1.DEFAULT_DETECTOR_MODULE, "large_scale_s1_detector")
    grouping_module = s1.load_python_module(s1.DEFAULT_GROUPING_MODULE, "large_scale_s1_grouping")
    started = time.perf_counter()
    result = s1.freeze_inputs(
        spec_path=output_root / "S1-INPUT-SPEC.local.json",
        output_root=output_root / "s1-runs",
        run_id=run_id,
        detector_factory=detector_module.PaddleDetector,
        grouping_module=grouping_module,
        environment=detector_module.collect_environment(),
        detector_module=detector_module,
    )
    elapsed = time.perf_counter() - started
    timing = {"schema_version": "large-scale-e1-e2-s1-timing-v1", "s1_results_relative_path": str(result.relative_to(output_root)), "elapsed_seconds": elapsed, "page_count": EXPECTED_PAGE_COUNT, "seconds_per_page": elapsed / EXPECTED_PAGE_COUNT}
    (output_root / "s1-timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return timing


def apply_candidates(image: np.ndarray, results: tuple[mask.ContextResult, ...]) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, float | int]]:
    effective = np.zeros(image.shape[:2], dtype=np.bool_)
    e1 = image.copy()
    e12 = image.copy()
    e1_started = time.perf_counter()
    for result in results:
        effective |= result.effective
        if result.risk == "E1" and result.decision == "REVIEW_REQUIRED" and result.effective.any():
            candidate = mask.border_sampled_fill(image, result.effective, result.safe, result.soft)
            e1[result.effective] = candidate[result.effective]
            e12[result.effective] = candidate[result.effective]
    e1_elapsed = time.perf_counter() - e1_started
    e12_started = time.perf_counter()
    for result in results:
        if result.risk == "E2" and result.decision == "REVIEW_REQUIRED" and result.effective.any():
            candidate = mask.low_radius_telea(image, result.effective)
            e12[result.effective] = candidate[result.effective]
    e12_elapsed = time.perf_counter() - e12_started
    return e1, e12, effective, {"e1_apply_seconds": e1_elapsed, "e12_incremental_e2_apply_seconds": e12_elapsed}


def contact_sheet(records: list[dict[str, Any]], output_dir: Path) -> None:
    thumb_w, thumb_h = 176, 250
    labels_h, cols = 20, 4
    rows = (len(records) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * thumb_w, rows * (thumb_h * 2 + labels_h * 2)), "white")
    for index, record in enumerate(records):
        page_dir = output_dir / record["asset_id"]
        x = (index % cols) * thumb_w
        y = (index // cols) * (thumb_h * 2 + labels_h * 2)
        for offset, filename, label in ((0, "candidate-e1-only.jpg", "E1"), (thumb_h + labels_h, "candidate-e1-plus-e2.jpg", "E1+E2")):
            image = Image.open(page_dir / filename).convert("RGB")
            image.thumbnail((thumb_w, thumb_h))
            left = x + (thumb_w - image.width) // 2
            canvas.paste(image, (left, y + offset))
            ImageDraw.Draw(canvas).text((x + 2, y + offset + thumb_h), f"{record['asset_id']} {label}", fill="black")
    canvas.save(output_dir / "book-contact-sheet-e1-vs-e1-plus-e2.jpg", quality=92)


def oversized_seed_reason(asset: dict[str, Any]) -> str | None:
    page_area = int(asset["width"]) * int(asset["height"])
    largest = max((int(item["bbox"]["width"]) * int(item["bbox"]["height"]) for item in asset["fragments"]), default=0)
    if page_area and largest / page_area > MAX_SINGLE_SEED_AREA_RATIO:
        return "oversized_fragment_seed"
    return None


def compose(output_root: Path, s1_path: Path, goal5_lock: Path = GOAL5_LOCK, max_pages: int | None = None) -> dict[str, Any]:
    output_root = output_root.resolve()
    candidates = output_root / "candidates"
    s1_result = load(s1_path)
    policy_lock = load(goal5_lock)
    if s1_result.get("status") != "completed" or s1_result.get("input_hashes_unchanged") is not True:
        raise ComparisonStop("S1 run is not complete and hash-stable")
    if load(output_root / "MASK-POLICY-LOCK.local.json").get("selected_policy") != "P0_conservative":
        raise ComparisonStop("P0 mask policy lock is unavailable")
    association_policy = policy_from_lock(policy_lock)
    assets = tuple(s1_result.get("assets", ()))
    if len(assets) != EXPECTED_PAGE_COUNT:
        raise ComparisonStop("S1 asset count differs from 40-page contract")
    if any(sha256(output_root / item["relative_path"]) != item["sha256"] for item in assets):
        raise ComparisonStop("frozen source hashes changed")
    candidates.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    total_association = total_mask = total_e1 = total_e12_increment = 0.0
    newly_processed = 0
    for asset in assets:
        page_dir = candidates / asset["asset_id"]
        completed = page_dir / "result.json"
        if completed.is_file():
            record = load(completed)
            records.append(record)
            timing = record.get("timing_seconds", {})
            total_association += float(timing.get("association", 0.0))
            total_mask += float(timing.get("mask", 0.0))
            total_e1 += float(timing.get("e1_apply_seconds", 0.0))
            total_e12_increment += float(timing.get("e12_incremental_e2_apply_seconds", 0.0))
            continue
        if max_pages is not None and newly_processed >= max_pages:
            break
        image = np.asarray(Image.open(output_root / asset["relative_path"]).convert("RGB"))
        resource_reason = oversized_seed_reason(asset)
        association_seconds = 0.0
        if resource_reason:
            association_route = "REGIONLESS_ABSTENTION"
            association_topology = "not_applicable"
            association_eligible = False
            abstention_reasons = [resource_reason]
            contexts = ()
        else:
            association_started = time.perf_counter()
            association = routed.run_routed_association(routed.page_from_s1_asset(output_root, asset), association_policy)
            association_seconds = time.perf_counter() - association_started
            association_json = association.to_jsonable()
            association_route = association.route
            association_topology = association.topology
            association_eligible = association.goal6_trial_eligible
            abstention_reasons = list(association.abstention_reasons)
            contexts = _contexts(association_json) if association_eligible else ()
        mask_started = time.perf_counter()
        results = tuple(mask.process_context(image, context, _fragments(asset), association.route, POLICIES["P0_conservative"], (other.mask for other in contexts if other.region_id != context.region_id)) for context in contexts)
        mask.verify_disjoint(results)
        mask_seconds = time.perf_counter() - mask_started
        e1, e12, effective, timing = apply_candidates(image, results)
        if mask.changed_outside(image, e1, effective) or mask.changed_outside(image, e12, effective):
            raise ComparisonStop(f"candidate changed outside M_effective: {asset['asset_id']}")
        page_dir.mkdir(exist_ok=True)
        all_mask = union_effective(results, {"E1", "E2", "E3", "E4"}) if results else effective
        e1_mask = union_effective(results, {"E1"}) if results else effective
        e12_mask = union_effective(results, {"E1", "E2"}) if results else effective
        skipped = union_effective(results, {"E3", "E4"}) if results else effective
        Image.fromarray(image).save(page_dir / "source.jpg", quality=95)
        Image.fromarray(semantic_overlay(image, all_mask, (40, 145, 245))).save(page_dir / "all-context-effective-overlay.jpg", quality=95)
        Image.fromarray(semantic_overlay(image, e1_mask, (30, 180, 80))).save(page_dir / "e1-applied-effective-overlay.jpg", quality=95)
        Image.fromarray(semantic_overlay(image, e12_mask, (90, 105, 240))).save(page_dir / "e1-plus-e2-applied-effective-overlay.jpg", quality=95)
        Image.fromarray(semantic_overlay(image, skipped, (230, 65, 55))).save(page_dir / "skipped-e3-effective-overlay.jpg", quality=95)
        Image.fromarray(context_risk_overlay(image, results)).save(page_dir / "context-risk-map.jpg", quality=95)
        Image.fromarray(e1).save(page_dir / "candidate-e1-only.jpg", quality=95)
        Image.fromarray(e12).save(page_dir / "candidate-e1-plus-e2.jpg", quality=95)
        risk_counts = Counter(result.risk for result in results)
        record = {
            "asset_id": asset["asset_id"], "source_sha256": asset["sha256"], "route": association_route, "topology": association_topology,
            "goal6_trial_eligible": association_eligible, "abstention_reasons": abstention_reasons,
            "fragment_count": len(asset["fragments"]), "group_count": len(asset["groups"]), "context_count": len(results), "risk_counts": dict(sorted(risk_counts.items())),
            "effective_mask_pixels": int(effective.sum()), "e1_changed_pixels": int(np.any(image != e1, axis=2).sum()), "e1_plus_e2_changed_pixels": int(np.any(image != e12, axis=2).sum()),
            "changed_outside_effective": {"e1_only": mask.changed_outside(image, e1, effective), "e1_plus_e2": mask.changed_outside(image, e12, effective)},
            "timing_seconds": {"association": association_seconds, "mask": mask_seconds, **timing},
            "contexts": [{"context_id": result.context_id, "risk": result.risk, "decision": result.decision, "diagnostics": result.diagnostics} for result in results],
        }
        (page_dir / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append(record)
        newly_processed += 1
        total_association += association_seconds; total_mask += mask_seconds; total_e1 += float(timing["e1_apply_seconds"]); total_e12_increment += float(timing["e12_incremental_e2_apply_seconds"])
        del image, results, effective, e1, e12
        gc.collect()
    if len(records) != EXPECTED_PAGE_COUNT:
        partial = {"status": "PARTIAL", "completed_pages": len(records), "remaining_pages": EXPECTED_PAGE_COUNT - len(records), "newly_processed": newly_processed}
        (candidates / "partial-progress.json").write_text(json.dumps(partial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return partial
    contact_sheet(records, candidates)
    summary = {
        "schema_version": "large-scale-e1-e2-comparison-v1", "status": "READY_FOR_HUMAN_REVIEW", "purpose": "isolated aggressive comparison; no AUTO_ACCEPT or product policy change",
        "page_count": len(records), "source_hashes_unchanged": True, "goal5_lock_sha256": sha256(goal5_lock), "s1_results_sha256": sha256(s1_path),
        "aggregate": {"routes": dict(sorted(Counter(item["route"] for item in records).items())), "risks": dict(sorted(Counter(risk for item in records for risk, count in item["risk_counts"].items() for _ in range(count)).items())), "contexts": sum(item["context_count"] for item in records), "e1_changed_pixels": sum(item["e1_changed_pixels"] for item in records), "e1_plus_e2_changed_pixels": sum(item["e1_plus_e2_changed_pixels"] for item in records), "changed_outside_effective": sum(item["changed_outside_effective"]["e1_only"] + item["changed_outside_effective"]["e1_plus_e2"] for item in records)},
        "timing_seconds": {"association_total": total_association, "mask_total": total_mask, "e1_apply_total": total_e1, "e1_plus_e2_incremental_e2_apply_total": total_e12_increment, "e1_plus_e2_apply_total": total_e1 + total_e12_increment},
        "records": records,
    }
    (candidates / "matrix.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command", required=True)
    materialize_p = subs.add_parser("materialize"); materialize_p.add_argument("--output-root", type=Path, required=True); materialize_p.add_argument("--source", type=Path, default=BOOK_SOURCE)
    freeze_p = subs.add_parser("freeze"); freeze_p.add_argument("--output-root", type=Path, required=True); freeze_p.add_argument("--run-id", default="s1-book-40-v0.1")
    compose_p = subs.add_parser("compose"); compose_p.add_argument("--output-root", type=Path, required=True); compose_p.add_argument("--s1", type=Path, required=True); compose_p.add_argument("--goal5-lock", type=Path, default=GOAL5_LOCK); compose_p.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args()
    try:
        result = materialize(args.output_root, args.source) if args.command == "materialize" else freeze(args.output_root, args.run_id) if args.command == "freeze" else compose(args.output_root, args.s1, args.goal5_lock, args.max_pages)
    except (OSError, ValueError, json.JSONDecodeError, ComparisonStop, mask.Goal6Stop, s1.FreezeStop) as error:
        print(f"STOP: {error}")
        return 2
    display = {key: value for key, value in result.items() if key != "records"}
    print(json.dumps(display, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
