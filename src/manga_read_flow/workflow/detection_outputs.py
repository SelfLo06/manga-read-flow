from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class DetectedTextBlock:
    text_block_id: str
    reading_order: int
    bbox_json: str
    polygon_json: str
    geometry_hash: str
    confidence: float | None


def detected_text_blocks(
    page_id: str,
    candidate_outputs: dict[str, object],
) -> tuple[DetectedTextBlock, ...]:
    blocks = candidate_outputs.get("text_blocks", ())
    detected: list[DetectedTextBlock] = []
    for index, block in enumerate(blocks, start=1):
        if not isinstance(block, dict):
            raise ValueError("Detection output item must be an object.")
        bbox = block.get("bbox")
        if not isinstance(bbox, dict):
            raise ValueError("Detection output must include a bbox object.")
        bbox_json = json.dumps(bbox, sort_keys=True, separators=(",", ":"))
        polygon_json = json.dumps(_bbox_polygon(bbox), separators=(",", ":"))
        provider_ref = str(block.get("provider_block_ref") or f"tb-{page_id}-{index:03d}")
        reading_order = int(block.get("reading_order") or index)
        confidence = block.get("confidence")
        detected.append(
            DetectedTextBlock(
                text_block_id=provider_ref,
                reading_order=reading_order,
                bbox_json=bbox_json,
                polygon_json=polygon_json,
                geometry_hash=_hash_text(f"{page_id}:{provider_ref}:{bbox_json}"),
                confidence=float(confidence) if confidence is not None else None,
            )
        )
    return tuple(detected)


def _bbox_polygon(bbox: dict[str, object]) -> list[list[float]]:
    x = float(bbox["x"])
    y = float(bbox["y"])
    width = float(bbox["width"])
    height = float(bbox["height"])
    return [
        [x, y],
        [x + width, y],
        [x + width, y + height],
        [x, y + height],
    ]


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
