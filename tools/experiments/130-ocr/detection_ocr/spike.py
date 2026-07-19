#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

from PIL import Image, ImageDraw


ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_GROUND_TRUTH = ROOT_DIR / "data/local/datasets/110-detection/detection-ocr-ground-truth-v0.1.json"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "data/local/runs/130-ocr/detection-ocr-v0.1"
SCORING_REGION_COUNT = 27
IMAGE_ASSET_COUNT = 8
ORACLE_UNION_PADDING_PX = 8
PREDICTION_COVERAGE_THRESHOLD = 0.5


class MatchResult(NamedTuple):
    assigned: dict[str, list[dict[str, Any]]]
    unmatched: list[dict[str, Any]]
    details: list[dict[str, Any]]


class SpikeStop(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_ocr_text(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace(" ", "").replace("\n", "")


def exact_match(expected: str | None, actual: str | None) -> bool:
    return normalize_ocr_text(expected) == normalize_ocr_text(actual)


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + (left_char != right_char)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def character_error_rate(expected: str | None, actual: str | None) -> float:
    expected_norm = normalize_ocr_text(expected)
    actual_norm = normalize_ocr_text(actual)
    if not expected_norm:
        return 0.0 if not actual_norm else 1.0
    return levenshtein_distance(expected_norm, actual_norm) / len(expected_norm)


def bbox_edges(bbox: dict[str, Any]) -> tuple[float, float, float, float]:
    x = float(bbox["x"])
    y = float(bbox["y"])
    return x, y, x + float(bbox["width"]), y + float(bbox["height"])


def bbox_area(bbox: dict[str, Any]) -> float:
    return max(0.0, float(bbox["width"])) * max(0.0, float(bbox["height"]))


def intersection_area(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_x1, left_y1, left_x2, left_y2 = bbox_edges(left)
    right_x1, right_y1, right_x2, right_y2 = bbox_edges(right)
    width = max(0.0, min(left_x2, right_x2) - max(left_x1, right_x1))
    height = max(0.0, min(left_y2, right_y2) - max(left_y1, right_y1))
    return width * height


def center_in_container(prediction_bbox: dict[str, Any], gt_bbox: dict[str, Any]) -> bool:
    pred_x1, pred_y1, pred_x2, pred_y2 = bbox_edges(prediction_bbox)
    gt_x1, gt_y1, gt_x2, gt_y2 = bbox_edges(gt_bbox)
    center_x = (pred_x1 + pred_x2) / 2
    center_y = (pred_y1 + pred_y2) / 2
    return gt_x1 <= center_x <= gt_x2 and gt_y1 <= center_y <= gt_y2


def prediction_coverage(prediction_bbox: dict[str, Any], gt_bbox: dict[str, Any]) -> float:
    area = bbox_area(prediction_bbox)
    if area <= 0:
        return 0.0
    return intersection_area(prediction_bbox, gt_bbox) / area


def prediction_matches_gt(prediction_bbox: dict[str, Any], gt_bbox: dict[str, Any]) -> bool:
    return center_in_container(prediction_bbox, gt_bbox) or (
        prediction_coverage(prediction_bbox, gt_bbox) >= PREDICTION_COVERAGE_THRESHOLD
    )


def match_predictions_to_regions(
    predictions: list[dict[str, Any]], gt_regions: list[dict[str, Any]]
) -> MatchResult:
    assigned = {region["region_id"]: [] for region in sorted(gt_regions, key=lambda item: item["region_id"])}
    unmatched: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for prediction in sorted(predictions, key=lambda item: item["prediction_id"]):
        candidates = []
        for region in gt_regions:
            if not prediction_matches_gt(prediction["bbox"], region["bbox"]):
                continue
            candidates.append(
                {
                    "region_id": region["region_id"],
                    "coverage": prediction_coverage(prediction["bbox"], region["bbox"]),
                    "center_inside": center_in_container(prediction["bbox"], region["bbox"]),
                }
            )

        if not candidates:
            unmatched.append(prediction)
            details.append(
                {
                    "prediction_id": prediction["prediction_id"],
                    "matched_region_id": None,
                    "candidate_region_ids": [],
                }
            )
            continue

        candidates.sort(key=lambda item: (-item["coverage"], item["region_id"]))
        winner = candidates[0]
        assigned[winner["region_id"]].append(prediction)
        details.append(
            {
                "prediction_id": prediction["prediction_id"],
                "matched_region_id": winner["region_id"],
                "candidate_region_ids": [item["region_id"] for item in candidates],
                "coverage": winner["coverage"],
                "center_inside": winner["center_inside"],
                "cross_container": len(candidates) > 1,
            }
        )

    for region_id in assigned:
        assigned[region_id].sort(key=lambda item: item["prediction_id"])
    return MatchResult(assigned=assigned, unmatched=unmatched, details=details)


def union_bbox(
    bboxes: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
    padding: int = 0,
) -> dict[str, int]:
    if not bboxes:
        raise ValueError("cannot union empty bbox list")

    min_x = min(float(bbox["x"]) for bbox in bboxes) - padding
    min_y = min(float(bbox["y"]) for bbox in bboxes) - padding
    max_x = max(float(bbox["x"]) + float(bbox["width"]) for bbox in bboxes) + padding
    max_y = max(float(bbox["y"]) + float(bbox["height"]) for bbox in bboxes) + padding

    x1 = max(0, int(min_x // 1))
    y1 = max(0, int(min_y // 1))
    x2 = min(image_width, int(max_x + 0.999999))
    y2 = min(image_height, int(max_y + 0.999999))
    return {"x": x1, "y": y1, "width": max(0, x2 - x1), "height": max(0, y2 - y1)}


def sort_fragments(fragments: list[dict[str, Any]], *, orientation: str) -> list[dict[str, Any]]:
    def horizontal_key(item: dict[str, Any]) -> tuple[float, float, str]:
        bbox = item["bbox"]
        return float(bbox["y"]), float(bbox["x"]), str(item["prediction_id"])

    def vertical_key(item: dict[str, Any]) -> tuple[float, float, str]:
        bbox = item["bbox"]
        return -float(bbox["x"]), float(bbox["y"]), str(item["prediction_id"])

    key = vertical_key if orientation == "vertical" else horizontal_key
    return sorted(fragments, key=key)


def safe_run_path(run_dir: Path, *parts: str) -> Path:
    base = run_dir.resolve()
    candidate = base.joinpath(*parts).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise ValueError(f"output path would escape run directory: {candidate}") from error
    return candidate


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return to_jsonable(value.tolist())
    if hasattr(value, "json"):
        json_value = value.json
        if callable(json_value):
            json_value = json_value()
        return to_jsonable(json_value)
    if hasattr(value, "__dict__"):
        return to_jsonable(vars(value))
    return repr(value)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SpikeStop(f"JSON root must be an object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_relative_path(relative_path: str) -> None:
    posix_path = PurePosixPath(relative_path)
    if posix_path.is_absolute() or ".." in posix_path.parts:
        raise SpikeStop(f"invalid relative_path: {relative_path}")


def is_scored_region(asset: dict[str, Any], region: dict[str, Any]) -> bool:
    if region.get("bbox") is None:
        return False
    if asset.get("source_type") == "synthetic":
        return True
    return asset.get("source_type") == "real" and region.get("include_in_core_ocr_score") is True


def iter_assets(gt: dict[str, Any]) -> list[dict[str, Any]]:
    assets = gt.get("assets")
    if not isinstance(assets, list):
        raise SpikeStop("ground truth assets must be a list")
    return assets


def image_path_for_asset(asset: dict[str, Any], samples_root: Path) -> Path:
    relative_path = asset.get("relative_path")
    if not isinstance(relative_path, str):
        raise SpikeStop(f"{asset.get('file_name')}: missing relative_path")
    validate_relative_path(relative_path)
    return samples_root / relative_path


def scored_regions_for_asset(asset: dict[str, Any]) -> list[dict[str, Any]]:
    return [region for region in asset.get("regions", []) if is_scored_region(asset, region)]


def all_scored_regions(gt: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for asset in iter_assets(gt):
        for region in scored_regions_for_asset(asset):
            pairs.append((asset, region))
    return pairs


def validate_ground_truth(ground_truth_path: Path) -> tuple[dict[str, Any], dict[str, int]]:
    gt = load_json(ground_truth_path)
    samples_root = ground_truth_path.parent
    stats = {
        "assets": 0,
        "regions": 0,
        "synthetic_scored_regions": 0,
        "real_core_regions": 0,
        "real_auxiliary_regions": 0,
    }
    seen_region_ids: set[str] = set()

    for asset in iter_assets(gt):
        stats["assets"] += 1
        image_path = image_path_for_asset(asset, samples_root)
        if not image_path.exists():
            raise SpikeStop(f"missing input image: {image_path}")
        with Image.open(image_path) as image:
            if image.size != (asset.get("width"), asset.get("height")):
                raise SpikeStop(f"{asset.get('file_name')}: image size does not match GT")

        for region in asset.get("regions", []):
            region_id = region.get("region_id")
            if not isinstance(region_id, str) or not region_id:
                raise SpikeStop(f"{asset.get('file_name')}: invalid region_id")
            if region_id in seen_region_ids:
                raise SpikeStop(f"duplicate region_id: {region_id}")
            seen_region_ids.add(region_id)
            stats["regions"] += 1

            if is_scored_region(asset, region):
                bbox = region["bbox"]
                for key in ("x", "y", "width", "height"):
                    if not isinstance(bbox.get(key), int):
                        raise SpikeStop(f"{region_id}: bbox.{key} must be an integer")
                if bbox["width"] <= 0 or bbox["height"] <= 0:
                    raise SpikeStop(f"{region_id}: bbox dimensions must be positive")
                if asset["source_type"] == "synthetic":
                    stats["synthetic_scored_regions"] += 1
                else:
                    stats["real_core_regions"] += 1
            elif asset.get("source_type") == "real":
                stats["real_auxiliary_regions"] += 1

    if stats["assets"] != IMAGE_ASSET_COUNT:
        raise SpikeStop(f"expected {IMAGE_ASSET_COUNT} assets, got {stats['assets']}")
    if stats["synthetic_scored_regions"] + stats["real_core_regions"] != SCORING_REGION_COUNT:
        raise SpikeStop("expected 27 scored regions")
    return gt, stats


def input_hashes(ground_truth_path: Path, gt: dict[str, Any]) -> dict[str, str]:
    samples_root = ground_truth_path.parent
    hashes = {str(ground_truth_path.relative_to(ROOT_DIR)): sha256_file(ground_truth_path)}
    for asset in iter_assets(gt):
        image_path = image_path_for_asset(asset, samples_root)
        hashes[str(image_path.relative_to(ROOT_DIR))] = sha256_file(image_path)
    return hashes


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(3).hex()


def create_run_dir(output_root: Path, run_id: str | None = None) -> tuple[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    actual_run_id = run_id or make_run_id()
    run_dir = output_root / actual_run_id
    if run_dir.exists():
        raise SpikeStop(f"run directory already exists: {run_dir}")
    for name in ("raw", "crops", "visualizations", "logs"):
        safe_run_path(run_dir, name).mkdir(parents=True, exist_ok=False)
    return actual_run_id, run_dir


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"


def run_command(command: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as error:  # pragma: no cover - environment dependent
        return {"command": command, "error": repr(error)}


def collect_environment() -> dict[str, Any]:
    env = {
        "os": platform.platform(),
        "python": sys.version.replace("\n", " "),
        "conda_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
        "packages": {
            "torch": package_version("torch"),
            "paddlepaddle": package_version("paddlepaddle"),
            "paddleocr": package_version("paddleocr"),
            "manga-ocr": package_version("manga-ocr"),
            "Pillow": package_version("Pillow"),
            "opencv-python": package_version("opencv-python"),
        },
        "pip_check": run_command([sys.executable, "-m", "pip", "check"], timeout=60),
        "nvidia_smi": run_command(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,memory.used",
                "--format=csv,noheader",
            ],
            timeout=10,
        ),
    }

    try:
        import torch

        env["torch_cuda"] = {
            "available": torch.cuda.is_available(),
            "cuda": getattr(torch.version, "cuda", None),
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        }
    except Exception as error:  # pragma: no cover - environment dependent
        env["torch_cuda"] = {"error": repr(error)}

    try:
        import paddle

        env["paddle"] = {
            "version": getattr(paddle, "__version__", ""),
            "cuda_compiled": bool(paddle.device.is_compiled_with_cuda()),
            "device": str(paddle.device.get_device()),
        }
    except Exception as error:  # pragma: no cover - environment dependent
        env["paddle"] = {"error": repr(error)}

    return env


def polygon_to_bbox(points: Any) -> dict[str, int]:
    point_list = to_jsonable(points)
    if not point_list:
        raise ValueError("empty polygon")
    xs = [float(point[0]) for point in point_list]
    ys = [float(point[1]) for point in point_list]
    min_x = min(xs)
    min_y = min(ys)
    max_x = max(xs)
    max_y = max(ys)
    return {
        "x": int(min_x // 1),
        "y": int(min_y // 1),
        "width": max(1, int(max_x + 0.999999) - int(min_x // 1)),
        "height": max(1, int(max_y + 0.999999) - int(min_y // 1)),
    }


def extract_polygons_from_value(value: Any) -> list[Any]:
    value = to_jsonable(value)
    if isinstance(value, dict):
        for key in ("dt_polys", "text_detection", "polys", "boxes"):
            if key in value:
                return extract_polygons_from_value(value[key])
        if "res" in value:
            return extract_polygons_from_value(value["res"])
        return []
    if isinstance(value, list):
        if not value:
            return []
        first = value[0]
        if isinstance(first, dict):
            polygons: list[Any] = []
            for item in value:
                polygons.extend(extract_polygons_from_value(item))
            return polygons
        if isinstance(first, list) and first and isinstance(first[0], (int, float)):
            return [value]
        if isinstance(first, list) and first and isinstance(first[0], list):
            return value
    return []


class PaddleDetector:
    def __init__(self) -> None:
        start = time.perf_counter()
        try:
            from paddleocr import TextDetection

            self.model = TextDetection()
            self.mode = "TextDetection"
        except Exception:
            from paddleocr import PaddleOCR

            self.model = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
            self.mode = "PaddleOCR"
        self.init_duration_sec = time.perf_counter() - start

    def predict(self, image_path: Path) -> dict[str, Any]:
        start = time.perf_counter()
        if self.mode == "TextDetection":
            raw = self.model.predict(str(image_path), batch_size=1)
        elif hasattr(self.model, "predict"):
            raw = self.model.predict(str(image_path))
        else:
            raw = self.model.ocr(str(image_path), det=True, rec=False, cls=False)

        raw_json = to_jsonable(raw)
        polygons = extract_polygons_from_value(raw_json)
        predictions = []
        for index, polygon in enumerate(polygons, start=1):
            try:
                bbox = polygon_to_bbox(polygon)
            except Exception:
                continue
            predictions.append(
                {
                    "prediction_id": f"p{index:04d}",
                    "bbox": bbox,
                    "polygon": polygon,
                    "score": None,
                }
            )
        return {
            "duration_sec": time.perf_counter() - start,
            "predictions": predictions,
            "raw": raw_json,
            "mode": self.mode,
        }


class MangaOcrRunner:
    def __init__(self) -> None:
        start = time.perf_counter()
        from manga_ocr import MangaOcr

        self.model = MangaOcr()
        self.init_duration_sec = time.perf_counter() - start

    def recognize(self, crop_path: Path) -> dict[str, Any]:
        start = time.perf_counter()
        with Image.open(crop_path) as image:
            image.load()
            try:
                text = self.model(image)
            except TypeError:
                text = self.model(str(crop_path))
        return {"raw_text": str(text), "duration_sec": time.perf_counter() - start, "error": None}


def crop_to_path(image_path: Path, bbox: dict[str, Any], crop_path: Path) -> None:
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as image:
        x, y, x2, y2 = bbox_edges(bbox)
        crop = image.crop((int(x), int(y), int(x2), int(y2)))
        crop.save(crop_path, "WEBP", lossless=True, quality=100, method=6)


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def ocr_crop(
    ocr_runner: MangaOcrRunner,
    *,
    image_path: Path,
    bbox: dict[str, Any],
    run_dir: Path,
    crop_name: str,
) -> dict[str, Any]:
    crop_path = safe_run_path(run_dir, "crops", f"{safe_name(crop_name)}.webp")
    crop_to_path(image_path, bbox, crop_path)
    try:
        result = ocr_runner.recognize(crop_path)
    except Exception as error:
        result = {"raw_text": "", "duration_sec": 0.0, "error": repr(error)}
    result["crop_path"] = str(crop_path.relative_to(run_dir))
    return result


def ocr_region_result(
    ocr_runner: MangaOcrRunner,
    *,
    asset: dict[str, Any],
    region: dict[str, Any],
    image_path: Path,
    run_dir: Path,
    cycle_name: str,
    experiment: str,
    bbox: dict[str, Any],
) -> dict[str, Any]:
    result = ocr_crop(
        ocr_runner,
        image_path=image_path,
        bbox=bbox,
        run_dir=run_dir,
        crop_name=f"{cycle_name}_{experiment}_{region['region_id']}",
    )
    expected = region.get("normalized_text") or region.get("expected_text", "")
    actual = result["raw_text"]
    normalized_actual = normalize_ocr_text(actual)
    return {
        "expected": region.get("expected_text", ""),
        "normalized_expected": normalize_ocr_text(expected),
        "actual_raw": actual,
        "normalized_actual": normalized_actual,
        "exact": normalize_ocr_text(expected) == normalized_actual,
        "cer": character_error_rate(expected, actual),
        "duration_sec": result["duration_sec"],
        "error": result["error"],
        "crop_path": result["crop_path"],
        "failure_tags": failure_tags_for_ocr(asset, region, result["error"], expected, actual),
    }


def failure_tags_for_ocr(
    asset: dict[str, Any], region: dict[str, Any], error: str | None, expected: str | None, actual: str | None
) -> list[str]:
    tags: list[str] = []
    normalized_actual = normalize_ocr_text(actual)
    if error:
        tags.append("runtime_error")
    if not normalized_actual:
        tags.append("ocr_empty")
    elif normalize_ocr_text(expected) != normalized_actual:
        tags.append("ocr_substitution")

    scenario_tags = set(asset.get("scenario_tags", []))
    orientation = region.get("text_orientation")
    difficulty = region.get("expected_difficulty")
    if orientation == "vertical":
        tags.append("vertical_text_failure")
    if difficulty == "hard" or "small_bubble" in scenario_tags:
        tags.append("small_text_failure")
    if "color" in scenario_tags or "mixed_font_color" in scenario_tags:
        tags.append("color_text_failure")
    if "weak_contrast" in scenario_tags:
        tags.append("low_contrast_failure")
    if orientation == "angled" or "angled_text" in scenario_tags:
        tags.append("skew_failure")
    if "complex_background" in scenario_tags:
        tags.append("complex_background_failure")
    return sorted(set(tags))


def render_detection_visualization(
    *,
    image_path: Path,
    asset: dict[str, Any],
    predictions: list[dict[str, Any]],
    matches: MatchResult,
    output_path: Path,
) -> None:
    with Image.open(image_path) as image:
        canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)

    for region in scored_regions_for_asset(asset):
        x1, y1, x2, y2 = bbox_edges(region["bbox"])
        color = (0, 180, 0) if matches.assigned.get(region["region_id"]) else (220, 0, 0)
        draw.rectangle((x1, y1, x2, y2), outline=color, width=4)
        draw.text((x1 + 4, y1 + 4), region["region_id"], fill=color)

    matched_prediction_ids = {
        prediction["prediction_id"]
        for assigned in matches.assigned.values()
        for prediction in assigned
    }
    for prediction in predictions:
        x1, y1, x2, y2 = bbox_edges(prediction["bbox"])
        color = (0, 90, 255) if prediction["prediction_id"] in matched_prediction_ids else (255, 190, 0)
        draw.rectangle((x1, y1, x2, y2), outline=color, width=2)
        draw.text((x1 + 2, y1 + 2), prediction["prediction_id"], fill=color)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")


def classify_unmatched_prediction(_prediction: dict[str, Any], _asset: dict[str, Any]) -> str:
    return "uncertain"


def run_detection_cycle(
    detector: PaddleDetector,
    *,
    gt: dict[str, Any],
    ground_truth_path: Path,
    run_dir: Path,
    cycle_name: str,
) -> dict[str, Any]:
    samples_root = ground_truth_path.parent
    by_asset: dict[str, Any] = {}
    for asset in iter_assets(gt):
        image_path = image_path_for_asset(asset, samples_root)
        detection = detector.predict(image_path)
        predictions = detection["predictions"]
        matches = match_predictions_to_regions(predictions, scored_regions_for_asset(asset))

        asset_id = asset["file_name"]
        raw_path = safe_run_path(run_dir, "raw", f"{cycle_name}_{safe_name(asset_id)}_detection.json")
        write_json(raw_path, {"asset": asset_id, "detection": detection})

        viz_path = safe_run_path(run_dir, "visualizations", f"{cycle_name}_{safe_name(asset_id)}_detection.png")
        render_detection_visualization(
            image_path=image_path,
            asset=asset,
            predictions=predictions,
            matches=matches,
            output_path=viz_path,
        )

        unmatched = [
            {
                **prediction,
                "unmatched_category": classify_unmatched_prediction(prediction, asset),
            }
            for prediction in matches.unmatched
        ]
        by_asset[asset_id] = {
            "asset_id": asset_id,
            "split": asset["source_type"],
            "duration_sec": detection["duration_sec"],
            "predictions": predictions,
            "prediction_count": len(predictions),
            "matches": {
                "assigned": matches.assigned,
                "unmatched": unmatched,
                "details": matches.details,
            },
            "raw_path": str(raw_path.relative_to(run_dir)),
            "visualization_path": str(viz_path.relative_to(run_dir)),
        }
    return by_asset


def empty_region_record(asset: dict[str, Any], region: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset["file_name"],
        "relative_path": asset["relative_path"],
        "split": asset["source_type"],
        "region_id": region["region_id"],
        "region_type": region.get("region_type", ""),
        "bbox": region["bbox"],
        "direction": region.get("text_orientation", "unknown"),
        "expected": region.get("expected_text", ""),
        "normalized_expected": normalize_ocr_text(region.get("normalized_text") or region.get("expected_text", "")),
        "scenario_tags": asset.get("scenario_tags", []),
        "experiment_a": None,
        "detection": None,
        "b1_oracle_container_group": None,
        "b2_native_fragments": None,
    }


def run_experiment_a(
    ocr_runner: MangaOcrRunner,
    *,
    gt: dict[str, Any],
    ground_truth_path: Path,
    run_dir: Path,
    cycle_name: str,
    region_records: dict[str, dict[str, Any]],
) -> None:
    samples_root = ground_truth_path.parent
    for asset, region in all_scored_regions(gt):
        image_path = image_path_for_asset(asset, samples_root)
        region_records[region["region_id"]]["experiment_a"] = ocr_region_result(
            ocr_runner,
            asset=asset,
            region=region,
            image_path=image_path,
            run_dir=run_dir,
            cycle_name=cycle_name,
            experiment="A_gt_crop",
            bbox=region["bbox"],
        )


def run_experiment_b(
    ocr_runner: MangaOcrRunner,
    *,
    gt: dict[str, Any],
    ground_truth_path: Path,
    run_dir: Path,
    cycle_name: str,
    detections_by_asset: dict[str, Any],
    region_records: dict[str, dict[str, Any]],
) -> None:
    samples_root = ground_truth_path.parent
    for asset, region in all_scored_regions(gt):
        asset_detection = detections_by_asset[asset["file_name"]]
        assigned = asset_detection["matches"]["assigned"].get(region["region_id"], [])
        record = region_records[region["region_id"]]
        prediction_count = len(assigned)
        record["detection"] = {
            "hit": prediction_count > 0,
            "prediction_count": prediction_count,
            "fragmented": prediction_count > 1,
            "prediction_ids": [prediction["prediction_id"] for prediction in assigned],
        }

        image_path = image_path_for_asset(asset, samples_root)
        if not assigned:
            miss_result = {
                "expected": record["expected"],
                "normalized_expected": record["normalized_expected"],
                "actual_raw": "",
                "normalized_actual": "",
                "exact": False,
                "cer": 1.0 if record["normalized_expected"] else 0.0,
                "duration_sec": 0.0,
                "error": "detection_miss",
                "crop_path": "",
                "failure_tags": ["detection_miss"],
            }
            record["b1_oracle_container_group"] = dict(miss_result)
            record["b2_native_fragments"] = {**miss_result, "fragment_count": 0, "reading_order_failure": False}
            continue

        union = union_bbox(
            [prediction["bbox"] for prediction in assigned],
            image_width=int(asset["width"]),
            image_height=int(asset["height"]),
            padding=ORACLE_UNION_PADDING_PX,
        )
        b1 = ocr_region_result(
            ocr_runner,
            asset=asset,
            region=region,
            image_path=image_path,
            run_dir=run_dir,
            cycle_name=cycle_name,
            experiment="B1_oracle",
            bbox=union,
        )
        b1["union_bbox"] = union
        b1["prediction_count"] = prediction_count
        b1["failure_tags"] = sorted(set(b1["failure_tags"] + (["grouping_required"] if prediction_count > 1 else [])))
        record["b1_oracle_container_group"] = b1

        sorted_fragments = sort_fragments(assigned, orientation=record["direction"])
        fragment_results = []
        raw_parts = []
        total_duration = 0.0
        errors = []
        for index, prediction in enumerate(sorted_fragments, start=1):
            fragment = ocr_region_result(
                ocr_runner,
                asset=asset,
                region=region,
                image_path=image_path,
                run_dir=run_dir,
                cycle_name=cycle_name,
                experiment=f"B2_native_{index}",
                bbox=prediction["bbox"],
            )
            fragment["prediction_id"] = prediction["prediction_id"]
            fragment["prediction_bbox"] = prediction["bbox"]
            fragment_results.append(fragment)
            raw_parts.append(fragment["actual_raw"])
            total_duration += float(fragment["duration_sec"])
            if fragment.get("error"):
                errors.append(fragment["error"])

        actual_raw = "\n".join(raw_parts)
        expected = record["normalized_expected"]
        tags = []
        if prediction_count > 1:
            tags.extend(["detection_fragmented", "grouping_required"])
        native = {
            "expected": record["expected"],
            "normalized_expected": expected,
            "actual_raw": actual_raw,
            "normalized_actual": normalize_ocr_text(actual_raw),
            "exact": normalize_ocr_text(actual_raw) == expected,
            "cer": character_error_rate(expected, actual_raw),
            "duration_sec": total_duration,
            "error": "; ".join(errors) if errors else None,
            "fragment_count": prediction_count,
            "fragments": fragment_results,
            "reading_order_failure": False,
            "failure_tags": sorted(set(tags + failure_tags_for_ocr(asset, region, None, expected, actual_raw))),
        }
        record["b2_native_fragments"] = native


def run_cycle(
    *,
    cycle_name: str,
    gt: dict[str, Any],
    ground_truth_path: Path,
    run_dir: Path,
    detector: PaddleDetector | None,
    ocr_runner: MangaOcrRunner | None,
    include_ocr_gt: bool,
    include_detection: bool,
    include_detection_ocr: bool,
) -> dict[str, Any]:
    started_at = utc_now()
    start = time.perf_counter()
    region_records = {
        region["region_id"]: empty_region_record(asset, region)
        for asset, region in all_scored_regions(gt)
    }
    detections_by_asset: dict[str, Any] = {}

    if include_ocr_gt:
        if ocr_runner is None:
            raise SpikeStop("OCR runner is required")
        run_experiment_a(
            ocr_runner,
            gt=gt,
            ground_truth_path=ground_truth_path,
            run_dir=run_dir,
            cycle_name=cycle_name,
            region_records=region_records,
        )

    if include_detection or include_detection_ocr:
        if detector is None:
            raise SpikeStop("Paddle detector is required")
        detections_by_asset = run_detection_cycle(
            detector,
            gt=gt,
            ground_truth_path=ground_truth_path,
            run_dir=run_dir,
            cycle_name=cycle_name,
        )

    if include_detection_ocr:
        if ocr_runner is None:
            raise SpikeStop("OCR runner is required")
        run_experiment_b(
            ocr_runner,
            gt=gt,
            ground_truth_path=ground_truth_path,
            run_dir=run_dir,
            cycle_name=cycle_name,
            detections_by_asset=detections_by_asset,
            region_records=region_records,
        )

    page_e2e = []
    for asset in iter_assets(gt):
        asset_id = asset["file_name"]
        detection_duration = detections_by_asset.get(asset_id, {}).get("duration_sec", 0.0)
        ocr_duration = sum(
            float((record.get("b1_oracle_container_group") or {}).get("duration_sec") or 0.0)
            + float((record.get("b2_native_fragments") or {}).get("duration_sec") or 0.0)
            for record in region_records.values()
            if record["asset_id"] == asset_id
        )
        page_e2e.append({"asset_id": asset_id, "duration_sec": detection_duration + ocr_duration})

    cycle = {
        "cycle": cycle_name,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_sec": time.perf_counter() - start,
        "regions": list(region_records.values()),
        "assets": detections_by_asset,
        "performance": {"page_end_to_end": page_e2e},
        "status": "completed",
    }
    return cycle


def values_for_experiment(cycle: dict[str, Any], experiment_key: str, split: str | None = None) -> list[dict[str, Any]]:
    values = []
    for region in cycle.get("regions", []):
        if split is not None and region.get("split") != split:
            continue
        result = region.get(experiment_key)
        if result is not None:
            values.append(result)
    return values


def summarize_ocr_results(results: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    if not results:
        return {"regions": 0, "exact": 0, "exact_rate": 0.0, "median_cer": None, "mean_cer": None, "cer_lte": 0}
    cers = [float(result["cer"]) for result in results if result.get("cer") is not None]
    exact_count = sum(1 for result in results if result.get("exact") is True)
    return {
        "regions": len(results),
        "exact": exact_count,
        "exact_rate": exact_count / len(results),
        "median_cer": statistics.median(cers) if cers else None,
        "mean_cer": statistics.mean(cers) if cers else None,
        f"cer_lte_{threshold}": sum(1 for value in cers if value <= threshold),
    }


def summarize_detection(cycle: dict[str, Any], split: str) -> dict[str, Any]:
    regions = [region for region in cycle.get("regions", []) if region.get("split") == split]
    hits = sum(1 for region in regions if (region.get("detection") or {}).get("hit"))
    fragmented = sum(1 for region in regions if (region.get("detection") or {}).get("fragmented"))
    unmatched = 0
    clear_fp = 0
    for asset in cycle.get("assets", {}).values():
        if asset.get("split") != split:
            continue
        for prediction in asset.get("matches", {}).get("unmatched", []):
            unmatched += 1
            if prediction.get("unmatched_category") == "clear_false_positive":
                clear_fp += 1
    return {
        "gt": len(regions),
        "hit": hits,
        "miss": len(regions) - hits,
        "recall": hits / len(regions) if regions else 0.0,
        "fragmented": fragmented,
        "unmatched_predictions": unmatched,
        "clear_false_positive": clear_fp,
    }


def summarize_cycle(cycle: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "experiment_a": {
            "synthetic": summarize_ocr_results(values_for_experiment(cycle, "experiment_a", "synthetic"), 0.25),
            "real": summarize_ocr_results(values_for_experiment(cycle, "experiment_a", "real"), 0.25),
        },
        "detection": {
            "synthetic": summarize_detection(cycle, "synthetic"),
            "real": summarize_detection(cycle, "real"),
        },
        "b1_oracle_container_group": {
            "synthetic": summarize_ocr_results(
                values_for_experiment(cycle, "b1_oracle_container_group", "synthetic"), 0.30
            ),
            "real": summarize_ocr_results(values_for_experiment(cycle, "b1_oracle_container_group", "real"), 0.30),
        },
        "b2_native_fragments": {
            "synthetic": summarize_ocr_results(values_for_experiment(cycle, "b2_native_fragments", "synthetic"), 0.30),
            "real": summarize_ocr_results(values_for_experiment(cycle, "b2_native_fragments", "real"), 0.30),
        },
    }
    page_durations = [
        float(item["duration_sec"]) for item in cycle.get("performance", {}).get("page_end_to_end", [])
    ]
    summary["performance"] = {
        "page_end_to_end_p50": statistics.median(page_durations) if page_durations else None,
        "page_end_to_end_max": max(page_durations) if page_durations else None,
    }
    return summary


def scenario_failures(cycle: dict[str, Any]) -> dict[str, Any]:
    scenario_predicates = {
        "horizontal": lambda region: region.get("direction") == "horizontal",
        "vertical": lambda region: region.get("direction") == "vertical",
        "small_text": lambda region: "small_bubble" in region.get("scenario_tags", []),
        "color_text": lambda region: "color" in region.get("scenario_tags", []),
        "complex_background": lambda region: "complex_background" in region.get("scenario_tags", []),
        "low_contrast": lambda region: "weak_contrast" in region.get("scenario_tags", []),
        "skewed_text": lambda region: region.get("direction") == "angled" or "angled_text" in region.get("scenario_tags", []),
    }
    result = {}
    for name, predicate in scenario_predicates.items():
        regions = [region for region in cycle.get("regions", []) if predicate(region)]
        successes = [
            region
            for region in regions
            if (region.get("b2_native_fragments") or {}).get("cer") is not None
            and float((region.get("b2_native_fragments") or {}).get("cer")) <= 0.30
        ]
        result[name] = {
            "regions": len(regions),
            "successes_cer_lte_0.30": len(successes),
            "systematic_failure": bool(regions) and not successes,
        }
    return result


def decide_exit(results: dict[str, Any]) -> str:
    if results.get("fatal_error"):
        return "FURTHER_SPIKE"
    cycles = results.get("cycles", [])
    completed = [cycle for cycle in cycles if cycle.get("status") == "completed"]
    if len(completed) < 2:
        return "FURTHER_SPIKE"

    canonical = completed[0]
    summary = summarize_cycle(canonical)
    warm_summary = summarize_cycle(completed[1])
    scenarios = scenario_failures(canonical)

    synthetic_det_hit = summary["detection"]["synthetic"]["hit"]
    real_det_hit = summary["detection"]["real"]["hit"]
    real_pure = summary["experiment_a"]["real"]
    real_native = summary["b2_native_fragments"]["real"]
    warm_p50 = warm_summary["performance"]["page_end_to_end_p50"]

    go = (
        synthetic_det_hit >= 10
        and real_det_hit >= 14
        and real_pure.get("median_cer") is not None
        and real_pure["median_cer"] <= 0.15
        and real_pure.get("cer_lte_0.25", 0) >= 13
        and real_native.get("cer_lte_0.3", 0) >= 12
        and not any(item["systematic_failure"] for item in scenarios.values())
        and warm_p50 is not None
        and warm_p50 <= 10
    )
    if go:
        return "GO"

    severe = (
        synthetic_det_hit < 6
        or real_det_hit < 8
        or (real_pure.get("median_cer") is not None and real_pure["median_cer"] > 0.50)
        or real_native.get("cer_lte_0.3", 0) < 5
    )
    if severe:
        return "NO_GO"
    return "CONDITIONAL_GO"


def write_regions_csv(run_dir: Path, cycle: dict[str, Any]) -> None:
    path = safe_run_path(run_dir, "regions.csv")
    fieldnames = [
        "asset_id",
        "split",
        "region_id",
        "region_type",
        "direction",
        "expected",
        "normalized_expected",
        "detection_hit",
        "prediction_count",
        "fragmented",
        "a_actual",
        "a_exact",
        "a_cer",
        "b1_actual",
        "b1_exact",
        "b1_cer",
        "b2_actual",
        "b2_exact",
        "b2_cer",
        "failure_tags",
    ]
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for region in cycle.get("regions", []):
            detection = region.get("detection") or {}
            a = region.get("experiment_a") or {}
            b1 = region.get("b1_oracle_container_group") or {}
            b2 = region.get("b2_native_fragments") or {}
            tags = sorted(
                set(
                    (a.get("failure_tags") or [])
                    + (b1.get("failure_tags") or [])
                    + (b2.get("failure_tags") or [])
                    + (["detection_fragmented"] if detection.get("fragmented") else [])
                    + ([] if detection.get("hit") else ["detection_miss"])
                )
            )
            writer.writerow(
                {
                    "asset_id": region["asset_id"],
                    "split": region["split"],
                    "region_id": region["region_id"],
                    "region_type": region["region_type"],
                    "direction": region["direction"],
                    "expected": region["expected"],
                    "normalized_expected": region["normalized_expected"],
                    "detection_hit": detection.get("hit"),
                    "prediction_count": detection.get("prediction_count"),
                    "fragmented": detection.get("fragmented"),
                    "a_actual": a.get("actual_raw"),
                    "a_exact": a.get("exact"),
                    "a_cer": a.get("cer"),
                    "b1_actual": b1.get("actual_raw"),
                    "b1_exact": b1.get("exact"),
                    "b1_cer": b1.get("cer"),
                    "b2_actual": b2.get("actual_raw"),
                    "b2_exact": b2.get("exact"),
                    "b2_cer": b2.get("cer"),
                    "failure_tags": ";".join(tags),
                }
            )


def save_results(run_dir: Path, results: dict[str, Any]) -> None:
    write_json(safe_run_path(run_dir, "results.json"), results)


def run_spike(args: argparse.Namespace, *, mode: str) -> int:
    ground_truth_path = args.ground_truth.resolve()
    gt, stats = validate_ground_truth(ground_truth_path)
    before_hashes = input_hashes(ground_truth_path, gt)
    run_id, run_dir = create_run_dir(args.output_root.resolve(), getattr(args, "run_id", None))

    results: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "mode": mode,
        "started_at": utc_now(),
        "ground_truth": str(ground_truth_path.relative_to(ROOT_DIR)),
        "stats": stats,
        "parameters": {
            "oracle_union_padding_px": ORACLE_UNION_PADDING_PX,
            "prediction_coverage_threshold": PREDICTION_COVERAGE_THRESHOLD,
        },
        "input_hashes_before": before_hashes,
        "environment": collect_environment(),
        "cycles": [],
    }
    save_results(run_dir, results)

    detector: PaddleDetector | None = None
    ocr_runner: MangaOcrRunner | None = None
    try:
        if mode in {"run-detection", "run-detection-ocr", "run-all"}:
            detector = PaddleDetector()
            results["performance_init"] = {"paddle_detection_sec": detector.init_duration_sec}
            save_results(run_dir, results)
        if mode in {"run-ocr-gt", "run-detection-ocr", "run-all"}:
            ocr_runner = MangaOcrRunner()
            results.setdefault("performance_init", {})["manga_ocr_sec"] = ocr_runner.init_duration_sec
            save_results(run_dir, results)
    except Exception as error:
        results["status"] = "stopped"
        results["fatal_error"] = {
            "stage": "model_initialization",
            "error": repr(error),
            "traceback": traceback.format_exc(),
        }
        results["input_hashes_after"] = input_hashes(ground_truth_path, gt)
        results["input_hashes_unchanged"] = results["input_hashes_before"] == results["input_hashes_after"]
        results["finished_at"] = utc_now()
        results["exit_decision"] = decide_exit(results)
        save_results(run_dir, results)
        print(f"Model initialization failed; saved {run_dir / 'results.json'}", file=sys.stderr)
        return 2

    include_ocr_gt = mode in {"run-ocr-gt", "run-all"}
    include_detection = mode in {"run-detection", "run-all"}
    include_detection_ocr = mode in {"run-detection-ocr", "run-all"}
    cycle_names = ["cold", "warm"] if mode == "run-all" else [mode]

    try:
        for cycle_name in cycle_names:
            cycle = run_cycle(
                cycle_name=cycle_name,
                gt=gt,
                ground_truth_path=ground_truth_path,
                run_dir=run_dir,
                detector=detector,
                ocr_runner=ocr_runner,
                include_ocr_gt=include_ocr_gt,
                include_detection=include_detection,
                include_detection_ocr=include_detection_ocr,
            )
            cycle["summary"] = summarize_cycle(cycle)
            cycle["scenario_failures"] = scenario_failures(cycle)
            results["cycles"].append(cycle)
            save_results(run_dir, results)
    except Exception as error:
        results["status"] = "stopped"
        results["fatal_error"] = {
            "stage": "experiment",
            "error": repr(error),
            "traceback": traceback.format_exc(),
        }
        results["input_hashes_after"] = input_hashes(ground_truth_path, gt)
        results["input_hashes_unchanged"] = results["input_hashes_before"] == results["input_hashes_after"]
        results["finished_at"] = utc_now()
        results["exit_decision"] = decide_exit(results)
        save_results(run_dir, results)
        print(f"Experiment failed; saved {run_dir / 'results.json'}", file=sys.stderr)
        return 2

    results["input_hashes_after"] = input_hashes(ground_truth_path, gt)
    results["input_hashes_unchanged"] = results["input_hashes_before"] == results["input_hashes_after"]
    if not results["input_hashes_unchanged"]:
        results["status"] = "stopped"
        results["fatal_error"] = {"stage": "verify_inputs", "error": "input hash changed"}
    else:
        results["status"] = "completed"
    results["finished_at"] = utc_now()
    results["exit_decision"] = decide_exit(results)
    if results["cycles"]:
        write_regions_csv(run_dir, results["cycles"][0])
    save_results(run_dir, results)
    print(f"run_id={run_id}")
    print(f"output_dir={run_dir}")
    print(f"exit_decision={results['exit_decision']}")
    return 0 if results["status"] == "completed" else 2


def validate_command(args: argparse.Namespace) -> int:
    gt, stats = validate_ground_truth(args.ground_truth.resolve())
    hashes = input_hashes(args.ground_truth.resolve(), gt)
    print(
        "Validation passed: "
        f"{stats['assets']} assets, "
        f"{stats['synthetic_scored_regions']} synthetic scored regions, "
        f"{stats['real_core_regions']} real core regions, "
        f"{stats['real_auxiliary_regions']} real auxiliary regions, "
        f"{len(hashes)} hashed inputs"
    )
    return 0


def verify_inputs_command(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    results = load_json(run_dir / "results.json")
    ground_truth_path = (ROOT_DIR / results["ground_truth"]).resolve()
    gt, _stats = validate_ground_truth(ground_truth_path)
    current_hashes = input_hashes(ground_truth_path, gt)
    expected_hashes = results.get("input_hashes_before")
    if current_hashes != expected_hashes:
        print("Input hash verification failed", file=sys.stderr)
        return 1
    print(f"Input hash verification passed for {run_dir}")
    return 0


def summarize_command(args: argparse.Namespace) -> int:
    results = load_json(args.run_dir.resolve() / "results.json")
    print(f"run_id={results.get('run_id')}")
    print(f"status={results.get('status')}")
    print(f"exit_decision={results.get('exit_decision')}")
    for cycle in results.get("cycles", []):
        print(f"cycle={cycle['cycle']}")
        print(json.dumps(cycle.get("summary", {}), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detection + OCR Real Tool Spike harness.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    validate.set_defaults(func=validate_command)

    for command in ("run-ocr-gt", "run-detection", "run-detection-ocr", "run-all"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
        sub.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
        sub.add_argument("--run-id", default=None)
        sub.set_defaults(func=lambda parsed, selected=command: run_spike(parsed, mode=selected))

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("--run-dir", type=Path, required=True)
    summarize.set_defaults(func=summarize_command)

    verify = subparsers.add_parser("verify-inputs")
    verify.add_argument("--run-dir", type=Path, required=True)
    verify.set_defaults(func=verify_inputs_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SpikeStop as error:
        print(f"Spike stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
