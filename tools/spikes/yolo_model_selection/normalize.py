"""Coordinate conversion and normalized result construction."""

from __future__ import annotations

from typing import Any


def normalize_bbox_xyxy(bbox: list[float], width: int, height: int) -> list[float]:
    if width <= 0 or height <= 0 or len(bbox) != 4:
        raise ValueError("bbox requires four values and positive image dimensions")
    x1, y1, x2, y2 = bbox
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox coordinates must be ordered")
    return [x1 / width, y1 / height, x2 / width, y2 / height]


def denormalize_bbox_xyxy(bbox: list[float], width: int, height: int) -> list[float]:
    if width <= 0 or height <= 0 or len(bbox) != 4:
        raise ValueError("bbox requires four values and positive image dimensions")
    return [bbox[0] * width, bbox[1] * height, bbox[2] * width, bbox[3] * height]


def normalized_detection(
    *, bbox_xyxy: list[float], confidence: float, label: str, width: int, height: int, mask_path: str | None = None
) -> dict[str, Any]:
    detection: dict[str, Any] = {
        "label": label,
        "confidence": confidence,
        "bbox_xyxy": bbox_xyxy,
        "bbox_normalized_xyxy": normalize_bbox_xyxy(bbox_xyxy, width, height),
    }
    if mask_path is not None:
        detection["mask_path"] = mask_path
    return detection

