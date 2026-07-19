#!/usr/bin/env python3
"""Run Slice 3 real-page full-page Cleaning without a case-specific algorithm.

The command consumes frozen visual-contract records plus the existing E1
cleaner/validator.  Case 71's single g002 correction is the already-approved
text-aware boundary policy; it is reserved durably before pixel work.  All
other evidence uses the same fixed extractor and config for both pages.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from uuid import uuid4

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from manga_read_flow.application.full_page_cleaning_harness import (  # noqa: E402
    FullPageCleaningHarnessCommand,
    FullPageCleaningHarnessService,
    FullPageCleaningTarget,
)
from manga_read_flow.application.full_page_cleaning_eligibility import (  # noqa: E402
    FullPageEligibilityInput,
    decide_full_page_cleaning_eligibility,
)
from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService  # noqa: E402
from manga_read_flow.artifacts.service import ArtifactService  # noqa: E402
from manga_read_flow.persistence.full_page_cleaning_acceptance_repository import (  # noqa: E402
    CleanedPassDispositionDraft,
    CleaningIssueRelationDraft,
    FullPageCleaningAcceptanceCommand,
    FullPageCleaningBlockCommand,
)
from manga_read_flow.persistence.full_page_cleaning_ledger_repository import CorrectionChainDraft  # noqa: E402
from manga_read_flow.persistence.project_store import AppStore  # noqa: E402
from manga_read_flow.providers.border_sampled_fill import BorderSampledFillCleanerProvider  # noqa: E402
from manga_read_flow.quality.text_aware_boundary import TextAwareBoundaryInputs, correct_text_aware_virtual_boundary  # noqa: E402

RUN_BASE = ROOT / "data/local/runs/150-cleaning/full-page-v0.1/slice-3/run-v0.5"
SNAPSHOT = ROOT / "data/local/reviews/120-grouping/visual-contract-a-v0.1/run-v0.4/visual-contract-snapshot.json"
PIXEL_SNAPSHOT = ROOT / "data/local/reviews/160-typesetting/visual-contract-b-v0.1/run-v0.7/pixel-evidence-snapshot.json"
IMAGE_ROOT = ROOT / "data/local/reviews/150-cleaning/association-goal6-v0.1/full-page-v0.1/images"

EVIDENCE_CONFIG = {
    "extractor": "spike-b-dark-core-visible-support-v1",
    "max_text_luminance": 180.0,
    "visible_support_dilation_px": 2,
    "boundary_band_px": 4,
}
VALIDATOR_CONFIG = {"validator": "cleaning-validation-v0.1", "background_delta_threshold": 12.0}
CLEANER_CONFIG = {"cleaner": "border-sampled-fill-cleaner", "tool_version": "mvp1-v0.1"}
RUNNER_PROFILE_IDENTITY = "mvp1-full-page-cleaning-slice3-profile-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--case", choices=("case-71", "case-72"), required=True)
    accept = sub.add_parser("accept-case-71")
    accept.add_argument("--run-dir", type=Path, default=RUN_BASE / "case-71")
    args = parser.parse_args()
    if args.command == "prepare":
        _prepare(args.case)
    else:
        _accept_case71(args.run_dir)


def _prepare(case_id: str) -> None:
    run_dir = RUN_BASE / case_id
    if run_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing formal run: {run_dir}")
    source = IMAGE_ROOT / f"{case_id}.webp"
    if not source.is_file():
        raise SystemExit(f"Missing frozen source: {source}")
    run_dir.mkdir(parents=True)
    page = _page_snapshot(case_id)
    targets, correction = _build_targets(case_id, page, source, run_dir)
    store = AppStore.initialize(run_dir / "workspace")
    project = store.create_project(name=f"Slice 3 {case_id} 整页清字", source_language="ja", target_language="zh-Hans")
    repositories = store.open_project(project.project_id).repositories()
    artifacts = ArtifactService(project_id=project.project_id, project_workspace_path=project.workspace_path, artifact_repository=repositories.artifact_metadata)
    imported = ImportPageService(project_id=project.project_id, repositories=repositories, artifact_service=artifacts).import_page(
        ImportPageCommand(source_path=source, batch_name="mvp1-full-page-cleaning-slice3", page_index=1, batch_id=f"slice3-{case_id}", page_id=case_id)
    )
    for target in targets:
        repositories.content_state.create_text_block(text_block_id=target.source_text_block_id, page_id=case_id, reading_order=target.inventory_ordinal, ocr_status="done", translation_status="done")
    config_hash = _digest({"cleaner": CLEANER_CONFIG, "evidence": EVIDENCE_CONFIG, "validator": VALIDATOR_CONFIG, "correction": "text-aware-boundary-v0.1"})
    command = FullPageCleaningHarnessCommand(
        page_cleaning_run_id=f"run::{case_id}::{uuid4()}",
        page_cleaning_run_idempotency_key=f"slice3::{case_id}::{_hash(source)}::{config_hash}",
        page_id=case_id,
        batch_id=f"slice3-{case_id}",
        source_artifact_id=imported.original_artifact.artifact_id,
        source_hash=imported.original_artifact.file_hash,
        source_image_path=source,
        visual_contract_revision_id=f"visual-contract::{case_id}::slice3::{_digest([target.dependency_fingerprint for target in targets])[:20]}",
        input_hash=_digest({"source": imported.original_artifact.file_hash, "targets": [target.text_segment_revision_id for target in targets]}),
        config_hash=config_hash,
        validator_config_hash=_digest(VALIDATOR_CONFIG),
        work_root=run_dir / "work",
        targets=tuple(targets),
    )
    def reserve_correction(run_id: str) -> None:
        if correction is None:
            return
        reservation = repositories.uow.reserve_or_replay_cleaning_correction(
            chain=CorrectionChainDraft(correction["chain_id"], run_id, case_id, correction["scope_hash"], correction["source_fingerprint"], correction["target_fingerprint"], correction["policy_identity"]),
            correction_reservation_id=correction["reservation_id"], idempotency_key=correction["idempotency_key"], reserved_attempt_id=None,
        )
        if reservation.ordinal != 1 or reservation.budget_after != 0:
            raise RuntimeError("Correction reservation did not preserve the one-correction budget.")
        repositories.uow.mark_cleaning_correction_executing(correction_reservation_id=reservation.correction_reservation_id)
    service = FullPageCleaningHarnessService(project_id=project.project_id, repositories=repositories, artifact_service=artifacts, cleaner_provider=BorderSampledFillCleanerProvider())
    result = service.prepare(command, before_execution=reserve_correction)
    if correction is not None:
        repositories.uow.complete_cleaning_correction(correction_reservation_id=correction["reservation_id"])
    decision = None
    if result.validation_status == "fail":
        relations = tuple(CleaningIssueRelationDraft(f"relation::{uuid4()}", issue_id, "decided_by", workflow_decision_id=f"decision::{case_id}::block") for issue_id in result.issue_ids)
        decision = repositories.uow.block_page_cleaning_atomically(FullPageCleaningBlockCommand(result.page_cleaning_run_id, case_id, result.task_id, "running", "cleaning", f"decision::{case_id}::block", "page_validation_failed", (), relations))
        if not decision.committed or decision.result_code != "BLOCKED":
            raise RuntimeError(f"Full-page block transaction failed: {decision}")
    summary = _write_materials(run_dir, source, project, repositories, result, command, targets, correction, decision)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def _build_targets(case_id: str, page: dict, source: Path, run_dir: Path):
    spike = _spike_b_functions()
    source_pixels = _read_rgb(source)
    pixel_snapshot = _pixel_snapshot()
    pixel_evidence_revision = _pixel_evidence_revision(pixel_snapshot)
    by_segment_pixel = {record["segment_id"]: record for record in pixel_snapshot["records"] if record.get("page_id") == case_id}
    instances = {segment_id: instance for instance in page["bubble_instances"] for segment_id in instance["segment_ids"]}
    assessments = {
        assessment["instance_id"]: assessment
        for assessment in page["eligibility_assessments"]
    }
    evidence_root = run_dir / "evidence"
    evidence_root.mkdir()
    built: dict[str, dict] = {}
    for segment in page["text_segments"]:
        segment_id = segment["segment_id"]
        instance = instances[segment_id]
        instance_mask = _read_mask(ROOT / "data/local/reviews/120-grouping/visual-contract-a-v0.1/run-v0.4" / instance["mask_artifact"]["relative_path"])
        core = spike["text_core_from_bbox"](source_pixels, segment["bbox"], instance_mask, max_text_luminance=EVIDENCE_CONFIG["max_text_luminance"])
        visible = spike["expand_visible_text_support"](core, instance_mask, dilation_px=EVIDENCE_CONFIG["visible_support_dilation_px"])
        protected, uncertainty = spike["boundary_and_uncertainty"](instance_mask, band_px=EVIDENCE_CONFIG["boundary_band_px"])
        safe = spike["build_safe_edit_evidence"](visible, protected, uncertainty)["_safe_edit_mask"]
        completeness = spike["evaluate_required_text_completeness"](visible, safe)
        pixel_record = by_segment_pixel.get(segment_id)
        assessment = assessments[instance["instance_id"]]
        built[segment_id] = {
            "segment": segment,
            "instance": instance,
            "instance_mask": instance_mask,
            "visible": visible,
            "safe": safe,
            "protected": protected,
            "uncertainty": uncertainty,
            "completeness": completeness,
            "historical_risk": assessment["candidate_risk"],
            "target_class": _target_class_from_formal_metadata(segment, assessment),
            "classifier_policy_version": assessment["threshold_version"],
            "pixel_evidence_revision": pixel_evidence_revision,
            "legacy_pixel_record": pixel_record,
        }
    correction = None
    if case_id == "case-71":
        s1, s2 = "case-71__g002__s01", "case-71__g002__s02"
        data = built[s2]
        unsafe_before = int((data["visible"] & ~data["safe"]).sum())
        corrected = correct_text_aware_virtual_boundary(TextAwareBoundaryInputs(data["instance_mask"], built[s1]["instance_mask"], data["uncertainty"], data["protected"], data["visible"], data["protected"], data["uncertainty"], source_sha256=_hash(source)), correction_ordinal=1)
        if corrected.status != "COMPLETE":
            raise RuntimeError(f"Existing text-aware correction cannot satisfy case-71: {corrected.reason_code}")
        data.update({"instance_mask": corrected.primary_instance, "safe": corrected.primary_safe_edit, "protected": corrected.primary_protected, "uncertainty": corrected.uncertainty, "completeness": {"decision": "COMPLETE", "unsafe_required_pixels": corrected.unsafe_required_pixels}, "correction": corrected})
        correction = {"chain_id": f"correction-chain::{case_id}::g002", "reservation_id": f"correction-reservation::{case_id}::g002::v1", "idempotency_key": f"slice3::{case_id}::g002::text-aware-boundary-v0.1", "scope_hash": _digest([s1, s2]), "source_fingerprint": _hash(source), "target_fingerprint": corrected.dependency_fingerprint, "policy_identity": "text-aware-boundary-v0.1", "unsafe_before": unsafe_before, "unsafe_after": corrected.unsafe_required_pixels}
    targets = []
    for segment_id, data in built.items():
        paths = _save_target_masks(evidence_root, segment_id, data)
        instance_revision = data["instance"]["revision_id"] + "::slice3-v1"
        if case_id == "case-71" and segment_id == "case-71__g002__s02":
            instance_revision += "::text-aware-boundary-corrected"
        elif case_id == "case-71" and segment_id == "case-71__g002__s01":
            instance_revision += "::shared-boundary-revalidated"
        complete = data["completeness"]["decision"] == "COMPLETE"
        required_pixels = int(data["completeness"].get("required_text_pixels", 0))
        safe_covered_pixels = int(data["completeness"].get("safe_edit_covered_required_pixels", 0))
        decision = decide_full_page_cleaning_eligibility(
            FullPageEligibilityInput(
                target_class=data["target_class"],
                historical_candidate_risk=data["historical_risk"],
                required_pixels=required_pixels,
                safe_covered_required_pixels=safe_covered_pixels,
                required_protected_overlap_pixels=int((data["visible"] & data["protected"]).sum()),
                required_uncertainty_overlap_pixels=int((data["visible"] & data["uncertainty"]).sum()),
                support_completeness="COMPLETE" if complete else "INCOMPLETE_REVIEW",
                bubble_instance_revision_id=instance_revision,
                text_segment_revision_id=f"{segment_id}::slice3-v1",
                evidence_source_revision=data["pixel_evidence_revision"],
                classifier_policy_version=data["classifier_policy_version"],
                profile_identity=RUNNER_PROFILE_IDENTITY,
                config_identity=_digest({"evidence": EVIDENCE_CONFIG, "validator": VALIDATOR_CONFIG}),
            )
        )
        disposition = None
        reason = decision.reason_code
        if not complete:
            disposition = "BLOCKED_UNSAFE_REQUIRED"
            if data["target_class"] in {"ordinary_dialogue", "narration"} and decision.evidence_summary["required_protected_overlap_pixels"]:
                reason = "physical_boundary_capability_requires_review"
        elif decision.eligibility == "E3":
            disposition = "UNSUPPORTED_E3"
        elif decision.eligibility != "E1":
            disposition = (
                "UNSUPPORTED_FREE_TEXT"
                if data["target_class"] == "sfx_or_free_text"
                else "INCOMPLETE_REVIEW"
            )
        fingerprint = _digest({"source": _hash(source), "segment": segment_id, "instance_revision": instance_revision, "eligibility_decision": decision.dependency_fingerprint, "paths": {key: _hash(path) for key, path in paths.items()}, "config": EVIDENCE_CONFIG, "correction": correction["target_fingerprint"] if correction and segment_id.endswith("g002__s02") else None})
        evidence_summary = {
            "current_required_text": {
                "required_pixels": int(data["completeness"].get("required_text_pixels", 0)),
                "safe_covered_pixels": int(data["completeness"].get("safe_edit_covered_required_pixels", 0)),
                "unsafe_required_pixels": int(data["completeness"].get("unsafe_required_pixels", 0)),
                "decision": data["completeness"]["decision"],
            },
            "historical_visual_status": data["segment"]["historical_status"],
            "historical_exclusion_reason": data["segment"].get("historical_exclusion_reason"),
            "target_class": data["target_class"],
            "eligibility_decision": decision.evidence_summary,
            "legacy_pixel_evidence": (
                data["legacy_pixel_record"].get("required_text_completeness")
                if data["legacy_pixel_record"] is not None
                else "MISSING_HISTORICAL_PIXEL_LEDGER"
            ),
        }
        targets.append(
            FullPageCleaningTarget(
                text_segment_id=segment_id,
                text_segment_revision_id=f"{segment_id}::slice3-v1",
                source_text_block_id=segment_id,
                bubble_instance_id=data["instance"]["instance_id"],
                bubble_instance_revision_id=instance_revision,
                region_hash=_mask_digest(data["instance_mask"]),
                inventory_ordinal=data["segment"]["reading_order"],
                target_class=data["target_class"],
                eligibility=decision.eligibility,
                support_completeness=decision.support_completeness,
                reason_code=reason,
                dependency_fingerprint=fingerprint,
                instance_mask_path=paths["instance"],
                required_support_path=paths["visible"],
                safe_edit_path=paths["safe"],
                protected_mask_path=paths["protected"],
                uncertainty_mask_path=paths["uncertainty"],
                visible_support_path=paths["visible"],
                disposition_code=disposition,
                disposition_blocking=True,
                evidence_summary_json=json.dumps(evidence_summary, ensure_ascii=False, sort_keys=True),
                eligibility_evidence_json=json.dumps(decision.evidence_summary, ensure_ascii=False, sort_keys=True),
            )
        )
    return targets, correction


def _write_materials(run_dir, source, project, repositories, result, command, targets, correction, decision):
    visual_root = run_dir / "visuals"; visual_root.mkdir()
    candidate_artifact = repositories.artifact_metadata.get_artifact(result.combined_artifact_id)
    candidate_path = project.workspace_path / candidate_artifact.relative_path
    original = _read_rgb(source); candidate = _read_rgb(candidate_path); changed = np.any(original != candidate, axis=2)
    _write_rgb(visual_root / "01-original.png", original)
    _write_rgb(visual_root / "02-combined-candidate.png", candidate)
    _write_rgb(visual_root / "03-side-by-side.png", np.concatenate((original, candidate), axis=1))
    _write_rgb(visual_root / "04-absolute-diff.png", np.abs(original.astype(np.int16) - candidate.astype(np.int16)).astype(np.uint8))
    overlay = original.copy(); overlay[changed] = (255, 0, 0); _write_rgb(visual_root / "05-actual-changed-overlay.png", overlay)
    for target in targets:
        crop_root = visual_root / "instances" / target.text_segment_id; crop_root.mkdir(parents=True)
        bbox = next(item["bbox"] for item in _page_snapshot(command.page_id)["text_segments"] if item["segment_id"] == target.text_segment_id)
        ys, xs = _crop_slice(bbox, original.shape[:2]); _write_rgb(crop_root / "original.png", original[ys, xs]); _write_rgb(crop_root / "candidate.png", candidate[ys, xs])
        mask = _read_mask(target.required_support_path); evidence = original.copy(); evidence[mask] = (0, 255, 0); evidence[changed] = (255, 0, 0); _write_rgb(crop_root / "changed-and-required-overlay.png", evidence[ys, xs])
        safe = _read_mask(target.safe_edit_path); protected = _read_mask(target.protected_mask_path); uncertainty = _read_mask(target.uncertainty_mask_path); controls = original.copy(); controls[safe] = (0, 255, 0); controls[protected] = (255, 0, 0); controls[uncertainty] = (255, 255, 0); _write_rgb(crop_root / "evidence-overlay.png", controls[ys, xs])
    recovery = repositories.uow.load_page_cleaning_recovery_ledger(page_cleaning_run_id=result.page_cleaning_run_id)
    acceptance_recovery = repositories.full_page_cleaning_acceptance.load_page_cleaning_acceptance_recovery(page_cleaning_run_id=result.page_cleaning_run_id)
    summary = {"case_id": command.page_id, "project_id": project.project_id, "workspace": str(project.workspace_path), "run_id": result.page_cleaning_run_id, "task_id": result.task_id, "source": {"path": str(source), "sha256": _hash(source), "artifact_id": command.source_artifact_id}, "visual_contract_revision_id": command.visual_contract_revision_id, "config_hash": command.config_hash, "inventory": [item.__dict__ for item in recovery.inventory], "instance_results": [item.__dict__ for item in recovery.instance_results], "dispositions": [item.__dict__ for item in recovery.current_dispositions], "candidate": {"id": result.combined_cleaning_candidate_id, "artifact_id": result.combined_artifact_id, "sha256": result.combined_hash, "delta_artifact_id": result.combined_delta_artifact_id}, "validation": {"id": result.page_cleaning_validation_record_id, "status": result.validation_status}, "correction": correction, "decision": decision.__dict__ if decision else None, "active_cleaned_artifact_id": repositories.content_state.get_page(command.page_id).active_cleaned_artifact_id, "acceptance_recovery": {"candidate_statuses": [item.status for item in acceptance_recovery.candidates], "validation_statuses": [item.status for item in acceptance_recovery.validations]}, "target_result_ids": result.target_result_ids, "target_inventory_ids": result.target_inventory_ids}
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=list) + "\n", encoding="utf-8")
    if _requires_human_form(command.page_id):
        (run_dir / "FORM.md").write_text(_case71_form(), encoding="utf-8")
    lock = {str(path.relative_to(run_dir)): _hash(path) for path in sorted(path for path in run_dir.rglob("*") if path.is_file() and "workspace" not in path.parts)}
    (run_dir / "review-material-lock.json").write_text(json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _accept_case71(run_dir: Path) -> None:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    form = (run_dir / "FORM.md").read_text(encoding="utf-8")
    if "FULL_PAGE_RESULT_ACCEPTABLE = ACCEPT" not in form:
        raise SystemExit("FORM must contain `FULL_PAGE_RESULT_ACCEPTABLE = ACCEPT` before atomic acceptance.")
    project = AppStore.initialize(run_dir / "workspace").open_project(summary["project_id"])
    repositories = project.repositories(); recovery = repositories.uow.load_page_cleaning_recovery_ledger(page_cleaning_run_id=summary["run_id"])
    passes = tuple(CleanedPassDispositionDraft(f"accepted-pass::{uuid4()}", item.cleaning_inventory_item_id, next(result.instance_cleaning_result_id for result in recovery.instance_results if item.cleaning_inventory_item_id in result.inventory_item_ids), item.dependency_fingerprint) for item in recovery.inventory)
    command = FullPageCleaningAcceptanceCommand(f"acceptance::{uuid4()}", f"acceptance-key::{summary['run_id']}", summary["run_id"], "case-71", summary["candidate"]["id"], summary["validation"]["id"], summary["candidate"]["artifact_id"], None, summary["source"]["artifact_id"], summary["visual_contract_revision_id"], summary["task_id"], "running", "cleaning", f"decision::case-71::accept", "human_visual_gate_accepted", passes)
    eligibility = repositories.uow.validate_active_cleaned_pointer_eligibility(command)
    if eligibility.result_code != "ELIGIBLE": raise RuntimeError(f"Acceptance freshness/integrity guard failed: {eligibility.result_code}")
    accepted = repositories.uow.accept_page_cleaning_atomically(command); replay = repositories.uow.accept_page_cleaning_atomically(command)
    if accepted.result_code != "ACCEPTED" or replay.result_code != "ALREADY_ACCEPTED": raise RuntimeError(f"Atomic acceptance/replay failed: {accepted}, {replay}")
    updated = {**summary, "human_form": "ACCEPT", "acceptance": {"outcome": accepted.__dict__, "replay": replay.__dict__}, "active_cleaned_artifact_id": repositories.content_state.get_page("case-71").active_cleaned_artifact_id}
    (run_dir / "summary.json").write_text(json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True, default=list) + "\n", encoding="utf-8")
    _refresh_material_lock(run_dir)
    print(json.dumps(updated["acceptance"], ensure_ascii=False, indent=2, sort_keys=True))


def _requires_human_form(case_id): return case_id == "case-71"
def _case71_form():
    return """# Slice 3 case-71 整页人工视觉 Gate\n\n![原图](visuals/01-original.png)\n\n![候选](visuals/02-combined-candidate.png)\n\n![并排](visuals/03-side-by-side.png)\n\n![差分](visuals/04-absolute-diff.png)\n\n![变更覆盖](visuals/05-actual-changed-overlay.png)\n\nCASE_71_FULL_PAGE_VISUAL_COMPLETENESS = \nALL_REQUIRED_TEXT_REMOVED = \nVISIBLE_RESIDUE_OR_HALO = \nBUBBLE_BOUNDARY_DAMAGE = \nCHARACTER_OR_BACKGROUND_DAMAGE = \nCROSS_INSTANCE_SEAM_OR_COLOR_MISMATCH = \nORIGINAL_IMMUTABILITY = \nFULL_PAGE_RESULT_ACCEPTABLE = \nNOTES = \n\n填写 `FULL_PAGE_RESULT_ACCEPTABLE = ACCEPT` 后才可运行原子验收。\n"""


def _refresh_material_lock(run_dir: Path) -> None:
    lock = {str(path.relative_to(run_dir)): _hash(path) for path in sorted(path for path in run_dir.rglob("*") if path.is_file() and "workspace" not in path.parts and path.name != "review-material-lock.json")}
    (run_dir / "review-material-lock.json").write_text(json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _page_snapshot(case_id): return next(page for page in json.loads(SNAPSHOT.read_text(encoding="utf-8"))["pages"] if page["page_id"] == case_id)
def _pixel_snapshot(): return json.loads(PIXEL_SNAPSHOT.read_text(encoding="utf-8"))
def _pixel_evidence_revision(snapshot): return f'{snapshot["schema_version"]}:{snapshot["snapshot_sha256"]}'
def _target_class_from_formal_metadata(segment, assessment):
    reasons = set(assessment["reason_codes"])
    if "UNSUPPORTED_COMPLEX_FREE_TEXT_OR_SFX_CANDIDATE" in reasons:
        return "sfx_or_free_text"
    if "BACKGROUND_EVIDENCE_INSUFFICIENT" in reasons:
        return "sign_or_scene_text_review"
    if segment["historical_status"] == "eligible" or str(segment.get("historical_exclusion_reason") or "").startswith("E3"):
        return "ordinary_dialogue"
    return "review"
def _hash(path): return sha256(Path(path).read_bytes()).hexdigest()
def _digest(value): return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def _read_mask(path):
    value = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if value is None: raise ValueError(f"Unreadable mask: {path}")
    return value > 0
def _read_rgb(path):
    value = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if value is None: raise ValueError(f"Unreadable image: {path}")
    return cv2.cvtColor(value, cv2.COLOR_BGR2RGB)
def _write_rgb(path, value):
    if not cv2.imwrite(str(path), cv2.cvtColor(value, cv2.COLOR_RGB2BGR)): raise ValueError(f"Unable to write image: {path}")
def _mask_digest(mask): return sha256(np.ascontiguousarray(mask.astype(np.uint8)).tobytes()).hexdigest()
def _crop_slice(bbox, shape):
    x, y, width, height = (bbox[key] for key in ("x", "y", "width", "height")); return slice(max(0, y - 16), min(shape[0], y + height + 16)), slice(max(0, x - 16), min(shape[1], x + width + 16))
def _save_target_masks(root, segment_id, data):
    path = root / segment_id; path.mkdir()
    result = {}
    for key, value in {"instance": data["instance_mask"], "visible": data["visible"], "safe": data["safe"], "protected": data["protected"], "uncertainty": data["uncertainty"]}.items():
        file = path / f"{key}.png"
        if not cv2.imwrite(str(file), value.astype(np.uint8) * 255): raise ValueError(f"Unable to save evidence: {file}")
        result[key] = file
    return result
def _spike_b_functions():
    spec = importlib.util.spec_from_file_location("slice3_spike_b", ROOT / "tools/experiments/150-cleaning/visual_contract/spike_b.py")
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(module)
    return {name: getattr(module, name) for name in ("text_core_from_bbox", "expand_visible_text_support", "boundary_and_uncertainty", "build_safe_edit_evidence", "evaluate_required_text_completeness")}


if __name__ == "__main__": main()
