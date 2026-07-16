"""Minimal YOLOE inference adapter, used only by the isolated smoke test."""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .base import missing_dependencies

try:
    from ..model_registry import sha256_file
except ImportError:
    from model_registry import sha256_file


def required_dependencies() -> list[str]:
    return missing_dependencies(("torch", "ultralytics", "clip"))


def validate_text_encoder(path: Path, expected_size_bytes: int, expected_sha256: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"local YOLOE text encoder is missing: {path}")
    actual_size = path.stat().st_size
    if actual_size != expected_size_bytes:
        raise ValueError(f"local YOLOE text encoder size mismatch: expected {expected_size_bytes}, got {actual_size}")
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(f"local YOLOE text encoder SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}")


@contextmanager
def local_only_ultralytics_asset(text_encoder_path: Path) -> Iterator[None]:
    """Make Ultralytics resolve exactly one verified local asset and forbid network fallback."""
    import ultralytics.utils.downloads as downloads  # type: ignore[import-not-found]

    original = downloads.attempt_download_asset

    def resolve_local(file: str | Path, *args: Any, **kwargs: Any) -> str:
        requested = Path(file)
        if requested.name != text_encoder_path.name:
            raise FileNotFoundError(
                f"Ultralytics requested unregistered asset {requested.name!r}; automatic download is disabled"
            )
        if not text_encoder_path.is_file():
            raise FileNotFoundError(f"registered local asset is missing: {text_encoder_path}")
        return str(text_encoder_path)

    downloads.attempt_download_asset = resolve_local
    try:
        yield
    finally:
        downloads.attempt_download_asset = original


def load_model(
    weight_path: Path,
    prompts: list[str],
    text_encoder_path: Path,
    expected_encoder_size_bytes: int,
    expected_encoder_sha256: str,
) -> Any:
    for dependency in ("torch", "ultralytics", "clip"):
        importlib.import_module(dependency)
    validate_text_encoder(text_encoder_path, expected_encoder_size_bytes, expected_encoder_sha256)
    from ultralytics import YOLO  # type: ignore[import-not-found]

    model = YOLO(str(weight_path))
    if hasattr(model, "set_classes"):
        original_cwd = Path.cwd()
        try:
            os.chdir(text_encoder_path.parent)
            with local_only_ultralytics_asset(text_encoder_path):
                model.set_classes(prompts)
        finally:
            os.chdir(original_cwd)
    return model


def predict_loaded(model: Any, image_path: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    results = model.predict(
        source=str(image_path),
        imgsz=config["imgsz"],
        conf=config["confidence"],
        iou=config["iou"],
        max_det=config["max_det"],
        device=config["device"],
        half=config["half"],
        verbose=False,
    )
    result = results[0]
    boxes = result.boxes
    if boxes is None:
        return []
    masks = result.masks
    predictions: list[dict[str, Any]] = []
    for index, xyxy in enumerate(boxes.xyxy.cpu().tolist()):
        predictions.append(
            {
                "bbox_xyxy": xyxy,
                "confidence": float(boxes.conf[index]),
                "label": str(result.names[int(boxes.cls[index])]),
                "mask": masks.data[index].cpu().numpy() if masks is not None else None,
            }
        )
    return predictions


def predict(
    weight_path: Path,
    image_path: Path,
    prompts: list[str],
    config: dict[str, Any],
    text_encoder_path: Path,
    expected_encoder_size_bytes: int,
    expected_encoder_sha256: str,
) -> list[dict[str, Any]]:
    model = load_model(
        weight_path,
        prompts,
        text_encoder_path,
        expected_encoder_size_bytes,
        expected_encoder_sha256,
    )
    return predict_loaded(model, image_path, config)
