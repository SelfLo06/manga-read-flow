"""Oracle-free adapter for the existing local Paddle Detection spike.

This module deliberately only accepts a full source image, its hash, and a
run-local output directory.  It reuses the experiment's existing
``PaddleDetector``; it does not change its model configuration or inspect the
case/oracle/ROI.
"""
from __future__ import annotations

from hashlib import sha256
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[4]
SPIKE_PATH = ROOT / "tools/experiments/130-ocr/detection_ocr/spike.py"
MODEL_CACHE = Path.home() / ".paddlex/official_models/PP-OCRv6_medium_det"
MODEL_FILE = MODEL_CACHE / "inference.pdiparams"


class DetectionAdapterError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_bbox(values: dict[str, Any], *, width: int, height: int) -> dict[str, float]:
    """Validate (rather than silently clip) existing detector geometry."""
    try:
        x = float(values["x"])
        y = float(values["y"])
        box_width = float(values["width"])
        box_height = float(values["height"])
    except (KeyError, TypeError, ValueError) as error:
        raise DetectionAdapterError("Paddle prediction lacks a numeric bbox") from error
    if not (0.0 <= x < x + box_width <= width and 0.0 <= y < y + box_height <= height):
        raise DetectionAdapterError(f"Paddle emitted out-of-bounds bbox: {values}")
    return {"x": x, "y": y, "width": box_width, "height": box_height}


def normalize_polygon(points: Any, *, width: int, height: int) -> list[list[float]]:
    if not isinstance(points, list) or len(points) < 3:
        raise DetectionAdapterError("Paddle prediction lacks a usable polygon")
    normalized: list[list[float]] = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            raise DetectionAdapterError("Paddle emitted an invalid polygon point")
        x, y = float(point[0]), float(point[1])
        if not (0.0 <= x <= width and 0.0 <= y <= height):
            raise DetectionAdapterError(f"Paddle emitted out-of-bounds polygon point: {point}")
        normalized.append([x, y])
    return normalized


def _load_spike() -> Any:
    if not SPIKE_PATH.is_file():
        raise DetectionAdapterError(f"existing Paddle Detection spike is missing: {SPIKE_PATH}")
    spec = importlib.util.spec_from_file_location("page_edge_existing_paddle_spike", SPIKE_PATH)
    if spec is None or spec.loader is None:
        raise DetectionAdapterError("cannot load existing Paddle Detection spike")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"


def run(*, source_path: Path, source_sha256: str, output_dir: Path) -> dict[str, Any]:
    """Run the existing full-page Paddle detector and freeze normalized evidence."""
    if not source_path.is_file() or sha256_file(source_path) != source_sha256:
        raise DetectionAdapterError("source hash mismatch")
    if not MODEL_FILE.is_file():
        raise DetectionAdapterError(f"local PP-OCRv6 detection model cache is missing: {MODEL_FILE}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise DetectionAdapterError(f"detection output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    # The exact default model is already cached.  Disable source health checks
    # so an offline experiment cannot fetch or install an alternative model.
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    with Image.open(source_path) as image:
        width, height = image.size
    try:
        spike = _load_spike()
        detector = spike.PaddleDetector()
        result = detector.predict(source_path)
    except Exception as error:  # pragma: no cover - environment-dependent evidence
        raise DetectionAdapterError(f"existing Paddle Detection spike failed: {error!r}") from error

    candidates = []
    for ordinal, prediction in enumerate(result["predictions"], start=1):
        polygon = normalize_polygon(prediction["polygon"], width=width, height=height)
        bbox = normalize_bbox(prediction["bbox"], width=width, height=height)
        candidates.append(
            {
                "candidate_id": f"paddle-{ordinal:04d}",
                "geometry_type": "polygon",
                "geometry": polygon,
                "bbox_full_page": bbox,
                "confidence": prediction.get("score"),
                "class": "detected_text",
                "provider_provenance": {
                    "implementation": "tools/experiments/130-ocr/detection_ocr/spike.py:PaddleDetector",
                    "mode": result["mode"],
                    "model": "PP-OCRv6_medium_det",
                    "local_model_path": str(MODEL_FILE),
                    "local_model_sha256": sha256_file(MODEL_FILE),
                },
            }
        )
    config = {
        "implementation": "existing PaddleDetector default configuration",
        "model": "PP-OCRv6_medium_det",
        "model_cache": str(MODEL_CACHE),
        "network_disabled_by": {"PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True"},
        "algorithm_input": "full_page",
    }
    provenance = {
        "provider": "PaddleOCR",
        "implementation": "tools/experiments/130-ocr/detection_ocr/spike.py:PaddleDetector",
        "paddleocr_version": _package_version("paddleocr"),
        "paddle_version": _package_version("paddlepaddle-gpu"),
        "source_sha256": source_sha256,
        "coordinate_space": "full_page",
        "detector_mode": result["mode"],
        "init_duration_sec": detector.init_duration_sec,
        "prediction_duration_sec": result["duration_sec"],
    }
    candidates_json = {
        "schema_version": "page-edge-bubble-detection-candidates-v1",
        "source_sha256": source_sha256,
        "coordinate_space": "full_page",
        "image_dimensions": {"width": width, "height": height},
        "candidates": candidates,
    }
    _write_json(output_dir / "detection_candidates.json", candidates_json)
    _write_json(output_dir / "detection_config.json", config)
    _write_json(output_dir / "detection_provenance.json", provenance)
    with Image.open(source_path) as image:
        overlay = image.convert("RGB")
    draw = ImageDraw.Draw(overlay)
    for candidate in candidates:
        polygon = [tuple(point) for point in candidate["geometry"]]
        draw.line([*polygon, polygon[0]], fill=(255, 32, 32), width=3)
        draw.text(polygon[0], candidate["candidate_id"], fill=(255, 32, 32))
    overlay.save(output_dir / "detection_overlay.png", "PNG")
    return {
        "candidate_count": len(candidates),
        "candidates_path": output_dir / "detection_candidates.json",
        "config_path": output_dir / "detection_config.json",
        "provenance_path": output_dir / "detection_provenance.json",
        "overlay_path": output_dir / "detection_overlay.png",
        "implementation": config["implementation"],
        "provider_version": provenance["paddleocr_version"],
    }
