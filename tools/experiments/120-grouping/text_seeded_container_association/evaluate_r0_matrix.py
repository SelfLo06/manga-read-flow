#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


EXPECTED_MATRIX_SHA256 = "8884ab063fb5acdc7925a267f105fa6e6457f36bfe3553489e553473ad088bcb"
EXPECTED_CONTRACT_SHA256 = "984ca71f1f1abe0a28fc09e222baad3e4d50c48329237c506b20d86f92dfb385"
EXPECTED_METHOD_IDS = ("B0", "B1", "P1")
SCHEMA_VERSION = "text-seeded-container-r0-evaluation-v1"


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


def verify_inputs(matrix_root: Path, contract_path: Path) -> dict[str, Any]:
    matrix_path = matrix_root / "matrix.json"
    matrix_hash = sha256_file(matrix_path)
    contract_hash = sha256_file(contract_path)
    if matrix_hash != EXPECTED_MATRIX_SHA256:
        raise EvaluationStop(f"frozen R0 matrix hash mismatch: {matrix_hash}")
    if contract_hash != EXPECTED_CONTRACT_SHA256:
        raise EvaluationStop(f"frozen evaluator contract hash mismatch: {contract_hash}")
    matrix = _load_json(matrix_path)
    contract = _load_json(contract_path)
    if matrix.get("status") != "completed" or matrix.get("ground_truth_accessed") is not False:
        raise EvaluationStop("matrix did not complete with GT isolation")
    if matrix.get("parameter_updates_after_r0") is not False:
        raise EvaluationStop("matrix reports post-R0 parameter updates")
    if matrix.get("method_ids") != list(EXPECTED_METHOD_IDS):
        raise EvaluationStop(f"matrix method scope mismatch: {matrix.get('method_ids')}")
    if contract.get("evaluator_only") is not True or contract.get("frozen_before_r0_run") is not True:
        raise EvaluationStop("evaluator contract is not frozen and isolated")
    outputs = matrix.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 18:
        raise EvaluationStop(f"matrix output count must be 18, got {len(outputs or [])}")
    for record in outputs:
        for path_key, hash_key in (
            ("result_relative_path", "result_sha256"),
            ("overlay_relative_path", "overlay_sha256"),
        ):
            path = matrix_root / record[path_key]
            if sha256_file(path) != record[hash_key]:
                raise EvaluationStop(f"matrix artifact hash mismatch: {path}")
    return {
        "matrix_root": matrix_root.resolve(),
        "matrix_path": matrix_path.resolve(),
        "matrix_sha256": matrix_hash,
        "contract_path": contract_path.resolve(),
        "contract_sha256": contract_hash,
        "matrix": matrix,
        "contract": contract,
    }


def assess_topology(
    target_fragment_groups: list[list[str]],
    expected_topology: str,
    regions: list[dict[str, Any]],
) -> dict[str, Any]:
    fragment_to_regions: dict[str, list[str]] = {}
    for region in regions:
        for fragment_id in region["fragment_ids"]:
            fragment_to_regions.setdefault(fragment_id, []).append(region["region_id"])
    group_region_ids: list[list[str]] = []
    integral = True
    for group in target_fragment_groups:
        ids = sorted({rid for fragment in group for rid in fragment_to_regions.get(fragment, [])})
        if len(ids) != 1 or any(len(fragment_to_regions.get(fragment, [])) != 1 for fragment in group):
            integral = False
        group_region_ids.append(ids)
    distinct = sorted({region_id for ids in group_region_ids for region_id in ids})
    if expected_topology == "not_applicable":
        assessment = "NOT_APPLICABLE"
    elif not integral:
        assessment = "FAIL"
    elif expected_topology == "same_container":
        assessment = "PASS" if len(distinct) == 1 else "FAIL"
    elif expected_topology == "different_containers":
        assessment = "PASS" if len(distinct) == len(target_fragment_groups) else "FAIL"
    else:
        raise EvaluationStop(f"unknown expected topology: {expected_topology}")
    return {
        "assessment": assessment,
        "group_integrity": integral,
        "group_region_ids": group_region_ids,
        "target_region_ids": distinct,
        "target_region_count": len(distinct),
    }


def decode_bool_rle(payload: dict[str, Any]) -> np.ndarray:
    shape = tuple(payload["shape"])
    values: list[np.ndarray] = []
    value = int(payload["starts_with"])
    for count in payload["counts"]:
        values.append(np.full(int(count), value, dtype=np.bool_))
        value = 1 - value
    flat = np.concatenate(values) if values else np.zeros(0, dtype=np.bool_)
    if flat.size != int(np.prod(shape)):
        raise EvaluationStop("invalid region RLE length")
    return flat.reshape(shape)


def _mask_diagnostics(result: dict[str, Any], target_region_ids: list[str]) -> list[dict[str, Any]]:
    diagnostics = []
    for region in result["regions"]:
        if region["region_id"] not in target_region_ids:
            continue
        mask = decode_bool_rle(region["mask_rle"])
        ys, xs = np.nonzero(mask)
        bbox = None if not len(xs) else [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
        touches = bool(
            mask.size
            and (mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())
        )
        diagnostics.append(
            {
                "region_id": region["region_id"],
                "bbox_xyxy": bbox,
                "touches_roi_edge": touches,
            }
        )
    return diagnostics


def _type_assessment(case: dict[str, Any], result: dict[str, Any], target_region_ids: list[str]) -> str:
    expected = case["expected_container_type"]
    if expected == "not_text":
        return "PASS" if not result["regions"] and result["recommended_decision"] == "SKIP" else "FAIL"
    target_regions = [item for item in result["regions"] if item["region_id"] in target_region_ids]
    if not target_regions:
        return "FAIL"
    types = {item["container_type"] for item in target_regions}
    if types == {"uncertain"}:
        return "UNSUPPORTED_BY_BASELINE"
    return "PASS" if types == {expected} else "FAIL"


def _evaluate_record(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    topology = assess_topology(
        case["target_fragment_groups"], case["expected_topology"], result["regions"]
    )
    target_regions = [
        item for item in result["regions"] if item["region_id"] in topology["target_region_ids"]
    ]
    excluded = set(case["excluded_or_false_seed_fragments"])
    contamination = sorted(
        excluded.intersection(fragment_id for region in target_regions for fragment_id in region["fragment_ids"])
    )
    false_seed_regions = [
        region["region_id"]
        for region in result["regions"]
        if excluded.intersection(region["fragment_ids"])
    ]
    safety_pass = result["recommended_decision"] in case["required_safety_decisions"]
    false_low_risk = (
        result["recommended_decision"] == "LOW_RISK_ASSOCIATION_CANDIDATE" and not safety_pass
    )
    return {
        "asset_id": case["asset_id"],
        "method_id": result["method_id"],
        "semantic_role": case["semantic_role"],
        "expected_container_type": case["expected_container_type"],
        "expected_container_count": case["expected_container_count"],
        "expected_topology": case["expected_topology"],
        "recommended_decision": result["recommended_decision"],
        "safety_decision_assessment": "PASS" if safety_pass else "FAIL",
        "false_low_risk_candidate": false_low_risk,
        "container_type_assessment": _type_assessment(case, result, topology["target_region_ids"]),
        "topology": topology,
        "excluded_fragment_contamination": contamination,
        "false_or_excluded_seed_region_ids": false_seed_regions,
        "coarse_reference_boxes_xyxy": case["coarse_reference_boxes_xyxy"],
        "target_region_mask_diagnostics": _mask_diagnostics(result, topology["target_region_ids"]),
        "coarse_reference_assessment": "MANUAL_VISUAL_REVIEW_REQUIRED",
        "abstention_reasons": result["abstention_reasons"],
    }


def evaluate_matrix(matrix_root: Path, contract_path: Path) -> dict[str, Any]:
    verified = verify_inputs(matrix_root, contract_path)
    output_by_key = {
        (item["asset_id"], item["method_id"]): item for item in verified["matrix"]["outputs"]
    }
    records = []
    for case in verified["contract"]["cases"]:
        for method_id in EXPECTED_METHOD_IDS:
            output = output_by_key[(case["asset_id"], method_id)]
            result = _load_json(verified["matrix_root"] / output["result_relative_path"])
            records.append(_evaluate_record(case, result))
    summaries = {}
    for method_id in EXPECTED_METHOD_IDS:
        selected = [item for item in records if item["method_id"] == method_id]
        eligible = [item for item in selected if item["topology"]["assessment"] != "NOT_APPLICABLE"]
        summaries[method_id] = {
            "case_count": len(selected),
            "safety_decision_pass_count": sum(
                item["safety_decision_assessment"] == "PASS" for item in selected
            ),
            "topology_pass_count": sum(item["topology"]["assessment"] == "PASS" for item in eligible),
            "topology_eligible_count": len(eligible),
            "container_type_pass_count": sum(
                item["container_type_assessment"] == "PASS" for item in selected
            ),
            "false_low_risk_candidate_count": sum(
                item["false_low_risk_candidate"] for item in selected
            ),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "matrix_sha256": verified["matrix_sha256"],
        "evaluator_contract_sha256": verified["contract_sha256"],
        "records": records,
        "method_summaries": summaries,
        "limitations": {
            "coarse_reference_only": True,
            "strict_boundary_metric_available": False,
            "inter_annotator_boundary_agreement_available": False,
        },
    }


def _panel(image: Image.Image, label: str) -> Image.Image:
    cell = Image.new("RGB", (440, 540), "white")
    copy = image.copy()
    copy.thumbnail((420, 500), Image.Resampling.LANCZOS)
    x = (440 - copy.width) // 2
    y = 32 + (500 - copy.height) // 2
    cell.paste(copy, (x, y))
    ImageDraw.Draw(cell).text((10, 8), label, fill="black")
    return cell


def write_contact_sheets(
    r0_root: Path, matrix_root: Path, contract: dict[str, Any], output_dir: Path
) -> list[dict[str, Any]]:
    sheets_dir = output_dir / "contact-sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for case in contract["cases"]:
        asset_id = case["asset_id"]
        source = Image.open(r0_root / "images" / f"{asset_id}.png").convert("RGB")
        panels = [_panel(source, "SOURCE")]
        if asset_id == "case-01":
            panels.append(_panel(source, "A COARSE REF: NOT_TEXT / NONE"))
        else:
            reference = Image.open(
                r0_root / "annotator-a" / "overlays" / f"{asset_id}-overlay.png"
            ).convert("RGB")
            panels.append(_panel(reference, "ANNOTATOR A COARSE REFERENCE"))
        for method_id in EXPECTED_METHOD_IDS:
            overlay = Image.open(matrix_root / "overlays" / f"{asset_id}-{method_id}.png").convert("RGB")
            panels.append(_panel(overlay, method_id))
        sheet = Image.new("RGB", (440 * len(panels), 540), "#dddddd")
        for index, panel in enumerate(panels):
            sheet.paste(panel, (index * 440, 0))
        path = sheets_dir / f"{asset_id}-comparison.png"
        sheet.save(path)
        records.append(
            {
                "asset_id": asset_id,
                "relative_path": path.relative_to(output_dir).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return records


def write_evaluation(
    r0_root: Path, matrix_root: Path, contract_path: Path, output_dir: Path
) -> dict[str, Any]:
    if output_dir.exists():
        raise EvaluationStop(f"evaluation output already exists: {output_dir}")
    payload = evaluate_matrix(matrix_root, contract_path)
    contract = _load_json(contract_path)
    output_dir.mkdir(parents=True)
    payload["contact_sheets"] = write_contact_sheets(r0_root, matrix_root, contract, output_dir)
    path = output_dir / "evaluation.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the frozen R0 matrix after the run.")
    parser.add_argument("--r0-root", required=True, type=Path)
    parser.add_argument("--matrix-root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = write_evaluation(
            args.r0_root, args.matrix_root, args.contract, args.output_dir
        )
    except EvaluationStop as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
