#!/usr/bin/env python3
"""Build a local, review-only Goal 6 calibration bundle from Goal 5 artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from tools.spikes.text_seeded_container_association import goal6_mask_harness as mask


POLICIES = {
    "P0_conservative": mask.MaskPolicy(-4, 1, 4, 0.97, soft_edge_completion_radius=1),
    "P1_balanced": mask.MaskPolicy(8, 1, 3, 0.95, soft_edge_completion_radius=2),
    "P2_recall": mask.MaskPolicy(18, 2, 2, 0.92, soft_edge_completion_radius=3),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fragments(asset: dict[str, Any]) -> tuple[mask.Fragment, ...]:
    return tuple(
        mask.Fragment(
            item["fragment_id"],
            tuple(tuple(point) for point in item["polygon"]),
            item.get("score"),
        )
        for item in asset["fragments"]
    )


def _contexts(result: dict[str, Any]) -> tuple[mask.Context, ...]:
    entries = result.get("container_regions_or_null") or result.get("support_regions_or_null") or []
    return tuple(
        mask.Context(item["region_id"], tuple(item["fragment_ids"]), mask.rle_to_mask(item["mask_rle"]))
        for item in entries
    )


def _overlay(image: np.ndarray, result: mask.ContextResult) -> Image.Image:
    canvas = image.copy().astype(np.float32)
    for layer, color, alpha in (
        (result.safe, (30, 180, 80), 0.22),
        (result.protected, (230, 65, 55), 0.42),
        (result.uncertain, (255, 190, 20), 0.52),
        (result.effective, (30, 150, 255), 0.70),
    ):
        canvas[layer] = canvas[layer] * (1.0 - alpha) + np.asarray(color) * alpha
    return Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))


def candidate_for(image: np.ndarray, result: mask.ContextResult) -> tuple[np.ndarray, str]:
    if result.risk == "E1" and result.effective.any():
        return mask.border_sampled_fill(image, result.effective, result.safe, result.soft), "border_sampled_fill"
    if result.risk == "E2" and result.effective.any():
        return mask.low_radius_telea(image, result.effective), "telea_r2_comparison"
    return image.copy(), f"source_copy_for_{result.risk}"


def _comparison(image: np.ndarray, result: mask.ContextResult) -> Image.Image:
    source = Image.fromarray(image)
    overlay = _overlay(image, result)
    candidate, _ = candidate_for(image, result)
    width, height = source.size
    sheet = Image.new("RGB", (width * 3, height), "white")
    sheet.paste(source, (0, 0))
    sheet.paste(overlay, (width, 0))
    sheet.paste(Image.fromarray(candidate), (width * 2, 0))
    return sheet


def build(root: Path, s1_path: Path, goal5_lock: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise mask.Goal6Stop(f"calibration output already exists: {output_dir}")
    root = root.resolve()
    s1 = load(s1_path)
    lock = load(goal5_lock)
    assets = {item["asset_id"]: item for item in s1["assets"]}
    cases = ("cal-51", "cal-52", "cal-53", "cal-54")
    if tuple(sorted(assets)) != ("cal-51", "cal-52", "cal-53", "cal-54", "case-51", "case-52", "case-53", "case-54"):
        raise mask.Goal6Stop("unexpected S1 scope")
    if lock.get("status") != "FROZEN":
        raise mask.Goal6Stop("Goal 5 calibration lock is not frozen")
    output_dir.mkdir(parents=True)
    previews = output_dir / "previews"
    previews.mkdir()
    records: dict[str, Any] = {}
    for case_id in cases:
        asset = assets[case_id]
        image = np.asarray(Image.open(root / asset["relative_path"]).convert("RGB"))
        routed = lock["selected"]["outcomes"][case_id]["result"]
        contexts = _contexts(routed)
        rows: dict[str, Any] = {}
        if not contexts:
            rows["regionless"] = {"route": routed["route"], "decision": "SKIP", "reason": routed["abstention_reasons"]}
        else:
            fragments = _fragments(asset)
            for name, policy in POLICIES.items():
                results = tuple(
                    mask.process_context(image, context, fragments, routed["route"], policy, (other.mask for other in contexts if other.region_id != context.region_id))
                    for context in contexts
                )
                mask.verify_disjoint(results)
                paths = []
                for result in results:
                    path = previews / f"{case_id}__{name}__{result.context_id}.png"
                    _comparison(image, result).save(path)
                    paths.append(path.name)
                rows[name] = {
                    "policy": policy.__dict__,
                    "candidate_methods": [candidate_for(image, item)[1] for item in results],
                    "contexts": [
                        {
                            "context_id": item.context_id,
                            "risk": item.risk,
                            "decision": item.decision,
                            "fragment_status": item.fragment_status,
                            "diagnostics": item.diagnostics,
                        }
                        for item in results
                    ],
                    "preview_files": paths,
                }
        records[case_id] = rows
    payload = {
        "schema_version": "goal6-calibration-bundle-v1",
        "goal5_s1_sha256": sha256(s1_path),
        "goal5_lock_sha256": sha256(goal5_lock),
        "source_hashes_unchanged": all(sha256(root / item["relative_path"]) == item["sha256"] for item in assets.values()),
        "evaluation_assets_accessed": False,
        "records": records,
    }
    (output_dir / "bundle.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    form = """# Goal 6 calibration review form\n\n状态：待填写。每张 preview 从左到右为原图、Mask/safe overlay、border-sampled candidate。\n\n对 cal-51、cal-52、cal-53：在 `P0_conservative` / `P1_balanced` / `P2_recall` / `ALL_SKIP` 中选一个；若多 context，请按最差 context 判断。cal-54 固定 `SKIP`。\n\n| Case | Choice | 可辨认残字（none/minor/readable） | 结构伤害（none/minor/severe） | 备注 |\n| --- | --- | --- | --- | --- |\n| cal-51 |  |  |  |  |\n| cal-52 |  |  |  |  |\n| cal-53 |  |  |  |  |\n| cal-54 | SKIP | n/a | none | regionless control |\n\n选择只用于冻结单一保守 policy；它不会修改 Goal 5 或直接产生 AUTO_ACCEPT。\n"""
    (output_dir / "FORM.md").write_text(form, encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--s1", required=True, type=Path)
    parser.add_argument("--goal5-lock", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = build(args.root, args.s1, args.goal5_lock, args.output_dir)
    except (OSError, ValueError, mask.Goal6Stop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": "READY_FOR_REVIEW", "source_hashes_unchanged": payload["source_hashes_unchanged"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
