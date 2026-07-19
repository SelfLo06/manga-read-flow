#!/usr/bin/env python3
"""Bounded Spike C: visible glyph support and residue completeness evidence.

Run-local only.  This module never invokes a cleaner or provider and never
touches SQLite, Workflow, ArtifactService, Repository, API or UI state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from tools.experiments.cleaning_150.visual_contract import spike_b


class SpikeCStop(RuntimeError):
    """Raised when a bounded residue-evidence invariant is invalid."""


@dataclass(frozen=True)
class ResidueProfile:
    version: str = "mvp1-spike-c-local-background-v1"
    support_dilation_px: int = 2
    background_ring_outer_px: int = 5
    min_background_pixels: int = 16
    min_local_contrast: float = 6.0
    min_component_pixels: int = 3


DEFAULT_PROFILE = ResidueProfile()


def _require_mask(mask: np.ndarray, name: str) -> None:
    if not isinstance(mask, np.ndarray) or mask.ndim != 2 or mask.dtype != np.bool_:
        raise SpikeCStop(f"{name} must be a 2D bool mask")


def _same_shape(*masks: np.ndarray) -> None:
    for mask in masks:
        _require_mask(mask, "mask")
    if len({mask.shape for mask in masks}) != 1:
        raise SpikeCStop("mask shape mismatch")


def _lab(image: np.ndarray) -> np.ndarray:
    if image.ndim != 3 or image.shape[2] != 3:
        raise SpikeCStop("image must be RGB")
    return cv2.cvtColor(image, cv2.COLOR_RGB2LAB).astype(np.float32)


def _delta_lab(image: np.ndarray, background_lab: np.ndarray) -> np.ndarray:
    return np.linalg.norm(_lab(image) - background_lab.reshape(1, 1, 3), axis=2)


def _dilate(mask: np.ndarray, iterations: int) -> np.ndarray:
    _require_mask(mask, "mask")
    if iterations < 1:
        raise SpikeCStop("dilation must be positive")
    return cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), dtype=np.uint8), iterations=iterations).astype(bool)


def estimate_local_background(
    image: np.ndarray,
    text_core: np.ndarray,
    instance_mask: np.ndarray,
    *,
    profile: ResidueProfile = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Estimate a local Lab background from an instance-internal safe ring."""

    _same_shape(text_core, instance_mask)
    if image.shape[:2] != text_core.shape:
        raise SpikeCStop("image/mask shape mismatch")
    inner = _dilate(text_core, profile.support_dilation_px)
    outer = _dilate(text_core, profile.background_ring_outer_px)
    ring = instance_mask & outer & ~inner
    if int(ring.sum()) < profile.min_background_pixels:
        ring = instance_mask & ~inner
    if int(ring.sum()) < profile.min_background_pixels:
        raise SpikeCStop("insufficient local-background samples")
    samples = _lab(image)[ring]
    median = np.median(samples, axis=0)
    mad = np.median(np.abs(samples - median), axis=0)
    return {
        "profile_version": profile.version,
        # Large masks stay run-local artifacts; never serialize them inside the
        # structured evidence ledger.
        "_sampling_region_mask": ring,
        "sampling_region_pixels": int(ring.sum()),
        "background_lab_median": [round(float(value), 6) for value in median],
        "background_lab_mad": [round(float(value), 6) for value in mad],
        "_background_lab": median.astype(np.float32),
    }


def build_visible_support(
    source: np.ndarray,
    text_core: np.ndarray,
    instance_mask: np.ndarray,
    *,
    profile: ResidueProfile = DEFAULT_PROFILE,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return a local-contrast constrained visible-glyph support candidate."""

    background = estimate_local_background(source, text_core, instance_mask, profile=profile)
    expanded = _dilate(text_core, profile.support_dilation_px) & instance_mask
    contrast = _delta_lab(source, background["_background_lab"])
    support = (expanded & (contrast >= profile.min_local_contrast)) | text_core
    support &= instance_mask
    background["source_max_local_contrast"] = round(float(contrast[support].max()), 6)
    background["source_mean_local_contrast"] = round(float(contrast[support].mean()), 6)
    background["support_expansion_pixels"] = int(support.sum())
    return support, background


def required_safe_completeness(required_support: np.ndarray, safe_edit: np.ndarray) -> dict[str, Any]:
    """Use explicit support semantics rather than a misleading text_core field."""

    _same_shape(required_support, safe_edit)
    unsafe = required_support & ~safe_edit
    required_pixels = int(required_support.sum())
    unsafe_pixels = int(unsafe.sum())
    return {
        "required_support_pixels": required_pixels,
        "required_support_hash": spike_b.mask_digest(required_support),
        "safe_edit_pixels": int(safe_edit.sum()),
        "safe_edit_covered_required_pixels": int((safe_edit & required_support).sum()),
        "unsafe_required_pixels": unsafe_pixels,
        "unsafe_required_ratio": 0.0 if not required_pixels else round(unsafe_pixels / required_pixels, 8),
        "unsafe_required_hash": spike_b.mask_digest(unsafe),
        "decision": "COMPLETE" if unsafe_pixels == 0 else "INCOMPLETE_REVIEW",
        "issue_code": None if unsafe_pixels == 0 else "required_text_not_safely_editable",
    }


def evaluate_visible_residue(
    source: np.ndarray,
    output: np.ndarray,
    required_support: np.ndarray,
    background: dict[str, Any],
    *,
    profile: ResidueProfile = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Classify structured residue inside support using local—not global—contrast."""

    _require_mask(required_support, "required_support")
    if source.shape != output.shape or source.shape[:2] != required_support.shape:
        raise SpikeCStop("source/output/support shape mismatch")
    if "_background_lab" not in background:
        raise SpikeCStop("background evidence lacks internal Lab median")
    contrast = _delta_lab(output, background["_background_lab"])
    candidate = required_support & (contrast >= profile.min_local_contrast)
    count, labels = cv2.connectedComponents(candidate.astype(np.uint8), connectivity=8)
    components: list[dict[str, Any]] = []
    accepted = np.zeros_like(candidate)
    for label in range(1, count):
        component = labels == label
        pixels = int(component.sum())
        values = contrast[component]
        evidence = {
            "component_index": label,
            "pixels": pixels,
            "max_local_contrast": round(float(values.max()), 6),
            "mean_local_contrast": round(float(values.mean()), 6),
            "accepted_as_glyph_structure": pixels >= profile.min_component_pixels,
        }
        components.append(evidence)
        if evidence["accepted_as_glyph_structure"]:
            accepted |= component
    accepted_components = [item for item in components if item["accepted_as_glyph_structure"]]
    residual_pixels = int(accepted.sum())
    return {
        "profile_version": profile.version,
        # Persisted separately as a PNG artifact.  Structured JSON records only
        # its digest/counts, never the full ndarray.
        "_residue_candidate_mask": accepted,
        "residue_candidate_hash": spike_b.mask_digest(accepted),
        "residue_candidate_pixels": residual_pixels,
        "residue_component_count": len(accepted_components),
        "components": components,
        "residual_support_pixels": residual_pixels,
        "max_local_contrast": 0.0 if not residual_pixels else round(float(contrast[accepted].max()), 6),
        "mean_local_contrast": 0.0 if not residual_pixels else round(float(contrast[accepted].mean()), 6),
        "decision": "BLOCK" if accepted_components else "PASS",
        "issue_code": "cleaning_residue" if accepted_components else None,
        "reason_codes": ["STRUCTURED_LOCAL_CONTRAST_RESIDUE"] if accepted_components else ["NO_STRUCTURED_RESIDUE_COMPONENT"],
    }


def _image_hash(image: np.ndarray) -> str:
    if image.ndim != 3 or image.shape[2] != 3:
        raise SpikeCStop("image must be RGB")
    header = spike_b.canonical_json({"shape": list(image.shape), "encoding": "rgb-u8-row-major-v1"})
    return hashlib.sha256(header + image.tobytes()).hexdigest()


def cleaning_residue_issue_draft(
    *,
    page_id: str,
    segment_id: str,
    binding: dict[str, str],
    residue: dict[str, Any],
    completeness: dict[str, Any],
    source: np.ndarray,
    output: np.ndarray,
) -> dict[str, Any]:
    """Future QualityCheck input only—no persistence or workflow choice."""

    return {
        "root_issue": "cleaning_residue",
        "affected_segment_id": segment_id,
        "page_id": page_id,
        "instance_id": binding["instance_id"],
        "region_revision_id": binding["region_revision_id"],
        "region_hash": binding["region_hash"],
        "source_image_hash": _image_hash(source),
        "output_image_hash": _image_hash(output),
        "residue_mask_hash": residue["residue_candidate_hash"],
        "residue_component_count": residue["residue_component_count"],
        "residual_support_pixels": residue["residual_support_pixels"],
        "max_local_contrast": residue["max_local_contrast"],
        "mean_local_contrast": residue["mean_local_contrast"],
        "required_support_coverage": completeness["safe_edit_covered_required_pixels"],
        "unsafe_required_ratio": completeness["unsafe_required_ratio"],
        "reason_codes": list(residue["reason_codes"]),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SpikeCStop(f"JSON root must be an object: {path}")
    return value


def _load_mask(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L")) > 0


def _load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def _save_mask(mask: np.ndarray, path: Path, run_root: Path) -> dict[str, Any]:
    _require_mask(mask, "artifact mask")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L").save(path, "PNG")
    return {
        "relative_path": str(path.relative_to(run_root)),
        "file_sha256": _sha256_file(path),
        "content_sha256": spike_b.mask_digest(mask),
        "pixel_count": int(mask.sum()),
        "shape": list(mask.shape),
        "encoding": "png-l8-binary-v1",
        "coordinate_space": "full-page-pixel-v1",
    }


def _save_image(image: np.ndarray, path: Path, run_root: Path) -> dict[str, Any]:
    if image.ndim != 3 or image.shape[2] != 3:
        raise SpikeCStop("artifact image must be RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(path, "PNG")
    return {
        "relative_path": str(path.relative_to(run_root)),
        "file_sha256": _sha256_file(path),
        "content_sha256": _image_hash(image),
        "shape": list(image.shape),
        "encoding": "png-rgb-v1",
        "coordinate_space": "full-page-pixel-v1",
    }


def _overlay(
    image: np.ndarray,
    layers: list[tuple[np.ndarray, tuple[int, int, int]]],
    path: Path,
    run_root: Path,
) -> dict[str, Any]:
    rendered = image.astype(np.float32).copy()
    for mask, color in layers:
        _require_mask(mask, "overlay mask")
        if mask.shape != image.shape[:2]:
            raise SpikeCStop("overlay/image shape mismatch")
        rendered[mask] = rendered[mask] * 0.54 + np.asarray(color, dtype=np.float32) * 0.46
    return _save_image(np.clip(rendered, 0, 255).astype(np.uint8), path, run_root)


def _boundary(mask: np.ndarray) -> np.ndarray:
    _require_mask(mask, "instance mask")
    eroded = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), dtype=np.uint8), iterations=1).astype(bool)
    return mask & ~eroded


def _public(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [_public(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _fixture_scene() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Deterministic fixture for A--F; never derived from an oracle outcome."""

    image = np.full((48, 48, 3), 245, dtype=np.uint8)
    instance = np.zeros((48, 48), dtype=bool)
    instance[4:44, 4:44] = True
    core = np.zeros_like(instance)
    core[20:28, 21:27] = True
    halo = np.zeros_like(instance)
    halo[18:30, 19:29] = True
    halo &= ~core
    image[core] = (30, 30, 30)
    image[halo] = (220, 220, 220)
    return image, instance, core, halo


def _control_records(profile: ResidueProfile) -> tuple[list[dict[str, Any]], dict[str, np.ndarray]]:
    """Create controls before oracle access; B--D deliberately retain glyph support."""

    source, instance, core, halo = _fixture_scene()
    support, background = build_visible_support(source, core, instance, profile=profile)
    safe = support.copy()
    complete = required_safe_completeness(support, safe)
    outputs: dict[str, np.ndarray] = {}
    outputs["A_complete_removal"] = np.full_like(source, 245)
    core_only = np.full_like(source, 245)
    core_only[halo] = source[halo]
    outputs["B_halo_remaining"] = core_only
    near_white_source = np.full_like(source, 238)
    near_white_source[core] = (222, 222, 222)
    near_white_support, near_white_background = build_visible_support(near_white_source, core, instance, profile=profile)
    near_white_output = np.full_like(source, 238)
    near_white_output[near_white_support] = (227, 227, 227)
    outputs["C_near_white_residue"] = near_white_output
    stroke = np.zeros_like(support)
    stroke[21:27, 23:25] = True
    key_stroke = np.full_like(source, 245)
    key_stroke[stroke] = (70, 70, 70)
    outputs["D_key_stroke"] = key_stroke
    noise = np.full_like(source, 245)
    noise[7, 7] = (228, 228, 228)
    outputs["E_background_noise"] = noise
    incomplete_safe = safe.copy()
    incomplete_safe[22:24, 23:25] = False
    records: list[dict[str, Any]] = []
    for control_id, output in outputs.items():
        current_source = near_white_source if control_id == "C_near_white_residue" else source
        current_support = near_white_support if control_id == "C_near_white_residue" else support
        current_background = near_white_background if control_id == "C_near_white_residue" else background
        residue = evaluate_visible_residue(current_source, output, current_support, current_background, profile=profile)
        expected = "PASS" if control_id in {"A_complete_removal", "E_background_noise"} else "BLOCK"
        records.append({
            "control_id": control_id,
            "expected_decision": expected,
            "observed_decision": residue["decision"],
            "issue_code": residue["issue_code"],
            "result": "PASS" if residue["decision"] == expected else "FAIL",
            "residue": residue,
            "completeness": complete,
            "source": current_source,
            "output": output,
            "support": current_support,
            "core": core,
            "instance": instance,
            "background": current_background,
        })
    records.append({
        "control_id": "F_incomplete_required_safe",
        "expected_decision": "INCOMPLETE_REVIEW",
        "observed_decision": required_safe_completeness(support, incomplete_safe)["decision"],
        "issue_code": "required_text_not_safely_editable",
        "result": "PASS" if required_safe_completeness(support, incomplete_safe)["decision"] == "INCOMPLETE_REVIEW" else "FAIL",
        "residue": None,
        "completeness": required_safe_completeness(support, incomplete_safe),
        "source": source,
        "output": source,
        "support": support,
        "core": core,
        "instance": instance,
        "background": background,
    })
    return records, outputs


def _spike_b_regression() -> dict[str, Any]:
    """Keep the frozen B glyph/revision controls observable without rewriting B."""

    shape = (20, 20)
    region_a = np.zeros(shape, dtype=bool)
    region_a[2:18, 2:18] = True
    region_b = np.zeros(shape, dtype=bool)
    region_b[2:18, 0:1] = True
    binding_a = spike_b.region_binding("instance-a", "revision-a", region_a)
    binding_b = spike_b.region_binding("instance-b", "revision-b", region_b)
    glyph = np.zeros(shape, dtype=bool)
    glyph[8:11, 8:11] = True
    valid = spike_b.glyph_evidence("segment-a", binding_a, glyph)
    wrong = spike_b.glyph_evidence("segment-a", binding_b, glyph)
    wrong_instance = spike_b.validate_glyph_ledger(
        expected={"segment-a": binding_a}, glyphs=[wrong],
        region_masks={binding_b["region_hash"]: region_b},
        boundary_masks={binding_b["region_hash"]: np.zeros_like(region_b)},
    )
    duplicate = spike_b.validate_glyph_ledger(
        expected={"segment-a": binding_a}, glyphs=[valid, valid],
        region_masks={binding_a["region_hash"]: region_a},
        boundary_masks={binding_a["region_hash"]: np.zeros_like(region_a)},
    )
    overflow_mask = glyph.copy()
    overflow_mask[0, 0] = True
    overflow = spike_b.validate_glyph_ledger(
        expected={"segment-a": binding_a}, glyphs=[spike_b.glyph_evidence("segment-a", binding_a, overflow_mask)],
        region_masks={binding_a["region_hash"]: region_a},
        boundary_masks={binding_a["region_hash"]: np.zeros_like(region_a)},
    )
    boundary_mask = glyph.copy()
    boundary_mask[2, 4] = True
    boundary = np.zeros_like(region_a)
    boundary[2, :] = region_a[2, :]
    boundary_touch = spike_b.validate_glyph_ledger(
        expected={"segment-a": binding_a}, glyphs=[spike_b.glyph_evidence("segment-a", binding_a, boundary_mask)],
        region_masks={binding_a["region_hash"]: region_a}, boundary_masks={binding_a["region_hash"]: boundary},
    )
    validator_mismatch = dict(valid)
    validator_mismatch["validator_binding"] = binding_b
    mismatch = spike_b.validate_glyph_ledger(
        expected={"segment-a": binding_a}, glyphs=[validator_mismatch],
        region_masks={binding_a["region_hash"]: region_a, binding_b["region_hash"]: region_b},
        boundary_masks={binding_a["region_hash"]: np.zeros_like(region_a), binding_b["region_hash"]: np.zeros_like(region_b)},
    )
    correction = spike_b.reserve_correction([], root_issue="cleaning_residue", idempotency_key="spike-c-correction")
    second = spike_b.reserve_correction([correction], root_issue="cleaning_residue", idempotency_key="other")
    return {
        "missing_rejected": "segment_missing" in spike_b.validate_glyph_ledger(
            expected={"segment-a": binding_a}, glyphs=[],
            region_masks={binding_a["region_hash"]: region_a},
            boundary_masks={binding_a["region_hash"]: np.zeros_like(region_a)},
        ),
        "duplicate_rejected": "segment_rendered_multiple_times" in duplicate,
        "wrong_instance_rejected": "wrong_instance_rendering" in wrong_instance,
        "overflow_rejected": "glyph_overflow" in overflow,
        "boundary_touch_rejected": "glyph_boundary_touch" in boundary_touch,
        "validator_region_mismatch_rejected": "validator_region_binding_mismatch" in mismatch,
        "one_correction_reserved": correction["decision"] == "RESERVED",
        "second_correction_rejected": second["decision"] == "REJECTED_SECOND_AUTOMATIC_CORRECTION",
    }


def _write_form(path: Path) -> None:
    path.write_text(
        """# Spike C Human Review FORM — run-v0.1

本轮只审查 Visible Glyph Support / residue Validator 证据；所有 `cleaned-control` 均为确定性合成 control，**不是**真实 Cleaner 或整页清字输出。每题只选一个。

图例：红=instance boundary；绿=text core；紫=visible-support candidate；蓝=safe-edit；橙=residue candidate；青=local-background sampling ring。

## case-71 接触 BubbleInstance

![case-71](overlays/case-71-contact-evidence.png)

- [ ] PASS：两个接触实例的 purple support、orange residue 与 boundary 保持隔离
- [ ] FAIL：support 或 residue 跨越实例边界/虚拟分隔
- [ ] UNCLEAR

备注：

## visible support 覆盖

![case-71 support](overlays/case-71-contact-evidence.png)
![case-72 support](overlays/case-72-evidence.png)

- [ ] PASS：固定样本中未见明显可辨字形落在紫色 support 之外
- [ ] FAIL_FALSE_NEGATIVE：仍有明显笔画、halo 或彩色描边在紫色 support 外
- [ ] UNCLEAR

备注：

## residue positives / negatives

![controls](overlays/controls-grid.png)

- [ ] PASS：B/C/D 残字均被橙色 residue 覆盖并判 BLOCK；A/E 未误报
- [ ] FAIL_FALSE_NEGATIVE
- [ ] FAIL_FALSE_POSITIVE
- [ ] UNCLEAR

备注：

## 根因归属证据

- [ ] PASS：ledger 可将 cleaning_residue 绑定到 page/segment/instance/revision/hash，且不含 retry/fallback/skip 决策
- [ ] FAIL
- [ ] UNCLEAR

备注：

## Overall

- [ ] PASS
- [ ] PASS_WITH_LIMITS
- [ ] CHANGES_REQUIRED

备注：
""",
        encoding="utf-8",
    )


def build_run(*, spike_a_run: Path, spike_b_run: Path, source_root: Path, output_root: Path, oracle_path: Path) -> dict[str, Any]:
    """Build a new hash-locked evidence run; no output is a Cleaner result."""

    if output_root.exists():
        raise SpikeCStop(f"refusing to overwrite run directory: {output_root}")
    b_snapshot_path = spike_b_run / "pixel-evidence-snapshot.json"
    a_snapshot_path = spike_a_run / "visual-contract-snapshot.json"
    b_form_path = spike_b_run / "FORM.md"
    for item in (a_snapshot_path, b_snapshot_path, b_form_path, oracle_path):
        if not item.is_file():
            raise SpikeCStop(f"missing frozen input: {item}")
    b_snapshot = _load_json(b_snapshot_path)
    a_snapshot = _load_json(a_snapshot_path)
    selected = {"case-71__g002__s01", "case-71__g002__s02", "case-72__g001__s01", "case-72__g006__s01"}
    a_instances = {
        item["instance_id"]: (page, item)
        for page in a_snapshot["pages"] for item in page["bubble_instances"]
    }
    output_root.mkdir(parents=True)
    profile = DEFAULT_PROFILE
    input_lock = {
        "schema_version": "mvp1-visual-contract-spike-c-input-lock-v1",
        "created_at": _utc_now(),
        "spike_a_snapshot_sha256": _sha256_file(a_snapshot_path),
        "spike_b_snapshot_sha256": _sha256_file(b_snapshot_path),
        "spike_b_form_sha256": _sha256_file(b_form_path),
        "spike_c_module_sha256": _sha256_file(Path(__file__)),
        # File bytes are hashed here for reproducibility, but expected decisions
        # are neither parsed nor available to candidate generation until after
        # the snapshot below has been written.
        "oracle_sha256": _sha256_file(oracle_path),
        "oracle_hash_read_before_candidate_snapshot": True,
        "candidate_generation_oracle_decision_access": False,
        "profile": asdict(profile),
    }
    records: list[dict[str, Any]] = []
    start = time.perf_counter()
    for prior in b_snapshot["records"]:
        segment_id = prior["segment_id"]
        if segment_id not in selected:
            continue
        binding = prior["instance_binding"]
        page, instance = a_instances[binding["instance_id"]]
        source_path = source_root / "images" / f"{prior['page_id']}.webp"
        instance_mask = _load_mask(spike_a_run / instance["mask_artifact"]["relative_path"])
        source = _load_rgb(source_path)
        core = _load_mask(spike_b_run / prior["artifacts"]["text_core"]["relative_path"])
        safe = _load_mask(spike_b_run / prior["artifacts"]["safe_edit"]["relative_path"])
        support, background = build_visible_support(source, core, instance_mask, profile=profile)
        completeness = required_safe_completeness(support, safe)
        # This is a deterministic evidence control: write only the candidate support
        # to its local background median.  It is never called a Cleaner result.
        control_output = source.copy()
        local_rgb = cv2.cvtColor(np.uint8([[background["_background_lab"]]]), cv2.COLOR_LAB2RGB)[0, 0]
        if completeness["decision"] == "COMPLETE":
            control_output[support] = local_rgb
        residue = evaluate_visible_residue(source, control_output, support, background, profile=profile)
        artifact_root = output_root / "artifacts" / prior["page_id"] / hashlib.sha256(segment_id.encode()).hexdigest()[:16]
        artifacts = {
            "text_core": _save_mask(core, artifact_root / "text-core.png", output_root),
            "visible_support_candidate": _save_mask(support, artifact_root / "visible-support-candidate.png", output_root),
            "safe_edit": _save_mask(safe, artifact_root / "safe-edit.png", output_root),
            "local_background_sampling": _save_mask(background["_sampling_region_mask"], artifact_root / "local-background-sampling.png", output_root),
            "residue_candidate": _save_mask(residue["_residue_candidate_mask"], artifact_root / "residue-candidate.png", output_root),
            "source": _save_image(source, artifact_root / "source.png", output_root),
            "cleaned_control": _save_image(control_output, artifact_root / "cleaned-control.png", output_root),
        }
        record = {
            "page_id": prior["page_id"], "segment_id": segment_id,
            "instance_binding": binding,
            "source_image_hash": _image_hash(source),
            "output_image_hash": _image_hash(control_output),
            "artifacts": artifacts,
            "local_background_evidence": background,
            "required_safe_completeness": completeness,
            "residue_evidence": residue,
            "decision": "INCOMPLETE_REVIEW" if completeness["decision"] != "COMPLETE" else residue["decision"],
            "issue_code": completeness["issue_code"] or residue["issue_code"],
            "reason_codes": (["UNSAFE_REQUIRED_SUPPORT"] if completeness["decision"] != "COMPLETE" else residue["reason_codes"]),
        }
        record["quality_issue_draft"] = None if record["issue_code"] != "cleaning_residue" else cleaning_residue_issue_draft(
            page_id=record["page_id"], segment_id=segment_id, binding=binding, residue=residue,
            completeness=completeness, source=source, output=control_output,
        )
        records.append(record)
    candidate_snapshot = {
        "schema_version": "mvp1-visual-contract-spike-c-snapshot-v1",
        "created_at": _utc_now(), "status": "CANDIDATE_FROZEN_BEFORE_ORACLE",
        "input_lock": input_lock, "records": _public(records),
    }
    snapshot_path = output_root / "visible-glyph-residue-snapshot.json"
    snapshot_path.write_text(json.dumps(candidate_snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Only now may the fixed expected matrix be read; it is not used to produce masks.
    oracle = _load_json(oracle_path)
    controls, _ = _control_records(profile)
    control_public: list[dict[str, Any]] = []
    for control in controls:
        control_id = control["control_id"]
        expected = oracle["controls"][control_id]
        artifact_root = output_root / "controls" / control_id
        residue = control["residue"]
        artifacts = {
            "source": _save_image(control["source"], artifact_root / "source.png", output_root),
            "output": _save_image(control["output"], artifact_root / "output.png", output_root),
            "text_core": _save_mask(control["core"], artifact_root / "text-core.png", output_root),
            "visible_support_candidate": _save_mask(control["support"], artifact_root / "visible-support.png", output_root),
        }
        if residue is not None:
            artifacts["residue_candidate"] = _save_mask(residue["_residue_candidate_mask"], artifact_root / "residue.png", output_root)
        control_layers = [
            (_boundary(control["instance"]), (255, 0, 0)),
            (control["core"], (0, 255, 0)),
            (control["support"], (180, 0, 255)),
            (control["background"]["_sampling_region_mask"], (0, 255, 255)),
        ]
        if residue is not None:
            control_layers.append((residue["_residue_candidate_mask"], (255, 130, 0)))
        artifacts["evidence_overlay"] = _overlay(
            control["source"], control_layers, output_root / "overlays" / f"control-{control_id}.png", output_root
        )
        control_binding = spike_b.region_binding(
            f"fixture-instance::{control_id}", "fixture-revision::v1", control["instance"]
        )
        issue_draft = None
        if residue is not None and residue["decision"] == "BLOCK":
            issue_draft = cleaning_residue_issue_draft(
                page_id="fixture-page::spike-c", segment_id=f"fixture-segment::{control_id}",
                binding=control_binding, residue=residue, completeness=control["completeness"],
                source=control["source"], output=control["output"],
            )
        control_public.append({
            "control_id": control_id, "expected_decision": expected,
            "observed_decision": control["observed_decision"], "issue_code": control["issue_code"],
            "result": "PASS" if control["observed_decision"] == expected else "FAIL",
            "completeness": _public(control["completeness"]),
            "residue_evidence": None if residue is None else _public(residue),
            "quality_issue_draft": issue_draft,
            "artifacts": artifacts,
        })
    regressions = _spike_b_regression()
    # Diagnostic overlays are independent of all decision inputs.
    for page_id in ("case-71", "case-72"):
        page_records = [r for r in records if r["page_id"] == page_id]
        if not page_records:
            continue
        source = _load_rgb(source_root / "images" / f"{page_id}.webp")
        layers: list[tuple[np.ndarray, tuple[int, int, int]]] = []
        for record in page_records:
            binding = record["instance_binding"]
            _, instance = a_instances[binding["instance_id"]]
            mask = _load_mask(spike_a_run / instance["mask_artifact"]["relative_path"])
            layers.extend([
                (_boundary(mask), (255, 0, 0)),
                (_load_mask(output_root / record["artifacts"]["text_core"]["relative_path"]), (0, 255, 0)),
                (_load_mask(output_root / record["artifacts"]["visible_support_candidate"]["relative_path"]), (180, 0, 255)),
                (_load_mask(output_root / record["artifacts"]["safe_edit"]["relative_path"]), (0, 110, 255)),
                (_load_mask(output_root / record["artifacts"]["local_background_sampling"]["relative_path"]), (0, 255, 255)),
            ])
        _overlay(source, layers, output_root / "overlays" / f"{page_id}{'-contact' if page_id == 'case-71' else ''}-evidence.png", output_root)
    # Small deterministic control strip, presented only for review, not calculation.
    thumbs = [_load_rgb(output_root / item["artifacts"]["evidence_overlay"]["relative_path"]) for item in control_public]
    grid = np.concatenate(thumbs, axis=1)
    _save_image(grid, output_root / "overlays" / "controls-grid.png", output_root)
    _write_form(output_root / "FORM.md")
    result = {
        "schema_version": "mvp1-visual-contract-spike-c-result-v1", "run_id": output_root.name,
        "candidate_snapshot_sha256": _sha256_file(snapshot_path), "input_lock": input_lock,
        "records": _public(records), "controls": control_public, "spike_b_regressions": regressions,
        "elapsed_seconds": round(time.perf_counter() - start, 6),
        "candidate_generation_oracle_decision_access": False,
        "actual_cleaner_executed": False,
    }
    (output_root / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spike-a-run", type=Path, required=True)
    parser.add_argument("--spike-b-run", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    args = parser.parse_args()
    result = build_run(spike_a_run=args.spike_a_run, spike_b_run=args.spike_b_run, source_root=args.source_root,
                       output_root=args.output_root, oracle_path=args.oracle)
    print(json.dumps({"run_id": result["run_id"], "elapsed_seconds": result["elapsed_seconds"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
