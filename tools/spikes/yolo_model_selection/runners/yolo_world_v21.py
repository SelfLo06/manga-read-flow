"""YOLO-World V2.1 dependency gate. No bbox is ever synthesized as a mask."""

from __future__ import annotations

from .base import missing_dependencies


def required_dependencies() -> list[str]:
    return missing_dependencies(("torch", "mmengine", "mmdet", "mmcv", "mmyolo"))
