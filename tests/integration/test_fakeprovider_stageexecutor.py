from __future__ import annotations

from dataclasses import fields
import importlib
import sqlite3
import struct
import zlib
from pathlib import Path

import pytest

from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.domain.provider_contracts import (
    ProviderOutcome,
    ProviderResult,
    ProviderTempFileRef,
)
from manga_read_flow.providers.fake import FakeProvider
from manga_read_flow.workflow.stage_executor import (
    StageExecutionConflictError,
    StageExecutionContext,
    StageExecutor,
    StageResult,
)


def test_detection_success_returns_deterministic_candidates_without_textblock_rows(tmp_path):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    context = _stage_context(
        project_id=project.project_id,
        batch_id=imported.batch.batch_id,
        page_id=imported.page.page_id,
        stage="detection",
        attempt_temp_root=tmp_path / "attempts" / "detection",
    )
    _create_task(repositories, context)
    executor = StageExecutor(
        attempt_recorder=repositories.workflow_execution,
        evidence_writer=repositories.stage_evidence_writer,
        artifact_service=artifact_service,
    )

    result = executor.execute(
        context,
        FakeProvider(fake_mode="detection_success"),
    )

    assert result.status == "succeeded"
    assert result.provider_called
    assert result.provider_result.outcome.value == "success"
    assert result.candidate_outputs["text_blocks"] == (
        {
            "provider_block_ref": "fake-block-1",
            "bbox": {"x": 10, "y": 20, "width": 80, "height": 24},
            "source_direction": "vertical",
            "reading_order": 1,
            "confidence": 0.93,
        },
        {
            "provider_block_ref": "fake-block-2",
            "bbox": {"x": 12, "y": 64, "width": 84, "height": 22},
            "source_direction": "vertical",
            "reading_order": 2,
            "confidence": 0.91,
        },
    )
    assert _count_rows(project.project_db_path, "text_blocks") == 0


def test_ocr_success_returns_deterministic_candidate_without_result_or_active_pointer(
    tmp_path,
):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    _create_text_blocks(repositories, imported.page.page_id, ("tb-1",))
    result = _execute_stage(
        project,
        repositories,
        artifact_service,
        imported,
        stage="ocr",
        fake_mode="ocr_success",
        target_type="text_block",
        target_id="tb-1",
        text_block_ids=("tb-1",),
        attempt_temp_root=tmp_path / "attempts" / "ocr",
    )

    assert result.status == "succeeded"
    assert result.candidate_outputs["ocr_items"] == (
        {
            "text_block_id": "tb-1",
            "source_text": "fake_source_1",
            "confidence": 0.96,
            "detected_direction": "vertical",
        },
    )
    assert _count_rows(project.project_db_path, "ocr_results") == 0
    assert _text_block_pointers(project.project_db_path, "tb-1") == (None, None)


def test_translation_success_returns_candidates_without_result_or_active_pointer(
    tmp_path,
):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    _create_text_blocks(repositories, imported.page.page_id, ("tb-1", "tb-2"))
    result = _execute_stage(
        project,
        repositories,
        artifact_service,
        imported,
        stage="translation",
        fake_mode="translation_success",
        text_block_ids=("tb-1", "tb-2"),
        attempt_temp_root=tmp_path / "attempts" / "translation",
    )

    assert result.status == "succeeded"
    assert result.candidate_outputs["translations"] == (
        {
            "text_block_id": "tb-1",
            "translation_text": "fake_translation_1",
            "confidence": "high",
            "needs_review": False,
        },
        {
            "text_block_id": "tb-2",
            "translation_text": "fake_translation_2",
            "confidence": "high",
            "needs_review": False,
        },
    )
    assert _count_rows(project.project_db_path, "translation_results") == 0
    assert _text_block_pointers(project.project_db_path, "tb-1") == (None, None)
    assert _text_block_pointers(project.project_db_path, "tb-2") == (None, None)


def test_invalid_translation_output_is_evidence_without_active_selection(tmp_path):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    _create_text_blocks(repositories, imported.page.page_id, ("tb-1", "tb-2"))
    result = _execute_stage(
        project,
        repositories,
        artifact_service,
        imported,
        stage="translation",
        fake_mode="translation_invalid_json",
        text_block_ids=("tb-1", "tb-2"),
        attempt_temp_root=tmp_path / "attempts" / "translation-invalid",
    )
    tool_run = _tool_run(project.project_db_path, result.provider_result.provider_name)

    assert result.status == "invalid_output"
    assert result.provider_result.error is not None
    assert result.provider_result.error.code == "translation_invalid_json"
    assert tool_run["status"] == "invalid_output"
    assert tool_run["error_code"] == "translation_invalid_json"
    assert _count_rows(project.project_db_path, "translation_results") == 0
    assert _text_block_pointers(project.project_db_path, "tb-1") == (None, None)


def test_partial_translation_output_remains_partial_evidence(tmp_path):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    _create_text_blocks(repositories, imported.page.page_id, ("tb-1", "tb-2"))
    result = _execute_stage(
        project,
        repositories,
        artifact_service,
        imported,
        stage="translation",
        fake_mode="translation_partial",
        text_block_ids=("tb-1", "tb-2"),
        attempt_temp_root=tmp_path / "attempts" / "translation-partial",
    )

    assert result.status == "partial_success"
    assert result.provider_result.outcome is ProviderOutcome.PARTIAL_SUCCESS
    assert result.candidate_outputs["translations"] == (
        {
            "text_block_id": "tb-1",
            "translation_text": "fake_translation_1",
            "confidence": "medium",
            "needs_review": False,
        },
    )
    assert result.candidate_outputs["missing_targets"] == ("tb-2",)
    assert _count_rows(project.project_db_path, "translation_results") == 0


def test_translation_failure_records_failure_evidence_without_artifacts(tmp_path):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    _create_text_blocks(repositories, imported.page.page_id, ("tb-1",))
    result = _execute_stage(
        project,
        repositories,
        artifact_service,
        imported,
        stage="translation",
        fake_mode="translation_failure",
        text_block_ids=("tb-1",),
        attempt_temp_root=tmp_path / "attempts" / "translation-failure",
    )
    tool_run = _tool_run(project.project_db_path, result.provider_result.provider_name)

    assert result.status == "failed"
    assert result.provider_result.outcome is ProviderOutcome.FAILURE
    assert result.provider_result.error is not None
    assert result.provider_result.error.kind == "provider_unavailable"
    assert tool_run["status"] == "failed"
    assert result.registered_artifacts == ()
    assert _count_rows(project.project_db_path, "quality_issues") == 0
    assert _count_rows(project.project_db_path, "workflow_decisions") == 0


def test_provider_refusal_records_sanitized_evidence_without_issues_or_decisions(
    tmp_path,
):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    _create_text_blocks(repositories, imported.page.page_id, ("tb-1",))
    result = _execute_stage(
        project,
        repositories,
        artifact_service,
        imported,
        stage="translation",
        fake_mode="translation_refusal",
        text_block_ids=("tb-1",),
        attempt_temp_root=tmp_path / "attempts" / "translation-refusal",
    )
    tool_run = _tool_run(project.project_db_path, result.provider_result.provider_name)
    attempt = _attempt(project.project_db_path, result.attempt_id)

    assert result.status == "refused"
    assert result.provider_result.error is not None
    assert result.provider_result.error.is_provider_refusal
    assert tool_run["status"] == "refused"
    assert tool_run["is_provider_refusal"] == 1
    assert "token" not in tool_run["sanitized_message"].lower()
    assert "secret" not in tool_run["sanitized_message"].lower()
    assert attempt["status"] == "refused"
    assert _count_rows(project.project_db_path, "quality_issues") == 0
    assert _count_rows(project.project_db_path, "workflow_decisions") == 0


def test_cleaning_skip_returns_evidence_without_quality_decision(tmp_path):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    _create_text_blocks(repositories, imported.page.page_id, ("tb-1",))
    result = _execute_stage(
        project,
        repositories,
        artifact_service,
        imported,
        stage="cleaning",
        fake_mode="cleaning_skip",
        text_block_ids=("tb-1",),
        attempt_temp_root=tmp_path / "attempts" / "cleaning-skip",
    )

    assert result.status == "partial_success"
    assert result.candidate_outputs["block_results"] == (
        {
            "text_block_id": "tb-1",
            "status_hint": "cannot_clean",
            "reason_code": "cleaning_complex_background",
        },
    )
    assert result.registered_artifacts == ()
    assert _count_rows(project.project_db_path, "quality_issues") == 0
    assert _count_rows(project.project_db_path, "workflow_decisions") == 0


def test_cleaning_success_registers_official_unselected_artifact(tmp_path):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    result = _execute_stage(
        project,
        repositories,
        artifact_service,
        imported,
        stage="cleaning",
        fake_mode="cleaning_success",
        attempt_temp_root=tmp_path / "attempts" / "cleaning-success",
    )
    page = _page(project.project_db_path, imported.page.page_id)

    assert result.status == "succeeded"
    assert len(result.registered_artifacts) == 1
    artifact = result.registered_artifacts[0]
    assert artifact.artifact_type == "cleaned_image"
    assert artifact.source_stage == "cleaning"
    assert artifact.storage_state == "present"
    assert (project.workspace_path / artifact.relative_path).is_file()
    assert page["active_cleaned_artifact_id"] is None
    assert _count_rows(project.project_db_path, "workflow_decisions") == 0


def test_typesetting_overflow_returns_preview_without_readiness(tmp_path):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    _create_text_blocks(repositories, imported.page.page_id, ("tb-1",))
    result = _execute_stage(
        project,
        repositories,
        artifact_service,
        imported,
        stage="typesetting",
        fake_mode="typesetting_overflow",
        text_block_ids=("tb-1",),
        attempt_temp_root=tmp_path / "attempts" / "typesetting-overflow",
    )
    task = _task(project.project_db_path, result.task_id)

    assert result.status == "partial_success"
    assert result.candidate_outputs["layout_results"] == (
        {
            "text_block_id": "tb-1",
            "fitted": False,
            "overflow": True,
            "final_font_size": 10,
            "line_count": 4,
        },
    )
    assert result.registered_artifacts[0].artifact_type == "typeset_preview_image"
    assert task["status"] == "running"
    assert task["current_stage"] == "typesetting"
    assert _count_rows(project.project_db_path, "workflow_decisions") == 0


def test_typesetting_success_registers_official_unselected_artifact(tmp_path):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    result = _execute_stage(
        project,
        repositories,
        artifact_service,
        imported,
        stage="typesetting",
        fake_mode="typesetting_success",
        attempt_temp_root=tmp_path / "attempts" / "typesetting-success",
    )
    page = _page(project.project_db_path, imported.page.page_id)

    assert result.status == "succeeded"
    assert result.registered_artifacts[0].artifact_type == "typeset_image"
    assert result.registered_artifacts[0].source_stage == "typesetting"
    assert page["active_typeset_artifact_id"] is None


def test_artifact_registration_failure_is_stage_evidence_not_provider_success(
    tmp_path,
):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    context = _stage_context(
        project_id=project.project_id,
        batch_id=imported.batch.batch_id,
        page_id=imported.page.page_id,
        stage="cleaning",
        attempt_temp_root=tmp_path / "attempts" / "missing-temp",
    )
    _create_task(repositories, context)
    executor = StageExecutor(
        attempt_recorder=repositories.workflow_execution,
        evidence_writer=repositories.stage_evidence_writer,
        artifact_service=artifact_service,
    )

    result = executor.execute(context, MissingTempOutputProvider())
    attempt = _attempt(project.project_db_path, result.attempt_id)

    assert result.provider_result.outcome is ProviderOutcome.SUCCESS
    assert result.status == "failed"
    assert result.artifact_errors[0].code == "artifact_registration_failed"
    assert attempt["status"] == "failed"
    assert _artifact_types(project.project_db_path) == ("original_image",)


def test_provider_request_has_no_repository_sqlite_or_official_artifact_capability(
    tmp_path,
):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    context = _stage_context(
        project_id=project.project_id,
        batch_id=imported.batch.batch_id,
        page_id=imported.page.page_id,
        stage="translation",
        attempt_temp_root=tmp_path / "attempts" / "capability-probe",
    )
    _create_task(repositories, context)
    executor = StageExecutor(
        attempt_recorder=repositories.workflow_execution,
        evidence_writer=repositories.stage_evidence_writer,
        artifact_service=artifact_service,
    )

    result = executor.execute(context, CapabilityProbeProvider())

    assert result.status == "succeeded"


def test_provider_call_does_not_hold_sqlite_write_transaction(tmp_path):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    context = _stage_context(
        project_id=project.project_id,
        batch_id=imported.batch.batch_id,
        page_id=imported.page.page_id,
        stage="translation",
        attempt_temp_root=tmp_path / "attempts" / "transaction-probe",
    )
    _create_task(repositories, context)
    executor = StageExecutor(
        attempt_recorder=repositories.workflow_execution,
        evidence_writer=repositories.stage_evidence_writer,
        artifact_service=artifact_service,
    )

    result = executor.execute(context, TransactionProbeProvider(project.project_db_path))

    assert result.status == "succeeded"


def test_stage_executor_stops_when_attempt_reservation_conflicts(tmp_path):
    project, repositories, artifact_service, imported = _ready_imported_page(tmp_path)
    context = _stage_context(
        project_id=project.project_id,
        batch_id=imported.batch.batch_id,
        page_id=imported.page.page_id,
        stage="translation",
        attempt_temp_root=tmp_path / "attempts" / "reservation-conflict",
    )
    repositories.workflow_execution.create_task(
        task_id=context.task_id,
        target_type=context.target_type,
        target_id=context.target_id,
        task_type="translation_stage",
        status="running",
        current_stage=context.expected_current_stage,
    )
    executor = StageExecutor(
        attempt_recorder=repositories.workflow_execution,
        evidence_writer=repositories.stage_evidence_writer,
        artifact_service=artifact_service,
    )

    with pytest.raises(StageExecutionConflictError, match="task_status"):
        executor.execute(context, ProviderThatMustNotRun())

    assert _count_rows(project.project_db_path, "workflow_attempts") == 0
    assert _count_rows(project.project_db_path, "tool_run_logs") == 0


def test_stage_executor_api_exposes_no_decision_or_active_pointer_authority():
    forbidden = (
        "active",
        "quality_issue",
        "workflow_decision",
        "retry_budget",
        "readiness",
        "fallback",
        "warning",
        "pause",
    )
    public_methods = {
        name
        for name in dir(StageExecutor)
        if not name.startswith("_") and callable(getattr(StageExecutor, name))
    }

    assert public_methods == {"execute"}
    for dto in (StageExecutionContext, StageResult):
        dto_fields = {field.name for field in fields(dto)}
        assert all(
            not any(term in field_name for term in forbidden)
            for field_name in dto_fields
        )


def test_fakeprovider_module_has_no_persistence_or_artifactservice_dependency():
    module = importlib.import_module("manga_read_flow.providers.fake")
    source = Path(module.__file__).read_text()

    assert "sqlite3" not in source
    assert "manga_read_flow.persistence" not in source
    assert "ArtifactService" not in source
    assert "register_artifact" not in source


def _ready_imported_page(tmp_path):
    from manga_read_flow.persistence.project_store import AppStore, ProjectOpenStatus

    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="FakeProvider StageExecutor",
        source_language="ja",
        target_language="zh-Hans",
    )
    opened = store.open_project(project.project_id)
    assert opened.status is ProjectOpenStatus.READY
    repositories = opened.repositories()
    artifact_service = ArtifactService(
        project_id=project.project_id,
        project_workspace_path=project.workspace_path,
        artifact_repository=repositories.artifact_metadata,
    )
    source_png = tmp_path / "source.png"
    source_png.write_bytes(_tiny_png(width=8, height=8))
    imported = ImportPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
    ).import_page(
        ImportPageCommand(
            source_path=source_png,
            batch_id="batch-stage",
            batch_name="Stage",
            page_id="page-stage",
            page_index=1,
        )
    )
    return project, repositories, artifact_service, imported


def _execute_stage(
    project,
    repositories,
    artifact_service,
    imported,
    *,
    stage: str,
    fake_mode: str,
    attempt_temp_root,
    target_type: str = "page",
    target_id: str | None = None,
    text_block_ids: tuple[str, ...] = (),
) -> StageResult:
    context = _stage_context(
        project_id=project.project_id,
        batch_id=imported.batch.batch_id,
        page_id=imported.page.page_id,
        stage=stage,
        target_type=target_type,
        target_id=target_id,
        text_block_ids=text_block_ids,
        attempt_temp_root=attempt_temp_root,
    )
    _create_task(repositories, context)
    return StageExecutor(
        attempt_recorder=repositories.workflow_execution,
        evidence_writer=repositories.stage_evidence_writer,
        artifact_service=artifact_service,
    ).execute(context, FakeProvider(fake_mode=fake_mode))


def _stage_context(
    *,
    project_id: str,
    batch_id: str,
    page_id: str,
    stage: str,
    attempt_temp_root,
    target_type: str = "page",
    target_id: str | None = None,
    text_block_ids: tuple[str, ...] = (),
) -> StageExecutionContext:
    target = target_id or page_id
    return StageExecutionContext(
        project_id=project_id,
        task_id=f"task-{stage}",
        attempt_id=f"attempt-{stage}",
        tool_run_id=f"tool-{stage}",
        request_id=f"request-{stage}",
        stage=stage,
        target_type=target_type,
        target_id=target,
        batch_id=batch_id,
        page_id=page_id,
        text_block_ids=text_block_ids,
        expected_task_status="queued",
        expected_current_stage=stage,
        runner_id="test-runner",
        attempt_temp_root=attempt_temp_root,
        input_hash=f"input-{stage}",
        config_hash=f"config-{stage}",
        context_hash=f"context-{stage}",
        source_language="ja",
        target_language="zh-Hans",
    )


def _create_text_blocks(repositories, page_id: str, text_block_ids: tuple[str, ...]) -> None:
    for index, text_block_id in enumerate(text_block_ids, start=1):
        repositories.content_state.create_text_block(
            text_block_id=text_block_id,
            page_id=page_id,
            reading_order=index,
            ocr_status="pending",
            translation_status="pending",
        )


def _count_rows(project_db_path, table_name: str) -> int:
    with sqlite3.connect(project_db_path) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _text_block_pointers(project_db_path, text_block_id: str):
    with sqlite3.connect(project_db_path) as connection:
        row = connection.execute(
            """
            SELECT active_ocr_result_id, active_translation_result_id
            FROM text_blocks
            WHERE text_block_id = ?
            """,
            (text_block_id,),
        ).fetchone()
    return row


def _tool_run(project_db_path, provider_name: str):
    with sqlite3.connect(project_db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT status, error_code, error_class, is_provider_refusal, sanitized_message
            FROM tool_run_logs
            WHERE provider_name = ?
            """,
            (provider_name,),
        ).fetchone()


def _attempt(project_db_path, attempt_id: str):
    with sqlite3.connect(project_db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT status, error_code, sanitized_message
            FROM workflow_attempts
            WHERE attempt_id = ?
            """,
            (attempt_id,),
        ).fetchone()


def _task(project_db_path, task_id: str):
    with sqlite3.connect(project_db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT status, current_stage
            FROM processing_tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()


def _page(project_db_path, page_id: str):
    with sqlite3.connect(project_db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT active_cleaned_artifact_id, active_typeset_artifact_id
            FROM pages
            WHERE page_id = ?
            """,
            (page_id,),
        ).fetchone()


def _artifact_types(project_db_path) -> tuple[str, ...]:
    with sqlite3.connect(project_db_path) as connection:
        return tuple(
            row[0]
            for row in connection.execute(
                """
                SELECT artifact_type
                FROM processing_artifacts
                ORDER BY artifact_type
                """
            ).fetchall()
        )


def _create_task(repositories, context: StageExecutionContext) -> None:
    repositories.workflow_execution.create_task(
        task_id=context.task_id,
        target_type=context.target_type,
        target_id=context.target_id,
        task_type=f"{context.stage}_stage",
        status=context.expected_task_status,
        current_stage=context.expected_current_stage,
    )


class MissingTempOutputProvider:
    provider_name = "MissingTempProvider"
    model_id = "missing-temp-model"
    tool_name = "missing-temp-provider"
    tool_version = "0.1"

    def run(self, request):
        return ProviderResult(
            outcome=ProviderOutcome.SUCCESS,
            provider_name=self.provider_name,
            model_id=self.model_id,
            payload={"cleaned_image_temp_ref": "missing-cleaned"},
            temp_files=(
                ProviderTempFileRef(
                    temp_ref_id="missing-cleaned",
                    kind="image",
                    temp_path=request.attempt_temp_root / "does-not-exist.png",
                    media_type="image/png",
                    expected_artifact_type="cleaned_image",
                ),
            ),
        )


class CapabilityProbeProvider:
    provider_name = "CapabilityProbeProvider"
    model_id = "capability-probe-model"
    tool_name = "capability-probe-provider"
    tool_version = "0.1"

    def run(self, request):
        forbidden = {
            "repository",
            "repositories",
            "sqlite",
            "connection",
            "cursor",
            "session",
            "artifact_service",
            "register_artifact",
            "official_workspace_path",
            "project_db_path",
            "app_db_path",
        }
        assert forbidden.isdisjoint(set(vars(request)))
        return ProviderResult(
            outcome=ProviderOutcome.SUCCESS,
            provider_name=self.provider_name,
            model_id=self.model_id,
            payload={"translations": ()},
        )


class TransactionProbeProvider:
    provider_name = "TransactionProbeProvider"
    model_id = "transaction-probe-model"
    tool_name = "transaction-probe-provider"
    tool_version = "0.1"

    def __init__(self, project_db_path) -> None:
        self._project_db_path = project_db_path

    def run(self, request):
        with sqlite3.connect(self._project_db_path, timeout=0.1) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
        return ProviderResult(
            outcome=ProviderOutcome.SUCCESS,
            provider_name=self.provider_name,
            model_id=self.model_id,
            payload={"translations": ()},
        )


class ProviderThatMustNotRun:
    provider_name = "ProviderThatMustNotRun"
    model_id = "must-not-run-model"
    tool_name = "must-not-run-provider"
    tool_version = "0.1"

    def run(self, request):
        raise AssertionError("Provider must not run after reservation conflict.")


def _tiny_png(*, width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw_rows = b"".join(b"\x00" + (b"\xff\x00\x00" * width) for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw_rows))
        + chunk(b"IEND", b"")
    )
