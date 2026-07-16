#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.spikes.text_seeded_container_association import harness
from tools.spikes.text_seeded_container_association import routed_association as routed


EXPECTED_EVALUATION_IDS = ("case-51", "case-52", "case-53", "case-54")
SCHEMA_VERSION = "text-seeded-container-goal5-evaluation-run-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise harness.HarnessStop(f"JSON root must be an object: {path}")
    return payload


def policy_from_lock(lock: dict[str, Any]) -> routed.RoutedPolicy:
    if lock.get("status") != "FROZEN" or lock.get("selected", {}).get("passed") is not True:
        raise harness.HarnessStop("calibration lock is not frozen and passing")
    return routed.RoutedPolicy(**lock["selected"]["policy"])


def run_once(root: Path, s1_path: Path, lock_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise harness.HarnessStop(f"evaluation output already exists: {output_dir}")
    root = root.resolve()
    s1 = load_json(s1_path)
    lock = load_json(lock_path)
    policy = policy_from_lock(lock)
    expected_hashes = lock.get("input", {})
    if sha256_file(s1_path) != expected_hashes.get("s1_results_sha256"):
        raise harness.HarnessStop("S1 results differ from calibration lock")
    if sha256_file(root / "S1-INPUT-SPEC.local.json") != expected_hashes.get("s1_spec_sha256"):
        raise harness.HarnessStop("S1 spec differs from calibration lock")
    if sha256_file(Path(routed.__file__)) != expected_hashes.get("routed_module_sha256"):
        raise harness.HarnessStop("routed implementation changed after calibration")
    if s1.get("input_hashes_unchanged") is not True:
        raise harness.HarnessStop("S1 source hashes changed")
    assets = [item for item in s1.get("assets", []) if item.get("asset_id", "").startswith("case-")]
    if tuple(item["asset_id"] for item in assets) != EXPECTED_EVALUATION_IDS:
        raise harness.HarnessStop("evaluation asset scope mismatch")
    output_dir.mkdir(parents=True)
    results_dir = output_dir / "results"
    results_dir.mkdir()
    outputs = []
    for asset in assets:
        page = routed.page_from_s1_asset(root, asset)
        result = routed.run_routed_association(page, policy)
        result_path = results_dir / f"{page.asset_id}.json"
        result_path.write_text(json.dumps(result.to_jsonable(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        outputs.append(
            {
                "asset_id": page.asset_id,
                "result_relative_path": result_path.relative_to(output_dir).as_posix(),
                "result_sha256": sha256_file(result_path),
                "route": result.route,
                "topology": result.topology,
                "container_count": len(result.container_regions),
                "support_count": len(result.support_regions),
                "goal6_trial_eligible": result.goal6_trial_eligible,
            }
        )
    source_hashes_after = {
        item["asset_id"]: sha256_file(root / item["relative_path"])
        for item in assets
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "asset_ids": list(EXPECTED_EVALUATION_IDS),
        "calibration_lock_sha256": sha256_file(lock_path),
        "routed_module_sha256": sha256_file(Path(routed.__file__)),
        "outputs": outputs,
        "source_hashes_after": source_hashes_after,
        "source_hashes_unchanged": all(
            source_hashes_after[item["asset_id"]] == item["sha256"] for item in assets
        ),
        "ground_truth_accessed": False,
        "evaluation_labels_accessed": False,
        "parameter_updates_after_evaluation": False,
        "cleaning_performed": False,
    }
    matrix_path = output_dir / "matrix.json"
    matrix_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--s1", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = run_once(args.root, args.s1, args.lock, args.output_dir)
    except (OSError, json.JSONDecodeError, harness.HarnessStop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
