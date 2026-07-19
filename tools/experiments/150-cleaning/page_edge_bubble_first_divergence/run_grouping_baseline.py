#!/usr/bin/env python3
"""Group one frozen Detection artifact, then compare associations offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).parent))
from core import artifact_inventory, full_to_roi, load_accepted_oracle, load_case, utc_now, write_json  # noqa: E402
from grouping_adapter import GroupingAdapterError, run as run_grouping, sha256_file  # noqa: E402

CASE_FILE = ROOT / "data/local/datasets/150-cleaning/page-edge-bubble-v0.1/cases.json"
ORACLE = ROOT / "data/local/datasets/150-cleaning/page-edge-bubble-v0.1/oracles/page_edge_bubble_v0.1/accepted-v1"
RUN_ROOT = ROOT / "data/local/runs/150-cleaning/page-edge-bubble-first-divergence-v0.1"
DEFAULT_DETECTION_RUN_ID = "20260719T0500-auto-baseline-paddle-detection-v0.1"


def _git(args: list[str]) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip()


def _log(run: Path, event: str, **fields: object) -> None:
    with (run / "LOG.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": utc_now(), "event": event, **fields}, ensure_ascii=False, sort_keys=True) + "\n")


def _bbox_mask(candidate: dict, shape: tuple[int, int]) -> np.ndarray:
    box = candidate["bbox_full_page"]
    result = np.zeros(shape, dtype=bool)
    x0, y0 = int(box["x"]), int(box["y"])
    x1, y1 = x0 + int(box["width"]), y0 + int(box["height"])
    result[y0:y1, x0:x1] = True
    return result


def _validated_detection_artifact(run_id: str, source_sha256: str) -> tuple[Path, str, dict]:
    detection_run = RUN_ROOT / run_id
    manifest_path = detection_run / "MANIFEST.json"
    candidates_path = detection_run / "artifacts/detection_candidates.json"
    if not manifest_path.is_file() or not candidates_path.is_file():
        raise GroupingAdapterError("required frozen Detection run/artifact is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("output_artifacts", {}).get("artifacts/detection_candidates.json", {}).get("sha256")
    if manifest.get("source", {}).get("sha256") != source_sha256 or manifest.get("oracle_injection") is not False or not isinstance(expected, str):
        raise GroupingAdapterError("Detection run provenance is incomplete or incompatible")
    actual = sha256_file(candidates_path)
    if actual != expected:
        raise GroupingAdapterError("frozen Detection artifact no longer matches its manifest hash")
    return candidates_path, actual, manifest


def evaluate_grouping(assignments: dict, candidates: list[dict], case, oracle, page_shape: tuple[int, int]) -> dict:
    required = oracle.masks["text_required"]
    target_candidate_ids = [
        candidate["candidate_id"]
        for candidate in candidates
        if bool((full_to_roi(_bbox_mask(candidate, page_shape), case) & required).any())
    ]
    by_candidate = {item["candidate_id"]: item for item in assignments["candidate_assignments"]}
    target_group_ids = sorted({by_candidate[candidate_id]["text_group_id"] for candidate_id in target_candidate_ids})
    groups = {group["group_id"]: group for group in assignments["groups"]}
    target_group = groups[target_group_ids[0]] if len(target_group_ids) == 1 else None
    target_members = [] if target_group is None else target_group["ordered_fragment_ids"]
    expected = oracle.association["text_groups"]
    return {
        "execution_status": "PARTIAL_SUCCESS",
        "candidate_count": len(candidates),
        "automatic_text_group_count": assignments["automatic_text_group_count"],
        "candidate_assignments": assignments["candidate_assignments"],
        "target_candidate_ids": target_candidate_ids,
        "target_group_ids": target_group_ids,
        "target_same_text_group": len(target_candidate_ids) > 0 and len(target_group_ids) == 1,
        "target_group_id": None if target_group is None else target_group["group_id"],
        "target_group_member_ids": target_members,
        "target_group_has_external_candidates": bool(target_group and set(target_members) != set(target_candidate_ids)),
        "association_comparison": {
            "oracle_text_group_count": len(expected),
            "oracle_visual_column_count": expected[0]["layout"]["visual_column_count"],
            "oracle_bubble_id": expected[0]["bubble_id"],
            "text_group_membership_assessment": "PASS" if len(target_candidate_ids) == 3 and len(target_group_ids) == 1 and set(target_members) == set(target_candidate_ids) else "FAIL",
        },
        "bubble_instance_assignment": {
            "status": "NOT_AVAILABLE",
            "reason": "reused geometry-only text-region Grouping spike does not infer a BubbleInstance/container",
        },
    }


def classify_grouping_outcome(grouping: dict) -> tuple[dict | None, dict | None]:
    if grouping["association_comparison"]["text_group_membership_assessment"] != "PASS":
        return ({"stage": "grouping", "type": "target_text_group_membership_mismatch", "evidence": [{"artifact": "METRICS.json", "metric": "association_comparison.text_group_membership_assessment", "observed": grouping["association_comparison"]["text_group_membership_assessment"], "oracle": "PASS"}]}, None)
    return (None, {"stage": "grouping", "component": "bubble_instance_assignment", "type": "automatic_bubble_container_assignment_not_available"})


def _failure(run: Path, run_id: str, error: Exception) -> int:
    failure = {"schema_version": "page-edge-bubble-grouping-observability-v1", "run_id": run_id, "execution_failure": {"stage": "grouping", "type": type(error).__name__, "message": str(error)}, "first_observed_divergence": None, "earliest_execution_gap": None, "causality": {"established": False}}
    write_json(run / "FIRST_DIVERGENCE.json", failure)
    write_json(run / "METRICS.json", {"input": {}, "grouping": {"execution_status": "FAILURE"}})
    write_json(run / "MANIFEST.json", {"schema_version": "page-edge-bubble-grouping-observability-v1", "run_id": run_id, "oracle_injection": False, "stage_execution_statuses": {"grouping": "FAILURE"}})
    (run / "REPORT.md").write_text(f"# page-edge-bubble Grouping baseline\n\nGrouping execution failed before assignments were produced: `{type(error).__name__}: {error}`. This is an execution failure, not a first observed divergence.\n", encoding="utf-8")
    _log(run, "execution_failure", error_type=type(error).__name__, message=str(error))
    print(f"STOP: {error}", file=sys.stderr)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    parser.add_argument("--detection-run-id", default=DEFAULT_DETECTION_RUN_ID)
    args = parser.parse_args()
    run_id = args.run_id or f"{utc_now().replace(':', '').replace('-', '')}-auto-baseline-grouping-v0.1-{uuid4().hex[:8]}"
    run = RUN_ROOT / run_id
    if run.exists():
        print(f"STOP: refusing to overwrite run: {run}", file=sys.stderr)
        return 2
    (run / "artifacts").mkdir(parents=True)
    try:
        case = load_case(CASE_FILE, ROOT)
        candidates_path, candidates_sha256, detection_manifest = _validated_detection_artifact(args.detection_run_id, case.source_sha256)
        _log(run, "source_and_detection_artifact_verified", source_sha256=case.source_sha256, detection_run_id=args.detection_run_id, detection_candidates_sha256=candidates_sha256)
        _log(run, "grouping_started", oracle_injection=False)
        execution = run_grouping(asset_id=case.case_id, source_path=case.source, source_sha256=case.source_sha256, detection_candidates_path=candidates_path, detection_candidates_sha256=candidates_sha256, output_dir=run / "artifacts")
        execution_artifacts = artifact_inventory(run)
        _log(run, "grouping_artifacts_frozen", automatic_text_group_count=execution["automatic_text_group_count"], artifacts=sorted(execution_artifacts))
        # This is deliberately the first oracle access, after assignment artifacts are hashed.
        _log(run, "oracle_evaluation_started", execution_oracle_access=False)
        oracle = load_accepted_oracle(case, ORACLE)
        assignments = json.loads((run / "artifacts/grouping_assignments.json").read_text(encoding="utf-8"))
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))["candidates"]
        with Image.open(case.source) as image:
            page_shape = (image.height, image.width)
        grouping = evaluate_grouping(assignments, candidates, case, oracle, page_shape)
        first, gap = classify_grouping_outcome(grouping)
        metrics = {"input": {"source_hash_matches_case": True, "detection_candidates_hash_matches_manifest": True, "roi_is_evaluation_only": True}, "grouping": grouping}
        first_divergence = {"case_id": case.case_id, "run_id": run_id, "first_observed_divergence": first, "earliest_execution_gap": gap, "execution_failure": None, "causality": {"established": False, "reason": "single-stage observation; no intervention executed"}}
        manifest = {"schema_version": "page-edge-bubble-grouping-observability-v1", "run_id": run_id, "case_id": case.case_id, "source": {"path": case.source_relative, "sha256": case.source_sha256}, "code_revision": _git(["rev-parse", "HEAD"]), "branch": _git(["branch", "--show-current"]), "working_tree_status": _git(["status", "--short"]), "upstream_detection": {"run_id": args.detection_run_id, "candidates_path": str(candidates_path.relative_to(ROOT)), "candidates_sha256": candidates_sha256, "manifest_sha256": sha256_file(RUN_ROOT / args.detection_run_id / "MANIFEST.json"), "oracle_injection": detection_manifest["oracle_injection"]}, "grouping_implementation": execution["implementation"], "oracle_injection": False, "execution_inputs": {"source_path": case.source_relative, "source_sha256": case.source_sha256, "detection_candidates_sha256": candidates_sha256}, "evaluation_inputs": {"oracle_manifest_sha256": oracle.manifest_sha256, "oracle_version": "accepted-v1"}, "stage_execution_statuses": {"grouping": "PARTIAL_SUCCESS", "bubble_instance_assignment": "NOT_AVAILABLE"}, "stop_stage": "grouping", "stop_reason": gap["type"] if gap else first["type"], "output_artifacts": execution_artifacts}
        write_json(run / "METRICS.json", metrics)
        write_json(run / "FIRST_DIVERGENCE.json", first_divergence)
        write_json(run / "MANIFEST.json", manifest)
        (run / "REPORT.md").write_text(f"# page-edge-bubble Grouping baseline\n\n## Capability investigation\n\nThis run reuses `tools/experiments/120-grouping/text_region_grouping/spike.py:group_fragments`. It accepts frozen full-page Detection geometry and produces text groups; it has no BubbleInstance/container inference.\n\n## Observation\n\nThe 13 frozen Paddle candidates became `{grouping['automatic_text_group_count']}` automatic text groups. Target candidates: `{', '.join(grouping['target_candidate_ids'])}`. Their text-group membership assessment: `{grouping['association_comparison']['text_group_membership_assessment']}`; external candidates in their group: `{grouping['target_group_has_external_candidates']}`. Oracle data was read only after Grouping artifacts were written and hashed.\n\n## Verdict\n\nfirst observed divergence: `{first['type'] if first else 'none'}`. earliest execution gap: `{gap['type'] if gap else 'none'}`. A text-group pass does not establish a BubbleInstance or physical boundary.\n\n## Project Decision\n\nUnchanged. Do not proceed to text support, physical boundary, Cleaner, product artifacts, or active-pointer updates.\n", encoding="utf-8")
        _log(run, "oracle_evaluation_finished", first_observed_divergence=None if first is None else "grouping", earliest_execution_gap=None if gap is None else gap["type"])
        _log(run, "run_completed", stop_stage=manifest["stop_stage"], stop_reason=manifest["stop_reason"])
        print(run)
        return 0
    except Exception as error:
        return _failure(run, run_id, error)


if __name__ == "__main__":
    raise SystemExit(main())
