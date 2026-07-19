#!/usr/bin/env python3
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_PACK = (
    ROOT_DIR
    / "data"
    / "local"
    / "reviews"
    / "120-grouping"
    / "association-r0-blind-v0.3"
)
DEFAULT_SPEC = DEFAULT_PACK / "S1-INPUT-SPEC.local.json"
DEFAULT_OUTPUT_ROOT = DEFAULT_PACK / "s1-runs"
DEFAULT_DETECTOR_MODULE = ROOT_DIR / "tools/experiments/130-ocr/detection_ocr/spike.py"
DEFAULT_GROUPING_MODULE = ROOT_DIR / "tools/experiments/120-grouping/text_region_grouping/spike.py"

SCHEMA_VERSION = "text-seeded-container-s1-freeze-v1"
SPEC_SCHEMA_VERSION = "text-seeded-container-s1-input-spec-v1"
BLIND_ASSET_PATTERN = re.compile(r"(?:case|cal)-\d{2}")
SPEC_FIELDS = {"schema_version", "assets"}
ASSET_FIELDS = {"asset_id", "relative_path", "sha256", "width", "height"}


class FreezeStop(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + __import__("os").urandom(3).hex()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FreezeStop(f"cannot read JSON {path}: {error}") from error


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_image_path(spec_path: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute() or candidate.parts[:1] != ("images",) or ".." in candidate.parts:
        raise FreezeStop(f"image path must be a blind images/ path: {relative_path}")
    resolved_root = spec_path.parent.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root / "images")
    except ValueError as error:
        raise FreezeStop(f"image path escapes blind images directory: {relative_path}") from error
    return resolved


def load_and_validate_spec(spec_path: Path) -> dict[str, Any]:
    spec_path = spec_path.resolve()
    data = load_json(spec_path)
    if not isinstance(data, dict):
        raise FreezeStop("input spec must be an object")
    unsupported_spec_fields = sorted(set(data) - SPEC_FIELDS)
    if unsupported_spec_fields:
        raise FreezeStop(f"unsupported spec fields: {unsupported_spec_fields}")
    if data.get("schema_version") != SPEC_SCHEMA_VERSION:
        raise FreezeStop(f"schema_version must be {SPEC_SCHEMA_VERSION}")
    assets = data.get("assets")
    if not isinstance(assets, list) or not assets:
        raise FreezeStop("assets must be a non-empty list")

    seen_ids: set[str] = set()
    normalized_assets: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise FreezeStop("each asset must be an object")
        unsupported_asset_fields = sorted(set(asset) - ASSET_FIELDS)
        if unsupported_asset_fields:
            raise FreezeStop(f"unsupported asset fields: {unsupported_asset_fields}")
        missing = sorted(ASSET_FIELDS - set(asset))
        if missing:
            raise FreezeStop(f"missing asset fields: {missing}")

        asset_id = asset["asset_id"]
        if not isinstance(asset_id, str) or BLIND_ASSET_PATTERN.fullmatch(asset_id) is None:
            raise FreezeStop(f"asset_id must be a blind asset ID: {asset_id!r}")
        if asset_id in seen_ids:
            raise FreezeStop(f"duplicate asset_id: {asset_id}")
        seen_ids.add(asset_id)

        relative_path = asset["relative_path"]
        if not isinstance(relative_path, str):
            raise FreezeStop(f"{asset_id}: relative_path must be a string")
        image_path = _safe_image_path(spec_path, relative_path)
        if not image_path.is_file():
            raise FreezeStop(f"{asset_id}: missing image {image_path}")

        expected_hash = asset["sha256"]
        actual_hash = sha256_file(image_path)
        if not isinstance(expected_hash, str) or actual_hash != expected_hash.lower():
            raise FreezeStop(f"{asset_id}: SHA-256 mismatch")

        width = asset["width"]
        height = asset["height"]
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise FreezeStop(f"{asset_id}: invalid dimensions")
        with Image.open(image_path) as image:
            if image.size != (width, height):
                raise FreezeStop(f"{asset_id}: image dimensions mismatch")

        normalized_assets.append(
            {
                "asset_id": asset_id,
                "relative_path": relative_path,
                "sha256": actual_hash,
                "width": width,
                "height": height,
                "_image_path": image_path,
            }
        )

    return {
        "schema_version": SPEC_SCHEMA_VERSION,
        "spec_path": spec_path,
        "spec_sha256": sha256_file(spec_path),
        "assets": sorted(normalized_assets, key=lambda item: item["asset_id"]),
    }


def load_python_module(path: Path, name: str):
    path = path.resolve()
    if not path.is_file():
        raise FreezeStop(f"missing Python module: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise FreezeStop(f"cannot load Python module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _module_provenance(module: Any) -> dict[str, Any]:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return {"path": None, "sha256": None}
    path = Path(module_file).resolve()
    try:
        display_path = str(path.relative_to(ROOT_DIR))
    except ValueError:
        display_path = str(path)
    return {"path": display_path, "sha256": sha256_file(path)}


def _normalize_fragment(prediction: dict[str, Any]) -> dict[str, Any]:
    required = {"prediction_id", "bbox", "polygon"}
    if not required.issubset(prediction):
        raise FreezeStop(f"detector prediction missing fields: {sorted(required - set(prediction))}")
    return {
        "fragment_id": str(prediction["prediction_id"]),
        "bbox": prediction["bbox"],
        "polygon": prediction["polygon"],
        "score": prediction.get("score"),
    }


def _detector_identity(detector: Any) -> dict[str, Any]:
    model = getattr(detector, "model", None)
    return {
        "mode": str(getattr(detector, "mode", "unknown")),
        "type": f"{type(model).__module__}.{type(model).__name__}" if model is not None else None,
        "model_name": str(getattr(model, "_model_name", "unknown")) if model is not None else None,
    }


def _input_hashes(spec: dict[str, Any]) -> dict[str, str]:
    hashes = {"spec": sha256_file(spec["spec_path"])}
    for asset in spec["assets"]:
        hashes[asset["asset_id"]] = sha256_file(asset["_image_path"])
    return hashes


def freeze_inputs(
    *,
    spec_path: Path,
    output_root: Path,
    run_id: str,
    detector_factory: Callable[[], Any],
    grouping_module: Any,
    environment: dict[str, Any],
    detector_module: Any | None = None,
) -> Path:
    spec = load_and_validate_spec(spec_path)
    before_hashes = _input_hashes(spec)
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / run_id
    if run_dir.exists():
        raise FreezeStop(f"run directory already exists: {run_dir}")
    run_dir.mkdir()
    result_path = run_dir / "results.json"

    started_at = utc_now()
    detector = detector_factory()
    assets_output: list[dict[str, Any]] = []
    for asset in spec["assets"]:
        detection = detector.predict(asset["_image_path"])
        fragments = [_normalize_fragment(item) for item in detection.get("predictions", [])]
        grouping_fragments = [
            grouping_module.FragmentInput(
                fragment_id=item["fragment_id"],
                asset_id=asset["asset_id"],
                bbox=item["bbox"],
                polygon=item["polygon"],
                score=item["score"],
                ocr_text="",
                ocr_error=None,
            )
            for item in fragments
        ]
        page = grouping_module.PageGroupingInput(
            asset_id=asset["asset_id"],
            width=asset["width"],
            height=asset["height"],
            fragments=grouping_fragments,
        )
        groups = [dataclasses.asdict(group) for group in grouping_module.group_fragments(page)]
        assets_output.append(
            {
                "asset_id": asset["asset_id"],
                "relative_path": asset["relative_path"],
                "sha256": asset["sha256"],
                "width": asset["width"],
                "height": asset["height"],
                "detector_mode": str(detection.get("mode", getattr(detector, "mode", "unknown"))),
                "fragments": fragments,
                "groups": groups,
            }
        )

    after_hashes = _input_hashes(spec)
    unchanged = before_hashes == after_hashes
    output = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": "completed" if unchanged else "stopped",
        "started_at": started_at,
        "finished_at": utc_now(),
        "input_spec": {
            "path": str(spec["spec_path"]),
            "sha256": spec["spec_sha256"],
            "contains_evaluator_labels": False,
        },
        "provenance": {
            "runner": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
            "detector": _detector_identity(detector),
            "detector_module": _module_provenance(detector_module) if detector_module else {"path": None, "sha256": None},
            "grouping_module": _module_provenance(grouping_module),
            "grouping_parameters": {
                "orientation_ratio": grouping_module.ORIENTATION_RATIO,
                "projection_overlap_ratio": grouping_module.PROJECTION_OVERLAP_RATIO,
                "gap_relative_limit": grouping_module.GAP_RELATIVE_LIMIT,
                "gap_min_px": grouping_module.GAP_MIN_PX,
            },
            "environment": environment,
        },
        "input_hashes_before": before_hashes,
        "input_hashes_after": after_hashes,
        "input_hashes_unchanged": unchanged,
        "assets": assets_output,
    }
    write_json(result_path, output)
    if not unchanged:
        raise FreezeStop("input hashes changed during run")
    return result_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze blind R0 Detection/Grouping inputs for the association spike")
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    detector_module = load_python_module(DEFAULT_DETECTOR_MODULE, "text_seeded_s1_detector")
    grouping_module = load_python_module(DEFAULT_GROUPING_MODULE, "text_seeded_s1_grouping")
    try:
        result_path = freeze_inputs(
            spec_path=args.spec,
            output_root=args.output_root,
            run_id=args.run_id or make_run_id(),
            detector_factory=detector_module.PaddleDetector,
            grouping_module=grouping_module,
            environment=detector_module.collect_environment(),
            detector_module=detector_module,
        )
    except FreezeStop as error:
        print(f"S1 freeze stopped: {error}", file=sys.stderr)
        return 2
    print(f"results={result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
