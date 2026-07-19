"""Immutable-run helpers for the page-edge bubble first-divergence experiment.

This is deliberately an experiment adapter.  It neither creates product
artifacts nor updates an active pointer.  In particular, automatic execution
receives a :class:`Case` only; oracle loading is a distinct evaluator step.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any

import cv2
import numpy as np
from PIL import Image


CASE_SCHEMA = "page-edge-bubble-case-v1"
ORACLE_SCHEMA = "page-edge-bubble-accepted-oracle-v1"
SEMANTIC_FILES = (
    "association.json", "bubble_interior_mask.png", "visible_boundary_mask.png",
    "page_truncation_mask.png", "text_core_mask.png", "text_fringe_mask.png",
    "text_required_mask.png",
)
DERIVED_CANDIDATE_FILES = (
    "safe_interior_mask.png", "protected_content_mask.png", "cleaner_write_mask.png",
)
VISUAL_REFERENCE_FILES = (
    "visual_reference_roi.png", "visual_reference_full_page.png", "oracle_overlay.png",
    "review_sheet.png", "roi_input.png",
)


class ExperimentStop(RuntimeError):
    """A fail-closed experiment-contract violation."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def mask_digest(mask: np.ndarray) -> str:
    if mask.dtype != np.bool_ or mask.ndim != 2:
        raise ExperimentStop("mask must be a 2D bool array")
    return sha256(canonical({"shape": list(mask.shape), "encoding": "packed-bool-v1"}) + np.packbits(mask).tobytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExperimentStop(f"invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ExperimentStop(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_mask(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ExperimentStop(f"unreadable mask: {path}")
    return (image > 0).astype(np.bool_)


def write_mask(path: Path, mask: np.ndarray) -> None:
    if mask.dtype != np.bool_ or mask.ndim != 2:
        raise ExperimentStop("only 2D bool masks can be written")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), mask.astype(np.uint8) * 255):
        raise ExperimentStop(f"cannot write mask: {path}")


def read_rgb(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ExperimentStop(f"unreadable image: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def write_rgb(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
        raise ExperimentStop(f"cannot write image: {path}")


@dataclass(frozen=True)
class Case:
    case_id: str
    source: Path
    source_relative: str
    source_sha256: str
    roi: tuple[int, int, int, int]
    case_path: Path


@dataclass(frozen=True)
class Oracle:
    root: Path
    case_id: str
    source_sha256: str
    roi: tuple[int, int, int, int]
    masks: dict[str, np.ndarray]
    association: dict[str, Any]
    manifest_sha256: str


def load_case(case_path: Path, repo_root: Path) -> Case:
    data = read_json(case_path)
    if data.get("schema_version") != CASE_SCHEMA or data.get("algorithm_input") != "full_page":
        raise ExperimentStop("case must require full_page algorithm input")
    roi = data.get("roi_xyxy")
    if not isinstance(roi, list) or len(roi) != 4 or any(type(x) is not int for x in roi):
        raise ExperimentStop("case ROI must contain four integers")
    x0, y0, x1, y1 = roi
    if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
        raise ExperimentStop("case ROI is invalid")
    source_relative = data.get("source_path")
    if not isinstance(source_relative, str) or Path(source_relative).is_absolute():
        raise ExperimentStop("source must be repository relative")
    source = (repo_root / source_relative).resolve()
    try:
        source.relative_to((repo_root / "data/local/sources").resolve())
    except ValueError as error:
        raise ExperimentStop("source escapes local source root") from error
    if not source.is_file() or digest(source) != data.get("source_sha256"):
        raise ExperimentStop(f"source hash mismatch: {data.get('case_id')}")
    with Image.open(source) as image:
        if x1 > image.width or y1 > image.height:
            raise ExperimentStop("ROI exceeds source bounds")
    return Case(str(data["case_id"]), source, source_relative, str(data["source_sha256"]), (x0, y0, x1, y1), case_path)


def _oracle_manifest(case: Case, root: Path, review_timestamp: str) -> dict[str, Any]:
    association = read_json(root / "association.json")
    if association.get("case_id") != case.case_id:
        raise ExperimentStop("oracle/case id mismatch")
    coordinate = association.get("coordinate_space", {})
    if coordinate.get("mask_space") != "roi_local" or tuple(coordinate.get("roi_xyxy_full_page", ())) != case.roi:
        raise ExperimentStop("oracle coordinate space or ROI mismatch")
    dimensions: dict[str, list[int]] = {}
    file_hashes: dict[str, str] = {}
    for name in (*SEMANTIC_FILES, *DERIVED_CANDIDATE_FILES, *VISUAL_REFERENCE_FILES, "VALIDATION.json", "README.md"):
        path = root / name
        if not path.is_file():
            raise ExperimentStop(f"oracle file missing: {name}")
        file_hashes[name] = digest(path)
        if name.endswith("_mask.png"):
            mask = read_mask(path)
            dimensions[name] = [int(mask.shape[1]), int(mask.shape[0])]
    expected = [case.roi[2] - case.roi[0], case.roi[3] - case.roi[1]]
    if any(size != expected for size in dimensions.values()):
        raise ExperimentStop("oracle mask dimensions do not match ROI")
    return {
        "schema_version": ORACLE_SCHEMA,
        "case_id": case.case_id,
        "source": {"path": case.source_relative, "sha256": case.source_sha256},
        "roi_xyxy": list(case.roi), "coordinate_space": "roi_local",
        "oracle_version": "accepted-v1", "review_status": "human_reviewed_accepted",
        "review_timestamp": review_timestamp, "files": file_hashes,
        "mask_dimensions": dimensions,
        "classifications": {
            "semantic_oracle": list(SEMANTIC_FILES),
            "derived_authorization_candidate": list(DERIVED_CANDIDATE_FILES),
            "visual_reference": list(VISUAL_REFERENCE_FILES),
        },
    }


def freeze_candidate_as_accepted(case: Case, candidate: Path, accepted: Path, *, review_timestamp: str | None = None) -> dict[str, Any]:
    """Copy a reviewed candidate once; never alters either source or accepted data."""
    if accepted.exists():
        raise ExperimentStop(f"accepted oracle already exists: {accepted}")
    if not candidate.is_dir():
        raise ExperimentStop(f"candidate oracle absent: {candidate}")
    shutil.copytree(candidate, accepted)
    try:
        association_path = accepted / "association.json"
        association = read_json(association_path)
        association["status"] = "human_reviewed_accepted"
        association["review"] = {"status": "human_reviewed_accepted", "accepted_at": review_timestamp or utc_now()}
        write_json(association_path, association)
        validation_path = accepted / "VALIDATION.json"
        validation = read_json(validation_path)
        validation["status"] = "human_reviewed_accepted"
        validation["review_status"] = "human_reviewed_accepted"
        write_json(validation_path, validation)
        readme = accepted / "README.md"
        readme.write_text("# Page-edge bubble accepted oracle v1\n\nStatus: `human_reviewed_accepted`. Semantic masks are the human-reviewed oracle; authorization masks remain derived candidates.\n", encoding="utf-8")
        manifest = _oracle_manifest(case, accepted, review_timestamp or utc_now())
        write_json(accepted / "ORACLE_MANIFEST.json", manifest)
        return manifest
    except BaseException:
        # A partial accepted directory is unsafe to reuse, so make the failed copy
        # visibly invalid rather than silently attempting a replacement.
        raise


def load_accepted_oracle(case: Case, accepted: Path) -> Oracle:
    manifest_path = accepted / "ORACLE_MANIFEST.json"
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != ORACLE_SCHEMA or manifest.get("review_status") != "human_reviewed_accepted":
        raise ExperimentStop("oracle is not human_reviewed_accepted")
    if manifest.get("case_id") != case.case_id or manifest.get("source", {}).get("sha256") != case.source_sha256 or tuple(manifest.get("roi_xyxy", ())) != case.roi:
        raise ExperimentStop("accepted oracle does not bind to this case/source/ROI")
    expected = [case.roi[2] - case.roi[0], case.roi[3] - case.roi[1]]
    for name, expected_hash in manifest.get("files", {}).items():
        path = accepted / name
        if not path.is_file() or digest(path) != expected_hash:
            raise ExperimentStop(f"accepted oracle hash mismatch: {name}")
    masks = {name.removesuffix("_mask.png"): read_mask(accepted / name) for name in SEMANTIC_FILES if name.endswith("_mask.png")}
    if any([int(mask.shape[1]), int(mask.shape[0])] != expected for mask in masks.values()):
        raise ExperimentStop("accepted oracle mask dimensions mismatch")
    source = read_rgb(case.source)
    x0, y0, x1, y1 = case.roi
    roi_input = cv2.cvtColor(cv2.imread(str(accepted / "roi_input.png"), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    if roi_input.shape != source[y0:y1, x0:x1].shape or not np.array_equal(roi_input, source[y0:y1, x0:x1]):
        raise ExperimentStop("oracle ROI is not an exact source crop")
    return Oracle(accepted, case.case_id, case.source_sha256, case.roi, masks, read_json(accepted / "association.json"), digest(manifest_path))


def roi_to_full(mask: np.ndarray, case: Case, shape: tuple[int, int]) -> np.ndarray:
    if mask.shape != (case.roi[3] - case.roi[1], case.roi[2] - case.roi[0]):
        raise ExperimentStop("ROI mask shape mismatch")
    result = np.zeros(shape, dtype=np.bool_)
    x0, y0, x1, y1 = case.roi
    result[y0:y1, x0:x1] = mask
    return result


def full_to_roi(mask: np.ndarray, case: Case) -> np.ndarray:
    """Return the deterministic inverse crop for a full-page mask."""
    if mask.dtype != np.bool_ or mask.ndim != 2:
        raise ExperimentStop("full-page mask must be a 2D bool array")
    x0, y0, x1, y1 = case.roi
    if x1 > mask.shape[1] or y1 > mask.shape[0]:
        raise ExperimentStop("ROI exceeds full-page mask")
    return mask[y0:y1, x0:x1].copy()


def derive_authorization(oracle: Oracle, *, boundary_radius: int = 2, fringe_radius: int = 1) -> dict[str, np.ndarray | dict[str, Any]]:
    if boundary_radius < 0 or fringe_radius < 0:
        raise ExperimentStop("authorization radii cannot be negative")
    interior = oracle.masks["bubble_interior"]
    visible = oracle.masks["visible_boundary"]
    truncation = oracle.masks["page_truncation"]
    required = oracle.masks["text_required"]
    fringe = oracle.masks["text_fringe"]
    kernel = np.ones((boundary_radius * 2 + 1, boundary_radius * 2 + 1), np.uint8)
    protected = cv2.dilate((visible | truncation).astype(np.uint8), kernel).astype(bool)
    safe = interior & ~protected
    cleanup = cv2.dilate((required | fringe).astype(np.uint8), np.ones((fringe_radius * 2 + 1, fringe_radius * 2 + 1), np.uint8)).astype(bool)
    write = cleanup & safe
    return {
        "safe": safe, "protected": protected, "write": write,
        "rules": {
            "boundary_protection_radius_px": boundary_radius,
            "text_fringe_cleanup_radius_px": fringe_radius,
            "morphology_kernel": "square", "clipping_rule": "bubble_interior AND NOT protected",
            "unknown_handling": "no unknown semantic oracle supplied; unknown is never authorized",
            "page_truncation_handling": "page_truncation is included in protected before clipping",
            "inpaint_influence_allowance_px": 0,
        },
    }


def binary_metrics(predicted: np.ndarray, expected: np.ndarray) -> dict[str, Any]:
    if predicted.shape != expected.shape:
        raise ExperimentStop("metric masks shape mismatch")
    tp, fp, fn = int((predicted & expected).sum()), int((predicted & ~expected).sum()), int((~predicted & expected).sum())
    return {"tp": tp, "fp": fp, "fn": fn, "precision": None if tp + fp == 0 else round(tp / (tp + fp), 8), "recall": None if tp + fn == 0 else round(tp / (tp + fn), 8), "iou": None if tp + fp + fn == 0 else round(tp / (tp + fp + fn), 8)}


def first_divergence_for_unavailable_detection(case: Case, oracle: Oracle) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "first_observed_divergence": None,
        "earliest_execution_gap": {
            "stage": "detection", "type": "automatic_stage_not_available",
            "evidence": [{"artifact": "artifacts/detection_candidates.json", "metric": "status", "observed": "NOT_AVAILABLE", "oracle": f"required_text_pixels={int(oracle.masks['text_required'].sum())}"}],
        },
        "causality": {"established": False, "reason": "observational comparison only"},
    }


def artifact_inventory(run_dir: Path) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for path in sorted((run_dir / "artifacts").rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(run_dir))
        item: dict[str, Any] = {"sha256": digest(path), "media_type": "application/json" if path.suffix == ".json" else "image/png" if path.suffix == ".png" else "application/octet-stream"}
        if path.suffix == ".png":
            with Image.open(path) as image:
                item["dimensions"] = [image.width, image.height]
        entries[relative] = item
    return entries
