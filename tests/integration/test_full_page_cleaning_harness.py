from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import cv2
import numpy as np

from manga_read_flow.application.full_page_cleaning_harness import (
    FullPageCleaningHarnessCommand,
    FullPageCleaningHarnessService,
    FullPageCleaningTarget,
)
from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.persistence.full_page_cleaning_acceptance_repository import (
    FullPageCleaningBlockCommand,
)
from manga_read_flow.persistence.project_store import AppStore
from manga_read_flow.providers.border_sampled_fill import BorderSampledFillCleanerProvider


def test_full_page_harness_prepares_unique_inventory_and_leaves_pointer_unselected(tmp_path):
    context = _context(tmp_path, "pass", blocker=False)

    result = _service(context).prepare(context["command"])

    assert len(result.inventory_item_ids) == 2
    assert len(set(result.inventory_item_ids)) == 2
    assert len(result.instance_result_ids) == 2
    assert result.validation_status == "pass"
    assert context["repositories"].content_state.get_page("page-pass").active_cleaned_artifact_id is None
    recovery = context["repositories"].uow.load_page_cleaning_recovery_ledger(
        page_cleaning_run_id=context["command"].page_cleaning_run_id
    )
    assert recovery.run.status == "candidate_ready"
    assert len(recovery.inventory) == 2
    assert recovery.current_dispositions == ()


def test_full_page_harness_records_blocker_then_atomic_block_keeps_pointer_null(tmp_path):
    context = _context(tmp_path, "block", blocker=True)

    result = _service(context).prepare(context["command"])
    outcome = context["repositories"].uow.block_page_cleaning_atomically(
        FullPageCleaningBlockCommand(
            page_cleaning_run_id=result.page_cleaning_run_id,
            page_id="page-block",
            task_id=result.task_id,
            expected_task_status="running",
            expected_task_stage="cleaning",
            workflow_decision_id="decision-block-harness",
            reason_code="page_validation_failed",
            issue_changes=(),
            issue_relations=(),
        )
    )

    assert result.validation_status == "fail"
    assert len(result.disposition_ids) == 1
    assert outcome.result_code == "BLOCKED"
    page = context["repositories"].content_state.get_page("page-block")
    assert page.active_cleaned_artifact_id is None
    recovery = context["repositories"].uow.load_page_cleaning_recovery_ledger(
        page_cleaning_run_id=result.page_cleaning_run_id
    )
    assert recovery.run.status == "blocked"
    assert recovery.current_dispositions[0].disposition_code == "UNSUPPORTED_E3"
    evidence = context["repositories"].artifact_metadata.get_artifact(
        recovery.current_dispositions[0].evidence_artifact_id
    )
    payload = json.loads((context["project"].workspace_path / evidence.relative_path).read_text())
    assert payload["evidence_summary"] == {"historical": "missing", "unsafe_required_pixels": 7}


def _context(tmp_path: Path, suffix: str, *, blocker: bool):
    source = tmp_path / f"source-{suffix}.png"
    image = np.full((80, 80, 3), 255, dtype=np.uint8)
    image[20:28, 18:27] = 0
    image[45:53, 48:57] = 0
    assert cv2.imwrite(str(source), image)
    store = AppStore.initialize(tmp_path / f"workspace-{suffix}")
    project = store.create_project(name="整页 harness", source_language="ja", target_language="zh-Hans")
    repositories = store.open_project(project.project_id).repositories()
    artifacts = ArtifactService(project_id=project.project_id, project_workspace_path=project.workspace_path, artifact_repository=repositories.artifact_metadata)
    imported = ImportPageService(project_id=project.project_id, repositories=repositories, artifact_service=artifacts).import_page(
        ImportPageCommand(source_path=source, batch_name="harness", page_index=1, batch_id=f"batch-{suffix}", page_id=f"page-{suffix}")
    )
    targets = (
        _target(tmp_path, suffix, "a", 1, (18, 20, 27, 28), "E1", "COMPLETE", None),
        _target(
            tmp_path,
            suffix,
            "b",
            2,
            (48, 45, 57, 53),
            "E3" if blocker else "E1",
            "INCOMPLETE_REVIEW" if blocker else "COMPLETE",
            "UNSUPPORTED_E3" if blocker else None,
        ),
    )
    for target in targets:
        repositories.content_state.create_text_block(
            text_block_id=target.source_text_block_id,
            page_id=f"page-{suffix}",
            reading_order=target.inventory_ordinal,
            ocr_status="done",
            translation_status="done",
        )
    command = FullPageCleaningHarnessCommand(
        page_cleaning_run_id=f"run-{suffix}",
        page_cleaning_run_idempotency_key=f"run-key-{suffix}",
        page_id=f"page-{suffix}",
        batch_id=f"batch-{suffix}",
        source_artifact_id=imported.original_artifact.artifact_id,
        source_hash=imported.original_artifact.file_hash,
        source_image_path=source,
        visual_contract_revision_id=f"visual-{suffix}",
        input_hash=_hash(source),
        config_hash=_hash_text("border-sampled-fill-cleaner:mvp1-v0.1"),
        validator_config_hash=_hash_text("cleaning-validator:mvp1-v0.1"),
        work_root=tmp_path / f"run-{suffix}",
        targets=targets,
    )
    return {"project": project, "repositories": repositories, "artifacts": artifacts, "command": command}


def _target(tmp_path, suffix, name, ordinal, bbox, eligibility, completeness, disposition):
    x1, y1, x2, y2 = bbox
    instance = np.zeros((80, 80), dtype=np.uint8)
    instance[y1 - 8:y2 + 8, x1 - 8:x2 + 8] = 255
    required = np.zeros((80, 80), dtype=np.uint8)
    required[y1:y2, x1:x2] = 255
    safe = instance.copy()
    zero = np.zeros((80, 80), dtype=np.uint8)
    paths = {}
    for key, pixels in {"instance": instance, "required": required, "safe": safe, "protected": zero, "uncertainty": zero, "visible": required}.items():
        path = tmp_path / f"{suffix}-{name}-{key}.png"
        assert cv2.imwrite(str(path), pixels)
        paths[key] = path
    segment = f"segment-{suffix}-{name}"
    return FullPageCleaningTarget(
        text_segment_id=segment,
        text_segment_revision_id=f"{segment}::v1",
        source_text_block_id=segment,
        bubble_instance_id=f"instance-{suffix}-{name}",
        bubble_instance_revision_id=f"instance-{suffix}-{name}::v1",
        region_hash=_hash(paths["instance"]),
        inventory_ordinal=ordinal,
        target_class="ordinary_dialogue",
        eligibility=eligibility,
        support_completeness=completeness,
        reason_code="supported_e1" if disposition is None else "unsupported_e3",
        dependency_fingerprint=_hash(paths["required"]),
        instance_mask_path=paths["instance"],
        required_support_path=paths["required"],
        safe_edit_path=paths["safe"],
        protected_mask_path=paths["protected"],
        uncertainty_mask_path=paths["uncertainty"],
        visible_support_path=paths["visible"],
        disposition_code=disposition,
        evidence_summary_json=(
            json.dumps({"historical": "missing", "unsafe_required_pixels": 7})
            if disposition is not None
            else "{}"
        ),
    )


def _service(context):
    return FullPageCleaningHarnessService(
        project_id=context["project"].project_id,
        repositories=context["repositories"],
        artifact_service=context["artifacts"],
        cleaner_provider=BorderSampledFillCleanerProvider(),
    )


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _hash_text(value: str) -> str:
    return sha256(value.encode()).hexdigest()
