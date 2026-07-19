#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.experiments.grouping_120.text_seeded_container_association import harness


EXPECTED_IDS = ("case-51", "case-52", "case-53", "case-54")


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


def evaluate(matrix_path: Path, labels_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise harness.HarnessStop(f"evaluation output already exists: {output_path}")
    matrix = load_json(matrix_path)
    labels_payload = load_json(labels_path)
    labels = labels_payload.get("labels")
    if not isinstance(labels, dict) or tuple(sorted(labels)) != EXPECTED_IDS:
        raise harness.HarnessStop("evaluation label scope mismatch")
    if matrix.get("ground_truth_accessed") is not False or matrix.get("evaluation_labels_accessed") is not False:
        raise harness.HarnessStop("run reports evaluator access")
    if matrix.get("source_hashes_unchanged") is not True:
        raise harness.HarnessStop("source hashes changed")
    run_dir = matrix_path.parent
    cases = []
    route_checks: list[bool] = []
    topology_checks: list[bool] = []
    container_count_checks: list[bool] = []
    support_checks: list[bool] = []
    abstention_checks: list[bool] = []
    false_low_risk_candidate_count = 0
    cross_container_leakage_violation_count = 0
    for item in matrix.get("outputs", []):
        asset_id = item["asset_id"]
        if asset_id not in labels:
            raise harness.HarnessStop(f"unexpected evaluation asset: {asset_id}")
        result_path = run_dir / item["result_relative_path"]
        if sha256_file(result_path) != item["result_sha256"]:
            raise harness.HarnessStop(f"result hash mismatch: {asset_id}")
        result = load_json(result_path)
        label = labels[asset_id]
        failures = []
        route_ok = result.get("route") == label["route"]
        route_checks.append(route_ok)
        topology_ok = result.get("topology") == label["topology"]
        if not route_ok:
            failures.append("route")
        if not topology_ok:
            failures.append("topology")
        regions = result.get("container_regions_or_null") or []
        supports = result.get("support_regions_or_null") or []
        container_count_ok = len(regions) == label["container_count"]
        if not container_count_ok:
            failures.append("container_count")
        if label["topology"] in {"same", "different"}:
            topology_checks.append(topology_ok)
        if label["route"] == "COARSE_CONTAINER_SEARCH":
            container_count_checks.append(container_count_ok)
        if label["route"] == "BOUNDED_SUPPORT":
            support_ok = bool(supports) and not any(
                entry.get("touches_roi_edge") for entry in supports
            )
            support_checks.append(support_ok)
            if not support_ok:
                failures.append("bounded_support")
        if label["route"] == "REGIONLESS_ABSTENTION":
            abstention_ok = not regions and not supports and not result.get("goal6_trial_eligible")
            abstention_checks.append(abstention_ok)
            if not abstention_ok:
                failures.append("regionless_abstention")
        if result.get("topology") == "uncertain" and result.get("goal6_trial_eligible"):
            failures.append("unsafe_topology_eligibility")
        if result.get("recommended_decision") not in {"REVIEW_REQUIRED", "SKIP"}:
            false_low_risk_candidate_count += 1
            failures.append("forbidden_decision")
        if (
            label["topology"] == "different"
            and result.get("route") == "COARSE_CONTAINER_SEARCH"
            and result.get("goal6_trial_eligible")
            and (not topology_ok or not container_count_ok)
        ):
            cross_container_leakage_violation_count += 1
        cases.append({"asset_id": asset_id, "passed": not failures, "failures": failures})
    if tuple(item["asset_id"] for item in cases) != EXPECTED_IDS:
        raise harness.HarnessStop("evaluation output scope mismatch")
    passed = sum(item["passed"] for item in cases)

    def ratio(checks: list[bool]) -> str:
        return f"{sum(checks)}/{len(checks)}"

    payload = {
        "schema_version": "text-seeded-container-goal5-evaluation-v1",
        "matrix_sha256": sha256_file(matrix_path),
        "labels_sha256": sha256_file(labels_path),
        "route_correctness": ratio(route_checks),
        "topology_correctness": ratio(topology_checks),
        "container_count_correctness": ratio(container_count_checks),
        "bounded_support_validity": ratio(support_checks),
        "regionless_abstention": ratio(abstention_checks),
        "false_low_risk_candidate_count": false_low_risk_candidate_count,
        "cross_container_leakage_violation_count": cross_container_leakage_violation_count,
        "cases": cases,
        "passed": passed == 4 and false_low_risk_candidate_count == 0
        and cross_container_leakage_violation_count == 0,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = evaluate(args.matrix, args.labels, args.output)
    except (OSError, json.JSONDecodeError, harness.HarnessStop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
