#!/usr/bin/env python3
"""One-shot, review-only Goal 6 evaluation over frozen Goal 5 cases."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from tools.experiments.grouping_120.text_seeded_container_association import goal6_full_page_trial as full_page
from tools.experiments.grouping_120.text_seeded_container_association import goal6_mask_harness as mask
from tools.experiments.grouping_120.text_seeded_container_association.goal6_build_calibration import POLICIES, _contexts, _fragments


EXPECTED_CASES = ("case-51", "case-52", "case-53", "case-54")


class EvaluationStop(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluationStop(f"JSON root must be an object: {path}")
    return value


def build_review_form(records: list[dict[str, Any]]) -> str:
    rows = []
    for record in records:
        choice = "`SKIP（固定）`" if record["route"] == "REGIONLESS_ABSTENTION" else ""
        rows.append(f"| {record['asset_id']} | {choice} |  |  |  |  |")
    return """# Goal 6 frozen independent evaluation review

每张 `comparison.png` 从左到右为：原图、完整 mask/safe overlay、E1-only candidate、
E1 加 E2 comparison candidate。四张 semantic overlay 分别说明全部构造 mask、E1 实际
应用、E1+E2 comparison 应用和 E3 跳过范围。它们不会产生 `AUTO_ACCEPT`。

| Case | Overall (`ACCEPTABLE` / `REVIEW` / `UNUSABLE` / `SKIP`) | Text residue (`none` / `minor` / `readable`) | Non-text / border damage (`none` / `minor` / `severe`) | E2 observation (`n/a` / `better` / `same` / `worse`) | Note |
| --- | --- | --- | --- | --- |\n""" + "\n".join(rows) + """

`case-54` 必须保持固定 `SKIP`。任何 readable residue、severe damage、context 外修改、
跨容器泄漏或错误处理 regionless 都不能得出扩展结论。
"""


def _candidate_layers(image: np.ndarray, results: tuple[mask.ContextResult, ...]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    effective = np.zeros(image.shape[:2], dtype=np.bool_)
    e1_only = image.copy()
    e2_comparison = image.copy()
    for result in results:
        effective |= result.effective
        if result.decision != "REVIEW_REQUIRED" or not result.effective.any():
            continue
        if result.risk == "E1":
            candidate = mask.border_sampled_fill(image, result.effective, result.safe, result.soft)
            e1_only[result.effective] = candidate[result.effective]
            e2_comparison[result.effective] = candidate[result.effective]
        elif result.risk == "E2":
            candidate = mask.low_radius_telea(image, result.effective)
            e2_comparison[result.effective] = candidate[result.effective]
    if mask.changed_outside(image, e1_only, effective) != 0:
        raise EvaluationStop("E1 candidate modified pixels outside M_effective")
    if mask.changed_outside(image, e2_comparison, effective) != 0:
        raise EvaluationStop("E2 comparison modified pixels outside M_effective")
    return effective, e1_only, e2_comparison


def run(root: Path, s1_path: Path, goal5_matrix_path: Path, mask_policy_lock_path: Path, output_dir: Path) -> dict[str, Any]:
    root = root.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise EvaluationStop("Goal 6 evaluation output already exists")
    s1 = load(s1_path)
    matrix = load(goal5_matrix_path)
    mask_lock = load(mask_policy_lock_path)
    if s1.get("status") != "completed" or s1.get("input_hashes_unchanged") is not True:
        raise EvaluationStop("S1 input is not stable")
    if matrix.get("status") != "completed" or matrix.get("source_hashes_unchanged") is not True:
        raise EvaluationStop("Goal 5 evaluation result is not stable")
    if tuple(matrix.get("asset_ids", ())) != EXPECTED_CASES or matrix.get("evaluation_labels_accessed") is not False:
        raise EvaluationStop("unexpected Goal 5 evaluation scope or label access")
    if mask_lock.get("status") != "FROZEN_FOR_FULL_PAGE_REVIEW_ONLY" or mask_lock.get("selected_policy") != "P0_conservative":
        raise EvaluationStop("P0 mask policy is not frozen")
    if mask_lock.get("policy") != POLICIES["P0_conservative"].__dict__:
        raise EvaluationStop("P0 mask policy lock mismatch")
    assets = {item["asset_id"]: item for item in s1.get("assets", [])}
    if not all(case in assets for case in EXPECTED_CASES):
        raise EvaluationStop("Goal 5 S1 results lack evaluation assets")
    output_map = {item["asset_id"]: item for item in matrix.get("outputs", [])}
    if tuple(output_map) != EXPECTED_CASES:
        raise EvaluationStop("Goal 5 evaluation output ordering/scope mismatch")
    for case in EXPECTED_CASES:
        asset = assets[case]
        if sha256(root / asset["relative_path"]) != asset["sha256"] or matrix["source_hashes_after"].get(case) != asset["sha256"]:
            raise EvaluationStop(f"source hash mismatch: {case}")

    output_dir.mkdir(parents=True)
    input_lock = {
        "schema_version": "goal6-evaluation-input-lock-v1",
        "p0_policy_lock_sha256": sha256(mask_policy_lock_path),
        "goal5_matrix_sha256": sha256(goal5_matrix_path),
        "s1_results_sha256": sha256(s1_path),
        "mask_harness_sha256": sha256(Path(mask.__file__)),
        "evaluation_runner_sha256": sha256(Path(__file__)),
        "full_page_overlay_helper_sha256": sha256(Path(full_page.__file__)),
        "parameter_updates_after_lock": False,
    }
    (output_dir / "INPUT-LOCK.json").write_text(json.dumps(input_lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    records: list[dict[str, Any]] = []
    for case in EXPECTED_CASES:
        asset = assets[case]
        frozen = output_map[case]
        routed = load(goal5_matrix_path.parent / frozen["result_relative_path"])
        image = np.asarray(Image.open(root / asset["relative_path"]).convert("RGB"))
        page_dir = output_dir / case
        page_dir.mkdir()
        Image.fromarray(image).save(page_dir / "source.png")
        if frozen["goal6_trial_eligible"] is not True:
            record = {
                "asset_id": case,
                "route": frozen["route"],
                "topology": frozen["topology"],
                "has_candidate": False,
                "effective_mask_pixels": 0,
                "changed_outside_effective": 0,
                "reason": routed["abstention_reasons"],
            }
            (page_dir / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            records.append(record)
            continue
        contexts = _contexts(routed)
        fragments = _fragments(asset)
        results = tuple(
            mask.process_context(
                image, context, fragments, routed["route"], POLICIES["P0_conservative"],
                (other.mask for other in contexts if other.region_id != context.region_id),
            )
            for context in contexts
        )
        mask.verify_disjoint(results)
        effective, e1_only, e2_comparison = _candidate_layers(image, results)
        Image.fromarray(full_page.page_overlay(image, results)).save(page_dir / "mask-safe-overlay.png")
        Image.fromarray(full_page.semantic_overlay(image, full_page.union_effective(results, {"E1", "E2", "E3", "E4"}), (40, 145, 245))).save(page_dir / "all-context-effective-overlay.png")
        Image.fromarray(full_page.semantic_overlay(image, full_page.union_effective(results, {"E1"}), (30, 180, 80))).save(page_dir / "e1-applied-effective-overlay.png")
        Image.fromarray(full_page.semantic_overlay(image, full_page.union_effective(results, {"E1", "E2"}), (90, 105, 240))).save(page_dir / "e1-plus-e2-comparison-effective-overlay.png")
        Image.fromarray(full_page.semantic_overlay(image, full_page.union_effective(results, {"E3", "E4"}), (230, 65, 55))).save(page_dir / "skipped-e3-effective-overlay.png")
        Image.fromarray(full_page.context_risk_overlay(image, results)).save(page_dir / "context-risk-map.png")
        Image.fromarray(e1_only).save(page_dir / "candidate-e1-only.png")
        Image.fromarray(e2_comparison).save(page_dir / "candidate-e2-comparison.png")
        full_page.comparison(image, full_page.page_overlay(image, results), e1_only, e2_comparison).save(page_dir / "comparison.png")
        changes_e1 = np.any(image != e1_only, axis=2)
        changes_e2 = np.any(image != e2_comparison, axis=2)
        record = {
            "asset_id": case,
            "route": frozen["route"],
            "topology": frozen["topology"],
            "has_candidate": bool(changes_e1.any() or changes_e2.any()),
            "effective_mask_pixels": int(effective.sum()),
            "e1_changed_pixels": int(changes_e1.sum()),
            "e2_comparison_changed_pixels": int(changes_e2.sum()),
            "changed_outside_effective": {
                "e1_only": mask.changed_outside(image, e1_only, effective),
                "e2_comparison": mask.changed_outside(image, e2_comparison, effective),
            },
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
        }
        (page_dir / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append(record)
    payload = {
        "schema_version": "goal6-frozen-independent-evaluation-v1",
        "status": "READY_FOR_HUMAN_REVIEW",
        "asset_ids": list(EXPECTED_CASES),
        "source_hashes_unchanged": True,
        "ground_truth_accessed": False,
        "evaluation_labels_accessed": False,
        "parameter_updates_after_lock": False,
        "AUTO_ACCEPT": False,
        "records": records,
    }
    (output_dir / "matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "FORM.md").write_text(build_review_form(records), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--s1", type=Path, required=True)
    parser.add_argument("--goal5-matrix", type=Path, required=True)
    parser.add_argument("--mask-policy-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = run(args.root, args.s1, args.goal5_matrix, args.mask_policy_lock, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError, EvaluationStop, mask.Goal6Stop) as error:
        print(f"STOP: {error}")
        return 2
    print(json.dumps({"status": payload["status"], "source_hashes_unchanged": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
