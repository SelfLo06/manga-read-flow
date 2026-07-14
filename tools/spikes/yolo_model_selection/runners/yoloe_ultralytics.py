"""Minimal YOLOE inference adapter, used only by the isolated smoke test."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import missing_dependencies


def required_dependencies() -> list[str]:
    return missing_dependencies(("torch", "ultralytics"))


def load_model(weight_path: Path, prompts: list[str]) -> Any:
    from ultralytics import YOLO  # type: ignore[import-not-found]

    model = YOLO(str(weight_path))
    if hasattr(model, "set_classes"):
        model.set_classes(prompts)
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


def predict(weight_path: Path, image_path: Path, prompts: list[str], config: dict[str, Any]) -> list[dict[str, Any]]:
    return predict_loaded(load_model(weight_path, prompts), image_path, config)
