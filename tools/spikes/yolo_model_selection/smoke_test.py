"""Run one explicit, non-overwriting smoke test per model family.

This script is intentionally not a Provider Adapter.  It reads local images and
weights, writes only below ``data/local/yolo-model-selection``, and never opens
SQLite or creates a formal artifact.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image
import yaml

try:
    from .environment_report import build_report
    from .model_registry import asset_path, find_model, load_registry, weight_path
    from .normalize import normalized_detection
    from .output_layout import create_run_layout
    from .overlays import save_overlay
    from .runners.base import classify_exception
    from .runners import yolo_world_v21, yoloe_ultralytics
    from .schemas import error_result
except ImportError:
    from environment_report import build_report
    from model_registry import asset_path, find_model, load_registry, weight_path
    from normalize import normalized_detection
    from output_layout import create_run_layout
    from overlays import save_overlay
    from runners.base import classify_exception
    from runners import yolo_world_v21, yoloe_ultralytics
    from schemas import error_result


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INFERENCE_CONFIG = REPO_ROOT / "docs/spikes/detection-ocr/followups/yolo-open-vocabulary-model-selection/configs/inference.yaml"
DEFAULT_MODELS_CONFIG = REPO_ROOT / "docs/spikes/detection-ocr/followups/yolo-open-vocabulary-model-selection/configs/models.yaml"
SMOKE_MODELS = (("YOLOE-26", "N"), ("YOLOE-11", "S"), ("YOLO-World V2.1", "S"))


def slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


def write_json(path: Path, record: dict[str, Any]) -> None:
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def raw_record(result: dict[str, Any]) -> dict[str, Any]:
    """Persist JSON-safe provider-facing evidence separately from normalized output."""
    provider_detections = [
        {
            "bbox_xyxy": detection["bbox_xyxy"],
            "confidence": detection["confidence"],
            "label": detection["label"],
            "mask_exported": "mask_path" in detection,
        }
        for detection in result["detections"]
    ]
    return {
        "schema_version": "0.1",
        "run_id": result["run_id"],
        "sample_id": result["sample_id"],
        "model": result["model"],
        "status": result["status"],
        "provider_output": {"detections": provider_detections},
        "error": result["error"],
    }


def gpu_snapshot() -> dict[str, Any]:
    try:
        import torch  # type: ignore[import-not-found]

        if torch.cuda.is_available():
            return {
                "device": 0,
                "allocated_bytes": torch.cuda.memory_allocated(0),
                "reserved_bytes": torch.cuda.memory_reserved(0),
                "max_allocated_bytes": torch.cuda.max_memory_allocated(0),
            }
    except Exception:
        pass
    return {}


def image_dimensions(image_path: Path) -> tuple[int, int]:
    """Verify a trusted local input can be opened, including very large manga pages."""
    original_limit = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(image_path) as image:
            return image.size
    finally:
        Image.MAX_IMAGE_PIXELS = original_limit


def load_inference_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = {"device", "half", "imgsz", "confidence", "iou", "max_det", "smoke_sample"}
    missing = sorted(required - config.keys())
    if missing:
        raise ValueError(f"inference config is missing required keys: {missing}")
    return config


def request_from_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_set": "text",
        "requested_imgsz": config["imgsz"],
        "confidence": config["confidence"],
        "iou": config["iou"],
        "device": config["device"],
        "half": config["half"],
    }


def runner_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: config[key] for key in ("imgsz", "confidence", "iou", "max_det", "device", "half")}


def select_sample(manifest: dict[str, Any], smoke_sample: dict[str, Any]) -> dict[str, Any]:
    for sample in manifest.get("samples", []):
        if sample.get("sample_id") != smoke_sample.get("sample_id"):
            continue
        if not sample.get("enabled"):
            raise ValueError("configured smoke sample is disabled")
        if sample.get("version") != smoke_sample.get("required_version"):
            raise ValueError("configured smoke sample does not match required_version")
        if sample.get("sha256") != smoke_sample.get("sha256"):
            raise ValueError("configured smoke sample sha256 does not match manifest")
        return sample
    raise ValueError("configured smoke sample_id is absent from manifest")


def save_mask(mask: Any, destination: Path, width: int, height: int) -> None:
    """Persist an actual segmentation mask; callers never invoke this for detection-only models."""
    import numpy as np

    array = (np.asarray(mask) > 0).astype("uint8") * 255
    Image.fromarray(array, mode="L").resize((width, height), Image.Resampling.NEAREST).save(destination)


def run_yoloe(
    model: dict[str, Any], registry_snapshot: dict[str, Any], image_path: Path, sample: dict[str, Any], run_dir: Path, run_id: str,
    request: dict[str, Any], inference: dict[str, Any],
) -> dict[str, Any]:
    missing = yoloe_ultralytics.required_dependencies()
    if missing:
        return error_result(
            run_id=run_id, sample_id=sample["sample_id"], model=model, request=request, status="dependency_missing",
            message="YOLOE smoke test skipped because optional dependencies are unavailable.", missing_dependencies=missing,
        )
    if not model["weight_exists"]:
        return error_result(
            run_id=run_id, sample_id=sample["sample_id"], model=model, request=request, status="model_load_failed",
            message="registered YOLOE weight is missing",
        )
    asset_name = model.get("text_encoder_asset")
    if not asset_name:
        return error_result(
            run_id=run_id, sample_id=sample["sample_id"], model=model, request=request, status="model_load_failed",
            message="registered YOLOE model has no local text encoder asset",
        )
    encoder = registry_snapshot["assets"][asset_name]
    if encoder["integrity_status"] != "verified":
        return error_result(
            run_id=run_id, sample_id=sample["sample_id"], model=model, request=request, status="model_load_failed",
            message=f"registered YOLOE text encoder integrity status is {encoder['integrity_status']}",
        )
    width, height = image_dimensions(image_path)
    try:
        model_instance = yoloe_ultralytics.load_model(
            weight_path(registry_snapshot, model),
            ["text"],
            asset_path(registry_snapshot, encoder),
            encoder["expected_size_bytes"],
            encoder["expected_sha256"],
        )
    except Exception as error:
        status = classify_exception(error)
        return error_result(
            run_id=run_id, sample_id=sample["sample_id"], model=model, request=request,
            status="oom" if status == "oom" else "model_load_failed", message=f"{type(error).__name__}: {error}",
        )
    try:
        started = time.perf_counter()
        predictions = yoloe_ultralytics.predict_loaded(model_instance, image_path, inference)
        elapsed = time.perf_counter() - started
    except Exception as error:
        return error_result(
            run_id=run_id, sample_id=sample["sample_id"], model=model, request=request,
            status=classify_exception(error), message=f"{type(error).__name__}: {error}",
        )
    detections: list[dict[str, Any]] = []
    boxes: list[list[float]] = []
    for index, prediction in enumerate(predictions):
        mask_path = None
        if prediction["mask"] is not None:
            mask_name = f"{sample['sample_id']}-{slug(model['family'])}-{model['variant'].lower()}-{index}.png"
            save_mask(prediction["mask"], run_dir / "masks" / mask_name, width, height)
            mask_path = f"masks/{mask_name}"
        detections.append(
            normalized_detection(
                bbox_xyxy=prediction["bbox_xyxy"], confidence=prediction["confidence"], label=prediction["label"],
                width=width, height=height, mask_path=mask_path,
            )
        )
        boxes.append(prediction["bbox_xyxy"])
    overlay_name = f"{sample['sample_id']}-{slug(model['family'])}-{model['variant'].lower()}.png"
    save_overlay(image_path, run_dir / "overlays" / overlay_name, boxes)
    return {
        "schema_version": "0.1", "run_id": run_id, "sample_id": sample["sample_id"], "model": model,
        "request": request, "actual": {"input_width": width, "input_height": height, "processed_width": inference["imgsz"], "processed_height": inference["imgsz"]},
        "detections": detections, "timing": {"inference_seconds": elapsed}, "gpu": gpu_snapshot(),
        "status": "success" if detections else "empty_result", "error": None,
    }


def run_yolo_world(model: dict[str, Any], sample: dict[str, Any], run_id: str, request: dict[str, Any]) -> dict[str, Any]:
    missing = yolo_world_v21.required_dependencies()
    if missing:
        return error_result(
            run_id=run_id, sample_id=sample["sample_id"], model=model, request=request, status="dependency_missing",
            message="YOLO-World V2.1 smoke test skipped because optional dependencies are unavailable.", missing_dependencies=missing,
        )
    return error_result(
        run_id=run_id, sample_id=sample["sample_id"], model=model, request=request, status="model_load_failed",
        message="YOLO-World V2.1 requires its matching MMYOLO model configuration; no configuration is bundled with the local checkpoint.",
    )


def run_smoke(
    data_root: Path,
    manifest_path: Path,
    output_root: Path,
    run_id: str,
    inference_config_path: Path,
    models_config_path: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = load_inference_config(inference_config_path)
    request = request_from_config(config)
    inference = runner_config(config)
    sample = select_sample(manifest, config["smoke_sample"])
    image_path = data_root / sample["relative_path"]
    if not image_path.is_file():
        raise FileNotFoundError(f"manifest image does not exist: {sample['relative_path']}")
    image_dimensions(image_path)
    registry_snapshot = load_registry(models_config_path, REPO_ROOT)
    run_dir = create_run_layout(output_root, run_id)
    environment = build_report(registry_snapshot)
    write_json(run_dir / "environment.json", environment)
    write_json(
        run_dir / "run-config.json",
        {
            "run_id": run_id,
            "request": request,
            "inference": inference,
            "smoke_sample": config["smoke_sample"],
            "models_config": str(models_config_path),
        },
    )
    results: list[dict[str, Any]] = []
    for family, variant in SMOKE_MODELS:
        model = find_model(registry_snapshot, family, variant)
        if family.startswith("YOLOE"):
            result = run_yoloe(model, registry_snapshot, image_path, sample, run_dir, run_id, request, inference)
        else:
            result = run_yolo_world(model, sample, run_id, request)
        filename = f"{sample['sample_id']}-{slug(family)}-{variant.lower()}.json"
        write_json(run_dir / "raw" / filename, raw_record(result))
        write_json(run_dir / "normalized" / filename, result)
        results.append(result)
    summary = {
        "schema_version": "0.1", "run_id": run_id, "sample_id": sample["sample_id"],
        "statuses": dict(Counter(result["status"] for result in results)), "results": [
            {"family": result["model"]["family"], "variant": result["model"]["variant"], "status": result["status"]} for result in results
        ],
    }
    write_json(run_dir / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/local"))
    parser.add_argument("--manifest", type=Path, default=Path("data/local/yolo-model-selection/manifest.local.json"))
    parser.add_argument("--output-root", type=Path, default=Path("data/local/yolo-model-selection"))
    parser.add_argument("--inference-config", type=Path, default=DEFAULT_INFERENCE_CONFIG)
    parser.add_argument("--models-config", type=Path, default=DEFAULT_MODELS_CONFIG)
    parser.add_argument("--run-id", required=True, help="Explicit, unique local run identifier; existing runs are never overwritten.")
    args = parser.parse_args()
    print(
        json.dumps(
            run_smoke(
                args.data_root,
                args.manifest,
                args.output_root,
                args.run_id,
                args.inference_config,
                args.models_config,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
