#!/usr/bin/env python3
"""Build a human-review-only Goal 6 targeted policy-calibration bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from tools.experiments.grouping_120.text_seeded_container_association import goal6_mask_harness as mask
from tools.experiments.grouping_120.text_seeded_container_association.goal6_build_calibration import (
    POLICIES,
    _comparison,
    _contexts,
    _fragments,
    candidate_for,
)


class BundleStop(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BundleStop(f"JSON root must be an object: {path}")
    return payload


def build(root: Path, s1_path: Path, association_dir: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise BundleStop("supplement calibration output already exists")
    root = root.resolve()
    s1 = load(s1_path)
    matrix = load(association_dir / "matrix.json")
    if matrix.get("status") != "COMPLETED_FOR_CALIBRATION_REVIEW":
        raise BundleStop("association result is not a calibration-review result")
    if matrix.get("source_hashes_unchanged") is not True:
        raise BundleStop("association source hashes changed")
    assets = {item["asset_id"]: item for item in s1.get("assets", [])}
    output_ids = tuple(item["asset_id"] for item in matrix.get("outputs", []))
    if not 6 <= len(output_ids) <= 8 or tuple(sorted(assets)) != tuple(sorted(output_ids)):
        raise BundleStop("supplement asset scope mismatch")
    output_dir.mkdir(parents=True)
    previews = output_dir / "previews"
    previews.mkdir()
    records: dict[str, Any] = {}
    for output in matrix["outputs"]:
        asset_id = output["asset_id"]
        asset = assets[asset_id]
        routed = load(association_dir / output["result_relative_path"])
        image = np.asarray(Image.open(root / asset["relative_path"]).convert("RGB"))
        source_hash_unchanged = sha256(root / asset["relative_path"]) == asset["sha256"]
        if not source_hash_unchanged:
            raise BundleStop(f"source changed: {asset_id}")
        if routed.get("goal6_trial_eligible") is not True:
            source_path = previews / f"{asset_id}__SKIP__source.png"
            Image.fromarray(image).save(source_path)
            records[asset_id] = {
                "forced_choice": "SKIP",
                "route": routed["route"],
                "topology": routed["topology"],
                "reason": routed["abstention_reasons"],
                "preview_files": [source_path.name],
            }
            continue
        contexts = _contexts(routed)
        if not contexts:
            raise BundleStop(f"eligible asset lacks a spatial context: {asset_id}")
        fragments = _fragments(asset)
        rows: dict[str, Any] = {}
        for name, policy in POLICIES.items():
            results = tuple(
                mask.process_context(
                    image,
                    context,
                    fragments,
                    routed["route"],
                    policy,
                    (other.mask for other in contexts if other.region_id != context.region_id),
                )
                for context in contexts
            )
            mask.verify_disjoint(results)
            files = []
            for result in results:
                path = previews / f"{asset_id}__{name}__{result.context_id}.png"
                _comparison(image, result).save(path)
                files.append(path.name)
            rows[name] = {
                "policy": policy.__dict__,
                "candidate_methods": [candidate_for(image, result)[1] for result in results],
                "contexts": [
                    {
                        "context_id": result.context_id,
                        "risk": result.risk,
                        "decision": result.decision,
                        "fragment_status": result.fragment_status,
                        "diagnostics": result.diagnostics,
                    }
                    for result in results
                ],
                "preview_files": files,
            }
        records[asset_id] = {
            "forced_choice": None,
            "route": routed["route"],
            "topology": routed["topology"],
            "policy_rows": rows,
        }
    payload = {
        "schema_version": "goal6-targeted-supplement-calibration-bundle-v1",
        "purpose": "human policy calibration only; no AUTO_ACCEPT and no evaluation scoring",
        "s1_results_sha256": sha256(s1_path),
        "association_matrix_sha256": sha256(association_dir / "matrix.json"),
        "source_hashes_unchanged": True,
        "evaluation_assets_accessed": False,
        "records": records,
    }
    (output_dir / "bundle.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = "\n".join(
        f"| {asset_id} | {'SKIP（固定）' if item['forced_choice'] else ''} |  |  |  |"
        for asset_id, item in records.items()
    )
    form = f"""# Goal 6 targeted calibration review form\n\n每张 preview 从左到右依次为：原图、Mask/safe overlay、border-sampled candidate。\n\n可选项：`P0_conservative` / `P1_balanced` / `P2_recall` / `ALL_SKIP`。若同一项有多个 context，按最差 context 判定。`SKIP（固定）` 表示上游证据不足，只有原图供确认，不得改为其他选项。选择仅用于人工 policy calibration，不会产生 AUTO_ACCEPT，也不会进入正式 evaluation。\n\n| Case | Choice | 残字（none/minor/readable） | 结构损伤（none/minor/severe） | 备注 |\n| --- | --- | --- | --- | --- |\n{rows}\n\n冻结门槛：至少两个实际正例选择同一 policy；所有边界项不得出现 severe structure damage；负例不得被接受为可清理候选。任何不满足均保持未冻结。\n"""
    (output_dir / "FORM.md").write_text(form, encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--s1", required=True, type=Path)
    parser.add_argument("--association-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = build(args.root, args.s1, args.association_dir, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError, BundleStop, mask.Goal6Stop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": "READY_FOR_REVIEW", "source_hashes_unchanged": payload["source_hashes_unchanged"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
