#!/usr/bin/env python3
"""Generate Stage A physical-boundary review material from frozen Slice 3 bytes.

This is intentionally a read-only evidence tool.  It never invokes a Cleaner,
never edits Slice 3 output, and writes only beneath its own ignored run root.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
FROZEN = ROOT / "data/local/runs/150-cleaning/full-page-v0.1/slice-3/run-v0.5/case-72"
DEFAULT_OUTPUT = ROOT / "data/local/runs/150-cleaning/physical-boundary-v0.1/stage-a-run-v0.2"
EVIDENCE_SPEC = importlib.util.spec_from_file_location("physical_boundary_evidence", Path(__file__).with_name("evidence.py"))
assert EVIDENCE_SPEC and EVIDENCE_SPEC.loader
EVIDENCE = importlib.util.module_from_spec(EVIDENCE_SPEC)
EVIDENCE_SPEC.loader.exec_module(EVIDENCE)
classify_a1 = EVIDENCE.classify_a1
classify_a2 = EVIDENCE.classify_a2
classify_a5 = EVIDENCE.classify_a5
color_evidence = EVIDENCE.color_evidence
components = EVIDENCE.components
mask_hash = EVIDENCE.mask_hash
text_core = EVIDENCE.text_core


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_mask(path: Path) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise RuntimeError(f"unreadable mask: {path}")
    return mask > 0


def load_rgb(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"unreadable source: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def save_mask(mask: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.where(mask, 255, 0).astype(np.uint8)).save(path)


def overlay(source: np.ndarray, layers: list[tuple[np.ndarray, tuple[int, int, int]]]) -> np.ndarray:
    result = source.astype(np.float32).copy()
    for mask, color in layers:
        result[mask] = 0.55 * result[mask] + 0.45 * np.asarray(color, dtype=np.float32)
    return np.clip(result, 0, 255).astype(np.uint8)


def crop_bounds(mask: np.ndarray, padding: int = 8) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    if not len(xs):
        raise RuntimeError("component unexpectedly empty")
    return max(0, int(xs.min()) - padding), max(0, int(ys.min()) - padding), min(mask.shape[1], int(xs.max()) + padding + 1), min(mask.shape[0], int(ys.max()) + padding + 1)


def save_crop(image: np.ndarray, bounds: tuple[int, int, int, int], path: Path, scale: int = 1) -> None:
    x0, y0, x1, y1 = bounds
    crop = Image.fromarray(image[y0:y1, x0:x1])
    if scale > 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(path)


def write_form_and_lock(output: Path) -> None:
    summary = json.loads((output / "stage-a-summary.json").read_text(encoding="utf-8"))
    form = ["# Stage A 人工像素／视觉标注 FORM", "", "此表由维护者填写；agent 不得代填。颜色分层只用于审计，不改变候选算法或阈值。", "", "图例：紫=旧 required，绿=候选 required_text，橙=unresolved，红=physical ridge，青=当前争议 component。", ""]
    for target in summary["targets"]:
        for component in target["components"]:
            component_id = component["component_id"]
            ordinal = component_id.rsplit("::", 1)[-1]
            base = f"targets/{target['target']}/components/component-{ordinal}"
            form += [
                f"## {component_id}",
                "",
                f"像素数：`{component['pixels']}`；protected：`{component['protected_pixels']}`；uncertainty-only：`{component['uncertainty_only_pixels']}`。",
                "",
                "### 原图（4× nearest-neighbor）",
                "",
                f"![原图放大]({base}/original-4x.png)",
                "",
                "### 当前基线与候选分类",
                "",
                f"![A0 基线]({base}/baseline-overlay.png)",
                "",
                f"![A1 text-seeded]({base}/a1-overlay.png)",
                "",
                f"![A2 boundary-aware]({base}/a2-overlay.png)",
                "",
                f"![A5 color-aware text-seeded]({base}/a5-overlay.png)",
                "",
                "COMPONENT_ID =",
                "HUMAN_CLASS = TEXT_EDGE / BUBBLE_BOUNDARY / MIXED / UNCERTAIN",
                "COLOR_STRATUM = DEEP_BLUE / ORANGE / ANTIALIAS_EDGE / MULTICOLOR / OTHER / UNSURE",
                "BOUNDARY_DAMAGE_RISK = LOW / HIGH / UNKNOWN",
                "ALLOW_AS_REQUIRED_TEXT = YES / NO / UNSURE",
                "NOTES =",
                "",
            ]
    (output / "FORM-stage-a.md").write_text("\n".join(form) + "\n", encoding="utf-8")
    locked = {str(path.relative_to(output)): digest(path) for path in sorted(output.rglob("*")) if path.is_file() and path.name != "review-material-lock.json"}
    (output / "review-material-lock.json").write_text(json.dumps(locked, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def freeze_human_review(output: Path) -> None:
    """Lock a completed human FORM without modifying the maintainer's labels."""
    summary = json.loads((output / "stage-a-summary.json").read_text(encoding="utf-8"))
    form_path = output / "FORM-stage-a.md"
    form = form_path.read_text(encoding="utf-8")
    required_ids = [item["component_id"] for target in summary["targets"] for item in target["components"]]
    reviews = []
    for component_id in required_ids:
        heading = re.escape(f"## {component_id}")
        match = re.search(heading + r"(?P<body>.*?)(?=\n## |\Z)", form, re.S)
        if match is None:
            raise RuntimeError(f"missing human form section: {component_id}")
        body = match.group("body")
        fields = {}
        for field in ("COMPONENT_ID", "HUMAN_CLASS", "COLOR_STRATUM", "BOUNDARY_DAMAGE_RISK", "ALLOW_AS_REQUIRED_TEXT"):
            value = re.search(rf"^{field}\s*=\s*(.+?)\s*$", body, re.M)
            if value is None or not value.group(1).strip() or "/" in value.group(1):
                raise RuntimeError(f"incomplete human field {field}: {component_id}")
            fields[field.lower()] = value.group(1).strip()
        if fields["component_id"].strip() != component_id:
            raise RuntimeError(f"human component id mismatch: {component_id}")
        reviews.append({"component_id": component_id, **fields})
    material_lock = json.loads((output / "review-material-lock.json").read_text(encoding="utf-8"))
    lock = {
        "schema": "physical-boundary-human-review-lock-v0.1",
        "form_sha256": digest(form_path),
        "pre_label_material_lock_sha256": digest(output / "review-material-lock.json"),
        "pre_label_material_count": len(material_lock),
        "reviews": reviews,
    }
    (output / "human-review-lock.json").write_text(json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target", action="append", dest="targets", default=["case-72__g002__s01", "case-72__g004__s01"])
    parser.add_argument("--rewrite-form", action="store_true", help="only rewrite the review form and its manifest from an existing Stage A summary")
    parser.add_argument("--freeze-human-review", action="store_true", help="validate and hash-lock a completed maintainer FORM without rewriting it")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.rewrite_form:
        if not (output / "stage-a-summary.json").is_file():
            raise RuntimeError("--rewrite-form requires an existing Stage A summary")
        write_form_and_lock(output)
        return
    if args.freeze_human_review:
        if not (output / "stage-a-summary.json").is_file():
            raise RuntimeError("--freeze-human-review requires an existing Stage A summary")
        freeze_human_review(output)
        return
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"refusing to overwrite existing evidence: {output}")
    output.mkdir(parents=True)
    summary = json.loads((FROZEN / "summary.json").read_text(encoding="utf-8"))
    source_path = Path(summary["source"]["path"])
    source = load_rgb(source_path)
    input_lock: dict[str, object] = {"source": {"path": str(source_path), "sha256": digest(source_path)}, "frozen_summary_sha256": digest(FROZEN / "summary.json"), "targets": {}}
    target_summaries = []
    for target in args.targets:
        evidence = FROZEN / "evidence" / target
        paths = {name: evidence / f"{name}.png" for name in ("instance", "visible", "safe", "protected", "uncertainty")}
        masks = {name: load_mask(path) for name, path in paths.items()}
        if any(mask.shape != source.shape[:2] for mask in masks.values()):
            raise RuntimeError(f"shape mismatch for {target}")
        old_required = masks["visible"]
        unsafe = old_required & ~masks["safe"]
        a1 = classify_a1(source, old_required, masks["instance"], masks["protected"], masks["uncertainty"])
        a2 = classify_a2(source, old_required, masks["instance"], masks["protected"], masks["uncertainty"])
        a5 = classify_a5(source, old_required, masks["instance"], masks["protected"], masks["uncertainty"])
        colors = color_evidence(source, old_required, masks["instance"], masks["protected"], masks["uncertainty"])
        target_dir = output / "targets" / target
        target_dir.mkdir(parents=True)
        input_lock["targets"][target] = {name: {"path": str(path), "sha256": digest(path), "mask_hash": mask_hash(masks[name])} for name, path in paths.items()}
        for name, mask in {**masks, "text-core": text_core(source, old_required), "unsafe": unsafe, "a1-ridge": a1.boundary_ridge, "a1-required-text": a1.required_text, "a1-unresolved": a1.unresolved_uncertain, "a2-ridge": a2.boundary_ridge, "a2-required-text": a2.required_text, "a2-unresolved": a2.unresolved_uncertain, "a5-ridge": a5.boundary_ridge, "a5-required-text": a5.required_text, "a5-unresolved": a5.unresolved_uncertain}.items():
            save_mask(mask, target_dir / "masks" / f"{name}.png")
        combined = overlay(source, [(old_required, (180, 0, 255)), (masks["safe"], (0, 220, 80)), (masks["protected"], (255, 40, 40)), (masks["uncertainty"], (255, 180, 0)), (unsafe, (0, 220, 255))])
        (target_dir / "overlays").mkdir(parents=True, exist_ok=True)
        Image.fromarray(combined).save(target_dir / "overlays" / "baseline.png")
        components_summary = []
        for ordinal, (_, component) in enumerate(components(unsafe), start=1):
            bounds = crop_bounds(component)
            prefix = target_dir / "components" / f"component-{ordinal:02d}"
            save_crop(source, bounds, prefix / "original.png")
            save_crop(source, bounds, prefix / "original-4x.png", 4)
            for name, image in {
                "baseline-overlay.png": combined,
                "a1-overlay.png": overlay(source, [(component, (0, 220, 255)), (a1.required_text, (0, 220, 80)), (a1.unresolved_uncertain, (255, 160, 0)), (a1.boundary_ridge, (255, 30, 30))]),
                "a2-overlay.png": overlay(source, [(component, (0, 220, 255)), (a2.required_text, (0, 220, 80)), (a2.unresolved_uncertain, (255, 160, 0)), (a2.boundary_ridge, (255, 30, 30))]),
                "a5-overlay.png": overlay(source, [(component, (0, 220, 255)), (a5.required_text, (0, 220, 80)), (a5.unresolved_uncertain, (255, 160, 0)), (a5.boundary_ridge, (255, 30, 30))]),
            }.items():
                save_crop(image, bounds, prefix / name)
            components_summary.append({"component_id": f"{target}::unsafe::{ordinal:02d}", "pixels": int(component.sum()), "bounds_xyxy": bounds, "protected_pixels": int((component & masks["protected"]).sum()), "uncertainty_only_pixels": int((component & masks["uncertainty"] & ~masks["protected"]).sum()), "a1_required_text": int((component & a1.required_text).sum()), "a1_unresolved": int((component & a1.unresolved_uncertain).sum()), "a2_required_text": int((component & a2.required_text).sum()), "a2_unresolved": int((component & a2.unresolved_uncertain).sum()), "a5_required_text": int((component & a5.required_text).sum()), "a5_unresolved": int((component & a5.unresolved_uncertain).sum())})
        (target_dir / "color-evidence.json").write_text(json.dumps(colors, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        target_summaries.append({"target": target, "a0": {"required": int(old_required.sum()), "safe": int(masks["safe"].sum()), "unsafe": int(unsafe.sum()), "protected_overlap": int((old_required & masks["protected"]).sum()), "uncertainty_overlap": int((old_required & masks["uncertainty"]).sum())}, "components": components_summary, "a1": {"required_text": int(a1.required_text.sum()), "unresolved": int(a1.unresolved_uncertain.sum()), "proven_boundary": 0}, "a2": {"required_text": int(a2.required_text.sum()), "unresolved": int(a2.unresolved_uncertain.sum()), "proven_boundary": 0}, "a5": {"required_text": int(a5.required_text.sum()), "unresolved": int(a5.unresolved_uncertain.sum()), "proven_boundary": 0, "color_evidence": colors}})
    (output / "input-lock.json").write_text(json.dumps(input_lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "stage-a-summary.json").write_text(json.dumps({"stage": "A", "source_sha256": digest(source_path), "targets": target_summaries, "candidate_policy": "physical-boundary-evidence-v0.1", "status": "PENDING_HUMAN_LABELS"}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_form_and_lock(output)


if __name__ == "__main__":
    main()
