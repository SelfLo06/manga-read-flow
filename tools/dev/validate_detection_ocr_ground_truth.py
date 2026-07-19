#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from build_detection_ocr_ground_truth import build_ground_truth


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLES_DIR = ROOT_DIR / "data" / "local" / "datasets" / "110-detection"
BBOX_SEMANTICS = "text_container_region"
LAYOUT_WHITESPACE_RE = re.compile(r"\s+")


class ValidationError(Exception):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"JSON file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValidationError(f"JSON root must be an object: {path}")
    return data


def without_layout_whitespace(value: str) -> str:
    return LAYOUT_WHITESPACE_RE.sub("", value)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def validate_relative_path(relative_path: str) -> None:
    posix_path = PurePosixPath(relative_path)
    require(not posix_path.is_absolute(), f"relative_path must be relative: {relative_path}")
    require(".." not in posix_path.parts, f"relative_path must not traverse upward: {relative_path}")


def validate_text_fields(asset_name: str, region: dict[str, Any]) -> None:
    region_id = region.get("region_id")
    expected_text = region.get("expected_text")
    expected_text_lines = region.get("expected_text_lines")
    normalized_text = region.get("normalized_text")

    require(isinstance(expected_text, str), f"{asset_name}/{region_id}: expected_text must be a string")
    require(
        isinstance(expected_text_lines, list) and all(isinstance(line, str) for line in expected_text_lines),
        f"{asset_name}/{region_id}: expected_text_lines must be a list of strings",
    )
    require(isinstance(normalized_text, str), f"{asset_name}/{region_id}: normalized_text must be a string")

    joined_lines = "".join(expected_text_lines)
    require(
        without_layout_whitespace(expected_text) == normalized_text,
        f"{asset_name}/{region_id}: expected_text does not normalize to normalized_text",
    )
    require(
        without_layout_whitespace(joined_lines) == normalized_text,
        f"{asset_name}/{region_id}: expected_text_lines do not normalize to normalized_text",
    )


def validate_bbox(asset_name: str, region: dict[str, Any], asset_width: int, asset_height: int) -> None:
    region_id = region.get("region_id")
    bbox = region.get("bbox")
    require(isinstance(bbox, dict), f"{asset_name}/{region_id}: bbox must be an object")

    for key in ("x", "y", "width", "height"):
        require(isinstance(bbox.get(key), int), f"{asset_name}/{region_id}: bbox.{key} must be an integer")

    x = bbox["x"]
    y = bbox["y"]
    width = bbox["width"]
    height = bbox["height"]

    require(width > 0, f"{asset_name}/{region_id}: bbox.width must be > 0")
    require(height > 0, f"{asset_name}/{region_id}: bbox.height must be > 0")
    require(x >= 0, f"{asset_name}/{region_id}: bbox.x must be >= 0")
    require(y >= 0, f"{asset_name}/{region_id}: bbox.y must be >= 0")
    require(x + width <= asset_width, f"{asset_name}/{region_id}: bbox exceeds image width")
    require(y + height <= asset_height, f"{asset_name}/{region_id}: bbox exceeds image height")


def bbox_overlap_ratio(a: dict[str, int], b: dict[str, int]) -> float:
    ax2 = a["x"] + a["width"]
    ay2 = a["y"] + a["height"]
    bx2 = b["x"] + b["width"]
    by2 = b["y"] + b["height"]
    overlap_width = max(0, min(ax2, bx2) - max(a["x"], b["x"]))
    overlap_height = max(0, min(ay2, by2) - max(a["y"], b["y"]))
    intersection = overlap_width * overlap_height
    if intersection == 0:
        return 0.0
    smaller_area = min(a["width"] * a["height"], b["width"] * b["height"])
    return intersection / smaller_area


def validate_manifest(manifest: dict[str, Any], samples_dir: Path) -> dict[str, int]:
    assets = manifest.get("assets")
    require(isinstance(assets, list), "assets must be a list")

    file_names: set[str] = set()
    relative_paths: set[str] = set()
    region_ids: set[str] = set()
    stats = {
        "assets": 0,
        "regions": 0,
        "real_core_regions": 0,
        "real_core_regions_with_bbox": 0,
        "real_auxiliary_pending_regions": 0,
        "synthetic_regions": 0,
        "overlap_warnings": 0,
    }

    for asset in assets:
        require(isinstance(asset, dict), "asset must be an object")
        file_name = asset.get("file_name")
        relative_path = asset.get("relative_path")
        source_type = asset.get("source_type")
        width = asset.get("width")
        height = asset.get("height")

        require(isinstance(file_name, str) and file_name, "asset file_name must be a non-empty string")
        require(isinstance(relative_path, str) and relative_path, f"{file_name}: relative_path required")
        require(source_type in {"real", "synthetic"}, f"{file_name}: source_type must be real or synthetic")
        require(isinstance(width, int) and width > 0, f"{file_name}: width must be a positive integer")
        require(isinstance(height, int) and height > 0, f"{file_name}: height must be a positive integer")
        require(file_name not in file_names, f"duplicate asset file_name: {file_name}")
        require(relative_path not in relative_paths, f"duplicate asset relative_path: {relative_path}")
        validate_relative_path(relative_path)

        file_names.add(file_name)
        relative_paths.add(relative_path)

        asset_path = samples_dir / relative_path
        require(asset_path.exists(), f"{file_name}: image file does not exist at {relative_path}")
        actual_width, actual_height = image_size(asset_path)
        require((actual_width, actual_height) == (width, height), f"{file_name}: manifest size != image size")

        regions = asset.get("regions")
        require(isinstance(regions, list), f"{file_name}: regions must be a list")
        asset_bboxes: list[tuple[str, dict[str, int]]] = []

        for region in regions:
            require(isinstance(region, dict), f"{file_name}: region must be an object")
            region_id = region.get("region_id")
            require(isinstance(region_id, str) and region_id, f"{file_name}: region_id required")
            require(region_id not in region_ids, f"duplicate region_id: {region_id}")
            region_ids.add(region_id)

            require(
                region.get("bbox_semantics") == BBOX_SEMANTICS,
                f"{file_name}/{region_id}: bbox_semantics must be {BBOX_SEMANTICS}",
            )
            validate_text_fields(file_name, region)

            is_real_core = source_type == "real" and region.get("include_in_core_ocr_score") is True
            is_real_auxiliary = source_type == "real" and region.get("include_in_core_ocr_score") is not True

            if source_type == "synthetic":
                stats["synthetic_regions"] += 1
                validate_bbox(file_name, region, width, height)
                asset_bboxes.append((region_id, region["bbox"]))
            elif is_real_core:
                stats["real_core_regions"] += 1
                require(
                    region.get("bbox_status") == "manually_annotated",
                    f"{file_name}/{region_id}: real core bbox_status must be manually_annotated",
                )
                validate_bbox(file_name, region, width, height)
                stats["real_core_regions_with_bbox"] += 1
                asset_bboxes.append((region_id, region["bbox"]))
            elif is_real_auxiliary:
                if region.get("bbox") is None:
                    require(
                        region.get("bbox_status") == "pending_manual_annotation",
                        f"{file_name}/{region_id}: pending real auxiliary bbox must have pending status",
                    )
                    stats["real_auxiliary_pending_regions"] += 1
                else:
                    validate_bbox(file_name, region, width, height)
                    asset_bboxes.append((region_id, region["bbox"]))

            stats["regions"] += 1

        for index, (left_id, left_bbox) in enumerate(asset_bboxes):
            for right_id, right_bbox in asset_bboxes[index + 1 :]:
                if bbox_overlap_ratio(left_bbox, right_bbox) > 0.75:
                    raise ValidationError(f"{file_name}: suspicious bbox overlap between {left_id} and {right_id}")

        stats["assets"] += 1

    require(stats["real_core_regions"] == stats["real_core_regions_with_bbox"], "not all real core regions have bbox")
    return stats


def validate_builder(samples_dir: Path, output_path: Path) -> None:
    real_manifest_path = samples_dir / "real" / "manifest.json"
    generated_manifest_path = samples_dir / "generated" / "manifest.json"
    before = {
        real_manifest_path: real_manifest_path.read_bytes(),
        generated_manifest_path: generated_manifest_path.read_bytes(),
    }

    first = build_ground_truth(samples_dir)
    second = build_ground_truth(samples_dir)
    require(first == second, "builder output is not deterministic")

    combined = load_json(output_path)
    require(first == combined, "combined ground truth is not equal to builder output")

    after = {
        real_manifest_path: real_manifest_path.read_bytes(),
        generated_manifest_path: generated_manifest_path.read_bytes(),
    }
    require(before == after, "builder modified an input manifest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Detection + OCR spike ground truth.")
    parser.add_argument(
        "--samples-dir",
        type=Path,
        default=DEFAULT_SAMPLES_DIR,
        help="Directory containing real/, generated/, and combined ground truth.",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=None,
        help="Ground-truth JSON path. Defaults to <samples-dir>/detection_ocr_ground_truth.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    samples_dir = args.samples_dir
    output_path = args.ground_truth or samples_dir / "detection_ocr_ground_truth.json"

    try:
        manifest = load_json(output_path)
        stats = validate_manifest(manifest, samples_dir)
        validate_builder(samples_dir, output_path)
    except ValidationError as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    print(
        "Validation passed: "
        f"{stats['assets']} assets, "
        f"{stats['regions']} regions, "
        f"{stats['real_core_regions_with_bbox']} real core bbox regions, "
        f"{stats['real_auxiliary_pending_regions']} real auxiliary pending regions, "
        f"{stats['synthetic_regions']} synthetic regions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
