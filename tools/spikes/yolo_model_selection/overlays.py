"""Overlay helpers consume original-coordinate boxes only."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw


def save_overlay(input_path: Path, output_path: Path, boxes: Iterable[list[float]]) -> None:
    original_limit = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(input_path) as image:
            canvas = image.convert("RGB")
    finally:
        Image.MAX_IMAGE_PIXELS = original_limit
    draw = ImageDraw.Draw(canvas)
    for box in boxes:
        draw.rectangle(box, outline="red", width=max(1, min(canvas.size) // 300))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
