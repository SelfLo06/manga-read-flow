#!/usr/bin/env python3
"""Offline-only evaluator for frozen PhysicalBoundaryEvidence v0.2 candidates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
RUN_ROOT = ROOT / "data/local/runs/150-cleaning/physical-boundary-v0.2"
OUTPUT = RUN_ROOT / "20260719T0735-offline-evaluation-v0.2"
SPECS = (
    ("page_edge_bubble_001", "20260719T0720-page-edge-spike-v0.2", ROOT / "data/local/datasets/150-cleaning/page-edge-bubble-v0.1/oracles/page_edge_bubble_v0.1/accepted-v1"),
    ("black2_touching_bubbles_001", "20260719T0710-black2-spike-v0.2", ROOT / "data/local/datasets/150-cleaning/page-edge-bubble-v0.1/oracles/black2_touching_bubbles_001/accepted-v1"),
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def mask(path: Path) -> np.ndarray:
    value = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if value is None:
        raise RuntimeError(f"unreadable mask: {path}")
    return value > 0


def verify_oracle(root: Path) -> tuple[dict, dict]:
    manifest = read(root / "ORACLE_MANIFEST.json")
    files = manifest["files"]
    records = ((path, expected) for path, expected in files.items()) if isinstance(files, dict) else ((item["path"], item["sha256"]) for item in files)
    for relative, expected in records:
        path = root / relative
        if not path.is_file() or sha(path) != expected:
            raise RuntimeError(f"oracle hash mismatch: {path}")
    return manifest, read(root / "association.json")


def verify_run(root: Path, case_id: str) -> tuple[dict, dict, Path]:
    manifest = read(root / "MANIFEST.json")
    for relative, value in manifest["candidate_artifacts"].items():
        path = root / relative
        if not path.is_file() or sha(path) != value["sha256"]:
            raise RuntimeError(f"candidate artifact hash mismatch: {path}")
    physical_path = root / "artifacts" / case_id / "physical_boundary_candidates.json"
    return manifest, read(physical_path), root / "artifacts" / case_id


def ratio(left: np.ndarray, right: np.ndarray) -> dict:
    intersection = int((left & right).sum())
    union = int((left | right).sum())
    return {"intersection_pixels": intersection, "union_pixels": union, "iou": 0.0 if union == 0 else round(intersection / union, 8), "candidate_pixels": int(left.sum()), "oracle_pixels": int(right.sum())}


def full_from_roi(local: np.ndarray, roi: list[int], shape: tuple[int, int]) -> np.ndarray:
    value = np.zeros(shape, dtype=bool); x0, y0, x1, y1 = roi; value[y0:y1, x0:x1] = local; return value


def evaluate(case_id: str, candidate_run_id: str, oracle_root: Path) -> dict:
    candidate_run = RUN_ROOT / candidate_run_id
    run_manifest, candidate, artifacts = verify_run(candidate_run, case_id)
    oracle_manifest, association = verify_oracle(oracle_root)
    cases = read(oracle_root / "cases.json")
    source = ROOT / cases["source_path"]
    if sha(source) != cases["source_sha256"] or candidate["source_sha256"] != cases["source_sha256"]:
        raise RuntimeError(f"source binding mismatch: {case_id}")
    with Image.open(source) as image: shape = (image.height, image.width)
    roi = cases["roi_xyxy"]
    bubbles = association["bubbles"]
    # Each oracle text group identifies its automatic candidate only after generation,
    # using frozen Detection geometry and required-mask overlap.
    detection = read(artifacts / "detection/detection_candidates.json")["candidates"]
    grouping = read(artifacts / "grouping/grouping_assignments.json")
    group_by_fragment = {x["candidate_id"]: x["text_group_id"] for x in grouping["candidate_assignments"]}
    target_groups: dict[str, set[str]] = {}
    for text in association["text_groups"]:
        required_name = text.get("required_mask") or text.get("text_required_mask")
        required = full_from_roi(mask(oracle_root / required_name), roi, shape)
        fragments = set()
        for item in detection:
            box = item["bbox_full_page"]; predicted = np.zeros(shape, dtype=bool); x, y, w, h = (int(box[k]) for k in ("x", "y", "width", "height")); predicted[y:y+h, x:x+w] = True
            if (predicted & required).any(): fragments.add(item["candidate_id"])
        target_groups[text["text_group_id"]] = {group_by_fragment[x] for x in fragments}
    physical = candidate["bubble_instance_candidates"]
    assignments = {}
    interior_metrics = {}
    contour_metrics = {}
    for bubble in bubbles:
        expected_text = bubble["text_group_ids"][0]
        automatic_groups = target_groups[expected_text]
        matched = [item for item in physical if automatic_groups & set(item["text_group_ids"])]
        assignments[expected_text] = {"automatic_text_group_ids": sorted(automatic_groups), "bubble_candidate_ids": [x["bubble_instance_candidate_id"] for x in matched]}
        oracle_interior_name = bubble.get("exclusive_interior_mask") or bubble.get("interior_mask")
        oracle_contour_name = bubble.get("visible_boundary_mask")
        if len(matched) == 1:
            interior_metrics[expected_text] = ratio(mask(artifacts / matched[0]["interior_mask"]), full_from_roi(mask(oracle_root / oracle_interior_name), roi, shape))
            contour_metrics[expected_text] = ratio(mask(artifacts / matched[0]["visible_contour_candidate"]), full_from_roi(mask(oracle_root / oracle_contour_name), roi, shape))
    assigned_candidate_sets = [set(x["bubble_candidate_ids"]) for x in assignments.values()]
    merge = bool(len(assigned_candidate_sets) == 2 and assigned_candidate_sets[0] & assigned_candidate_sets[1])
    target_count_ok = all(len(x["bubble_candidate_ids"]) == 1 for x in assignments.values()) and len({item for x in assignments.values() for item in x["bubble_candidate_ids"]}) == len(bubbles)
    page_left = any("left" in item["page_truncation_candidates"] for item in physical if item["bubble_instance_candidate_id"] in {x for row in assignments.values() for x in row["bubble_candidate_ids"]})
    truncation_required = case_id == "page_edge_bubble_001"
    checks = {"target_instance_count": "PASS" if target_count_ok else "FAIL", "assignment": "PASS" if target_count_ok else "FAIL", "black2_merge": "FAIL" if merge else "PASS", "page_truncated_left": "PASS" if not truncation_required or page_left else "FAIL"}
    verdict = "PASS" if all(value == "PASS" for value in checks.values()) else "FAIL"
    source_rgb = np.asarray(Image.open(source).convert("RGB"), dtype=np.uint8)
    overlay = source_rgb.copy()
    for item in physical:
        interior = mask(artifacts / item["interior_mask"]); overlay[interior] = (0.65 * overlay[interior] + 0.35 * np.array((0, 220, 90))).astype(np.uint8)
    for bubble in bubbles:
        name = bubble.get("visible_boundary_mask"); boundary = full_from_roi(mask(oracle_root / name), roi, shape); overlay[boundary] = (255, 30, 30)
    output_overlay = OUTPUT / "review_overlays" / f"{case_id}-oracle-vs-candidate.png"; output_overlay.parent.mkdir(parents=True, exist_ok=True); Image.fromarray(overlay).save(output_overlay)
    return {"case_id": case_id, "candidate_run_id": candidate_run_id, "checks": checks, "verdict": verdict, "expected_bubble_count": len(bubbles), "target_assignments": assignments, "interior_metrics": interior_metrics, "contour_metrics": contour_metrics, "page_truncation_candidates": [x["page_truncation_candidates"] for x in physical], "unknown_or_ambiguity": candidate["unknown_or_ambiguity"], "contact_or_latent_separator_candidates": candidate["contact_or_latent_separator_candidates"], "candidate_provenance": candidate["provenance"], "oracle_manifest_sha256": sha(oracle_root / "ORACLE_MANIFEST.json"), "review_overlay": str(output_overlay.relative_to(OUTPUT))}


def main() -> int:
    if OUTPUT.exists(): raise RuntimeError(f"refusing to overwrite evaluation: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    results = [evaluate(*spec) for spec in SPECS]
    overall = "PASS_WITHIN_CONTROLS" if all(x["verdict"] == "PASS" for x in results) else "FAIL"
    first = next((x for x in results if x["verdict"] == "FAIL"), None)
    first_divergence = None if first is None else {"stage": "physical_boundary_candidate_generation", "type": "page_truncation_left_not_expressed" if first["case_id"] == "page_edge_bubble_001" else "bubble_instance_assignment_mismatch", "case_id": first["case_id"]}
    write = lambda p, v: p.write_text(json.dumps(v, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write(OUTPUT / "METRICS.json", {"cases": results, "overall_verdict": overall})
    write(OUTPUT / "FIRST_DIVERGENCE.json", {"first_observed_divergence": first_divergence, "earliest_execution_gap": None, "execution_failure": None, "causality": {"established": False}})
    (OUTPUT / "REPORT.md").write_text(f"# PhysicalBoundaryEvidence v0.2 offline evaluation\n\n## Observation\n\nCandidates were read from frozen runs and evaluated only after generation.\n\n## Verdict\n\n`{overall}`.\n\n## Project Decision\n\nUnchanged: this does not close the M1 Cleaning gate or authorize Cleaner, active pointers, or general BubbleInstance capability.\n", encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__": raise SystemExit(main())
