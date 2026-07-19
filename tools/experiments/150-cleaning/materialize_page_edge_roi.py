#!/usr/bin/env python3
"""Materialize reproducible ROI views while keeping the full page authoritative."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[3]
CASE_SCHEMA = "page-edge-bubble-case-v1"
RUN_SCHEMA = "page-edge-bubble-roi-run-v1"
REQUIRED_ROI_USAGES = {"visualization", "annotation", "pixel_evaluation"}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class RoiMaterializationStop(RuntimeError):
    """Fail closed when a case could change the experiment contract."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _below(candidate: Path, root: Path, label: str) -> Path:
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise RoiMaterializationStop(f"{label} must remain below {root}") from error
    return resolved


def load_case(case_path: Path) -> dict[str, Any]:
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != CASE_SCHEMA:
        raise RoiMaterializationStop(f"case must use schema_version={CASE_SCHEMA}")

    for key in ("case_id", "source_path", "source_sha256", "purpose"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise RoiMaterializationStop(f"missing or invalid {key}")
    if not SHA256_PATTERN.fullmatch(payload["source_sha256"]):
        raise RoiMaterializationStop("source_sha256 must be a lowercase SHA-256 digest")
    if payload.get("algorithm_input") != "full_page":
        raise RoiMaterializationStop("algorithm_input must be full_page")

    roi = payload.get("roi_xyxy")
    if (
        not isinstance(roi, list)
        or len(roi) != 4
        or any(type(value) is not int for value in roi)
    ):
        raise RoiMaterializationStop("roi_xyxy must contain four integers")
    x0, y0, x1, y1 = roi
    if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
        raise RoiMaterializationStop("roi_xyxy must define a positive in-page rectangle")

    usages = payload.get("roi_usage")
    if not isinstance(usages, list) or any(not isinstance(item, str) for item in usages):
        raise RoiMaterializationStop("roi_usage must be a string list")
    if not REQUIRED_ROI_USAGES.issubset(usages):
        raise RoiMaterializationStop(
            "roi_usage must include visualization, annotation, and pixel_evaluation"
        )
    return payload


def materialize(case_path: Path, run_dir: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    case = load_case(case_path)
    source_relative = Path(case["source_path"])
    if source_relative.is_absolute():
        raise RoiMaterializationStop("source_path must be repository-relative")
    source_root = repo_root / "data" / "local" / "sources"
    source = _below(repo_root / source_relative, source_root, "source_path")
    if not source.is_file():
        raise RoiMaterializationStop(f"missing source: {case['source_path']}")
    actual_source_sha256 = sha256(source)
    if actual_source_sha256 != case["source_sha256"]:
        raise RoiMaterializationStop(f"source hash mismatch: {case['case_id']}")

    x0, y0, x1, y1 = case["roi_xyxy"]
    with Image.open(source) as opened:
        source_size = opened.size
        if x1 > opened.width or y1 > opened.height:
            raise RoiMaterializationStop(
                f"roi exceeds source bounds {opened.width}x{opened.height}: {case['case_id']}"
            )
        roi_image = opened.convert("RGB").crop((x0, y0, x1, y1))

    allowed_runs_root = repo_root / "data" / "local" / "runs" / "150-cleaning"
    run_dir = _below(run_dir, allowed_runs_root, "run_dir")
    if run_dir.exists():
        raise RoiMaterializationStop(f"run output already exists: {run_dir}")
    run_dir.parent.mkdir(parents=True, exist_ok=True)

    temporary = Path(tempfile.mkdtemp(prefix=f".{run_dir.name}-", dir=run_dir.parent))
    try:
        artifacts = temporary / "artifacts"
        artifacts.mkdir()
        roi_path = artifacts / "roi.png"
        roi_image.save(roi_path, format="PNG", optimize=False, compress_level=9)
        roi_sha256 = sha256(roi_path)
        manifest = {
            "schema_version": RUN_SCHEMA,
            "run_id": run_dir.name,
            "case_id": case["case_id"],
            "purpose": case["purpose"],
            "algorithm_input": "full_page",
            "source": {
                "path": case["source_path"],
                "sha256": actual_source_sha256,
                "width": source_size[0],
                "height": source_size[1],
            },
            "roi": {
                "xyxy": case["roi_xyxy"],
                "usage": case["roi_usage"],
            },
            "artifacts": {
                "roi": {
                    "path": "artifacts/roi.png",
                    "sha256": roi_sha256,
                    "width": roi_image.width,
                    "height": roi_image.height,
                    "role": "derived/visualization",
                }
            },
        }
        (temporary / "MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.rename(run_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a derived ROI artifact; algorithms still read the full page."
    )
    parser.add_argument("--case", required=True, type=Path, help="Path to cases.json")
    parser.add_argument("--run-dir", required=True, type=Path, help="New run directory")
    args = parser.parse_args()
    try:
        manifest = materialize(args.case, args.run_dir)
    except (OSError, ValueError, json.JSONDecodeError, RoiMaterializationStop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": "MATERIALIZED", **manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
