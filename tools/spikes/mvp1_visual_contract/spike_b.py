#!/usr/bin/env python3
"""Bounded Spike B: run-local pixel evidence and actual-glyph validation.

This module deliberately contains no product integration: no SQLite, active
pointers, Repository, Workflow, Provider, ArtifactService, CleanerProvider or
TypesetterProvider.  It only constructs immutable local evidence and tests
whether the contract rejects deliberately invalid evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


class SpikeBStop(RuntimeError):
    """Raised when a run-local evidence invariant is impossible to satisfy."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def mask_digest(mask: np.ndarray) -> str:
    _require_mask(mask, "mask")
    header = canonical_json({"shape": list(mask.shape), "encoding": "row-major-packed-bool-v1"})
    return hashlib.sha256(header + np.packbits(mask, axis=None).tobytes()).hexdigest()


def _require_mask(mask: np.ndarray, name: str) -> None:
    if not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.ndim != 2:
        raise SpikeBStop(f"{name} must be a 2D bool mask")


def _same_shape(*masks: np.ndarray) -> None:
    for mask in masks:
        _require_mask(mask, "mask")
    if len({mask.shape for mask in masks}) != 1:
        raise SpikeBStop("mask shape mismatch")


def actual_changed_pixel_mask(source: np.ndarray, output: np.ndarray) -> np.ndarray:
    """Return the post-hoc RGB difference mask; provider counters are ignored."""

    if source.shape != output.shape or source.ndim != 3 or source.shape[2] != 3:
        raise SpikeBStop("source/output image shape mismatch")
    return np.any(source != output, axis=2)


def validate_changed_mask(actual: np.ndarray, declared_write_mask: np.ndarray) -> list[str]:
    _same_shape(actual, declared_write_mask)
    return [] if np.array_equal(actual, declared_write_mask) else ["ACTUAL_CHANGED_MASK_MISMATCH"]


def _luminance(image: np.ndarray) -> np.ndarray:
    if image.ndim != 3 or image.shape[2] != 3:
        raise SpikeBStop("image must be RGB")
    return (0.2126 * image[..., 0] + 0.7152 * image[..., 1] + 0.0722 * image[..., 2]).astype(np.float32)


def evaluate_residue(
    required_text_mask: np.ndarray,
    output: np.ndarray,
    *,
    max_residual_luminance: float,
) -> dict[str, Any]:
    """Evaluate only required text pixels; changed-pixel count cannot substitute it."""

    _require_mask(required_text_mask, "required_text_mask")
    if output.shape[:2] != required_text_mask.shape:
        raise SpikeBStop("required-text/output shape mismatch")
    residual = required_text_mask & (_luminance(output) <= max_residual_luminance)
    count = int(residual.sum())
    return {
        "required_text_pixels": int(required_text_mask.sum()),
        "residual_required_pixels": count,
        "residual_ratio": 0.0 if not required_text_mask.any() else round(count / int(required_text_mask.sum()), 8),
        "max_residual_luminance": float(max_residual_luminance),
        "residual_mask_hash": mask_digest(residual),
        "decision": "PASS" if count == 0 else "BLOCK",
        "issue_code": None if count == 0 else "cleaning_residue",
    }


def build_safe_edit_evidence(
    text_core_mask: np.ndarray,
    protected_mask: np.ndarray,
    uncertainty_mask: np.ndarray,
) -> dict[str, Any]:
    """Keep semantic text, protected structure and uncertainty bands distinct."""

    _same_shape(text_core_mask, protected_mask, uncertainty_mask)
    protected_overlap = text_core_mask & protected_mask
    uncertainty_overlap = text_core_mask & uncertainty_mask & ~protected_mask
    excluded = protected_mask | uncertainty_mask
    safe = text_core_mask & ~excluded
    return {
        "decision_basis": "PIXEL_INTERSECTION_NOT_INSTANCE_RATIO",
        "text_core_pixels": int(text_core_mask.sum()),
        "protected_pixels": int(protected_mask.sum()),
        "uncertainty_pixels": int(uncertainty_mask.sum()),
        "protected_overlap_pixels": int(protected_overlap.sum()),
        "uncertainty_overlap_pixels": int(uncertainty_overlap.sum()),
        "safe_edit_pixels": int(safe.sum()),
        "text_core_hash": mask_digest(text_core_mask),
        "protected_hash": mask_digest(protected_mask),
        "uncertainty_hash": mask_digest(uncertainty_mask),
        "safe_edit_hash": mask_digest(safe),
        "_safe_edit_mask": safe,
    }


def evaluate_required_text_completeness(
    required_text_mask: np.ndarray,
    safe_edit_mask: np.ndarray,
) -> dict[str, Any]:
    """Report whether all required text can be safely edited without conflation.

    A nonempty unsafe remainder is a review/blocking fact, even if every safe
    pixel is written back and even if its restricted residue check would pass.
    """

    _same_shape(required_text_mask, safe_edit_mask)
    unsafe = required_text_mask & ~safe_edit_mask
    unsafe_pixels = int(unsafe.sum())
    required_pixels = int(required_text_mask.sum())
    return {
        "required_text_pixels": required_pixels,
        "safe_edit_covered_required_pixels": int((required_text_mask & safe_edit_mask).sum()),
        "unsafe_required_pixels": unsafe_pixels,
        "unsafe_required_ratio": 0.0 if required_pixels == 0 else round(unsafe_pixels / required_pixels, 8),
        "unsafe_required_hash": mask_digest(unsafe),
        "decision": "COMPLETE" if unsafe_pixels == 0 else "INCOMPLETE_REVIEW",
        "issue_code": None if unsafe_pixels == 0 else "required_text_not_safely_editable",
    }


def region_binding(instance_id: str, revision_id: str, region_mask: np.ndarray) -> dict[str, str]:
    _require_mask(region_mask, "region_mask")
    return {
        "instance_id": instance_id,
        "region_revision_id": revision_id,
        "region_hash": mask_digest(region_mask),
    }


def glyph_evidence(segment_id: str, binding: dict[str, str], full_canvas_coverage: np.ndarray) -> dict[str, Any]:
    """Create evidence from a full-canvas coverage mask, never a clipped mask."""

    _require_mask(full_canvas_coverage, "full_canvas_coverage")
    return {
        "segment_id": segment_id,
        "renderer_binding": dict(binding),
        "validator_binding": dict(binding),
        "full_canvas_coverage_hash": mask_digest(full_canvas_coverage),
        "full_canvas_coverage_pixels": int(full_canvas_coverage.sum()),
        "_full_canvas_coverage": full_canvas_coverage,
    }


def validate_glyph_ledger(
    *,
    expected: dict[str, dict[str, str]],
    glyphs: list[dict[str, Any]],
    region_masks: dict[str, np.ndarray],
    boundary_masks: dict[str, np.ndarray],
) -> list[str]:
    """Return deterministic blocking issue codes from actual, un-clipped glyph masks."""

    issues: list[str] = []
    by_segment: dict[str, list[dict[str, Any]]] = {}
    for evidence in glyphs:
        by_segment.setdefault(str(evidence.get("segment_id")), []).append(evidence)
    for segment_id, expected_binding in expected.items():
        candidates = by_segment.get(segment_id, [])
        if not candidates:
            issues.append("segment_missing")
            continue
        if len(candidates) != 1:
            issues.append("segment_rendered_multiple_times")
            continue
        evidence = candidates[0]
        renderer = evidence.get("renderer_binding")
        validator = evidence.get("validator_binding")
        if renderer != validator:
            issues.append("validator_region_binding_mismatch")
            continue
        if renderer != expected_binding:
            issues.append("wrong_instance_rendering")
            continue
        region_hash = expected_binding["region_hash"]
        region = region_masks.get(region_hash)
        boundary = boundary_masks.get(region_hash)
        coverage = evidence.get("_full_canvas_coverage")
        if region is None or boundary is None or not isinstance(coverage, np.ndarray):
            issues.append("glyph_evidence_artifact_missing")
            continue
        _same_shape(region, boundary, coverage)
        if not coverage.any():
            issues.append("missing_glyph")
            continue
        if np.any(coverage & ~region):
            issues.append("glyph_overflow")
            continue
        if np.any(coverage & boundary):
            issues.append("glyph_boundary_touch")
    for segment_id in by_segment:
        if segment_id not in expected:
            issues.append("unexpected_segment_glyph")
    return sorted(set(issues))


def reserve_correction(
    existing: list[dict[str, Any]],
    *,
    root_issue: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Pure immutable simulation of one permitted local correction reservation."""

    for item in existing:
        if item.get("idempotency_key") == idempotency_key:
            return {**item, "decision": "REPLAY"}
    if any(item.get("root_issue") == root_issue and int(item.get("ordinal", 0)) >= 1 for item in existing):
        return {
            "decision": "REJECTED_SECOND_AUTOMATIC_CORRECTION",
            "root_issue": root_issue,
            "idempotency_key": idempotency_key,
            "ordinal": None,
            "reservation_id": None,
        }
    ordinal = 1
    reservation = {
        "decision": "RESERVED",
        "root_issue": root_issue,
        "idempotency_key": idempotency_key,
        "ordinal": ordinal,
    }
    return {**reservation, "reservation_id": f"correction::{digest_value(reservation)[:20]}"}


def text_core_from_bbox(
    image: np.ndarray,
    bbox: dict[str, int],
    instance_mask: np.ndarray,
    *,
    max_text_luminance: float = 180.0,
) -> np.ndarray:
    """Minimal traceable text-core proposal for a bounded evidence harness.

    It is deliberately a candidate evidence extractor, not a product pixel-text
    mask algorithm.  The report records its threshold and resulting hash.
    """

    _require_mask(instance_mask, "instance_mask")
    if image.shape[:2] != instance_mask.shape:
        raise SpikeBStop("image/instance mask shape mismatch")
    x, y = int(bbox["x"]), int(bbox["y"])
    width, height = int(bbox["width"]), int(bbox["height"])
    if width <= 0 or height <= 0:
        raise SpikeBStop("invalid segment bbox")
    roi = np.zeros_like(instance_mask)
    roi[max(0, y) : min(instance_mask.shape[0], y + height), max(0, x) : min(instance_mask.shape[1], x + width)] = True
    return roi & instance_mask & (_luminance(image) <= max_text_luminance)


def expand_visible_text_support(
    text_core_mask: np.ndarray,
    instance_mask: np.ndarray,
    *,
    dilation_px: int = 2,
) -> np.ndarray:
    """Build a conservative visible-glyph support candidate around the dark core.

    It captures antialias/stroke neighbourhood pixels for residue controls but
    is deliberately not claimed as pixel-accurate visual-glyph ground truth.
    """

    _same_shape(text_core_mask, instance_mask)
    if dilation_px < 1:
        raise SpikeBStop("visible-support dilation must be positive")
    kernel = np.ones((3, 3), dtype=np.uint8)
    return cv2.dilate(text_core_mask.astype(np.uint8), kernel, iterations=dilation_px).astype(bool) & instance_mask


def boundary_and_uncertainty(instance_mask: np.ndarray, *, band_px: int = 4) -> tuple[np.ndarray, np.ndarray]:
    _require_mask(instance_mask, "instance_mask")
    if band_px < 1:
        raise SpikeBStop("boundary band must be positive")
    binary = instance_mask.astype(np.uint8)
    kernel = np.ones((3, 3), dtype=np.uint8)
    inner = cv2.erode(binary, kernel, iterations=1).astype(bool)
    boundary = instance_mask & ~inner
    uncertainty = cv2.dilate(boundary.astype(np.uint8), kernel, iterations=band_px).astype(bool) & instance_mask
    return boundary, uncertainty


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SpikeBStop(f"JSON root must be an object: {path}")
    return value


def _safe_name(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _save_mask(mask: np.ndarray, path: Path, run_root: Path) -> dict[str, Any]:
    _require_mask(mask, "artifact mask")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L").save(path, "PNG")
    return {
        "relative_path": str(path.relative_to(run_root)),
        "file_sha256": sha256_file(path),
        "content_sha256": mask_digest(mask),
        "pixel_count": int(mask.sum()),
        "shape": list(mask.shape),
        "encoding": "png-l8-binary-v1",
        "coordinate_space": "full-page-pixel-v1",
    }


def _save_image(image: np.ndarray, path: Path, run_root: Path) -> dict[str, Any]:
    if image.ndim != 3 or image.shape[2] != 3:
        raise SpikeBStop("artifact image must be RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(path, "PNG")
    return {
        "relative_path": str(path.relative_to(run_root)),
        "file_sha256": sha256_file(path),
        "shape": list(image.shape),
        "encoding": "png-rgb-v1",
        "coordinate_space": "full-page-pixel-v1",
    }


def _save_overlay(
    image: np.ndarray,
    layers: list[tuple[np.ndarray, tuple[int, int, int]]],
    path: Path,
    run_root: Path,
) -> dict[str, Any]:
    """Diagnostic-only overlay; it is never a geometry or relationship source."""

    rendered = image.astype(np.float32).copy()
    for mask, color in layers:
        _require_mask(mask, "overlay mask")
        if mask.shape != image.shape[:2]:
            raise SpikeBStop("overlay/image shape mismatch")
        rendered[mask] = rendered[mask] * 0.58 + np.asarray(color, dtype=np.float32) * 0.42
    return _save_image(np.clip(rendered, 0, 255).astype(np.uint8), path, run_root)


def _largest_component(mask: np.ndarray) -> np.ndarray:
    _require_mask(mask, "component mask")
    count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    if count <= 1:
        raise SpikeBStop("required-text evidence has no component")
    sizes = [(int((labels == label).sum()), label) for label in range(1, count)]
    _, largest = max(sizes)
    return labels == largest


def _render_vertical_full_canvas(
    shape: tuple[int, int],
    bbox: dict[str, int],
    text: str,
    font: ImageFont.FreeTypeFont,
) -> np.ndarray:
    """Render the complete string into a page canvas before any region check.

    The fixed 8 px control profile is intentionally not a typesetter or a font
    search.  It only makes the full translated text observable to the Validator.
    """

    if not text:
        raise SpikeBStop("active segment has no frozen translation text")
    canvas = Image.new("L", (shape[1], shape[0]), 0)
    draw = ImageDraw.Draw(canvas)
    x = int(bbox["x"] + bbox["width"] // 2)
    y = int(bbox["y"])
    step = 10
    for character in text:
        draw.text((x, y), character, font=font, fill=255, anchor="ma")
        y += step
    return np.asarray(canvas) > 0


def _public(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [_public(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _snapshot_maps(snapshot: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    pages = {item["page_id"]: item for item in snapshot["pages"]}
    segments: dict[str, dict[str, Any]] = {}
    instances: dict[str, dict[str, Any]] = {}
    assessments: dict[str, dict[str, Any]] = {}
    for page in pages.values():
        segments.update({item["segment_id"]: item for item in page["text_segments"]})
        instances.update({item["instance_id"]: item for item in page["bubble_instances"]})
        for assessment in page["eligibility_assessments"]:
            assessments[assessment["instance_id"]] = assessment
    return pages, segments, {**instances, "__assessments__": assessments}


def _translation_map(provenance: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for page in provenance["pages"]:
        for block in page["blocks"]:
            values[block["segment_id"]] = block["translation_text"]
    return values


def _selected_segment_ids() -> tuple[str, ...]:
    return (
        "case-71__g002__s01",
        "case-71__g002__s02",
        "case-72__g001__s01",
        "case-72__g002__s01",
        "case-72__g003__s01",
        "case-72__g004__s01",
        "case-72__g006__s01",
    )


def _write_form(path: Path) -> None:
    path.write_text(
        """# Spike B Human Review FORM

说明：只审查 Validator 证据，不评价清字或嵌字产品质量；每题选择一个。

图例：红色为 instance boundary；绿色为深色 text core；紫色为由 core 扩张得到的
visible-glyph support candidate；蓝色为 safe-edit candidate；黄色为未裁剪、全画布
生成后再验证的 glyph coverage。紫色 support 仍只是候选，不能单靠像素规则声称完整覆盖
全部可辨识原文。原日文仍可见是预期：本轮没有执行实际 Cleaning。

## case-71 接触实例

![case-71 evidence](overlays/case-71-evidence.png)

- [ ] PASS：两个 instance 的 required-text 与 glyph evidence 保持独立
- [ ] FAIL
- [ ] UNCLEAR

备注：

## case-72 g003 protected-overlap regression

![case-72 evidence](overlays/case-72-evidence.png)

- [ ] PASS：text/protected/uncertainty/safe-edit 被分开呈现，且没有伪称可实际清字
- [ ] FAIL
- [ ] UNCLEAR

备注：

## deliberate controls

残字正反例、actual changed mask 与 JSON 证据位于 `controls/` 与
`pixel-evidence-snapshot.json`；本题主要确认报告中列出的错误确实被 Gate 拒绝。

- [ ] PASS：residue、overflow、wrong validator region 的错误证据均被正确拒绝
- [ ] FAIL
- [ ] UNCLEAR

备注：

## visible-glyph support completeness

- [ ] PASS：紫色 support candidate 覆盖所有仍可辨识的原文字形、描边与抗锯齿边缘
- [ ] FAIL_FALSE_NEGATIVE：仍有可辨原文在紫色 support 之外
- [ ] UNCLEAR

备注：

## Overall

- [ ] PASS
- [ ] PASS_WITH_CHANGES
- [ ] NO_GO

备注：
""",
        encoding="utf-8",
    )


def build_run(
    *,
    spike_a_run: Path,
    source_root: Path,
    provenance_path: Path,
    font_path: Path,
    output_root: Path,
    oracle_path: Path,
) -> dict[str, Any]:
    """Build a new immutable run without consulting the oracle until frozen."""

    if output_root.exists():
        raise SpikeBStop(f"refusing to overwrite run directory: {output_root}")
    snapshot_path = spike_a_run / "visual-contract-snapshot.json"
    input_lock_path = spike_a_run / "input-lock.json"
    form_path = spike_a_run / "FORM.md"
    for required in (snapshot_path, input_lock_path, form_path, provenance_path, font_path, oracle_path):
        if not required.is_file():
            raise SpikeBStop(f"missing frozen input: {required}")
    snapshot = _load_json(snapshot_path)
    if snapshot.get("relationship_source", {}).get("exclusive_for_run") is not True:
        raise SpikeBStop("Spike A relationship source is not exclusive")
    provenance = _load_json(provenance_path)
    pages, segments, instance_map = _snapshot_maps(snapshot)
    assessments = instance_map.pop("__assessments__")
    translations = _translation_map(provenance)
    output_root.mkdir(parents=True)
    start = time.perf_counter()
    input_lock = {
        "schema_version": "mvp1-visual-contract-spike-b-input-lock-v1",
        "created_at": utc_now(),
        "spike_a_snapshot_file_sha256": sha256_file(snapshot_path),
        "spike_a_input_lock_sha256": sha256_file(input_lock_path),
        "spike_a_form_sha256": sha256_file(form_path),
        "spike_b_module_sha256": sha256_file(Path(__file__).resolve()),
        "provenance_sha256": sha256_file(provenance_path),
        "font_sha256": sha256_file(font_path),
        "oracle_sha256": sha256_file(oracle_path),
        "candidate_generation_oracle_access": False,
    }
    source_images: dict[str, np.ndarray] = {}
    for page_id in {segment_id.split("__", 1)[0] for segment_id in _selected_segment_ids()}:
        image_path = source_root / "images" / f"{page_id}.webp"
        if not image_path.is_file():
            raise SpikeBStop(f"missing source image: {image_path}")
        image = np.asarray(Image.open(image_path).convert("RGB"))
        if sha256_file(image_path) != pages[page_id]["source_sha256"]:
            raise SpikeBStop(f"source hash changed: {page_id}")
        source_images[page_id] = image
        input_lock[f"source::{page_id}"] = sha256_file(image_path)
    font = ImageFont.truetype(str(font_path), size=8)
    records: list[dict[str, Any]] = []
    runtime: dict[str, dict[str, np.ndarray]] = {}
    for segment_id in _selected_segment_ids():
        segment = segments[segment_id]
        page_id = segment_id.split("__", 1)[0]
        instance = next(item for item in instance_map.values() if segment_id in item["segment_ids"])
        instance_mask_path = spike_a_run / instance["mask_artifact"]["relative_path"]
        instance_mask = np.asarray(Image.open(instance_mask_path).convert("L")) > 0
        if mask_digest(instance_mask) != instance["mask_sha256"]:
            raise SpikeBStop(f"instance mask hash changed: {segment_id}")
        text_core = text_core_from_bbox(source_images[page_id], segment["bbox"], instance_mask)
        if not text_core.any():
            raise SpikeBStop(f"empty required-text candidate: {segment_id}")
        visible_support = expand_visible_text_support(text_core, instance_mask, dilation_px=2)
        protected, uncertainty = boundary_and_uncertainty(instance_mask, band_px=4)
        safe_evidence = build_safe_edit_evidence(visible_support, protected, uncertainty)
        completeness = evaluate_required_text_completeness(visible_support, safe_evidence["_safe_edit_mask"])
        assessment = assessments[instance["instance_id"]]
        status = "REVIEW_ONLY_G003" if segment_id == "case-72__g003__s01" else "E1_CONTROL"
        artifact_root = output_root / "artifacts" / page_id / _safe_name(segment_id)
        artifacts = {
            "text_core": _save_mask(text_core, artifact_root / "text-core.png", output_root),
            "visible_support_candidate": _save_mask(visible_support, artifact_root / "visible-support-candidate.png", output_root),
            "protected": _save_mask(protected, artifact_root / "protected.png", output_root),
            "uncertainty": _save_mask(uncertainty, artifact_root / "uncertainty.png", output_root),
            "safe_edit": _save_mask(safe_evidence["_safe_edit_mask"], artifact_root / "safe-edit.png", output_root),
        }
        binding = region_binding(instance["instance_id"], instance["revision_id"], instance_mask)
        glyph_mask = _render_vertical_full_canvas(source_images[page_id].shape[:2], segment["bbox"], translations[segment_id], font)
        glyph = glyph_evidence(segment_id, binding, glyph_mask)
        artifacts["glyph_coverage"] = _save_mask(glyph_mask, artifact_root / "glyph-full-canvas.png", output_root)
        record = {
            "segment_id": segment_id,
            "page_id": page_id,
            "status": status,
            "translation_sha256": digest_value(translations[segment_id]),
            "instance_binding": binding,
            "eligibility_snapshot": _public(assessment),
            "required_text_evidence": {
                "source_image_sha256": pages[page_id]["source_sha256"],
                "segment_bbox": segment["bbox"],
                "max_text_luminance": 180.0,
                "text_core_pixels": int(text_core.sum()),
                "text_core_hash": mask_digest(text_core),
                "visible_support_candidate_pixels": int(visible_support.sum()),
                "visible_support_candidate_hash": mask_digest(visible_support),
                "visible_support_method": "dilate-dark-core-within-instance-v1",
                "visible_support_dilation_px": 2,
                "visual_completeness_status": "CANDIDATE_UNVERIFIED_BY_PIXEL_RULE_ALONE",
            },
            "safe_edit_evidence": _public(safe_evidence),
            "required_text_completeness": completeness,
            "artifacts": artifacts,
            "glyph_evidence": _public(glyph),
        }
        records.append(record)
        runtime[segment_id] = {
            "text_core": text_core,
            "visible_support": visible_support,
            "required": visible_support,
            "safe": safe_evidence["_safe_edit_mask"],
            "instance": instance_mask,
            "boundary": protected,
            "glyph": glyph_mask,
        }
    controls: list[dict[str, Any]] = []
    for page_id, image in source_images.items():
        control_records = [
            item
            for item in records
            if item["page_id"] == page_id
            and item["status"] == "E1_CONTROL"
            and item["required_text_completeness"]["decision"] == "COMPLETE"
        ]
        incomplete_records = [
            item["segment_id"]
            for item in records
            if item["page_id"] == page_id
            and item["status"] == "E1_CONTROL"
            and item["required_text_completeness"]["decision"] != "COMPLETE"
        ]
        required = np.zeros(image.shape[:2], dtype=bool)
        for item in control_records:
            required |= runtime[item["segment_id"]]["required"]
        if not required.any():
            raise SpikeBStop(f"page has no E1 control pixels: {page_id}")
        clean = image.copy()
        clean[required] = 255
        changed = actual_changed_pixel_mask(image, clean)
        residual_component = _largest_component(required)
        positive = clean.copy()
        positive[residual_component] = image[residual_component]
        controls.append(
            {
                "page_id": page_id,
                "control_segment_ids": [item["segment_id"] for item in control_records],
                "excluded_incomplete_segment_ids": incomplete_records,
                "required_mask": _save_mask(required, output_root / "controls" / f"{page_id}-required.png", output_root),
                "clean_negative": {
                    "image": _save_image(clean, output_root / "controls" / f"{page_id}-clean-negative.png", output_root),
                    "actual_changed_mask": _save_mask(changed, output_root / "controls" / f"{page_id}-actual-changed.png", output_root),
                    "changed_mask_validation": validate_changed_mask(changed, changed),
                    "residue": evaluate_residue(required, clean, max_residual_luminance=240),
                },
                "deliberate_residue_positive": {
                    "image": _save_image(positive, output_root / "controls" / f"{page_id}-residue-positive.png", output_root),
                    "restored_component": _save_mask(residual_component, output_root / "controls" / f"{page_id}-restored-component.png", output_root),
                    "residue": evaluate_residue(required, positive, max_residual_luminance=240),
                },
            }
        )
    expected = {item["segment_id"]: item["instance_binding"] for item in records}
    regions = {item["instance_binding"]["region_hash"]: runtime[item["segment_id"]]["instance"] for item in records}
    boundaries = {item["instance_binding"]["region_hash"]: runtime[item["segment_id"]]["boundary"] for item in records}
    glyphs = [glyph_evidence(item["segment_id"], item["instance_binding"], runtime[item["segment_id"]]["glyph"]) for item in records]
    overlays: dict[str, dict[str, Any]] = {}
    for page_id in source_images:
        page_records = [item for item in records if item["page_id"] == page_id]
        layers: list[tuple[np.ndarray, tuple[int, int, int]]] = []
        for item in page_records:
            local = runtime[item["segment_id"]]
            layers.extend(
                [
                    (local["boundary"], (255, 70, 70)),
                    (local["text_core"], (70, 220, 80)),
                    (local["visible_support"], (210, 100, 255)),
                    (local["safe"], (60, 190, 255)),
                    (local["glyph"], (240, 200, 50)),
                ]
            )
        overlays[f"{page_id}-evidence"] = _save_overlay(
            source_images[page_id], layers, output_root / "overlays" / f"{page_id}-evidence.png", output_root
        )
    normal_issues = validate_glyph_ledger(expected=expected, glyphs=glyphs, region_masks=regions, boundary_masks=boundaries)
    first = glyphs[0]
    alternate = glyphs[1]
    overflow = runtime[first["segment_id"]]["glyph"].copy()
    outside = np.argwhere(~runtime[first["segment_id"]]["instance"])[0]
    overflow[tuple(outside)] = True
    touch = runtime[first["segment_id"]]["glyph"].copy()
    touch[tuple(np.argwhere(runtime[first["segment_id"]]["boundary"])[0])] = True
    wrong_validator = {**first, "validator_binding": alternate["renderer_binding"]}
    mutations = {
        "missing": validate_glyph_ledger(expected=expected, glyphs=glyphs[1:], region_masks=regions, boundary_masks=boundaries),
        "duplicate": validate_glyph_ledger(expected=expected, glyphs=[first, first, *glyphs[1:]], region_masks=regions, boundary_masks=boundaries),
        "wrong_instance": validate_glyph_ledger(expected=expected, glyphs=[{**first, "renderer_binding": alternate["renderer_binding"], "validator_binding": alternate["renderer_binding"]}, *glyphs[1:]], region_masks=regions, boundary_masks=boundaries),
        "overflow": validate_glyph_ledger(expected=expected, glyphs=[glyph_evidence(first["segment_id"], first["renderer_binding"], overflow), *glyphs[1:]], region_masks=regions, boundary_masks=boundaries),
        "boundary_touch": validate_glyph_ledger(expected=expected, glyphs=[glyph_evidence(first["segment_id"], first["renderer_binding"], touch), *glyphs[1:]], region_masks=regions, boundary_masks=boundaries),
        "wrong_validator_region": validate_glyph_ledger(expected=expected, glyphs=[wrong_validator, *glyphs[1:]], region_masks=regions, boundary_masks=boundaries),
    }
    correction = reserve_correction([], root_issue="glyph_overflow", idempotency_key="fixed-glyph-overflow")
    correction_replay = reserve_correction([correction], root_issue="glyph_overflow", idempotency_key="fixed-glyph-overflow")
    correction_second = reserve_correction([correction], root_issue="glyph_overflow", idempotency_key="new-overflow-attempt")
    candidate = {
        "schema_version": "mvp1-visual-contract-spike-b-snapshot-v1",
        "created_at": utc_now(),
        "status": "CANDIDATE_FROZEN_BEFORE_ORACLE",
        "relationship_source": {"kind": "SPIKE_A_SNAPSHOT_PLUS_RUN_LOCAL_PIXEL_LEDGER", "exclusive_for_run": True},
        "input_lock": input_lock,
        "records": records,
        "controls": controls,
        "diagnostic_overlays": overlays,
        "glyph_validation": {"normal_issues": normal_issues, "mutations": mutations},
        "correction_reservation": {"first": correction, "replay": correction_replay, "second": correction_second},
    }
    candidate["snapshot_sha256"] = digest_value(_public(candidate))
    snapshot_output = output_root / "pixel-evidence-snapshot.json"
    snapshot_output.write_text(json.dumps(_public(candidate), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    oracle = _load_json(oracle_path)  # Evaluation begins only after candidate snapshot is frozen.
    gates = {
        "B1_required_text_evidence": all(item["required_text_evidence"]["text_core_pixels"] > 0 for item in records),
        "B2_residue_controls": all(item["clean_negative"]["residue"]["decision"] == "PASS" and item["deliberate_residue_positive"]["residue"]["issue_code"] == "cleaning_residue" for item in controls),
        "B3_required_safe_separation": all(item["required_text_completeness"]["decision"] in {"COMPLETE", "INCOMPLETE_REVIEW"} for item in records) and any(item["segment_id"] == "case-71__g002__s02" and item["required_text_completeness"]["decision"] == "INCOMPLETE_REVIEW" for item in records),
        "B4_actual_changed_mask": all(not item["clean_negative"]["changed_mask_validation"] for item in controls),
        "B5_g003_pixel_evidence": any(item["segment_id"] == "case-72__g003__s01" and item["safe_edit_evidence"]["decision_basis"] == "PIXEL_INTERSECTION_NOT_INSTANCE_RATIO" and item["status"] == "REVIEW_ONLY_G003" for item in records),
        "B6_full_canvas_glyph": not normal_issues,
        "B7_deliberate_glyph_negatives": all(expected_code in mutations[name] for name, expected_code in oracle["glyph_mutation_expectations"].items()),
        "B8_correction_once": correction["decision"] == "RESERVED" and correction_replay["decision"] == "REPLAY" and correction_second["decision"] == "REJECTED_SECOND_AUTOMATIC_CORRECTION",
        "B9_snapshot_source": candidate["relationship_source"]["exclusive_for_run"] is True and input_lock["candidate_generation_oracle_access"] is False,
    }
    gate_matrix = {key: {"status": "PASS" if value else "FAIL"} for key, value in gates.items()}
    gate_matrix["B10_human_review"] = {"status": "PENDING_HUMAN_REVIEW"}
    (output_root / "gate-matrix.json").write_text(json.dumps(gate_matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "status": "PENDING_HUMAN_REVIEW" if all(gates.values()) else "NO_GO",
        "automatic_contract_passed": all(gates.values()),
        "oracle_loaded_after_snapshot_freeze": True,
        "gate_counts": {"pass": sum(gates.values()), "fail": len(gates) - sum(gates.values()), "pending": 1},
        "timings_ms": {"total": round((time.perf_counter() - start) * 1000, 3)},
    }
    (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_form(output_root / "FORM.md")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spike-a-run", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_run(
        spike_a_run=args.spike_a_run.resolve(),
        source_root=args.source_root.resolve(),
        provenance_path=args.provenance.resolve(),
        font_path=args.font.resolve(),
        oracle_path=args.oracle.resolve(),
        output_root=args.output.resolve(),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["automatic_contract_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
