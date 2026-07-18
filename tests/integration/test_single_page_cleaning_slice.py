from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import cv2
import numpy as np

from manga_read_flow.application.clean_single_page import (
    CleaningSliceInstanceInput,
    SinglePageCleaningCommand,
    SinglePageCleaningService,
)
from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.persistence.project_store import AppStore
from manga_read_flow.providers.border_sampled_fill import BorderSampledFillCleanerProvider


def test_case_style_incomplete_instance_blocks_candidate_without_switching_active_pointer(tmp_path):
    project, repositories, artifact_service, source, original = _page(tmp_path, "block")
    complete = _instance(tmp_path, "s01", bbox=(12, 12, 20, 20), complete=True)
    incomplete = _instance(tmp_path, "s02", bbox=(40, 40, 48, 48), complete=False)
    for order, item in enumerate((complete, incomplete), 1):
        repositories.content_state.create_text_block(
            text_block_id=item.source_text_block_id,
            page_id="case-test",
            reading_order=order,
            ocr_status="done",
            translation_status="done",
        )

    result = _service(project, repositories, artifact_service).run(
        _command(tmp_path, source, original.artifact_id, (complete, incomplete), "block")
    )

    page = repositories.content_state.get_page("case-test")
    assert result.decision == "block"
    assert result.provider_called is True
    assert result.active_cleaned_artifact_id is None
    assert page.active_cleaned_artifact_id is None
    assert repositories.quality_issues.count_open_blockers() == 1
    assert repositories.visual_contract.current_revision_id(page_id="case-test") == "visual::block"
    assert len(repositories.visual_contract.list_results(page_id="case-test")) == 1
    candidate = repositories.artifact_metadata.get_artifact(result.candidate_artifact_id)
    evidence = repositories.artifact_metadata.get_artifact(result.evidence_artifact_id)
    assert candidate.artifact_type == "cleaned_image"
    assert evidence.mime_type == "application/json"
    assert _sha256(source) == original.file_hash


def test_complete_slice_switches_active_pointer_and_reuses_valid_pass(tmp_path):
    project, repositories, artifact_service, source, original = _page(tmp_path, "pass")
    complete = _instance(tmp_path, "s01", bbox=(12, 12, 20, 20), complete=True)
    repositories.content_state.create_text_block(
        text_block_id=complete.source_text_block_id,
        page_id="case-test",
        reading_order=1,
        ocr_status="done",
        translation_status="done",
    )
    command = _command(tmp_path, source, original.artifact_id, (complete,), "pass")
    service = _service(project, repositories, artifact_service)

    first = service.run(command)
    second = service.run(command)

    assert first.decision == "pass"
    assert first.active_cleaned_artifact_id == first.candidate_artifact_id
    assert second.reused is True
    assert second.provider_called is False
    assert second.candidate_artifact_id == first.candidate_artifact_id
    assert len(repositories.visual_contract.list_results(page_id="case-test")) == 1


def test_partial_page_scope_blocks_selected_output_while_one_e1_is_revalidated(tmp_path):
    project, repositories, artifact_service, source, original = _page(tmp_path, "partial")
    retained = _instance(tmp_path, "retained", bbox=(12, 12, 20, 20), complete=True)
    corrected = _instance(tmp_path, "corrected", bbox=(40, 40, 48, 48), complete=True)
    retained = retained.__class__(**{**retained.__dict__, "execute_cleaner": False})
    for order, item in enumerate((retained, corrected), 1):
        repositories.content_state.create_text_block(
            text_block_id=item.source_text_block_id,
            page_id="case-test",
            reading_order=order,
            ocr_status="done",
            translation_status="done",
        )
    command = _command(tmp_path, source, original.artifact_id, (retained, corrected), "partial")
    command = command.__class__(**{**command.__dict__, "page_scope_complete": False})
    result = _service(project, repositories, artifact_service).run(command)
    assert result.provider_called is True
    assert result.decision == "block"
    assert result.active_cleaned_artifact_id is None
    assert repositories.content_state.get_page("case-test").active_cleaned_artifact_id is None


def _page(tmp_path: Path, suffix: str):
    source = tmp_path / f"source-{suffix}.png"
    image = np.full((64, 64, 3), 255, dtype=np.uint8)
    image[12:20, 12:20] = 0
    image[40:48, 40:48] = 0
    assert cv2.imwrite(str(source), image)
    store = AppStore.initialize(tmp_path / f"workspace-{suffix}")
    project = store.create_project(
        name="slice",
        source_language="ja",
        target_language="zh-Hans",
    )
    repositories = store.open_project(project.project_id).repositories()
    artifact_service = ArtifactService(
        project_id=project.project_id,
        project_workspace_path=project.workspace_path,
        artifact_repository=repositories.artifact_metadata,
    )
    imported = ImportPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
    ).import_page(
        ImportPageCommand(
            source_path=source,
            batch_name="slice",
            page_index=1,
            batch_id="batch-test",
            page_id="case-test",
        )
    )
    return project, repositories, artifact_service, source, imported.original_artifact


def _instance(tmp_path: Path, name: str, *, bbox, complete: bool):
    x1, y1, x2, y2 = bbox
    instance = np.zeros((64, 64), dtype=np.uint8)
    instance[max(0, y1 - 8):min(64, y2 + 8), max(0, x1 - 8):min(64, x2 + 8)] = 255
    required = np.zeros((64, 64), dtype=np.uint8)
    required[y1:y2, x1:x2] = 255
    safe = instance.copy()
    if not complete:
        safe[y1, x1] = 0
    zero = np.zeros((64, 64), dtype=np.uint8)
    paths = {}
    for key, array in {
        "instance": instance,
        "required": required,
        "safe": safe,
        "protected": zero,
        "uncertainty": zero,
    }.items():
        path = tmp_path / f"{name}-{key}.png"
        assert cv2.imwrite(str(path), array)
        paths[key] = path
    return CleaningSliceInstanceInput(
        bubble_instance_id=f"instance::{name}",
        bubble_instance_revision_id=f"instance-revision::{name}",
        region_hash=sha256(instance.tobytes()).hexdigest(),
        text_segment_id=f"segment::{name}",
        text_segment_revision_id=f"segment-revision::{name}",
        source_text_block_id=f"segment::{name}",
        segment_order=1,
        instance_mask_path=paths["instance"],
        required_support_path=paths["required"],
        safe_edit_path=paths["safe"],
        protected_mask_path=paths["protected"],
        uncertainty_mask_path=paths["uncertainty"],
        eligibility="E1",
        required_safe_completeness="COMPLETE" if complete else "INCOMPLETE_REVIEW",
        reason_code="complete" if complete else "required_text_not_safely_editable",
    )


def _command(tmp_path, source, original_artifact_id, instances, suffix):
    return SinglePageCleaningCommand(
        page_id="case-test",
        batch_id="batch-test",
        source_artifact_id=original_artifact_id,
        source_image_path=source,
        visual_contract_revision_id=f"visual::{suffix}",
        input_hash=sha256(f"input::{suffix}".encode()).hexdigest(),
        config_hash=sha256(b"border-sampled-fill-cleaner:mvp1-v0.1").hexdigest(),
        work_root=tmp_path / f"run-{suffix}",
        instances=instances,
    )


def _service(project, repositories, artifact_service):
    return SinglePageCleaningService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        cleaner_provider=BorderSampledFillCleanerProvider(),
    )


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
