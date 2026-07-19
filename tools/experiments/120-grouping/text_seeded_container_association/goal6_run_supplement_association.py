#!/usr/bin/env python3
"""Route Goal 6 calibration supplements with the already frozen Goal 5 router."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.experiments.grouping_120.text_seeded_container_association import routed_association as routed
from tools.experiments.grouping_120.text_seeded_container_association.run_routed_evaluation import policy_from_lock


class SupplementAssociationStop(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SupplementAssociationStop(f"JSON root must be an object: {path}")
    return data


def run(root: Path, s1_path: Path, lock_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise SupplementAssociationStop("supplement association output already exists")
    root = root.resolve()
    s1 = load(s1_path)
    lock = load(lock_path)
    policy = policy_from_lock(lock)
    assets = s1.get("assets")
    if not isinstance(assets, list) or not 6 <= len(assets) <= 8:
        raise SupplementAssociationStop("supplement S1 scope must contain 6–8 assets")
    if any(not str(item.get("asset_id", "")).startswith("cal-") for item in assets):
        raise SupplementAssociationStop("supplement can only route calibration assets")
    if s1.get("input_hashes_unchanged") is not True:
        raise SupplementAssociationStop("S1 source hashes changed")
    output_dir.mkdir(parents=True)
    results_dir = output_dir / "results"
    results_dir.mkdir()
    outputs: list[dict[str, Any]] = []
    for asset in sorted(assets, key=lambda item: item["asset_id"]):
        page = routed.page_from_s1_asset(root, asset)
        result = routed.run_routed_association(page, policy)
        result_path = results_dir / f"{page.asset_id}.json"
        result_path.write_text(json.dumps(result.to_jsonable(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        outputs.append(
            {
                "asset_id": page.asset_id,
                "route": result.route,
                "topology": result.topology,
                "goal6_trial_eligible": result.goal6_trial_eligible,
                "result_relative_path": result_path.relative_to(output_dir).as_posix(),
                "result_sha256": sha256(result_path),
            }
        )
    payload = {
        "schema_version": "goal6-targeted-supplement-association-v1",
        "status": "COMPLETED_FOR_CALIBRATION_REVIEW",
        "asset_ids": [item["asset_id"] for item in sorted(assets, key=lambda item: item["asset_id"])],
        "goal5_lock_sha256": sha256(lock_path),
        "routed_module_sha256": sha256(Path(routed.__file__)),
        "source_hashes_unchanged": all(sha256(root / item["relative_path"]) == item["sha256"] for item in assets),
        "evaluation_assets_accessed": False,
        "labels_accessed": False,
        "outputs": outputs,
    }
    (output_dir / "matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--s1", required=True, type=Path)
    parser.add_argument("--goal5-lock", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = run(args.root, args.s1, args.goal5_lock, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError, SupplementAssociationStop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": payload["status"], "source_hashes_unchanged": payload["source_hashes_unchanged"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
