#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path, PurePosixPath
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLES_DIR = ROOT_DIR / "data" / "local" / "datasets" / "110-detection"
GENERATED_AT = "2026-07-10T00:00:00Z"


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Manifest must be a JSON object: {path}")
    if not isinstance(data.get("assets"), list):
        raise ValueError(f"Manifest assets must be a list: {path}")
    return data


def validate_relative_path(relative_path: str, expected_dir_name: str, file_name: str) -> None:
    posix_path = PurePosixPath(relative_path)
    if posix_path.is_absolute() or ".." in posix_path.parts:
        raise ValueError(f"Invalid relative_path: {relative_path}")
    expected = PurePosixPath(expected_dir_name) / file_name
    if posix_path != expected:
        raise ValueError(f"relative_path must be {expected}, got {relative_path}")


def validate_asset(
    asset: dict[str, Any],
    samples_dir: Path,
    expected_dir_name: str,
    expected_source_type: str,
    seen_region_ids: set[str],
) -> dict[str, Any]:
    file_name = asset.get("file_name")
    if not isinstance(file_name, str) or not file_name:
        raise ValueError("Asset file_name must be a non-empty string")

    source_type = asset.get("source_type")
    if source_type != expected_source_type:
        raise ValueError(f"{file_name}: source_type must be {expected_source_type}")

    relative_path = asset.get("relative_path")
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError(f"{file_name}: relative_path must be a non-empty string")
    validate_relative_path(relative_path, expected_dir_name, file_name)

    asset_path = samples_dir / relative_path
    if not asset_path.exists():
        raise ValueError(f"{file_name}: asset file not found at {relative_path}")

    regions = asset.get("regions")
    if not isinstance(regions, list):
        raise ValueError(f"{file_name}: regions must be a list")

    for region in regions:
        if not isinstance(region, dict):
            raise ValueError(f"{file_name}: region must be a JSON object")
        region_id = region.get("region_id")
        if not isinstance(region_id, str) or not region_id:
            raise ValueError(f"{file_name}: region_id must be a non-empty string")
        if region_id in seen_region_ids:
            raise ValueError(f"Duplicate region_id: {region_id}")
        seen_region_ids.add(region_id)

    return copy.deepcopy(asset)


def validated_assets(
    manifest: dict[str, Any],
    samples_dir: Path,
    expected_dir_name: str,
    expected_source_type: str,
    seen_region_ids: set[str],
) -> list[dict[str, Any]]:
    assets = []
    for asset in manifest["assets"]:
        if not isinstance(asset, dict):
            raise ValueError("Asset entry must be a JSON object")
        assets.append(
            validate_asset(
                asset,
                samples_dir,
                expected_dir_name,
                expected_source_type,
                seen_region_ids,
            )
        )
    return assets


def build_ground_truth(samples_dir: Path) -> dict[str, Any]:
    real_manifest = load_manifest(samples_dir / "real" / "manifest.json")
    generated_manifest = load_manifest(samples_dir / "generated" / "manifest.json")

    seen_region_ids: set[str] = set()
    generated_assets = validated_assets(
        generated_manifest,
        samples_dir,
        expected_dir_name="generated",
        expected_source_type="synthetic",
        seen_region_ids=seen_region_ids,
    )
    real_assets = validated_assets(
        real_manifest,
        samples_dir,
        expected_dir_name="real",
        expected_source_type="real",
        seen_region_ids=seen_region_ids,
    )

    return {
        "version": "1.0",
        "generated_at": GENERATED_AT,
        "purpose": "Ground-truth annotations for the standalone Detection + OCR Real Tool Spike.",
        "terminology": real_manifest.get("terminology", {}),
        "reading_order_policy": real_manifest.get("reading_order_policy", {}),
        "comparison_policy": real_manifest.get("comparison_policy", {}),
        "annotation_status": {
            "synthetic_assets": "bbox and OCR text ready",
            "real_assets": real_manifest.get("annotation_status", {}).get(
                "real_assets",
                "OCR text ready; bbox pending manual annotation",
            ),
        },
        "assets": generated_assets + real_assets,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Detection + OCR spike ground truth.")
    parser.add_argument(
        "--samples-dir",
        type=Path,
        default=DEFAULT_SAMPLES_DIR,
        help="Directory containing real/ and generated/ sample manifests.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to <samples-dir>/detection_ocr_ground_truth.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    samples_dir = args.samples_dir
    output = args.output or samples_dir / "detection_ocr_ground_truth.json"

    manifest = build_ground_truth(samples_dir)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    asset_count = len(manifest["assets"])
    region_count = sum(len(asset["regions"]) for asset in manifest["assets"])
    print(f"Wrote {output} with {asset_count} assets and {region_count} regions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
