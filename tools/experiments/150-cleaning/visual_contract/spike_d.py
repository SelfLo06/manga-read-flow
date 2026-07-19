#!/usr/bin/env python3
"""Bounded Spike D: validate real local Cleaner output, run-local only.

This module deliberately has no production integration.  It invokes one
existing E1-style border-sampled fill on frozen local evidence and records
observed output pixels; it never accesses SQLite or a workflow/service layer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from tools.experiments.cleaning_150.visual_contract import spike_b, spike_c


class SpikeDStop(RuntimeError):
    """Raised when a bounded Cleaner evidence invariant is invalid."""


BACKGROUND_DELTA_MAX = 12.0


def _require_mask(mask: np.ndarray, name: str) -> None:
    if not isinstance(mask, np.ndarray) or mask.ndim != 2 or mask.dtype != np.bool_:
        raise SpikeDStop(f"{name} must be a 2D bool mask")


def _same_shape(*masks: np.ndarray) -> None:
    for mask in masks:
        _require_mask(mask, "mask")
    if len({mask.shape for mask in masks}) != 1:
        raise SpikeDStop("mask shape mismatch")


def _lab(image: np.ndarray) -> np.ndarray:
    if image.ndim != 3 or image.shape[2] != 3:
        raise SpikeDStop("image must be RGB")
    return cv2.cvtColor(image, cv2.COLOR_RGB2LAB).astype(np.float32)


def _delta_lab(image: np.ndarray, background_lab: np.ndarray) -> np.ndarray:
    return np.linalg.norm(_lab(image) - background_lab.reshape(1, 1, 3), axis=2)


def _dilate(mask: np.ndarray, iterations: int) -> np.ndarray:
    _require_mask(mask, "mask")
    return cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=iterations).astype(bool)


def actual_changed_mask(source: np.ndarray, output: np.ndarray) -> np.ndarray:
    if source.shape != output.shape or source.ndim != 3 or source.shape[2] != 3:
        raise SpikeDStop("source/output image shape mismatch")
    return np.any(source != output, axis=2)


def border_sampled_fill(
    source: np.ndarray,
    candidate: np.ndarray,
    instance: np.ndarray,
    protected: np.ndarray,
    uncertainty: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Existing Goal-6-style RGB median fill; only candidate pixels are written."""

    _same_shape(candidate, instance, protected, uncertainty)
    if source.shape[:2] != candidate.shape or not candidate.any():
        raise SpikeDStop("invalid candidate/source")
    ring = _dilate(candidate, 4) & instance & ~_dilate(candidate, 1) & ~protected & ~uncertainty
    if int(ring.sum()) < 16:
        raise SpikeDStop("insufficient unprotected local background samples")
    rgb_median = np.median(source[ring], axis=0).astype(np.uint8)
    output = source.copy()
    output[candidate] = rgb_median
    lab_median = np.median(_lab(source)[ring], axis=0).astype(np.float32)
    return output, {
        "sampling_region_pixels": int(ring.sum()),
        "background_rgb_median": [int(value) for value in rgb_median],
        "background_lab_median": [round(float(value), 6) for value in lab_median],
        "_sampling_region_mask": ring,
        "_background_lab": lab_median,
    }


def evaluate_structure_damage(
    source: np.ndarray,
    output: np.ndarray,
    safe_edit: np.ndarray,
    protected: np.ndarray,
    uncertainty: np.ndarray,
    *,
    instance_boundary: np.ndarray | None = None,
) -> dict[str, Any]:
    _same_shape(safe_edit, protected, uncertainty)
    changed = actual_changed_mask(source, output)
    if changed.shape != safe_edit.shape:
        raise SpikeDStop("changed/mask shape mismatch")
    outside = changed & ~safe_edit
    protected_changed = changed & protected
    uncertainty_changed = changed & uncertainty
    boundary_changed = np.zeros_like(changed) if instance_boundary is None else changed & instance_boundary
    reasons: list[str] = []
    if outside.any():
        reasons.append("outside_safe_edit")
    if protected_changed.any():
        reasons.append("protected_structure_damage")
    if uncertainty_changed.any():
        reasons.append("uncertainty_structure_damage")
    if boundary_changed.any():
        reasons.append("bubble_boundary_damage")
    damage = outside | protected_changed | uncertainty_changed | boundary_changed
    return {
        "actual_changed_mask": changed,
        "structure_damage_mask": damage,
        "actual_changed_pixels": int(changed.sum()),
        "changed_outside_safe_edit_pixels": int(outside.sum()),
        "changed_inside_protected_pixels": int(protected_changed.sum()),
        "changed_inside_uncertainty_pixels": int(uncertainty_changed.sum()),
        "changed_on_instance_boundary_pixels": int(boundary_changed.sum()),
        "decision": "BLOCK" if reasons else "PASS",
        "issue_code": None if not reasons else reasons[0],
        "reason_codes": reasons or ["NO_STRUCTURE_DAMAGE"],
    }


def evaluate_background_consistency(output: np.ndarray, candidate: np.ndarray, background: dict[str, Any]) -> dict[str, Any]:
    _require_mask(candidate, "candidate")
    lab = background.get("_background_lab")
    if not isinstance(lab, np.ndarray):
        raise SpikeDStop("background lacks internal Lab median")
    contrast = _delta_lab(output, lab)
    differences = candidate & (contrast > BACKGROUND_DELTA_MAX)
    seam_ring = _dilate(candidate, 1) & ~candidate
    seam_samples = _lab(output)[seam_ring]
    if not len(seam_samples):
        raise SpikeDStop("background seam ring is empty")
    seam_lab_median = np.median(seam_samples, axis=0)
    seam_delta = float(np.linalg.norm(seam_lab_median - lab))
    output_texture_std = np.std(_lab(output)[candidate], axis=0) if candidate.any() else np.zeros(3)
    pixels = int(candidate.sum())
    mean = 0.0 if not pixels else float(contrast[candidate].mean())
    maximum = 0.0 if not pixels else float(contrast[candidate].max())
    return {
        "background_difference_mask": differences,
        "background_difference_pixels": int(differences.sum()),
        "candidate_mean_local_background_delta": round(mean, 6),
        "candidate_max_local_background_delta": round(maximum, 6),
        "threshold": BACKGROUND_DELTA_MAX,
        "seam_ring_pixels": int(seam_ring.sum()),
        "seam_lab_median": [round(float(value), 6) for value in seam_lab_median],
        "seam_delta_to_local_background": round(seam_delta, 6),
        "candidate_lab_texture_std": [round(float(value), 6) for value in output_texture_std],
        "decision": "BLOCK" if differences.any() or seam_delta > BACKGROUND_DELTA_MAX else "PASS",
        "issue_code": "background_inconsistency" if differences.any() or seam_delta > BACKGROUND_DELTA_MAX else None,
        "reason_codes": (["BACKGROUND_DELTA_EXCEEDS_LOCAL_MODEL"] if differences.any() else [])
                        + (["CANDIDATE_EDGE_SEAM_EXCEEDS_LOCAL_MODEL"] if seam_delta > BACKGROUND_DELTA_MAX else [])
                        or ["LOCAL_BACKGROUND_CONSISTENT"],
    }


def _image_hash(image: np.ndarray) -> str:
    header = spike_b.canonical_json({"shape": list(image.shape), "encoding": "rgb-u8-row-major-v1"})
    return hashlib.sha256(header + image.tobytes()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SpikeDStop(f"JSON root must be object: {path}")
    return value


def _load_mask(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L")) > 0


def _load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def _save_mask(mask: np.ndarray, path: Path, root: Path) -> dict[str, Any]:
    _require_mask(mask, "artifact mask")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L").save(path, "PNG")
    return {"relative_path": str(path.relative_to(root)), "file_sha256": _sha256_file(path),
            "content_sha256": spike_b.mask_digest(mask), "pixel_count": int(mask.sum()),
            "shape": list(mask.shape), "encoding": "png-l8-binary-v1", "coordinate_space": "full-page-pixel-v1"}


def _save_image(image: np.ndarray, path: Path, root: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(path, "PNG")
    return {"relative_path": str(path.relative_to(root)), "file_sha256": _sha256_file(path),
            "content_sha256": _image_hash(image), "shape": list(image.shape),
            "encoding": "png-rgb-v1", "coordinate_space": "full-page-pixel-v1"}


def _overlay(image: np.ndarray, layers: list[tuple[np.ndarray, tuple[int, int, int]]], path: Path, root: Path) -> dict[str, Any]:
    painted = image.astype(np.float32).copy()
    for mask, color in layers:
        _require_mask(mask, "overlay mask")
        painted[mask] = painted[mask] * 0.54 + np.asarray(color, dtype=np.float32) * 0.46
    return _save_image(np.clip(painted, 0, 255).astype(np.uint8), path, root)


def _paint(image: np.ndarray, layers: list[tuple[np.ndarray, tuple[int, int, int]]]) -> np.ndarray:
    painted = image.astype(np.float32).copy()
    for mask, color in layers:
        _require_mask(mask, "overlay mask")
        painted[mask] = painted[mask] * 0.54 + np.asarray(color, dtype=np.float32) * 0.46
    return np.clip(painted, 0, 255).astype(np.uint8)


def _comparison(
    source: np.ndarray,
    output: np.ndarray,
    focus: np.ndarray,
    source_layers: list[tuple[np.ndarray, tuple[int, int, int]]],
    output_layers: list[tuple[np.ndarray, tuple[int, int, int]]],
    path: Path,
    root: Path,
) -> dict[str, Any]:
    """Three-panel crop: source evidence, visible output, then diagnostics."""

    _require_mask(focus, "focus")
    ys, xs = np.where(focus)
    if not len(xs):
        raise SpikeDStop("comparison focus is empty")
    pad = 36
    top, bottom = max(0, int(ys.min()) - pad), min(source.shape[0], int(ys.max()) + pad + 1)
    left, right = max(0, int(xs.min()) - pad), min(source.shape[1], int(xs.max()) + pad + 1)
    source_panel = _paint(source, source_layers)[top:bottom, left:right]
    output_panel = output[top:bottom, left:right]
    diagnostic_panel = _paint(output, output_layers)[top:bottom, left:right]
    separator = np.full((source_panel.shape[0], 6, 3), 255, dtype=np.uint8)
    return _save_image(np.concatenate((source_panel, separator, output_panel, separator, diagnostic_panel), axis=1), path, root)


def _boundary(mask: np.ndarray) -> np.ndarray:
    return mask & ~cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1).astype(bool)


def _public(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if not key.startswith("_") and not isinstance(item, np.ndarray)}
    if isinstance(value, list):
        return [_public(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _issue_draft(kind: str, record: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    binding = record["instance_binding"]
    return {
        "root_issue": kind, "page_id": record["page_id"], "affected_segment_id": record["segment_id"],
        "instance_id": binding["instance_id"], "region_revision_id": binding["region_revision_id"],
        "region_hash": binding["region_hash"], "source_image_hash": record["source_image_hash"],
        "output_image_hash": record["output_image_hash"], "reason_codes": list(evidence["reason_codes"]),
    }


def _write_form(path: Path) -> None:
    path.write_text("""# Spike D Human Review FORM — run-v0.1

本轮审查真实 `border_sampled_fill` 输出；不代表全页自动清字、产品 Workflow 或 AUTO_ACCEPT。每题每项只选一个。每张 comparison 从左至右是：原图证据、未遮挡的真实 Cleaner 输出、诊断层。

图例：红=instance boundary；绿=required support；蓝=safe-edit；黄=protected/uncertainty；橙=residue；紫=ActualChangedPixelMask；青=background difference。

## case-71 `g002/s01`

![case-71](comparisons/case-71__g002__s01.png)

- [ ] PASS
- [ ] BLOCK
- [ ] UNCLEAR

残字 / 结构损伤 / 背景接缝 / 自动 Gate 是否一致：

## case-72 `g001/s01`

![case-72 g001](comparisons/case-72__g001__s01.png)

- [ ] PASS
- [ ] BLOCK
- [ ] UNCLEAR

残字 / 结构损伤 / 背景接缝 / 自动 Gate 是否一致：

## case-72 `g006/s01`

![case-72 g006](comparisons/case-72__g006__s01.png)

- [ ] PASS
- [ ] BLOCK
- [ ] UNCLEAR

残字 / 结构损伤 / 背景接缝 / 自动 Gate 是否一致：

## Overall

- [ ] PASS_WITH_LIMITS：允许进入 single-page Cleaning vertical slice
- [ ] CHANGES_REQUIRED：不得扩大

备注：
""", encoding="utf-8")


def build_run(*, spike_a_run: Path, spike_b_run: Path, spike_c_run: Path, source_root: Path, output_root: Path, oracle_path: Path) -> dict[str, Any]:
    if output_root.exists():
        raise SpikeDStop(f"refusing to overwrite run: {output_root}")
    c_snapshot_path = spike_c_run / "visible-glyph-residue-snapshot.json"
    b_snapshot_path = spike_b_run / "pixel-evidence-snapshot.json"
    a_snapshot_path = spike_a_run / "visual-contract-snapshot.json"
    for path in (c_snapshot_path, b_snapshot_path, a_snapshot_path, oracle_path):
        if not path.is_file():
            raise SpikeDStop(f"missing frozen input: {path}")
    c_snapshot, b_snapshot, a_snapshot = _load_json(c_snapshot_path), _load_json(b_snapshot_path), _load_json(a_snapshot_path)
    b_by_segment = {item["segment_id"]: item for item in b_snapshot["records"]}
    instances = {item["instance_id"]: item for page in a_snapshot["pages"] for item in page["bubble_instances"]}
    selected = ("case-71__g002__s01", "case-72__g001__s01", "case-72__g006__s01")
    output_root.mkdir(parents=True)
    lock = {"schema_version": "mvp1-visual-contract-spike-d-input-lock-v1", "created_at": _utc_now(),
            "spike_a_snapshot_sha256": _sha256_file(a_snapshot_path), "spike_b_snapshot_sha256": _sha256_file(b_snapshot_path),
            "spike_c_snapshot_sha256": _sha256_file(c_snapshot_path), "spike_d_module_sha256": _sha256_file(Path(__file__)),
            "oracle_sha256": _sha256_file(oracle_path), "oracle_hash_read_before_candidate_snapshot": True,
            "candidate_generation_oracle_decision_access": False, "cleaner": "goal6-e1-border-sampled-rgb-median-v1"}
    records: list[dict[str, Any]] = []
    start = time.perf_counter()
    for c_record in c_snapshot["records"]:
        segment_id = c_record["segment_id"]
        if segment_id not in selected:
            continue
        if c_record["required_safe_completeness"]["decision"] != "COMPLETE":
            raise SpikeDStop(f"selected segment not COMPLETE: {segment_id}")
        b_record = b_by_segment[segment_id]
        binding = c_record["instance_binding"]
        instance = _load_mask(spike_a_run / instances[binding["instance_id"]]["mask_artifact"]["relative_path"])
        source = _load_rgb(source_root / "images" / f"{c_record['page_id']}.webp")
        support = _load_mask(spike_c_run / c_record["artifacts"]["visible_support_candidate"]["relative_path"])
        safe = _load_mask(spike_c_run / c_record["artifacts"]["safe_edit"]["relative_path"])
        protected = _load_mask(spike_b_run / b_record["artifacts"]["protected"]["relative_path"])
        uncertainty = _load_mask(spike_b_run / b_record["artifacts"]["uncertainty"]["relative_path"])
        candidate = support & safe & ~protected & ~uncertainty
        output, background = border_sampled_fill(source, candidate, instance, protected, uncertainty)
        structure = evaluate_structure_damage(source, output, safe, protected, uncertainty, instance_boundary=_boundary(instance))
        residue_background = {"_background_lab": background["_background_lab"]}
        residue = spike_c.evaluate_visible_residue(source, output, support, residue_background)
        bg = evaluate_background_consistency(output, candidate, background)
        issues = [item for item in (structure["issue_code"], residue["issue_code"], bg["issue_code"]) if item]
        decision = "BLOCK" if issues else "PASS"
        root = output_root / "artifacts" / c_record["page_id"] / hashlib.sha256(segment_id.encode()).hexdigest()[:16]
        artifacts = {
            "required_support": _save_mask(support, root / "required-support.png", output_root),
            "safe_edit": _save_mask(safe, root / "safe-edit.png", output_root),
            "protected": _save_mask(protected, root / "protected.png", output_root),
            "uncertainty": _save_mask(uncertainty, root / "uncertainty.png", output_root),
            "cleaner_candidate": _save_mask(candidate, root / "cleaner-candidate.png", output_root),
            "actual_changed": _save_mask(structure["actual_changed_mask"], root / "actual-changed.png", output_root),
            "residue_candidate": _save_mask(residue["_residue_candidate_mask"], root / "residue-candidate.png", output_root),
            "local_background_sampling": _save_mask(background["_sampling_region_mask"], root / "background-sampling.png", output_root),
            "structure_damage": _save_mask(structure["structure_damage_mask"], root / "structure-damage.png", output_root),
            "background_difference": _save_mask(bg["background_difference_mask"], root / "background-difference.png", output_root),
            "source": _save_image(source, root / "source.png", output_root), "cleaned_output": _save_image(output, root / "cleaned-output.png", output_root),
        }
        record = {"page_id": c_record["page_id"], "segment_id": segment_id, "instance_binding": binding,
                  "source_image_hash": _image_hash(source), "output_image_hash": _image_hash(output), "cleaner": lock["cleaner"],
                  "cleaner_code_hash": lock["spike_d_module_sha256"], "artifacts": artifacts,
                  "required_safe_completeness": c_record["required_safe_completeness"],
                  "local_background_evidence": background, "residue_evidence": residue, "structure_evidence": structure,
                  "background_evidence": bg, "decision": decision, "issue_code": issues[0] if issues else None,
                  "reason_codes": [code for group in (structure["reason_codes"], residue["reason_codes"], bg["reason_codes"]) for code in group]}
        record["quality_issue_drafts"] = [_issue_draft(kind, record, evidence) for kind, evidence in
            ((residue["issue_code"], residue), (structure["issue_code"], structure), (bg["issue_code"], bg)) if kind]
        records.append(record)
    snapshot = {"schema_version": "mvp1-visual-contract-spike-d-snapshot-v1", "created_at": _utc_now(),
                "status": "CANDIDATE_FROZEN_BEFORE_ORACLE", "input_lock": lock, "records": _public(records)}
    snapshot_path = output_root / "real-cleaner-snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    oracle = _load_json(oracle_path)
    controls: list[dict[str, Any]] = []
    first = records[0]
    source = _load_rgb(output_root / first["artifacts"]["source"]["relative_path"])
    candidate = _load_mask(output_root / first["artifacts"]["cleaner_candidate"]["relative_path"])
    safe = _load_mask(output_root / first["artifacts"]["safe_edit"]["relative_path"])
    protected = _load_mask(output_root / first["artifacts"]["protected"]["relative_path"])
    uncertainty = _load_mask(output_root / first["artifacts"]["uncertainty"]["relative_path"])
    background = records[0]["local_background_evidence"]
    background["_background_lab"] = np.asarray(background["background_lab_median"], dtype=np.float32)
    core = _load_mask(spike_b_run / b_by_segment[first["segment_id"]]["artifacts"]["text_core"]["relative_path"])
    variants: dict[str, np.ndarray] = {"control_source_unchanged": source.copy(), "control_core_only": source.copy(),
                                       "control_outside_safe": source.copy(), "control_protected_changed": source.copy(),
                                       "control_wrong_background": source.copy()}
    fill = np.asarray(background["background_rgb_median"], dtype=np.uint8)
    variants["control_core_only"][core] = fill
    variants["control_outside_safe"][candidate] = fill; variants["control_outside_safe"][0, 0] = 0
    variants["control_protected_changed"][candidate] = fill; variants["control_protected_changed"][protected] = 0
    variants["control_wrong_background"][candidate] = 0
    for control_id, output in variants.items():
        structure = evaluate_structure_damage(source, output, safe, protected, uncertainty)
        residue = spike_c.evaluate_visible_residue(source, output, candidate, {"_background_lab": background["_background_lab"]})
        bg = evaluate_background_consistency(output, candidate, background)
        observed = "BLOCK" if any(item["decision"] == "BLOCK" for item in (structure, residue, bg)) else "PASS"
        expected = oracle["controls"][control_id]
        controls.append({"control_id": control_id, "expected_decision": expected, "observed_decision": observed,
                         "result": "PASS" if expected == observed else "FAIL", "structure": _public(structure),
                         "residue": _public(residue), "background": _public(bg)})
    for record in records:
        source = _load_rgb(output_root / record["artifacts"]["source"]["relative_path"])
        output = _load_rgb(output_root / record["artifacts"]["cleaned_output"]["relative_path"])
        boundary = _boundary(_load_mask(spike_a_run / instances[record["instance_binding"]["instance_id"]]["mask_artifact"]["relative_path"]))
        required = _load_mask(output_root / record["artifacts"]["required_support"]["relative_path"])
        safe = _load_mask(output_root / record["artifacts"]["safe_edit"]["relative_path"])
        protected_or_uncertainty = _load_mask(output_root / record["artifacts"]["protected"]["relative_path"]) | _load_mask(output_root / record["artifacts"]["uncertainty"]["relative_path"])
        changed = _load_mask(output_root / record["artifacts"]["actual_changed"]["relative_path"])
        residue = _load_mask(output_root / record["artifacts"]["residue_candidate"]["relative_path"])
        damage = _load_mask(output_root / record["artifacts"]["structure_damage"]["relative_path"])
        background_difference = _load_mask(output_root / record["artifacts"]["background_difference"]["relative_path"])
        _comparison(source, output, required | changed,
                    [(boundary, (255, 0, 0)), (required, (0, 255, 0)), (safe, (0, 100, 255)), (protected_or_uncertainty, (255, 220, 0))],
                    [(boundary, (255, 0, 0)), (changed, (190, 0, 255)), (residue, (255, 120, 0)), (damage, (255, 0, 0)), (background_difference, (0, 255, 255))],
                    output_root / "comparisons" / f"{record['segment_id']}.png", output_root)
    _write_form(output_root / "FORM.md")
    summary = {"schema_version": "mvp1-visual-contract-spike-d-summary-v1", "run_id": output_root.name,
               "candidate_snapshot_sha256": _sha256_file(snapshot_path), "input_lock": lock, "records": _public(records),
               "controls": controls, "elapsed_seconds": round(time.perf_counter() - start, 6), "actual_cleaner_executed": True,
               "product_integration": False}
    (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spike-a-run", type=Path, required=True); parser.add_argument("--spike-b-run", type=Path, required=True)
    parser.add_argument("--spike-c-run", type=Path, required=True); parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--oracle", type=Path, required=True)
    args = parser.parse_args()
    result = build_run(spike_a_run=args.spike_a_run, spike_b_run=args.spike_b_run, spike_c_run=args.spike_c_run,
                       source_root=args.source_root, output_root=args.output_root, oracle_path=args.oracle)
    print(json.dumps({"run_id": result["run_id"], "elapsed_seconds": result["elapsed_seconds"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
