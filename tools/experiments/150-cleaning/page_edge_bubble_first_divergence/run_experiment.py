#!/usr/bin/env python3
"""Run the page-edge bubble baseline or oracle Cleaner isolation experiment."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from manga_read_flow.domain.provider_contracts import ProviderRequest  # noqa: E402
from manga_read_flow.providers.border_sampled_fill import BorderSampledFillCleanerProvider  # noqa: E402

from core import (  # noqa: E402
    Case, ExperimentStop, artifact_inventory, binary_metrics, derive_authorization, digest,
    first_divergence_for_unavailable_detection, freeze_candidate_as_accepted, load_accepted_oracle,
    load_case, mask_digest, read_rgb, roi_to_full, utc_now, write_json, write_mask, write_rgb,
)
from evaluator import boundary_metrics, stable_first_divergence, support_metrics  # noqa: E402

DATASET = ROOT / "data/local/datasets/150-cleaning/page-edge-bubble-v0.1"
DEFAULT_CASE = DATASET / "cases.json"
DEFAULT_ORACLE_PARENT = DATASET / "oracles/page_edge_bubble_v0.1"
DEFAULT_RUN_ROOT = ROOT / "data/local/runs/150-cleaning/page-edge-bubble-first-divergence-v0.1"


def _git(command: list[str]) -> str:
    return subprocess.run(["git", *command], cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip()


def _new_run(root: Path, mode: str, run_id: str | None) -> Path:
    name = run_id or f"{utc_now().replace(':', '').replace('-', '')}-{mode}-{uuid4().hex[:8]}"
    path = root / name
    if path.exists():
        raise ExperimentStop(f"refusing to overwrite run: {path}")
    (path / "artifacts").mkdir(parents=True)
    return path


def _base_manifest(case: Case, run_dir: Path, mode: str, *, oracle_injection: bool, injected_stages: list[str]) -> dict:
    return {
        "schema_version": "page-edge-bubble-first-divergence-run-v1", "run_id": run_dir.name,
        "mode": mode, "case_id": case.case_id, "source": {"path": case.source_relative, "sha256": case.source_sha256},
        "roi_xyxy": list(case.roi), "oracle_injection": oracle_injection, "injected_stages": injected_stages,
        "code_revision": _git(["rev-parse", "HEAD"]), "branch": _git(["branch", "--show-current"]),
        "working_tree_status": _git(["status", "--short"]), "config_snapshot": {},
        "provider_versions": {"cleaner": "border-sampled-fill-cleaner:mvp1-v0.1"}, "seeds": {"numpy": None},
        "execution_started_at": utc_now(), "stage_execution_statuses": {}, "execution_inputs": {"source_sha256": case.source_sha256},
    }


def _append_log(run_dir: Path, event: str, **details: object) -> None:
    with (run_dir / "LOG.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"timestamp": utc_now(), "event": event, **details}, ensure_ascii=False, sort_keys=True) + "\n")


def _blank_roi_artifacts(case: Case, run_dir: Path) -> None:
    shape = (case.roi[3] - case.roi[1], case.roi[2] - case.roi[0])
    blank = np.zeros(shape, dtype=np.bool_)
    for name in ("text_support_mask.png", "bubble_interior_candidate.png", "visible_boundary_candidate.png", "page_truncation_candidate.png", "unknown_mask.png", "safe_edit_candidate.png"):
        write_mask(run_dir / "artifacts" / name, blank)
    write_rgb(run_dir / "artifacts" / "detection_overlay.png", np.zeros((shape[0], shape[1], 3), dtype=np.uint8))
    write_rgb(run_dir / "artifacts" / "grouping_overlay.png", np.zeros((shape[0], shape[1], 3), dtype=np.uint8))


def run_auto_execution(case: Case, run_dir: Path) -> dict:
    """Execute without an Oracle parameter or any oracle-path access."""
    source = read_rgb(case.source)
    x0, y0, x1, y1 = case.roi
    _blank_roi_artifacts(case, run_dir)
    write_json(run_dir / "artifacts/source_metadata.json", {"source_sha256": digest(case.source), "dimensions": [int(source.shape[1]), int(source.shape[0])], "algorithm_input": "full_page", "roi_visualization_only": list(case.roi)})
    write_json(run_dir / "artifacts/config_snapshot.json", {"automatic_adapter": "none", "reason": "no reusable automatic full-page detection/grouping/boundary adapter is exposed by the current experiment tools"})
    write_json(run_dir / "artifacts/provider_versions.json", {"cleaner": "border-sampled-fill-cleaner:mvp1-v0.1"})
    write_json(run_dir / "artifacts/detection_candidates.json", {"status": "NOT_AVAILABLE", "candidate_count": 0, "reason": "no automatic detector adapter available"})
    for name in ("grouping.json", "topology.json", "authorization.json", "quality_issues.json"):
        write_json(run_dir / "artifacts" / name, {"status": "NOT_RUN", "blocked_by": "detection_not_available"})
    write_json(run_dir / "artifacts/boundary_class_map.json", {"status": "NOT_RUN", "classes": ["bubble_interior", "visible_boundary", "page_truncation", "unknown", "outside"]})
    decision = {"actual_cleaning": "NOT_RUN", "blocked_by": "detection_not_available", "root_stage_attribution": "detection", "evidence_artifacts": ["artifacts/detection_candidates.json"]}
    write_json(run_dir / "artifacts/decision.json", decision)
    return {"input": {"source_hash_matches_case": True, "roi_is_source_crop": True, "status": "PASS"}, "detection": {"status": "NOT_AVAILABLE", "candidate_count": 0}, "grouping": {"status": "NOT_RUN"}, "text_support": {"status": "NOT_RUN"}, "physical_boundary": {"status": "NOT_RUN"}, "authorization": {"status": "BLOCKED"}, "cleaner": {"status": "NOT_RUN"}, "cleaning_check": {"status": "NOT_RUN"}}


def run_auto(case: Case, accepted: Path, run_root: Path, run_id: str | None) -> Path:
    run_dir = _new_run(run_root, "auto-baseline", run_id)
    manifest = _base_manifest(case, run_dir, "auto-baseline", oracle_injection=False, injected_stages=[])
    _append_log(run_dir, "automatic_execution_started", oracle_injection=False)
    metrics = run_auto_execution(case, run_dir)
    manifest["stage_execution_statuses"] = {key: value.get("status", "PASS") for key, value in metrics.items()}
    _append_log(run_dir, "automatic_execution_finished", cleaner="NOT_RUN")
    # Evaluation is intentionally after automatic execution and is the first oracle load.
    _append_log(run_dir, "oracle_evaluation_started", execution_oracle_access=False)
    oracle = load_accepted_oracle(case, accepted)
    divergence = first_divergence_for_unavailable_detection(case, oracle)
    divergence["earliest_execution_gap"] = stable_first_divergence([
        ("input", "MATCH", []),
        ("detection", "automatic_stage_not_available", divergence["earliest_execution_gap"]["evidence"]),
    ])
    divergence["run_id"] = run_dir.name
    divergence["downstream_effect"] = {"cleaner_ran": False, "blocked_by": "detection_not_available", "quality_issues": []}
    metrics["evaluation"] = {"oracle_manifest_sha256": oracle.manifest_sha256, "required_text_pixels": int(oracle.masks["text_required"].sum()), "execution_oracle_access": False}
    _append_log(run_dir, "oracle_evaluation_finished", first_observed_divergence="detection", oracle_manifest_sha256=oracle.manifest_sha256)
    manifest["evaluation_inputs"] = {"oracle_manifest_sha256": oracle.manifest_sha256, "oracle_path": str(accepted)}
    manifest["execution_finished_at"] = utc_now(); manifest["output_artifacts"] = artifact_inventory(run_dir)
    write_json(run_dir / "METRICS.json", metrics); write_json(run_dir / "FIRST_DIVERGENCE.json", divergence)
    write_json(run_dir / "MANIFEST.json", manifest)
    (run_dir / "REPORT.md").write_text("# auto-baseline\n\n## Observation\n\nCurrent reusable tools expose no automatic full-page detection/grouping/boundary adapter for this case. The run therefore stops fail-closed before Cleaner.\n\n## Verdict\n\nNo first observed divergence exists because no automatic Detection output was observed. The earliest execution gap is `detection: automatic_stage_not_available`; this is not a root-cause claim.\n\n## Project Decision\n\nUnchanged. This single case does not authorize a general capability or active-pointer change.\n", encoding="utf-8")
    _append_log(run_dir, "run_completed", mode="auto-baseline", result="NOT_RUN", stop_reason="detection_not_available")
    return run_dir


def _overlay(source: np.ndarray, masks: list[tuple[np.ndarray, tuple[int, int, int]]]) -> np.ndarray:
    result = source.astype(np.float32).copy()
    for mask, color in masks:
        result[mask] = result[mask] * 0.5 + np.asarray(color, dtype=np.float32) * 0.5
    return np.clip(result, 0, 255).astype(np.uint8)


def run_isolation(case: Case, accepted: Path, run_root: Path, run_id: str | None) -> Path:
    run_dir = _new_run(run_root, "oracle-cleaner-isolation", run_id)
    manifest = _base_manifest(case, run_dir, "oracle-cleaner-isolation", oracle_injection=True, injected_stages=["grouping", "text_support", "physical_boundary"])
    oracle = load_accepted_oracle(case, accepted)
    source = read_rgb(case.source); shape = source.shape[:2]
    derived = derive_authorization(oracle)
    masks = {name: roi_to_full(value, case, shape) for name, value in derived.items() if isinstance(value, np.ndarray)}
    required = roi_to_full(oracle.masks["text_required"], case, shape)
    visible = roi_to_full(oracle.masks["visible_boundary"], case, shape)
    truncation = roi_to_full(oracle.masks["page_truncation"], case, shape)
    interior = roi_to_full(oracle.masks["bubble_interior"], case, shape)
    for name, mask in {"derived_safe_edit_mask.png": masks["safe"], "derived_protected_mask.png": masks["protected"], "derived_cleaner_write_mask.png": masks["write"], "required_text_mask.png": required, "visible_boundary_mask.png": visible, "page_truncation_mask.png": truncation, "bubble_interior_mask.png": interior, "unknown_mask.png": np.zeros(shape, dtype=bool)}.items():
        write_mask(run_dir / "artifacts" / name, mask)
    authorization = {"rules": derived["rules"], "required_pixels": int(required.sum()), "write_pixels": int(masks["write"].sum()), "required_write_coverage": int((required & masks["write"]).sum()), "write_visible_boundary_intersection": int((masks["write"] & visible).sum()), "write_page_truncation_intersection": int((masks["write"] & truncation).sum()), "write_outside_safe": int((masks["write"] & ~masks["safe"]).sum()), "oracle_input": "semantic masks only"}
    write_json(run_dir / "artifacts/authorization.json", authorization)
    _append_log(run_dir, "oracle_inputs_loaded", oracle_manifest_sha256=oracle.manifest_sha256, injected_stages=manifest["injected_stages"])
    _append_log(run_dir, "authorization_derived", required_pixels=authorization["required_pixels"], required_write_coverage=authorization["required_write_coverage"], write_pixels=authorization["write_pixels"], protected_intersections=authorization["write_visible_boundary_intersection"] + authorization["write_page_truncation_intersection"])
    temp = run_dir / "artifacts/cleaner-temp"; temp.mkdir()
    request = ProviderRequest(request_id=f"experiment::{run_dir.name}", stage="cleaning", target_type="experiment_case", target_id=case.case_id, page_id=case.case_id, text_block_ids=("text_group_001",), attempt_temp_root=temp, input_hash=sha256((case.source_sha256 + mask_digest(masks["write"])).encode()).hexdigest(), config_hash="border-sampled-fill-cleaner:mvp1-v0.1", context_hash=oracle.manifest_sha256, source_language="ja", target_language="zh-Hans", inputs={"source_image_path": case.source, "candidate_mask_path": run_dir / "artifacts/derived_cleaner_write_mask.png", "safe_edit_mask_path": run_dir / "artifacts/derived_safe_edit_mask.png", "instance_mask_path": run_dir / "artifacts/bubble_interior_mask.png", "protected_mask_path": run_dir / "artifacts/derived_protected_mask.png", "uncertainty_mask_path": run_dir / "artifacts/unknown_mask.png"})
    _append_log(run_dir, "cleaner_started", oracle_injection=True)
    result = BorderSampledFillCleanerProvider().run(request)
    provider = {"outcome": result.outcome.value, "provider": result.provider_name, "payload": result.payload, "identity": {"tool_version": "mvp1-v0.1"}}
    write_json(run_dir / "artifacts/cleaner_provider_result.json", provider)
    cleaner_ran = result.outcome.value == "success" and (temp / "cleaned.png").is_file()
    issues: list[dict[str, str]] = []
    if not cleaner_ran:
        issues.append({"code": "cleaner_not_run_or_partial", "stage": "cleaner"})
        output = source.copy(); actual = np.zeros(shape, dtype=bool)
    else:
        output = read_rgb(temp / "cleaned.png"); actual = np.any(output != source, axis=2)
        shutil.copy2(temp / "cleaned.png", run_dir / "artifacts/cleaned_full_page.png")
        shutil.copy2(temp / "actual-changed.png", run_dir / "artifacts/actual_changed_mask.png")
        shutil.copy2(temp / "cleaner-evidence.json", run_dir / "artifacts/cleaner_evidence.json")
    _append_log(run_dir, "cleaner_finished", outcome=result.outcome.value, cleaner_ran=cleaner_ran, actual_changed_pixels=int(actual.sum()))
    write_mask(run_dir / "artifacts/cleaner_write_mask.png", masks["write"])
    x0, y0, x1, y1 = case.roi
    write_rgb(run_dir / "artifacts/cleaned_roi.png", output[y0:y1, x0:x1])
    write_rgb(run_dir / "artifacts/pixel_diff.png", np.abs(output.astype(np.int16) - source.astype(np.int16)).astype(np.uint8))
    residue = required & (0.2126 * output[..., 0] + 0.7152 * output[..., 1] + 0.0722 * output[..., 2] <= 180)
    write_rgb(run_dir / "artifacts/residue_overlay.png", _overlay(source, [(residue, (255, 0, 255))]))
    write_rgb(run_dir / "artifacts/boundary_damage_overlay.png", _overlay(source, [(actual & (visible | truncation), (255, 0, 0))]))
    check = {"required_residue_pixels": int(residue.sum()), "unauthorized_write_pixels": int((actual & ~masks["write"]).sum()), "write_visible_boundary_pixels": int((actual & visible).sum()), "write_page_truncation_pixels": int((actual & truncation).sum()), "actual_outside_influence_contract_pixels": int((actual & ~masks["write"]).sum()), "source_hash_unchanged": digest(case.source) == case.source_sha256}
    if authorization["required_write_coverage"] != authorization["required_pixels"]: issues.append({"code": "required_not_fully_authorized", "stage": "authorization"})
    if authorization["write_visible_boundary_intersection"] or authorization["write_page_truncation_intersection"] or authorization["write_outside_safe"]: issues.append({"code": "authorization_crosses_protected_boundary", "stage": "authorization"})
    if check["unauthorized_write_pixels"]: issues.append({"code": "cleaner_unauthorized_write", "stage": "cleaning_check"})
    if check["write_visible_boundary_pixels"] or check["write_page_truncation_pixels"]: issues.append({"code": "cleaner_boundary_damage", "stage": "cleaning_check"})
    if check["required_residue_pixels"]: issues.append({"code": "cleaning_residue", "stage": "cleaning_check"})
    write_json(run_dir / "artifacts/quality_issues.json", issues)
    automatic_hard_pass = cleaner_ran and not issues
    verdict = "INCONCLUSIVE" if automatic_hard_pass else "FAIL"
    decision = {"actual_cleaning": "RUN" if cleaner_ran else "NOT_RUN", "verdict": verdict, "reason": "automatic contract checks passed but visual acceptance is intentionally not inferred" if automatic_hard_pass else "one or more hard experiment checks failed", "quality_issue_count": len(issues)}
    write_json(run_dir / "artifacts/decision.json", decision)
    roi_shape = oracle.masks["bubble_interior"].shape
    roi_outside = ~(oracle.masks["bubble_interior"] | oracle.masks["visible_boundary"] | oracle.masks["page_truncation"])
    # Class-map evaluation needs exclusive classes.  Page truncation takes
    # precedence where the semantic boundary labels overlap; protection still
    # uses their union above.
    expected_classes = {"bubble_interior": oracle.masks["bubble_interior"] & ~oracle.masks["visible_boundary"] & ~oracle.masks["page_truncation"], "visible_boundary": oracle.masks["visible_boundary"] & ~oracle.masks["page_truncation"], "page_truncation": oracle.masks["page_truncation"], "unknown": np.zeros(roi_shape, dtype=bool), "outside": roi_outside}
    metrics = {"input": {"source_hash_matches_case": True, "oracle_manifest_sha256": oracle.manifest_sha256}, "detection": {"status": "INJECTED_SEMANTIC_ORACLE"}, "grouping": {"status": "INJECTED", "bubble_count": 1, "text_group_count": 1}, "text_support": support_metrics(oracle.masks["text_required"], core=oracle.masks["text_core"], fringe=oracle.masks["text_fringe"], visible_boundary=oracle.masks["visible_boundary"], page_truncation=oracle.masks["page_truncation"], bubble_interior=oracle.masks["bubble_interior"]), "physical_boundary": {"status": "INJECTED", "visible_boundary_pixels": int(visible.sum()), "page_truncation_pixels": int(truncation.sum()), **boundary_metrics(expected_classes, expected_classes)}, "authorization": authorization, "cleaner": {"status": "RUN" if cleaner_ran else "NOT_RUN", "actual_changed_pixels": int(actual.sum())}, "cleaning_check": check}
    intervention = {"case_id": case.case_id, "mode": "oracle-cleaner-isolation", "verdict": verdict, "oracle_injection": True, "injected_stages": manifest["injected_stages"], "hard_checks_pass": automatic_hard_pass, "visual_acceptance": "NOT_REVIEWED"}
    manifest["oracle"] = {"path": str(accepted), "manifest_sha256": oracle.manifest_sha256}; manifest["stage_execution_statuses"] = {"grouping": "INJECTED", "text_support": "INJECTED", "physical_boundary": "INJECTED", "authorization": "PASS" if not issues else "FAIL", "cleaner": "RUN" if cleaner_ran else "NOT_RUN", "cleaning_check": "PASS" if not issues else "FAIL"}; manifest["execution_finished_at"] = utc_now(); manifest["output_artifacts"] = artifact_inventory(run_dir)
    write_json(run_dir / "METRICS.json", metrics); write_json(run_dir / "INTERVENTION_RESULT.json", intervention); write_json(run_dir / "MANIFEST.json", manifest)
    (run_dir / "REPORT.md").write_text(f"# oracle-cleaner-isolation\n\n## Observation\n\nCleaner status: `{decision['actual_cleaning']}`. Hard quality issues: `{len(issues)}`. Visual acceptance was not inferred from pixel metrics.\n\n## Verdict\n\n`{verdict}`. This verifies only the Cleaner under injected semantic inputs.\n\n## Project Decision\n\nUnchanged. No general Grouping, physical-boundary, or M1 Cleaning claim follows from one case.\n", encoding="utf-8")
    _append_log(run_dir, "cleaning_check_finished", quality_issue_count=len(issues), required_residue_pixels=check["required_residue_pixels"], unauthorized_write_pixels=check["unauthorized_write_pixels"])
    _append_log(run_dir, "run_completed", mode="oracle-cleaner-isolation", verdict=verdict, visual_acceptance="NOT_REVIEWED")
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="page_edge_bubble_001")
    parser.add_argument("--case-file", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--oracle", type=Path, default=DEFAULT_ORACLE_PARENT / "accepted-v1")
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--mode", choices=("auto-baseline", "oracle-cleaner-isolation"), required=False)
    parser.add_argument("--freeze-oracle", action="store_true")
    args = parser.parse_args()
    try:
        case = load_case(args.case_file, ROOT)
        if case.case_id != args.case: raise ExperimentStop("requested case does not match case file")
        if args.freeze_oracle:
            result = freeze_candidate_as_accepted(case, DEFAULT_ORACLE_PARENT / "candidate-v0.1", args.oracle)
            print(json.dumps({"status": "FROZEN", "oracle": str(args.oracle), "manifest": result}, ensure_ascii=False)); return 0
        if not args.mode: raise ExperimentStop("--mode is required unless --freeze-oracle is used")
        run = run_auto(case, args.oracle, args.run_root, args.run_id) if args.mode == "auto-baseline" else run_isolation(case, args.oracle, args.run_root, args.run_id)
        print(json.dumps({"status": "COMPLETE", "run_dir": str(run)}, ensure_ascii=False)); return 0
    except ExperimentStop as error:
        print(f"STOP: {error}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
