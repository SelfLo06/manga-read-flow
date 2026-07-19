#!/usr/bin/env python3
"""Materialize Goal 6 targeted calibration crops without changing their sources."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[4]
SCHEMA = "goal6-targeted-supplement-source-selection-v1"


class SupplementStop(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_selection(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA or not isinstance(payload.get("assets"), list):
        raise SupplementStop("invalid targeted supplement selection manifest")
    assets = payload["assets"]
    ids = [item.get("asset_id") for item in assets]
    if len(ids) < 6 or len(ids) > 8 or len(set(ids)) != len(ids):
        raise SupplementStop("supplement must contain 6–8 distinct assets")
    if any(not isinstance(asset_id, str) or not asset_id.startswith("cal-") for asset_id in ids):
        raise SupplementStop("supplement asset IDs must be calibration IDs")
    return assets


def source_path(relative_path: str) -> Path:
    candidate = (ROOT / relative_path).resolve()
    local_root = (ROOT / "data" / "local").resolve()
    try:
        candidate.relative_to(local_root)
    except ValueError as error:
        raise SupplementStop("source must remain below data/local") from error
    if not candidate.is_file():
        raise SupplementStop(f"missing source: {relative_path}")
    return candidate


def materialize(selection_path: Path, output_root: Path) -> dict[str, Any]:
    assets = load_selection(selection_path)
    output_root = output_root.resolve()
    image_dir = output_root / "images"
    if (output_root / "S1-INPUT-SPEC.local.json").exists() or image_dir.exists():
        raise SupplementStop("supplement output already exists")
    image_dir.mkdir(parents=True)
    spec_assets: list[dict[str, Any]] = []
    source_hashes: set[str] = set()
    for item in assets:
        source = source_path(item["source_relative_path"])
        actual_source_hash = sha256(source)
        if actual_source_hash != item.get("source_sha256"):
            raise SupplementStop(f"source hash mismatch: {item['asset_id']}")
        if actual_source_hash in source_hashes:
            raise SupplementStop("one source page may only produce one supplement asset")
        source_hashes.add(actual_source_hash)
        crop = item.get("crop_xywh")
        if not isinstance(crop, list) or len(crop) != 4 or any(not isinstance(value, int) for value in crop):
            raise SupplementStop(f"invalid crop: {item['asset_id']}")
        x, y, width, height = crop
        if x < 0 or y < 0 or width <= 0 or height <= 0:
            raise SupplementStop(f"invalid crop bounds: {item['asset_id']}")
        with Image.open(source) as image:
            if x + width > image.width or y + height > image.height:
                raise SupplementStop(f"crop exceeds source bounds: {item['asset_id']}")
            rendered = image.convert("RGB").crop((x, y, x + width, y + height))
        name = f"{item['asset_id']}.png"
        target = image_dir / name
        rendered.save(target)
        spec_assets.append(
            {
                "asset_id": item["asset_id"],
                "relative_path": f"images/{name}",
                "sha256": sha256(target),
                "width": width,
                "height": height,
            }
        )
    spec = {"schema_version": "text-seeded-container-s1-input-spec-v1", "assets": spec_assets}
    spec_path = output_root / "S1-INPUT-SPEC.local.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"asset_count": len(spec_assets), "source_hash_count": len(source_hashes), "spec": spec_path}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = materialize(args.selection, args.output_root)
    except (OSError, ValueError, json.JSONDecodeError, SupplementStop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": "MATERIALIZED", **{key: str(value) for key, value in result.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
