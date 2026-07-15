#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.spikes.text_seeded_container_association import focused_correction
from tools.spikes.text_seeded_container_association import harness
from tools.spikes.text_seeded_container_association import routed_association as routed


SCHEMA_VERSION = "text-seeded-container-goal5-calibration-lock-v1"
EXPECTED_CALIBRATION_IDS = ("cal-51", "cal-52", "cal-53", "cal-54")


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


def evaluate_contract(result: routed.RoutedResult, label: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if result.route != label["route"]:
        failures.append("route")
    if result.topology != label["topology"]:
        failures.append("topology")
    expected_count = int(label["container_count"])
    if len(result.container_regions) != expected_count:
        failures.append("container_count")
    if result.route == "BOUNDED_SUPPORT":
        if not result.support_regions:
            failures.append("support_missing")
        if any(item.evidence.get("touches_roi_edge") for item in result.support_regions):
            failures.append("support_touches_edge")
    if result.route == "REGIONLESS_ABSTENTION" and (
        result.container_regions or result.support_regions or result.goal6_trial_eligible
    ):
        failures.append("abstention_not_regionless")
    if result.route == "COARSE_CONTAINER_SEARCH" and result.topology == "uncertain":
        failures.append("topology_not_decisive")
    return {"passed": not failures, "failures": failures}


def candidate_policies():
    for boundary in (0.45, 0.50, 0.55):
        for padding in (0.15, 0.20):
            for same in (0.80, 0.85):
                yield routed.RoutedPolicy(
                    container_boundary_threshold=boundary,
                    extreme_seed_span_ratio=0.85,
                    extreme_seed_area_ratio=0.65,
                    max_support_group_count=2,
                    support_padding_scale=padding,
                    support_max_area_ratio=0.20,
                    topology_different_threshold=0.20,
                    topology_same_threshold=same,
                )


def calibrate(root: Path, s1_path: Path, labels_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise harness.HarnessStop(f"calibration output already exists: {output_path}")
    root = root.resolve()
    s1 = load_json(s1_path)
    labels_payload = load_json(labels_path)
    labels = labels_payload.get("labels")
    if not isinstance(labels, dict) or tuple(sorted(labels)) != EXPECTED_CALIBRATION_IDS:
        raise harness.HarnessStop("calibration label scope mismatch")
    assets = [item for item in s1.get("assets", []) if item.get("asset_id", "").startswith("cal-")]
    if tuple(item["asset_id"] for item in assets) != EXPECTED_CALIBRATION_IDS:
        raise harness.HarnessStop("calibration S1 asset scope mismatch")
    if s1.get("input_hashes_unchanged") is not True:
        raise harness.HarnessStop("S1 source hashes changed")
    pages = {item["asset_id"]: routed.page_from_s1_asset(root, item) for item in assets}
    trials = []
    passing = []
    for policy in candidate_policies():
        outcomes = {}
        for asset_id in EXPECTED_CALIBRATION_IDS:
            result = routed.run_routed_association(pages[asset_id], policy)
            outcomes[asset_id] = {
                "contract": evaluate_contract(result, labels[asset_id]),
                "result": result.to_jsonable(),
            }
        trial = {
            "policy": vars(policy),
            "passed": all(item["contract"]["passed"] for item in outcomes.values()),
            "outcomes": outcomes,
        }
        trials.append(trial)
        if trial["passed"]:
            passing.append(trial)
    if not passing:
        raise harness.HarnessStop("no calibration policy passes all four contracts")
    selected = max(
        passing,
        key=lambda item: (
            item["policy"]["container_boundary_threshold"],
            item["policy"]["topology_same_threshold"],
            -item["policy"]["support_padding_scale"],
        ),
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "FROZEN",
        "scope": {
            "calibration_asset_ids": list(EXPECTED_CALIBRATION_IDS),
            "evaluation_labels_accessed": False,
            "evaluation_assets_scored": False,
            "pixel_boundary_gt_used": False,
        },
        "input": {
            "s1_results_sha256": sha256_file(s1_path),
            "s1_spec_sha256": sha256_file(root / "S1-INPUT-SPEC.local.json"),
            "calibration_labels_sha256": sha256_file(labels_path),
            "routed_module_sha256": sha256_file(Path(routed.__file__)),
            "base_harness_sha256": sha256_file(Path(harness.__file__)),
            "focused_module_sha256": sha256_file(Path(focused_correction.__file__)),
        },
        "grid_size": len(trials),
        "passing_policy_count": len(passing),
        "selection_rule": "all contracts pass; maximize boundary and same thresholds; minimize support padding",
        "selected": selected,
        "trials": trials,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--s1", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = calibrate(args.root, args.s1, args.labels, args.output)
    except (OSError, json.JSONDecodeError, harness.HarnessStop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": payload["status"], "selected": payload["selected"]["policy"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
