#!/usr/bin/env python3
"""Deterministic, local-only replay probe for one Goal 6 calibration case."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from tools.experiments.grouping_120.text_seeded_container_association import goal6_mask_harness as mask
from tools.experiments.grouping_120.text_seeded_container_association.goal6_build_calibration import (
    POLICIES,
    _contexts,
    _fragments,
    candidate_for,
)


class DiagnosisStop(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DiagnosisStop(f"JSON root must be an object: {path}")
    return payload


def _changed_pixels(before: np.ndarray, after: np.ndarray) -> int:
    return int(np.any(before != after, axis=2).sum())


def _anti_alias_probe(
    image: np.ndarray,
    candidate: np.ndarray,
    result: mask.ContextResult,
    threshold: int,
) -> dict[str, int]:
    """Locate unchanged gray edge pixels without treating them as editable."""
    source_gray = mask.luminance(image)
    candidate_gray = mask.luminance(candidate)
    unchanged = np.all(image == candidate, axis=2)
    gray_edge = (source_gray > threshold) & (source_gray < 250)
    # `protected` also contains the intentionally non-editable uncertain band.
    intrinsic_protected = result.protected & ~result.uncertain
    intrinsic_safe = result.seed & ~intrinsic_protected
    residual = gray_edge & unchanged & (candidate_gray < 250)
    payload = {
        "gray_edge_seed_pixels": int((gray_edge & result.seed).sum()),
        "residual_gray_edge_seed_pixels": int((residual & result.seed).sum()),
        "residual_gray_edge_current_safe_pixels": int((residual & result.safe).sum()),
        "residual_gray_edge_intrinsic_safe_pixels": int((residual & intrinsic_safe).sum()),
        "residual_gray_edge_one_pixel_halo_pixels": 0,
        "residual_gray_edge_halo_intrinsic_safe_pixels": 0,
        "residual_gray_edge_halo_currently_uncertain_pixels": 0,
    }
    for radius in (1, 2, 3):
        halo = mask.dilate(result.core, radius) & result.seed & ~result.core
        payload[f"residual_gray_edge_halo_r{radius}_pixels"] = int((residual & halo).sum())
        payload[f"residual_gray_edge_halo_r{radius}_intrinsic_safe_pixels"] = int((residual & halo & intrinsic_safe).sum())
    one_pixel_halo = mask.dilate(result.core, 1) & result.seed & ~result.core
    payload["residual_gray_edge_one_pixel_halo_pixels"] = int((residual & one_pixel_halo).sum())
    payload["residual_gray_edge_halo_intrinsic_safe_pixels"] = int((residual & one_pixel_halo & intrinsic_safe).sum())
    payload["residual_gray_edge_halo_currently_uncertain_pixels"] = int((residual & one_pixel_halo & result.uncertain).sum())
    return payload


def diagnose(
    *,
    root: Path,
    s1_path: Path,
    routed_path: Path,
    bundle_path: Path,
    case_id: str,
    output_path: Path,
) -> dict[str, Any]:
    if output_path.exists():
        raise DiagnosisStop("diagnosis output already exists")
    root = root.resolve()
    s1 = load(s1_path)
    routed = load(routed_path)
    bundle = load(bundle_path)
    assets = {item["asset_id"]: item for item in s1.get("assets", [])}
    if case_id not in assets or case_id not in bundle.get("records", {}):
        raise DiagnosisStop("case is absent from frozen calibration inputs")
    asset = assets[case_id]
    source = root / asset["relative_path"]
    if sha256(source) != asset["sha256"]:
        raise DiagnosisStop("source image hash changed")
    image = np.asarray(Image.open(source).convert("RGB"))
    contexts = _contexts(routed)
    if len(contexts) != 1:
        raise DiagnosisStop("single-case diagnosis requires exactly one context")
    fragments = _fragments(asset)
    record = bundle["records"][case_id]
    rows: dict[str, Any] = {}
    for policy_name, policy in POLICIES.items():
        result = mask.process_context(image, contexts[0], fragments, routed["route"], policy)
        candidate, candidate_mode = candidate_for(image, result)
        try:
            forced_fill = mask.border_sampled_fill(image, result.effective, result.safe, result.soft)
            forced_fill_probe: dict[str, Any] = {
                "available": True,
                "changed_pixels": _changed_pixels(image, forced_fill),
                "changed_outside_effective": mask.changed_outside(image, forced_fill, result.effective),
            }
        except mask.Goal6Stop as error:
            forced_fill_probe = {"available": False, "reason": str(error)}
        threshold = int(result.diagnostics["threshold"])
        dark_seed = (mask.luminance(image) <= threshold) & result.seed
        seed_dark_count = int(dark_seed.sum())
        covered_seed_dark = int((dark_seed & result.effective).sum())
        preview_name = record["policy_rows"][policy_name]["preview_files"][0]
        preview_path = bundle_path.parent / "previews" / preview_name
        preview = np.asarray(Image.open(preview_path).convert("RGB"))
        height, width = image.shape[:2]
        if preview.shape != (height, width * 3, 3):
            raise DiagnosisStop(f"unexpected preview dimensions: {preview_name}")
        first_panel_matches_source = bool(np.array_equal(preview[:, :width], image))
        candidate_panel_matches_replay = bool(np.array_equal(preview[:, width * 2 :], candidate))
        rows[policy_name] = {
            "entered_policy": policy.__dict__,
            "threshold": threshold,
            "hard_core_pixels": int(result.diagnostics["hard_core_pixels"]),
            "soft_edge_completed_pixels": int(result.diagnostics["soft_edge_completed_pixels"]),
            "core_pixels": int(result.core.sum()),
            "effective_pixels": int(result.effective.sum()),
            "seed_dark_pixels": seed_dark_count,
            "effective_seed_dark_pixels": covered_seed_dark,
            "effective_seed_dark_coverage": (covered_seed_dark / seed_dark_count) if seed_dark_count else None,
            "risk": result.risk,
            "decision": result.decision,
            "candidate_mode": candidate_mode,
            "candidate_changed_pixels": _changed_pixels(image, candidate),
            "candidate_changed_outside_effective": mask.changed_outside(image, candidate, result.effective),
            "anti_alias_probe": _anti_alias_probe(image, candidate, result, threshold),
            "forced_border_sampled_fill_probe": forced_fill_probe,
            "first_panel_matches_source": first_panel_matches_source,
            "candidate_panel_matches_replay": candidate_panel_matches_replay,
        }
    payload = {
        "schema_version": "goal6-calibration-case-diagnosis-v1",
        "case_id": case_id,
        "source_sha256": sha256(source),
        "s1_results_sha256": sha256(s1_path),
        "routed_result_sha256": sha256(routed_path),
        "bundle_sha256": sha256(bundle_path),
        "route": routed["route"],
        "rows": rows,
        "parameter_effect_observed": len({row["threshold"] for row in rows.values()}) > 1
        or len({row["effective_pixels"] for row in rows.values()}) > 1,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--s1", required=True, type=Path)
    parser.add_argument("--routed", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = diagnose(
            root=args.root,
            s1_path=args.s1,
            routed_path=args.routed,
            bundle_path=args.bundle,
            case_id=args.case_id,
            output_path=args.output,
        )
    except (OSError, ValueError, json.JSONDecodeError, DiagnosisStop, mask.Goal6Stop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": "DIAGNOSED", "case_id": payload["case_id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
