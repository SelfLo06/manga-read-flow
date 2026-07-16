#!/usr/bin/env python3
"""Goal 6 full-page, human-review-only demonstration runner.

This is deliberately separate from Goal 6's independent evaluation.  It makes
no product artifacts and never overwrites the two user-selected source pages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from tools.spikes.text_seeded_container_association import goal6_mask_harness as mask
from tools.spikes.text_seeded_container_association import routed_association as routed
from tools.spikes.text_seeded_container_association.goal6_build_calibration import (
    POLICIES,
    _contexts,
    _fragments,
)
from tools.spikes.text_seeded_container_association.run_routed_evaluation import policy_from_lock


ROOT = Path(__file__).resolve().parents[3]
FULL_PAGE_SOURCES = (("case-71", "black2.webp"), ("case-72", "gura_color.webp"))


class FullPageStop(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FullPageStop(f"JSON root must be an object: {path}")
    return value


def materialize(output_root: Path) -> dict[str, Any]:
    """Copy the two approved pages into an immutable local spike input pack."""
    output_root = output_root.resolve()
    images = output_root / "images"
    if images.exists() or (output_root / "S1-INPUT-SPEC.local.json").exists():
        raise FullPageStop("full-page input pack already exists")
    images.mkdir(parents=True)
    assets: list[dict[str, Any]] = []
    source_records: list[dict[str, str]] = []
    for asset_id, filename in FULL_PAGE_SOURCES:
        source = ROOT / "local_samples" / "real" / filename
        if not source.is_file():
            raise FullPageStop(f"missing approved source: {source}")
        target = images / f"{asset_id}.webp"
        shutil.copyfile(source, target)
        with Image.open(target) as image:
            width, height = image.size
        assets.append(
            {
                "asset_id": asset_id,
                "relative_path": f"images/{target.name}",
                "sha256": sha256(target),
                "width": width,
                "height": height,
            }
        )
        source_records.append(
            {
                "asset_id": asset_id,
                "source_relative_path": f"local_samples/real/{filename}",
                "source_sha256": sha256(source),
                "copied_sha256": sha256(target),
            }
        )
    spec = {"schema_version": "text-seeded-container-s1-input-spec-v1", "assets": assets}
    (output_root / "S1-INPUT-SPEC.local.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_root / "FULL-PAGE-SOURCE-MANIFEST.local.json").write_text(
        json.dumps({"approved_user_sources": source_records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    policy = POLICIES["P0_conservative"]
    policy_lock = {
        "schema_version": "goal6-mask-policy-lock-v1",
        "status": "FROZEN_FOR_FULL_PAGE_REVIEW_ONLY",
        "selected_policy": "P0_conservative",
        "policy": policy.__dict__,
        "evidence": {
            "positive_cases": ["cal-61", "cal-62"],
            "positive_choice": "P0_conservative",
            "cal65": "ALL_SKIP_UPSTREAM_FALSE_POSITIVE",
            "review_form_relative_path": (
                "supplement-v0.2/calibration-runs/goal6-targeted-previews-v0.4-soft-edge/FORM.md"
            ),
        },
        "purpose": "full-page human review only; no AUTO_ACCEPT and no evaluation tuning",
    }
    (output_root / "MASK-POLICY-LOCK.local.json").write_text(
        json.dumps(policy_lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"asset_count": len(assets), "output_root": str(output_root)}


def page_overlay(image: np.ndarray, results: tuple[mask.ContextResult, ...]) -> np.ndarray:
    canvas = image.astype(np.float32).copy()
    for result in results:
        for layer, color, alpha in (
            (result.safe, (30, 180, 80), 0.18),
            (result.protected, (230, 65, 55), 0.36),
            (result.uncertain, (255, 190, 20), 0.46),
            (result.effective, (30, 150, 255), 0.66),
        ):
            canvas[layer] = canvas[layer] * (1.0 - alpha) + np.asarray(color) * alpha
    return np.clip(canvas, 0, 255).astype(np.uint8)


def union_effective(results: tuple[mask.ContextResult, ...], risks: set[str]) -> np.ndarray:
    """Return only the effective masks whose risk belongs to ``risks``."""
    if not results:
        raise FullPageStop("cannot build a semantic overlay without contexts")
    selected = np.zeros_like(results[0].effective)
    for result in results:
        if result.risk in risks:
            selected |= result.effective
    return selected


def semantic_overlay(image: np.ndarray, selected: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    canvas = image.astype(np.float32).copy()
    canvas[selected] = canvas[selected] * 0.28 + np.asarray(color) * 0.72
    return np.clip(canvas, 0, 255).astype(np.uint8)


def context_risk_overlay(image: np.ndarray, results: tuple[mask.ContextResult, ...]) -> np.ndarray:
    rendered = Image.fromarray(image.copy())
    labels = ImageDraw.Draw(rendered)
    for result in results:
        pixels = result.seed | result.effective
        y, x = np.where(pixels)
        if not len(x):
            continue
        text = f"{result.context_id} {result.risk} {'APPLY' if result.risk in {'E1', 'E2'} else 'SKIP'}"
        color = (20, 180, 80) if result.risk == "E1" else (50, 130, 230) if result.risk == "E2" else (220, 55, 45)
        labels.rectangle((int(x.min()), int(y.min()), int(x.min()) + max(80, len(text) * 6), int(y.min()) + 13), fill=(255, 255, 255))
        labels.text((int(x.min()) + 1, int(y.min()) + 1), text, fill=color)
    return np.asarray(rendered)


def comparison(source: np.ndarray, overlay: np.ndarray, e1_only: np.ndarray, e2_comparison: np.ndarray) -> Image.Image:
    height, width = source.shape[:2]
    sheet = Image.new("RGB", (width * 4, height), "white")
    for index, item in enumerate((source, overlay, e1_only, e2_comparison)):
        sheet.paste(Image.fromarray(item), (index * width, 0))
    return sheet


def compose(root: Path, s1_path: Path, goal5_lock_path: Path, policy_lock_path: Path, output_dir: Path) -> dict[str, Any]:
    """Compose immutable, review-only whole-page candidates from the frozen P0 mask."""
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FullPageStop("full-page output already exists")
    root = root.resolve()
    s1 = load(s1_path)
    goal5_lock = load(goal5_lock_path)
    mask_lock = load(policy_lock_path)
    if s1.get("status") != "completed" or s1.get("input_hashes_unchanged") is not True:
        raise FullPageStop("S1 run is not complete and hash-stable")
    if mask_lock.get("status") != "FROZEN_FOR_FULL_PAGE_REVIEW_ONLY":
        raise FullPageStop("mask policy lock is not frozen")
    if mask_lock.get("selected_policy") != "P0_conservative" or mask_lock.get("policy") != POLICIES["P0_conservative"].__dict__:
        raise FullPageStop("mask policy lock differs from frozen P0")
    association_policy = policy_from_lock(goal5_lock)
    assets = tuple(s1.get("assets", ()))
    if tuple(item.get("asset_id") for item in assets) != tuple(item[0] for item in FULL_PAGE_SOURCES):
        raise FullPageStop("unexpected full-page S1 asset scope")
    if any(sha256(root / item["relative_path"]) != item["sha256"] for item in assets):
        raise FullPageStop("full-page source hash changed")

    output_dir.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    for asset in assets:
        page = routed.page_from_s1_asset(root, asset)
        association = routed.run_routed_association(page, association_policy)
        association_json = association.to_jsonable()
        image = np.asarray(Image.open(root / asset["relative_path"]).convert("RGB"))
        contexts = _contexts(association_json) if association.goal6_trial_eligible else ()
        fragments = _fragments(asset)
        results = tuple(
            mask.process_context(
                image,
                context,
                fragments,
                association.route,
                POLICIES["P0_conservative"],
                (other.mask for other in contexts if other.region_id != context.region_id),
            )
            for context in contexts
        )
        mask.verify_disjoint(results)
        union_effective = np.zeros(image.shape[:2], dtype=np.bool_)
        e1_only = image.copy()
        e2_comparison = image.copy()
        for result in results:
            union_effective |= result.effective
            if result.decision != "REVIEW_REQUIRED" or not result.effective.any():
                continue
            if result.risk == "E1":
                candidate = mask.border_sampled_fill(image, result.effective, result.safe, result.soft)
                e1_only[result.effective] = candidate[result.effective]
                e2_comparison[result.effective] = candidate[result.effective]
            elif result.risk == "E2":
                candidate = mask.low_radius_telea(image, result.effective)
                e2_comparison[result.effective] = candidate[result.effective]
        if mask.changed_outside(image, e1_only, union_effective) != 0:
            raise FullPageStop("E1-only candidate changed pixels outside M_effective")
        if mask.changed_outside(image, e2_comparison, union_effective) != 0:
            raise FullPageStop("E2 comparison candidate changed pixels outside M_effective")

        page_dir = output_dir / asset["asset_id"]
        page_dir.mkdir()
        overlay = page_overlay(image, results)
        Image.fromarray(image).save(page_dir / "source.png")
        Image.fromarray(overlay).save(page_dir / "mask-safe-overlay.png")
        Image.fromarray(e1_only).save(page_dir / "candidate-e1-only.png")
        Image.fromarray(e2_comparison).save(page_dir / "candidate-e2-comparison.png")
        comparison(image, overlay, e1_only, e2_comparison).save(page_dir / "comparison.png")
        record = {
            "asset_id": asset["asset_id"],
            "source_sha256": asset["sha256"],
            "route": association.route,
            "topology": association.topology,
            "goal6_trial_eligible": association.goal6_trial_eligible,
            "abstention_reasons": list(association.abstention_reasons),
            "contexts": [
                {
                    "context_id": result.context_id,
                    "risk": result.risk,
                    "decision": result.decision,
                    "fragment_status": result.fragment_status,
                    "diagnostics": result.diagnostics,
                }
                for result in results
            ],
            "effective_mask_pixels": int(union_effective.sum()),
            "e1_only_changed_pixels": int(np.any(image != e1_only, axis=2).sum()),
            "e2_comparison_changed_pixels": int(np.any(image != e2_comparison, axis=2).sum()),
            "changed_outside_effective": {
                "e1_only": mask.changed_outside(image, e1_only, union_effective),
                "e2_comparison": mask.changed_outside(image, e2_comparison, union_effective),
            },
            "outputs": [
                "source.png",
                "mask-safe-overlay.png",
                "candidate-e1-only.png",
                "candidate-e2-comparison.png",
                "comparison.png",
            ],
        }
        (page_dir / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append(record)
    payload = {
        "schema_version": "goal6-full-page-human-review-v1",
        "purpose": "post-lock full-page human demonstration only; no AUTO_ACCEPT",
        "source_hashes_unchanged": True,
        "goal5_lock_sha256": sha256(goal5_lock_path),
        "mask_policy_lock_sha256": sha256(policy_lock_path),
        "records": records,
    }
    (output_dir / "matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def explain(
    root: Path,
    s1_path: Path,
    goal5_lock_path: Path,
    candidate_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Render non-mutating overlays that distinguish constructed from applied masks."""
    root = root.resolve()
    candidate_dir = candidate_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FullPageStop("semantic-overlay output already exists")
    s1 = load(s1_path)
    if s1.get("status") != "completed" or s1.get("input_hashes_unchanged") is not True:
        raise FullPageStop("S1 run is not complete and hash-stable")
    association_policy = policy_from_lock(load(goal5_lock_path))
    assets = tuple(s1.get("assets", ()))
    if tuple(item.get("asset_id") for item in assets) != tuple(item[0] for item in FULL_PAGE_SOURCES):
        raise FullPageStop("unexpected full-page S1 asset scope")
    output_dir.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    for asset in assets:
        source = np.asarray(Image.open(root / asset["relative_path"]).convert("RGB"))
        e1_candidate = np.asarray(Image.open(candidate_dir / asset["asset_id"] / "candidate-e1-only.png").convert("RGB"))
        e2_candidate = np.asarray(Image.open(candidate_dir / asset["asset_id"] / "candidate-e2-comparison.png").convert("RGB"))
        page = routed.page_from_s1_asset(root, asset)
        association = routed.run_routed_association(page, association_policy)
        contexts = _contexts(association.to_jsonable()) if association.goal6_trial_eligible else ()
        fragments = _fragments(asset)
        results = tuple(
            mask.process_context(
                source, context, fragments, association.route, POLICIES["P0_conservative"],
                (other.mask for other in contexts if other.region_id != context.region_id),
            )
            for context in contexts
        )
        if not results:
            raise FullPageStop(f"no contexts available to explain: {asset['asset_id']}")
        mask.verify_disjoint(results)
        page_dir = output_dir / asset["asset_id"]
        page_dir.mkdir()
        all_mask = union_effective(results, {"E1", "E2", "E3", "E4"})
        e1_mask = union_effective(results, {"E1"})
        e1_e2_mask = union_effective(results, {"E1", "E2"})
        e3_mask = union_effective(results, {"E3", "E4"})
        Image.fromarray(semantic_overlay(source, all_mask, (40, 145, 245))).save(page_dir / "all-context-effective-overlay.png")
        Image.fromarray(semantic_overlay(source, e1_mask, (30, 180, 80))).save(page_dir / "e1-applied-effective-overlay.png")
        Image.fromarray(semantic_overlay(source, e1_e2_mask, (90, 105, 240))).save(page_dir / "e1-plus-e2-comparison-effective-overlay.png")
        Image.fromarray(semantic_overlay(source, e3_mask, (230, 65, 55))).save(page_dir / "skipped-e3-effective-overlay.png")
        Image.fromarray(context_risk_overlay(source, results)).save(page_dir / "context-risk-map.png")
        changed_e1 = np.any(source != e1_candidate, axis=2)
        changed_e2 = np.any(source != e2_candidate, axis=2)
        rows = []
        for result in results:
            active = result.effective
            y, x = np.where(result.seed | active)
            rows.append(
                {
                    "context_id": result.context_id,
                    "risk": result.risk,
                    "decision": result.decision,
                    "application": "E1_ONLY" if result.risk == "E1" else "E2_COMPARISON_ONLY" if result.risk == "E2" else "SKIP",
                    "effective_pixels": int(active.sum()),
                    "core_protected_overlap_pixels": int((result.core & result.protected).sum()),
                    "e1_candidate_changed_inside": int(changed_e1[active].sum()),
                    "e2_candidate_changed_inside": int(changed_e2[active].sum()),
                    "bbox_xyxy": [int(x.min()), int(y.min()), int(x.max() + 1), int(y.max() + 1)],
                }
            )
        payload = {"asset_id": asset["asset_id"], "contexts": rows}
        (page_dir / "context-writeback-check.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append(payload)
    payload = {
        "schema_version": "goal6-full-page-semantic-overlay-v1",
        "purpose": "diagnostic overlay only; candidates and policy locks are unchanged",
        "records": records,
    }
    (output_dir / "matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    materialize_parser = subparsers.add_parser("materialize")
    materialize_parser.add_argument("--output-root", type=Path, required=True)
    compose_parser = subparsers.add_parser("compose")
    compose_parser.add_argument("--root", type=Path, required=True)
    compose_parser.add_argument("--s1", type=Path, required=True)
    compose_parser.add_argument("--goal5-lock", type=Path, required=True)
    compose_parser.add_argument("--mask-policy-lock", type=Path, required=True)
    compose_parser.add_argument("--output-dir", type=Path, required=True)
    explain_parser = subparsers.add_parser("explain")
    explain_parser.add_argument("--root", type=Path, required=True)
    explain_parser.add_argument("--s1", type=Path, required=True)
    explain_parser.add_argument("--goal5-lock", type=Path, required=True)
    explain_parser.add_argument("--candidate-dir", type=Path, required=True)
    explain_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "materialize":
            payload = materialize(args.output_root)
        elif args.command == "compose":
            payload = compose(args.root, args.s1, args.goal5_lock, args.mask_policy_lock, args.output_dir)
        else:
            payload = explain(args.root, args.s1, args.goal5_lock, args.candidate_dir, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError, FullPageStop, mask.Goal6Stop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": "READY_FOR_REVIEW", **payload}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
