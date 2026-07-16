"""Build a local-only image manifest without copying or changing image inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

try:
    from .model_registry import sha256_file
except ImportError:  # Direct execution: python tools/.../build_manifest.py
    from model_registry import sha256_file


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
EXCLUDED_TOP_LEVEL = {"models", "yolo-model-selection"}


def sample_id(relative_path: str, content_sha256: str) -> str:
    identity = f"{relative_path}\0{content_sha256}".encode("utf-8")
    return "sample_" + hashlib.sha256(identity).hexdigest()[:16]


def infer_version(relative: Path) -> str:
    """Classify the corpus's three per-work image versions without adding tags."""
    directory_name = relative.parent.name
    if "無字" in directory_name or "无字" in directory_name:
        return "cleaned"
    if "中国" in directory_name or "翻訳" in directory_name or "翻译" in directory_name:
        return "translated"
    return "original"


def scan_images(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and path.relative_to(root).parts[0] not in EXCLUDED_TOP_LEVEL
    )


def image_metadata(path: Path) -> tuple[int, int, str]:
    """Read dimensions for a trusted local image without decoding its full payload.

    Manga source pages legitimately exceed Pillow's generic decompression-bomb
    threshold.  The override is limited to this metadata read and always
    restored, so it cannot silently change behavior elsewhere in the process.
    """
    original_limit = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format or path.suffix.lstrip(".").upper()
        return width, height, image_format.upper()
    finally:
        Image.MAX_IMAGE_PIXELS = original_limit


def build_manifest(root: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in scan_images(root):
        relative = path.relative_to(root)
        width, height, image_format = image_metadata(path)
        content_hash = sha256_file(path)
        relative_text = relative.as_posix()
        entries.append(
            {
                "sample_id": sample_id(relative_text, content_hash),
                "relative_path": relative_text,
                "version": infer_version(relative),
                "sha256": content_hash,
                "width": width,
                "height": height,
                "format": image_format,
                "tags": [],
                "enabled": True,
            }
        )
    return {"schema_version": "0.1", "root": ".", "samples": entries}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/local"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.root.resolve()) is False:
        raise ValueError("manifest output must remain below --root")
    manifest = build_manifest(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(manifest['samples'])} samples to {args.output}")


if __name__ == "__main__":
    main()
