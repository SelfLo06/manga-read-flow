from __future__ import annotations

import json
import sqlite3
import struct
import zlib
from pathlib import Path

from manga_read_flow.domain.artifacts import ArtifactSafetyMetadata
from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService
from manga_read_flow.application.process_page import ProcessPageCommand, ProcessPageService
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.persistence.project_store import AppStore, ProjectOpenStatus
from manga_read_flow.persistence.repository_uow_core import (
    AcceptanceCommand,
    AcceptedResult,
    ActivePointerUpdate,
    AttemptReservation,
    ExpectedState,
    ExpectedStageStatus,
    StageStatusUpdate,
    TaskProgressUpdate,
    WorkflowDecisionDraft,
)
from manga_read_flow.providers.fake import FakeProvider
from manga_read_flow.workflow.engine import WorkflowLoopEngine
from manga_read_flow.workflow.stage_executor import StageExecutor


def test_imported_page_reaches_ready_for_export_through_fakeprovider_happy_path(
    tmp_path,
):
    project, repositories = _ready_project(tmp_path)
    artifact_service = _artifact_service(project, repositories)
    import_service = ImportPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
    )
    process_service = ProcessPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        provider=FakeProvider.happy_path(),
    )
    source_png = tmp_path / "incoming" / "page.png"
    source_png.parent.mkdir()
    source_png.write_bytes(_tiny_png(width=32, height=24))
    imported = import_service.import_page(
        ImportPageCommand(
            source_path=source_png,
            batch_id="batch-happy",
            batch_name="Happy Path",
            page_id="page-happy",
            page_index=1,
        )
    )

    result = process_service.process_page(
        ProcessPageCommand(page_id=imported.page.page_id)
    )

    assert result.task_status == "succeeded"
    assert result.page_status == "ready_for_export"
    assert result.final_decision == "finish_ready_for_export"

    with _project_connection(project.project_db_path) as connection:
        page = connection.execute(
            """
            SELECT
                status,
                original_artifact_id,
                active_cleaned_artifact_id,
                active_typeset_artifact_id
            FROM pages
            WHERE page_id = ?
            """,
            ("page-happy",),
        ).fetchone()
        text_blocks = connection.execute(
            """
            SELECT
                text_block_id,
                detection_status,
                ocr_status,
                translation_status,
                translation_check_status,
                cleaning_status,
                typesetting_status,
                active_ocr_result_id,
                active_translation_result_id
            FROM text_blocks
            WHERE page_id = ?
            ORDER BY reading_order
            """,
            ("page-happy",),
        ).fetchall()
        ocr_results = connection.execute(
            """
            SELECT
                ocr_result_id,
                text_block_id,
                version_number,
                source_text,
                source_text_hash
            FROM ocr_results
            ORDER BY text_block_id, version_number
            """
        ).fetchall()
        translation_results = connection.execute(
            """
            SELECT
                translation_result_id,
                text_block_id,
                version_number,
                source_ocr_result_id,
                source_text_hash,
                translation_text,
                translation_text_hash,
                glossary_version_id
            FROM translation_results
            ORDER BY text_block_id, version_number
            """
        ).fetchall()
        attempts = connection.execute(
            """
            SELECT stage, status
            FROM workflow_attempts
            ORDER BY attempt_number
            """
        ).fetchall()
        tool_logs = connection.execute(
            """
            SELECT stage, status, provider_name, is_provider_refusal
            FROM tool_run_logs
            ORDER BY started_at, tool_run_id
            """
        ).fetchall()
        decisions = connection.execute(
            """
            SELECT stage, decision_type
            FROM workflow_decisions
            ORDER BY created_at, decision_id
            """
        ).fetchall()
        artifacts = connection.execute(
            """
            SELECT
                artifact_id,
                artifact_type,
                source_stage,
                relative_path,
                storage_state,
                file_hash
            FROM processing_artifacts
            ORDER BY artifact_type
            """
        ).fetchall()
        snapshots = connection.execute(
            """
            SELECT settings_json, settings_hash
            FROM processing_profile_snapshots
            """
        ).fetchall()
        export_record_table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'export_records'
            """
        ).fetchone()

    assert page["status"] == "ready_for_export"
    assert page["original_artifact_id"] == imported.original_artifact.artifact_id
    assert page["active_cleaned_artifact_id"]
    assert page["active_typeset_artifact_id"]
    assert page["active_cleaned_artifact_id"] != page["original_artifact_id"]
    assert page["active_typeset_artifact_id"] != page["original_artifact_id"]

    assert len(text_blocks) == 2
    assert {block["detection_status"] for block in text_blocks} == {"done"}
    assert {block["ocr_status"] for block in text_blocks} == {"done"}
    assert {block["translation_status"] for block in text_blocks} == {"done"}
    assert {block["translation_check_status"] for block in text_blocks} == {"done"}
    assert {block["cleaning_status"] for block in text_blocks} == {"done"}
    assert {block["typesetting_status"] for block in text_blocks} == {"done"}
    assert all(block["active_ocr_result_id"] for block in text_blocks)
    assert all(block["active_translation_result_id"] for block in text_blocks)

    assert len(ocr_results) == len(text_blocks)
    assert {row["version_number"] for row in ocr_results} == {1}
    assert all(row["source_text"] for row in ocr_results)
    assert all(row["source_text_hash"] for row in ocr_results)
    assert {
        block["active_ocr_result_id"] for block in text_blocks
    } == {row["ocr_result_id"] for row in ocr_results}

    assert len(translation_results) == len(text_blocks)
    assert {row["version_number"] for row in translation_results} == {1}
    assert all(row["source_ocr_result_id"] for row in translation_results)
    assert all(row["source_text_hash"] for row in translation_results)
    assert all(row["translation_text"] for row in translation_results)
    assert all(row["translation_text_hash"] for row in translation_results)
    assert all(row["glossary_version_id"] for row in translation_results)
    assert {
        block["active_translation_result_id"] for block in text_blocks
    } == {row["translation_result_id"] for row in translation_results}

    expected_stages = [
        "detection",
        "ocr",
        "translation",
        "translation_check",
        "cleaning",
        "typesetting",
        "export_check",
    ]
    assert [row["stage"] for row in attempts] == expected_stages
    assert {row["status"] for row in attempts} == {"succeeded"}
    assert [row["stage"] for row in decisions] == expected_stages
    assert [row["decision_type"] for row in decisions] == [
        "continue",
        "continue",
        "continue",
        "continue",
        "continue",
        "continue",
        "finish_ready_for_export",
    ]
    assert {row["stage"] for row in tool_logs} >= set(expected_stages[:-1])
    assert {row["status"] for row in tool_logs} == {"succeeded"}
    assert not any(row["is_provider_refusal"] for row in tool_logs)

    artifact_types = {row["artifact_type"] for row in artifacts}
    assert {"original_image", "cleaned_image", "typeset_image"} <= artifact_types
    assert {"export_image", "export_zip", "manifest"}.isdisjoint(artifact_types)
    active_artifacts = {
        row["artifact_id"]: row for row in artifacts if row["artifact_id"] in {
            page["active_cleaned_artifact_id"],
            page["active_typeset_artifact_id"],
        }
    }
    assert {
        row["artifact_type"] for row in active_artifacts.values()
    } == {"cleaned_image", "typeset_image"}
    assert {row["storage_state"] for row in active_artifacts.values()} == {"present"}
    for artifact in active_artifacts.values():
        assert artifact["file_hash"]
        assert (project.workspace_path / artifact["relative_path"]).is_file()

    assert len(snapshots) == 1
    settings = json.loads(snapshots[0]["settings_json"])
    serialized_settings = json.dumps(settings, sort_keys=True).lower()
    assert snapshots[0]["settings_hash"]
    assert "fakeprovider_default" in serialized_settings
    assert "api_key" not in serialized_settings
    assert "token" not in serialized_settings
    assert "secret" not in serialized_settings
    assert "authorization" not in serialized_settings

    assert export_record_table is None


def test_acceptance_guard_reports_conflict_when_active_pointer_changed(tmp_path):
    _project, repositories = _ready_project(tmp_path)
    repositories.content_state.create_page(
        page_id="page-conflict",
        batch_id="batch-conflict",
        original_artifact_id="artifact-original",
        status="uploaded",
    )
    repositories.content_state.create_text_block(
        text_block_id="tb-conflict",
        page_id="page-conflict",
        reading_order=1,
        ocr_status="pending",
        translation_status="pending",
    )
    repositories.workflow_execution.create_task(
        task_id="task-conflict",
        target_type="page",
        target_id="page-conflict",
        task_type="process_page",
        status="queued",
        current_stage="ocr",
    )
    repositories.uow.reserve_attempt(
        AttemptReservation(
            task_id="task-conflict",
            attempt_id="attempt-conflict",
            stage="ocr",
            target_type="page",
            target_id="page-conflict",
            expected_task_status="queued",
            expected_current_stage="ocr",
            runner_id="runner-a",
        )
    )

    with _project_connection(_project.project_db_path) as connection:
        connection.execute(
            """
            INSERT INTO ocr_results (
                ocr_result_id,
                project_id,
                text_block_id,
                version_number,
                source_type,
                source_text,
                source_text_hash,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                "ocr-concurrent",
                _project.project_id,
                "tb-conflict",
                1,
                "user_edit",
                "並行",
                "seeded-hash",
            ),
        )
        connection.execute(
            """
            UPDATE text_blocks
            SET active_ocr_result_id = ?
            WHERE text_block_id = ?
            """,
            ("ocr-concurrent", "tb-conflict"),
        )

    outcome = repositories.uow.accept_stage(
        AcceptanceCommand(
            task_id="task-conflict",
            expected=ExpectedState(
                task_status="running",
                current_stage="ocr",
                active_ocr_result_ids={"tb-conflict": None},
            ),
            accepted_results=(
                AcceptedResult(
                    result_type="ocr",
                    result_id="ocr-conflict",
                    target_type="text_block",
                    target_id="tb-conflict",
                    source_text="text",
                    source_text_hash="hash",
                ),
            ),
            active_pointers=(
                ActivePointerUpdate(
                    owner_type="text_block",
                    owner_id="tb-conflict",
                    pointer_name="active_ocr_result_id",
                    value_id="ocr-conflict",
                ),
            ),
            issue_lifecycle=(),
            workflow_decision=WorkflowDecisionDraft(
                decision_id="decision-conflict",
                attempt_id="attempt-conflict",
                stage="ocr",
                decision_type="continue",
                reason_code="should_conflict",
            ),
            retry_budget_after={},
            task_progress=TaskProgressUpdate(
                status="running",
                current_stage="translation",
                progress_state="ocr_done",
            ),
            stage_statuses=(
                StageStatusUpdate(
                    target_type="text_block",
                    target_id="tb-conflict",
                    stage="ocr",
                    status="done",
                ),
            ),
        )
    )

    assert not outcome.committed
    assert outcome.reload_required
    assert "active_ocr_result_id" in outcome.conflict_fields


def test_acceptance_guard_reports_conflict_when_stage_status_changed(tmp_path):
    project, repositories = _ready_project(tmp_path)
    repositories.content_state.create_page(
        page_id="page-status-conflict",
        batch_id="batch-status-conflict",
        original_artifact_id="artifact-original",
        status="uploaded",
    )
    repositories.content_state.create_text_block(
        text_block_id="tb-status-conflict",
        page_id="page-status-conflict",
        reading_order=1,
        ocr_status="pending",
        translation_status="pending",
    )
    repositories.workflow_execution.create_task(
        task_id="task-status-conflict",
        target_type="page",
        target_id="page-status-conflict",
        task_type="process_page",
        status="queued",
        current_stage="ocr",
    )
    repositories.uow.reserve_attempt(
        AttemptReservation(
            task_id="task-status-conflict",
            attempt_id="attempt-status-conflict",
            stage="ocr",
            target_type="page",
            target_id="page-status-conflict",
            expected_task_status="queued",
            expected_current_stage="ocr",
            runner_id="runner-a",
        )
    )
    with _project_connection(project.project_db_path) as connection:
        connection.execute(
            """
            UPDATE text_blocks
            SET ocr_status = ?
            WHERE text_block_id = ?
            """,
            ("blocked", "tb-status-conflict"),
        )

    outcome = repositories.uow.accept_stage(
        AcceptanceCommand(
            task_id="task-status-conflict",
            expected=ExpectedState(
                task_status="running",
                current_stage="ocr",
                stage_statuses=(
                    ExpectedStageStatus(
                        target_type="text_block",
                        target_id="tb-status-conflict",
                        stage="ocr",
                        status="pending",
                    ),
                ),
            ),
            accepted_results=(
                AcceptedResult(
                    result_type="ocr",
                    result_id="ocr-status-conflict",
                    target_type="text_block",
                    target_id="tb-status-conflict",
                    source_text="text",
                    source_text_hash="hash",
                ),
            ),
            active_pointers=(
                ActivePointerUpdate(
                    owner_type="text_block",
                    owner_id="tb-status-conflict",
                    pointer_name="active_ocr_result_id",
                    value_id="ocr-status-conflict",
                ),
            ),
            issue_lifecycle=(),
            workflow_decision=WorkflowDecisionDraft(
                decision_id="decision-status-conflict",
                attempt_id="attempt-status-conflict",
                stage="ocr",
                decision_type="continue",
                reason_code="should_conflict",
            ),
            retry_budget_after={},
            task_progress=TaskProgressUpdate(
                status="running",
                current_stage="translation",
                progress_state="ocr_done",
            ),
            stage_statuses=(
                StageStatusUpdate(
                    target_type="text_block",
                    target_id="tb-status-conflict",
                    stage="ocr",
                    status="done",
                ),
            ),
        )
    )

    assert not outcome.committed
    assert outcome.reload_required
    assert "ocr_status" in outcome.conflict_fields


def test_missing_active_ocr_pointer_blocks_translation_acceptance(tmp_path):
    project, repositories = _ready_project(tmp_path)
    artifact_service = _artifact_service(project, repositories)
    repositories.content_state.create_page(
        page_id="page-missing-ocr",
        batch_id="batch-missing-ocr",
        original_artifact_id="artifact-original",
        status="uploaded",
    )
    repositories.content_state.create_text_block(
        text_block_id="tb-missing-ocr",
        page_id="page-missing-ocr",
        reading_order=1,
        ocr_status="pending",
        translation_status="pending",
    )
    repositories.workflow_execution.create_task(
        task_id="task-missing-ocr",
        target_type="page",
        target_id="page-missing-ocr",
        task_type="process_page",
        status="queued",
        current_stage="translation",
    )

    result = _workflow_engine(repositories, artifact_service).run_task("task-missing-ocr")

    assert result.task_status == "blocked"
    assert result.page_status == "blocked"
    with _project_connection(project.project_db_path) as connection:
        issue = connection.execute(
            "SELECT issue_type, is_blocking FROM quality_issues"
        ).fetchone()
        translation_count = connection.execute(
            "SELECT COUNT(*) AS count FROM translation_results"
        ).fetchone()["count"]

    assert issue["issue_type"] == "missing_active_ocr_pointer"
    assert issue["is_blocking"] == 1
    assert translation_count == 0


def test_missing_active_translation_pointer_blocks_typesetting_acceptance(tmp_path):
    project, repositories = _ready_project(tmp_path)
    artifact_service = _artifact_service(project, repositories)
    repositories.content_state.create_page(
        page_id="page-missing-translation",
        batch_id="batch-missing-translation",
        original_artifact_id="artifact-original",
        status="uploaded",
    )
    repositories.content_state.create_text_block(
        text_block_id="tb-missing-translation",
        page_id="page-missing-translation",
        reading_order=1,
        ocr_status="pending",
        translation_status="pending",
    )
    with _project_connection(project.project_db_path) as connection:
        connection.execute(
            """
            INSERT INTO ocr_results (
                ocr_result_id,
                project_id,
                text_block_id,
                version_number,
                source_type,
                source_text,
                source_text_hash,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                "ocr-for-typesetting-block",
                project.project_id,
                "tb-missing-translation",
                1,
                "workflow_acceptance",
                "source",
                "source-hash",
            ),
        )
        connection.execute(
            """
            UPDATE text_blocks
            SET active_ocr_result_id = ?,
                ocr_status = ?
            WHERE text_block_id = ?
            """,
            ("ocr-for-typesetting-block", "done", "tb-missing-translation"),
        )
    repositories.workflow_execution.create_task(
        task_id="task-missing-translation",
        target_type="page",
        target_id="page-missing-translation",
        task_type="process_page",
        status="queued",
        current_stage="typesetting",
    )

    result = _workflow_engine(repositories, artifact_service).run_task(
        "task-missing-translation"
    )

    assert result.task_status == "blocked"
    assert result.page_status == "blocked"
    with _project_connection(project.project_db_path) as connection:
        issue = connection.execute(
            "SELECT issue_type, is_blocking FROM quality_issues"
        ).fetchone()
        page = connection.execute(
            "SELECT active_typeset_artifact_id FROM pages WHERE page_id = ?",
            ("page-missing-translation",),
        ).fetchone()

    assert issue["issue_type"] == "missing_active_translation_pointer"
    assert issue["is_blocking"] == 1
    assert page["active_typeset_artifact_id"] is None


def test_registered_but_unaccepted_typeset_artifact_is_not_readiness_effective(
    tmp_path,
):
    project, repositories = _ready_project(tmp_path)
    artifact_service = _artifact_service(project, repositories)
    source_png = tmp_path / "page.png"
    source_png.write_bytes(_tiny_png(width=16, height=16))
    repositories.content_state.create_page(
        page_id="page-unaccepted-artifact",
        batch_id="batch-unaccepted-artifact",
        original_artifact_id="artifact-original",
        status="uploaded",
    )

    artifact = artifact_service.register_stage_image(
        source_path=source_png,
        batch_id="batch-unaccepted-artifact",
        page_id="page-unaccepted-artifact",
        stage="typesetting",
        artifact_type="typeset_image",
        retention_class="active_result",
        safety=ArtifactSafetyMetadata(
            may_contain_original_image=True,
            may_contain_translation=True,
        ),
    )
    readiness = repositories.readiness.get_page_export_readiness(
        "page-unaccepted-artifact"
    )
    page = repositories.content_state.get_page("page-unaccepted-artifact")

    assert artifact.storage_state == "present"
    assert page.active_typeset_artifact_id is None
    assert readiness.active_typeset_artifact_id is None


def test_open_blocking_issue_prevents_pure_export_readiness(tmp_path):
    project, repositories = _ready_project(tmp_path)
    artifact_service = _artifact_service(project, repositories)
    import_service = ImportPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
    )
    process_service = ProcessPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        provider=FakeProvider.happy_path(),
    )
    source_png = tmp_path / "incoming" / "blocker.png"
    source_png.parent.mkdir()
    source_png.write_bytes(_tiny_png(width=32, height=24))
    imported = import_service.import_page(
        ImportPageCommand(
            source_path=source_png,
            batch_id="batch-open-blocker",
            batch_name="Open Blocker",
            page_id="page-open-blocker",
            page_index=1,
        )
    )
    process_service.process_page(ProcessPageCommand(page_id=imported.page.page_id))
    with _project_connection(project.project_db_path) as connection:
        connection.execute(
            """
            INSERT INTO quality_issues (
                issue_id,
                project_id,
                issue_type,
                status,
                is_blocking,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                "issue-manual-open-blocker",
                project.project_id,
                "manual_blocker",
                "open",
                1,
            ),
        )
    repositories.workflow_execution.create_task(
        task_id="task-export-check-with-blocker",
        target_type="page",
        target_id="page-open-blocker",
        task_type="process_page",
        status="queued",
        current_stage="export_check",
    )

    result = _workflow_engine(repositories, artifact_service).run_task(
        "task-export-check-with-blocker"
    )

    assert result.task_status == "blocked"
    assert result.page_status == "blocked"
    with _project_connection(project.project_db_path) as connection:
        export_artifacts = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM processing_artifacts
            WHERE artifact_type IN ('export_image', 'export_zip', 'manifest')
            """
        ).fetchone()["count"]

    assert export_artifacts == 0


def test_active_non_typeset_artifact_does_not_satisfy_export_readiness(tmp_path):
    project, repositories = _ready_project(tmp_path)
    artifact_service = _artifact_service(project, repositories)
    source_png = tmp_path / "page.png"
    source_png.write_bytes(_tiny_png(width=16, height=16))
    repositories.content_state.create_page(
        page_id="page-wrong-artifact-type",
        batch_id="batch-wrong-artifact-type",
        original_artifact_id="artifact-original",
        status="uploaded",
    )
    repositories.content_state.create_text_block(
        text_block_id="tb-wrong-artifact-type",
        page_id="page-wrong-artifact-type",
        reading_order=1,
        ocr_status="pending",
        translation_status="pending",
    )
    cleaned_artifact = artifact_service.register_stage_image(
        source_path=source_png,
        batch_id="batch-wrong-artifact-type",
        page_id="page-wrong-artifact-type",
        stage="cleaning",
        artifact_type="cleaned_image",
        retention_class="active_result",
        safety=ArtifactSafetyMetadata(may_contain_original_image=True),
    )
    with _project_connection(project.project_db_path) as connection:
        connection.execute(
            """
            INSERT INTO ocr_results (
                ocr_result_id,
                project_id,
                text_block_id,
                version_number,
                source_type,
                source_text,
                source_text_hash,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                "ocr-wrong-artifact-type",
                project.project_id,
                "tb-wrong-artifact-type",
                1,
                "workflow_acceptance",
                "source",
                "source-hash",
            ),
        )
        connection.execute(
            """
            INSERT INTO translation_results (
                translation_result_id,
                project_id,
                text_block_id,
                version_number,
                source_type,
                source_ocr_result_id,
                source_text_hash,
                translation_text,
                translation_text_hash,
                glossary_version_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                "translation-wrong-artifact-type",
                project.project_id,
                "tb-wrong-artifact-type",
                1,
                "workflow_acceptance",
                "ocr-wrong-artifact-type",
                "source-hash",
                "target",
                "target-hash",
                "glossary-empty-v1",
            ),
        )
        connection.execute(
            """
            UPDATE text_blocks
            SET active_ocr_result_id = ?,
                active_translation_result_id = ?,
                detection_status = ?,
                ocr_status = ?,
                translation_status = ?,
                translation_check_status = ?,
                cleaning_status = ?,
                typesetting_status = ?
            WHERE text_block_id = ?
            """,
            (
                "ocr-wrong-artifact-type",
                "translation-wrong-artifact-type",
                "done",
                "done",
                "done",
                "done",
                "done",
                "done",
                "tb-wrong-artifact-type",
            ),
        )
        connection.execute(
            """
            UPDATE pages
            SET active_typeset_artifact_id = ?
            WHERE page_id = ?
            """,
            (cleaned_artifact.artifact_id, "page-wrong-artifact-type"),
        )
    repositories.workflow_execution.create_task(
        task_id="task-wrong-artifact-type",
        target_type="page",
        target_id="page-wrong-artifact-type",
        task_type="process_page",
        status="queued",
        current_stage="export_check",
    )

    result = _workflow_engine(repositories, artifact_service).run_task(
        "task-wrong-artifact-type"
    )

    assert result.task_status == "blocked"
    assert result.page_status == "blocked"


def _ready_project(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(
        name="Workflow Happy Path",
        source_language="ja",
        target_language="zh-Hans",
    )
    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.READY
    return created, opened.repositories()


def _artifact_service(project, repositories):
    return ArtifactService(
        project_id=project.project_id,
        project_workspace_path=project.workspace_path,
        artifact_repository=repositories.artifact_metadata,
    )


def _workflow_engine(repositories, artifact_service):
    provider = FakeProvider.happy_path()
    return WorkflowLoopEngine(
        repositories=repositories,
        artifact_service=artifact_service,
        stage_executor=StageExecutor(
            attempt_recorder=repositories.workflow_execution,
            evidence_writer=repositories.stage_evidence_writer,
            artifact_service=artifact_service,
        ),
        provider=provider,
    )


def _project_connection(path: Path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


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
