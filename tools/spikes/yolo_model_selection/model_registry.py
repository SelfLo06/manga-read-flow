"""Explicit local-weight registry. This module never loads a model."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


MODEL_SPECS = (
    ("YOLOE-26", "N", "segmentation", "ultralytics", "models/yoloe-26/yoloe-26n-seg.pt", True, True, "smoke"),
    ("YOLOE-26", "S", "segmentation", "ultralytics", "models/yoloe-26/yoloe-26s-seg.pt", True, True, "candidate"),
    ("YOLOE-26", "M", "segmentation", "ultralytics", "models/yoloe-26/yoloe-26m-seg.pt", True, True, "candidate"),
    ("YOLOE-11", "S", "segmentation", "ultralytics", "models/yoloe-11/yoloe-11s-seg.pt", True, True, "smoke"),
    ("YOLOE-11", "M", "segmentation", "ultralytics", "models/yoloe-11/yoloe-11m-seg.pt", True, True, "baseline"),
    ("YOLO-World V2.1", "S", "detection", "mmyolo", "models/yolo-world-v2.1/s_stage1-d1c1d7d8.pth", True, False, "smoke"),
    ("YOLO-World V2.1", "M", "detection", "mmyolo", "models/yolo-world-v2.1/m_stage1-7e1e5299.pth", True, False, "baseline"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def registry(data_root: Path) -> list[dict[str, Any]]:
    """Return all seven model records, including existence and immutable hash evidence."""
    models: list[dict[str, Any]] = []
    for family, variant, task_type, framework, relative_weight, bbox, mask, role in MODEL_SPECS:
        path = data_root / relative_weight
        models.append(
            {
                "family": family,
                "variant": variant,
                "task_type": task_type,
                "framework": framework,
                "weight_path": relative_weight,
                "weight_exists": path.is_file(),
                "weight_size_bytes": path.stat().st_size if path.is_file() else None,
                "weight_sha256": sha256_file(path) if path.is_file() else None,
                "supports_bbox": bbox,
                "supports_mask": mask,
                "default_role": role,
            }
        )
    return models


def find_model(data_root: Path, family: str, variant: str) -> dict[str, Any]:
    for model in registry(data_root):
        if model["family"] == family and model["variant"] == variant:
            return model
    raise KeyError(f"unregistered model: {family} {variant}")

