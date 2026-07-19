#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


EXPECTED_MATRIX_SHA256 = "075c232a8da60550daa275d12a0bd3d8c2651775c07f5cbb0939bf3357f1fa15"
EXPECTED_CONTRACT_SHA256 = "984ca71f1f1abe0a28fc09e222baad3e4d50c48329237c506b20d86f92dfb385"
EXPECTED_GOAL3_EVALUATION_SHA256 = "5713132f03ffb34b8e9d7a9b668d4536200cb9939ec9bd9ee03b10234d096077"
EXPECTED_ASSET_IDS = tuple(f"case-{index:02d}" for index in range(1, 7))
SCHEMA_VERSION = "text-seeded-container-goal4-r0-evaluation-v1"


class EvaluationStop(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationStop(f"cannot read JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise EvaluationStop(f"JSON root must be an object: {path}")
    return payload


def decode_bool_rle(payload: dict[str, Any] | None) -> np.ndarray | None:
    if payload is None:
        return None
    shape = tuple(payload["shape"])
    values = []
    value = int(payload["starts_with"])
    for count in payload["counts"]:
        values.append(np.full(int(count), value, dtype=np.bool_))
        value = 1 - value
    flat = np.concatenate(values) if values else np.zeros(0, dtype=np.bool_)
    if flat.size != int(np.prod(shape)):
        raise EvaluationStop("invalid region RLE length")
    return flat.reshape(shape)


def assess_topology(case: dict[str, Any], regions: list[dict[str, Any]]) -> dict[str, Any]:
    fragment_to_regions: dict[str, list[str]] = {}
    for region in regions:
        for fragment_id in region["fragment_ids"]:
            fragment_to_regions.setdefault(fragment_id, []).append(region["region_id"])
    group_region_ids = []
    integral = True
    for group in case["target_fragment_groups"]:
        ids = sorted({region_id for fragment in group for region_id in fragment_to_regions.get(fragment, [])})
        if len(ids) != 1 or any(len(fragment_to_regions.get(fragment, [])) != 1 for fragment in group):
            integral = False
        group_region_ids.append(ids)
    distinct = sorted({region_id for ids in group_region_ids for region_id in ids})
    expected = case["expected_topology"]
    if expected == "not_applicable":
        assessment = "NOT_APPLICABLE"
    elif not integral:
        assessment = "FAIL"
    elif expected == "same_container":
        assessment = "PASS" if len(distinct) == 1 else "FAIL"
    elif expected == "different_containers":
        assessment = "PASS" if len(distinct) == len(group_region_ids) else "FAIL"
    else:
        raise EvaluationStop(f"unknown topology: {expected}")
    return {
        "assessment": assessment,
        "group_integrity": integral,
        "group_region_ids": group_region_ids,
        "target_region_ids": distinct,
    }


def evaluate_result(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    topology = assess_topology(case, result["regions"])
    decoded = {region["region_id"]: decode_bool_rle(region["mask_rle"]) for region in result["regions"]}
    target_regions = [region for region in result["regions"] if region["region_id"] in topology["target_region_ids"]]
    target_nonnull = [region for region in target_regions if decoded[region["region_id"]] is not None]
    excluded = set(case["excluded_or_false_seed_fragments"])
    excluded_nonnull_regions = [
        region["region_id"]
        for region in result["regions"]
        if decoded[region["region_id"]] is not None and excluded.intersection(region["fragment_ids"])
    ]
    safety_pass = result["recommended_decision"] in case["required_safety_decisions"]
    expected_type = case["expected_container_type"]
    if expected_type == "not_text":
        type_pass = result["recommended_decision"] == "SKIP" and not any(
            mask is not None for mask in decoded.values()
        )
    else:
        type_pass = bool(target_regions) and len(target_nonnull) == len(target_regions) and {
            region["container_type"] for region in target_nonnull
        } == {expected_type}
    diagnostics = []
    for region in target_regions:
        mask = decoded[region["region_id"]]
        if mask is None:
            diagnostics.append({"region_id": region["region_id"], "mask_present": False})
            continue
        diagnostics.append(
            {
                "region_id": region["region_id"],
                "mask_present": True,
                "area_ratio": float(mask.mean()),
                "touches_roi_edge": bool(
                    mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any()
                ),
            }
        )
    return {
        "asset_id": case["asset_id"],
        "method_id": result["method_id"],
        "expected_container_type": expected_type,
        "expected_container_count": case["expected_container_count"],
        "expected_topology": case["expected_topology"],
        "recommended_decision": result["recommended_decision"],
        "safety_decision_assessment": "PASS" if safety_pass else "FAIL",
        "topology": topology,
        "target_region_availability_assessment": (
            "NOT_APPLICABLE"
            if not case["target_fragment_groups"]
            else "PASS"
            if len(target_nonnull) == len(target_regions)
            else "FAIL"
        ),
        "container_type_assessment": "PASS" if type_pass else "FAIL",
        "excluded_or_false_seed_nonnull_region_ids": excluded_nonnull_regions,
        "target_region_mask_diagnostics": diagnostics,
        "coarse_reference_assessment": "MANUAL_TOLERANT_REVIEW_REQUIRED",
        "abstention_reasons": result["abstention_reasons"],
    }


def evaluate(
    matrix_root: Path,
    contract_path: Path,
    goal3_evaluation_path: Path,
) -> dict[str, Any]:
    matrix_path = matrix_root / "matrix.json"
    hashes = {
        "matrix": sha256_file(matrix_path),
        "contract": sha256_file(contract_path),
        "goal3_evaluation": sha256_file(goal3_evaluation_path),
        "evaluator": sha256_file(Path(__file__)),
    }
    expected = {
        "matrix": EXPECTED_MATRIX_SHA256,
        "contract": EXPECTED_CONTRACT_SHA256,
        "goal3_evaluation": EXPECTED_GOAL3_EVALUATION_SHA256,
    }
    for name, value in expected.items():
        if hashes[name] != value:
            raise EvaluationStop(f"frozen {name} hash mismatch: {hashes[name]}")
    matrix = _load_json(matrix_path)
    contract = _load_json(contract_path)
    goal3 = _load_json(goal3_evaluation_path)
    if matrix.get("status") != "completed" or matrix.get("ground_truth_accessed") is not False:
        raise EvaluationStop("Goal 4 matrix is not a completed GT-isolated run")
    if matrix.get("parameter_updates_after_r0") is not False or matrix.get("source_hashes_unchanged") is not True:
        raise EvaluationStop("Goal 4 matrix violates parameter/source freeze")
    if matrix.get("asset_ids") != list(EXPECTED_ASSET_IDS):
        raise EvaluationStop("Goal 4 matrix asset scope mismatch")
    output_by_asset = {item["asset_id"]: item for item in matrix["outputs"]}
    records = []
    for case in contract["cases"]:
        output = output_by_asset[case["asset_id"]]
        result_path = matrix_root / output["result_relative_path"]
        overlay_path = matrix_root / output["overlay_relative_path"]
        if sha256_file(result_path) != output["result_sha256"] or sha256_file(overlay_path) != output["overlay_sha256"]:
            raise EvaluationStop(f"Goal 4 artifact hash mismatch: {case['asset_id']}")
        records.append(evaluate_result(case, _load_json(result_path)))
    eligible = [record for record in records if record["topology"]["assessment"] != "NOT_APPLICABLE"]
    summary = {
        "case_count": len(records),
        "safety_pass_count": sum(record["safety_decision_assessment"] == "PASS" for record in records),
        "topology_pass_count": sum(record["topology"]["assessment"] == "PASS" for record in eligible),
        "topology_eligible_count": len(eligible),
        "target_region_availability_pass_count": sum(
            record["target_region_availability_assessment"] == "PASS" for record in records
        ),
        "target_region_availability_eligible_count": sum(
            record["target_region_availability_assessment"] != "NOT_APPLICABLE" for record in records
        ),
        "container_type_pass_count": sum(record["container_type_assessment"] == "PASS" for record in records),
        "excluded_or_false_seed_nonnull_region_count": sum(
            len(record["excluded_or_false_seed_nonnull_region_ids"]) for record in records
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "input_hashes": hashes,
        "records": records,
        "corrected_p1_summary": summary,
        "goal3_b1_summary": goal3["method_summaries"]["B1"],
        "limitations": {
            "coarse_reference_only": True,
            "strict_boundary_metric_available": False,
            "inter_annotator_boundary_agreement_available": False,
            "manual_tolerant_review_required": True,
        },
    }


def write_evaluation(
    matrix_root: Path,
    contract_path: Path,
    goal3_evaluation_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if output_path.exists():
        raise EvaluationStop(f"Goal 4 evaluation already exists: {output_path}")
    payload = evaluate(matrix_root, contract_path, goal3_evaluation_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Goal 4 corrected P1 after the frozen R0 run.")
    parser.add_argument("--matrix-root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--goal3-evaluation", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = write_evaluation(
            args.matrix_root,
            args.contract,
            args.goal3_evaluation,
            args.output,
        )
    except EvaluationStop as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
