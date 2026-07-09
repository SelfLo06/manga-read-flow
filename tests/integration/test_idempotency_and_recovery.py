from __future__ import annotations

import sqlite3
import struct
import zlib
from hashlib import sha256
import importlib
import inspect

from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService
from manga_read_flow.application.process_page import ProcessPageCommand, ProcessPageService
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.domain.artifacts import ArtifactSafetyMetadata
from manga_read_flow.persistence.project_store import AppStore, ProjectOpenStatus
from manga_read_flow.providers.fake import FakeProvider
from manga_read_flow.workflow.engine import WorkflowLoopEngine
from manga_read_flow.workflow.stage_executor import StageExecutor


def test_unchanged_page_rerun_reuses_provider_outputs_without_new_result_rows(
    tmp_path,
):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)
    provider = FakeProvider.happy_path()
    process_service = ProcessPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        provider=provider,
    )

    first = process_service.process_page(ProcessPageCommand(page_id=page_id))
    before = _page_reuse_snapshot(project.project_db_path, page_id)

    second = process_service.process_page(ProcessPageCommand(page_id=page_id))
    after = _page_reuse_snapshot(project.project_db_path, page_id)

    assert first.task_status == "succeeded"
    assert second.task_status == "succeeded"
    assert provider.call_count("ocr") == 1
    assert provider.call_count("translation") == 1
    assert provider.call_count("cleaning") == 1
    assert provider.call_count("typesetting") == 1
    assert after["active_ocr_result_ids"] == before["active_ocr_result_ids"]
    assert after["active_translation_result_ids"] == before[
        "active_translation_result_ids"
    ]
    assert after["active_cleaned_artifact_id"] == before["active_cleaned_artifact_id"]
    assert after["active_typeset_artifact_id"] == before["active_typeset_artifact_id"]
    assert after["ocr_result_count"] == before["ocr_result_count"]
    assert after["translation_result_count"] == before["translation_result_count"]
    assert after["cleaned_artifact_count"] == before["cleaned_artifact_count"]
    assert after["typeset_artifact_count"] == before["typeset_artifact_count"]
    assert after["export_artifact_count"] == 0
    assert not after["export_record_table_exists"]
    assert "reuse_cached_result" in after["decision_types"]
    assert after["reused_attempt_count"] > 0


def test_dependency_hash_change_rerun_does_not_reuse_stale_outputs(tmp_path):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)
    provider = FakeProvider.happy_path()
    process_service = ProcessPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        provider=provider,
    )
    first = process_service.process_page(ProcessPageCommand(page_id=page_id))
    before = _page_reuse_snapshot(project.project_db_path, page_id)

    with _connection(project.project_db_path) as connection:
        connection.execute(
            """
            UPDATE text_blocks
            SET geometry_hash = ?
            WHERE page_id = ? AND reading_order = 1
            """,
            ("changed-geometry-hash", page_id),
        )

    second = process_service.process_page(ProcessPageCommand(page_id=page_id))
    after = _page_reuse_snapshot(project.project_db_path, page_id)

    assert first.task_status == "succeeded"
    assert second.task_status == "succeeded"
    assert provider.call_count("ocr") == 2
    assert provider.call_count("translation") == 2
    assert provider.call_count("cleaning") == 2
    assert provider.call_count("typesetting") == 2
    assert after["active_ocr_result_ids"] != before["active_ocr_result_ids"]
    assert after["active_translation_result_ids"] != before[
        "active_translation_result_ids"
    ]
    assert after["active_cleaned_artifact_id"] != before["active_cleaned_artifact_id"]
    assert after["active_typeset_artifact_id"] != before["active_typeset_artifact_id"]
    assert after["ocr_result_count"] == before["ocr_result_count"] + 2
    assert after["translation_result_count"] == before["translation_result_count"] + 2
    assert after["cleaned_artifact_count"] == before["cleaned_artifact_count"] + 1
    assert after["typeset_artifact_count"] == before["typeset_artifact_count"] + 1


def test_recovery_after_ocr_acceptance_resumes_translation_without_page_status_truth(
    tmp_path,
):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)
    _seed_accepted_ocr_only(project.project_db_path, project.project_id, page_id)
    repositories.workflow_execution.create_task(
        task_id="task-recover-after-ocr",
        target_type="page",
        target_id=page_id,
        task_type="process_page",
        status="queued",
        current_stage="translation",
    )
    provider = FakeProvider.happy_path()

    result = _engine(repositories, artifact_service, provider).run_task(
        "task-recover-after-ocr"
    )

    assert result.task_status == "succeeded"
    assert provider.call_count("ocr") == 0
    assert provider.call_count("translation") == 1
    with _connection(project.project_db_path) as connection:
        page = connection.execute(
            "SELECT status FROM pages WHERE page_id = ?",
            (page_id,),
        ).fetchone()
        ocr_results = connection.execute(
            "SELECT COUNT(*) AS count FROM ocr_results"
        ).fetchone()["count"]
        translation_results = connection.execute(
            "SELECT COUNT(*) AS count FROM translation_results"
        ).fetchone()["count"]

    assert page["status"] == "ready_for_export"
    assert ocr_results == 2
    assert translation_results == 2


def test_registered_but_unselected_typeset_artifact_is_not_selected_by_timestamp(
    tmp_path,
):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)
    ProcessPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        provider=FakeProvider.happy_path(),
    ).process_page(ProcessPageCommand(page_id=page_id))
    unselected_source = tmp_path / "unselected-typeset.png"
    unselected_source.write_bytes(_tiny_png(width=16, height=16))
    unselected_artifact = artifact_service.register_stage_image(
        source_path=unselected_source,
        batch_id="batch-slice-07",
        page_id=page_id,
        stage="typesetting",
        artifact_type="typeset_image",
        retention_class="active_result",
        safety=_typeset_safety(),
    )
    before = _page_reuse_snapshot(project.project_db_path, page_id)
    with _connection(project.project_db_path) as connection:
        connection.execute(
            """
            UPDATE pages
            SET active_typeset_artifact_id = NULL,
                status = ?
            WHERE page_id = ?
            """,
            ("recovering", page_id),
        )
        connection.execute(
            """
            UPDATE text_blocks
            SET typesetting_status = ?
            WHERE page_id = ?
            """,
            ("pending", page_id),
        )
    repositories.workflow_execution.create_task(
        task_id="task-unselected-typeset",
        target_type="page",
        target_id=page_id,
        task_type="process_page",
        status="queued",
        current_stage="typesetting",
    )
    provider = FakeProvider.happy_path()

    result = _engine(repositories, artifact_service, provider).run_task(
        "task-unselected-typeset"
    )

    assert result.task_status == "succeeded"
    assert provider.call_count("typesetting") == 1
    with _connection(project.project_db_path) as connection:
        page = connection.execute(
            "SELECT active_typeset_artifact_id FROM pages WHERE page_id = ?",
            (page_id,),
        ).fetchone()
        unselected = connection.execute(
            """
            SELECT storage_state
            FROM processing_artifacts
            WHERE artifact_id = ?
            """,
            (unselected_artifact.artifact_id,),
        ).fetchone()

    assert page["active_typeset_artifact_id"]
    assert page["active_typeset_artifact_id"] != before["active_typeset_artifact_id"]
    assert page["active_typeset_artifact_id"] != unselected_artifact.artifact_id
    assert unselected["storage_state"] == "present"


def test_missing_active_typeset_artifact_is_marked_missing_and_blocks_readiness(
    tmp_path,
):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)
    ProcessPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        provider=FakeProvider.happy_path(),
    ).process_page(ProcessPageCommand(page_id=page_id))
    active_typeset_id = _active_page_artifact_id(
        project.project_db_path,
        page_id,
        "active_typeset_artifact_id",
    )
    _delete_artifact_file(project.workspace_path, project.project_db_path, active_typeset_id)
    repositories.workflow_execution.create_task(
        task_id="task-missing-typeset",
        target_type="page",
        target_id=page_id,
        task_type="process_page",
        status="queued",
        current_stage="export_check",
    )

    result = _engine(
        repositories,
        artifact_service,
        FakeProvider.happy_path(),
    ).run_task("task-missing-typeset")

    assert result.task_status == "blocked"
    assert result.page_status == "blocked"
    with _connection(project.project_db_path) as connection:
        artifact = connection.execute(
            """
            SELECT storage_state
            FROM processing_artifacts
            WHERE artifact_id = ?
            """,
            (active_typeset_id,),
        ).fetchone()
        decision = _latest_decision(connection)
        issue = connection.execute(
            "SELECT issue_type, is_blocking FROM quality_issues ORDER BY created_at DESC"
        ).fetchone()
        export_artifacts = _export_artifact_count(connection)

    assert artifact["storage_state"] == "missing"
    assert decision["decision_type"] == "block"
    assert issue["issue_type"] == "export_readiness_blocked"
    assert issue["is_blocking"] == 1
    assert export_artifacts == 0


def test_missing_active_cleaned_artifact_is_marked_missing_and_rebuilt(tmp_path):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)
    ProcessPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        provider=FakeProvider.happy_path(),
    ).process_page(ProcessPageCommand(page_id=page_id))
    old_cleaned_id = _active_page_artifact_id(
        project.project_db_path,
        page_id,
        "active_cleaned_artifact_id",
    )
    _delete_artifact_file(project.workspace_path, project.project_db_path, old_cleaned_id)
    repositories.workflow_execution.create_task(
        task_id="task-missing-cleaned",
        target_type="page",
        target_id=page_id,
        task_type="process_page",
        status="queued",
        current_stage="cleaning",
    )
    provider = FakeProvider.happy_path()

    result = _engine(repositories, artifact_service, provider).run_task(
        "task-missing-cleaned"
    )

    assert result.task_status == "succeeded"
    assert provider.call_count("cleaning") == 1
    assert provider.call_count("typesetting") == 1
    with _connection(project.project_db_path) as connection:
        page = connection.execute(
            """
            SELECT active_cleaned_artifact_id, active_typeset_artifact_id
            FROM pages
            WHERE page_id = ?
            """,
            (page_id,),
        ).fetchone()
        old_cleaned = connection.execute(
            """
            SELECT storage_state
            FROM processing_artifacts
            WHERE artifact_id = ?
            """,
            (old_cleaned_id,),
        ).fetchone()
        cleaning_decision = connection.execute(
            """
            SELECT decision_type
            FROM workflow_decisions
            WHERE stage = 'cleaning'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert old_cleaned["storage_state"] == "missing"
    assert page["active_cleaned_artifact_id"] != old_cleaned_id
    assert page["active_typeset_artifact_id"]
    assert cleaning_decision["decision_type"] == "continue"


def test_open_blocking_issue_during_recovery_blocks_pure_readiness(tmp_path):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)
    ProcessPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
        provider=FakeProvider.happy_path(),
    ).process_page(ProcessPageCommand(page_id=page_id))
    with _connection(project.project_db_path) as connection:
        connection.execute(
            """
            INSERT INTO quality_issues (
                issue_id,
                project_id,
                target_type,
                target_id,
                page_id,
                discovered_stage,
                root_stage,
                issue_type,
                error_code,
                severity,
                status,
                is_blocking,
                message_key,
                suggested_action_key,
                dedupe_key,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                "issue-recovery-blocker",
                project.project_id,
                "page",
                page_id,
                page_id,
                "export_check",
                "workflow",
                "manual_recovery_blocker",
                "manual_recovery_blocker",
                "blocking",
                "open",
                1,
                "recovery.blocked",
                "action.review_blocker",
                f"{page_id}:recovery-blocker",
            ),
        )
    repositories.workflow_execution.create_task(
        task_id="task-open-blocker-recovery",
        target_type="page",
        target_id=page_id,
        task_type="process_page",
        status="queued",
        current_stage="export_check",
    )

    result = _engine(
        repositories,
        artifact_service,
        FakeProvider.happy_path(),
    ).run_task("task-open-blocker-recovery")

    assert result.task_status == "blocked"
    assert result.page_status == "blocked"
    with _connection(project.project_db_path) as connection:
        decision = _latest_decision(connection)
        links = connection.execute(
            """
            SELECT issue_id
            FROM workflow_decision_issues
            WHERE decision_id = ?
            """,
            (decision["decision_id"],),
        ).fetchall()

    assert decision["decision_type"] == "block"
    assert {row["issue_id"] for row in links} == {"issue-recovery-blocker"}


def test_locked_translation_is_not_replaced_by_automatic_reuse_or_rerun(tmp_path):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)
    _seed_accepted_ocr_only(project.project_db_path, project.project_id, page_id)
    locked_ids = _seed_locked_translations(
        project.project_db_path,
        project.project_id,
        page_id,
    )
    repositories.workflow_execution.create_task(
        task_id="task-locked-translation",
        target_type="page",
        target_id=page_id,
        task_type="process_page",
        status="queued",
        current_stage="translation",
    )
    provider = FakeProvider.happy_path()

    result = _engine(repositories, artifact_service, provider).run_task(
        "task-locked-translation"
    )

    assert result.task_status == "succeeded"
    assert provider.call_count("translation") == 0
    with _connection(project.project_db_path) as connection:
        active_locked = connection.execute(
            """
            SELECT active_translation_result_id, locked_translation_result_id
            FROM text_blocks
            WHERE page_id = ?
            ORDER BY reading_order
            """,
            (page_id,),
        ).fetchall()
        translation_count = connection.execute(
            "SELECT COUNT(*) AS count FROM translation_results"
        ).fetchone()["count"]
        preserve_decision = connection.execute(
            """
            SELECT decision_type, reason_code
            FROM workflow_decisions
            WHERE stage = 'translation'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert tuple(row["active_translation_result_id"] for row in active_locked) == locked_ids
    assert tuple(row["locked_translation_result_id"] for row in active_locked) == locked_ids
    assert translation_count == len(locked_ids)
    assert preserve_decision["decision_type"] == "reuse_cached_result"
    assert preserve_decision["reason_code"] == "locked_translation_preserved"


def test_reuse_and_recovery_boundaries_do_not_move_into_provider_stage_or_artifacts():
    provider_source = inspect.getsource(
        importlib.import_module("manga_read_flow.providers.fake")
    )
    stage_executor_source = inspect.getsource(
        importlib.import_module("manga_read_flow.workflow.stage_executor")
    )
    artifact_service_source = inspect.getsource(
        importlib.import_module("manga_read_flow.artifacts.service")
    )

    assert "reuse_cached_result" not in provider_source
    assert "reused_cached" not in provider_source
    assert "WorkflowDecision" not in provider_source
    assert "quality_issues" not in provider_source
    assert "reuse_cached_result" not in stage_executor_source
    assert "WorkflowDecision" not in stage_executor_source
    assert "quality_issues" not in stage_executor_source
    for workflow_outcome in (
        "retry_same_stage",
        "fallback_provider",
        "pause_for_user",
        "ready_for_export",
        "reuse_cached_result",
    ):
        assert workflow_outcome not in artifact_service_source


def _ready_imported_page(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Slice 07",
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
    source_png = tmp_path / "incoming" / "page.png"
    source_png.parent.mkdir(parents=True, exist_ok=True)
    source_png.write_bytes(_tiny_png(width=32, height=24))
    imported = ImportPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifact_service,
    ).import_page(
        ImportPageCommand(
            source_path=source_png,
            batch_id="batch-slice-07",
            batch_name="Slice 07",
            page_id="page-slice-07",
            page_index=1,
        )
    )
    return project, repositories, artifact_service, imported.page.page_id


def _engine(repositories, artifact_service, provider: FakeProvider) -> WorkflowLoopEngine:
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


def _typeset_safety() -> ArtifactSafetyMetadata:
    return ArtifactSafetyMetadata(
        may_contain_original_image=True,
        may_contain_translation=True,
    )


def _seed_accepted_ocr_only(project_db_path, project_id: str, page_id: str) -> None:
    with _connection(project_db_path) as connection:
        connection.execute(
            """
            UPDATE pages
            SET status = ?
            WHERE page_id = ?
            """,
            ("blocked", page_id),
        )
        for index in (1, 2):
            text_block_id = f"tb-{page_id}-{index:03d}"
            geometry_hash = f"geometry-{index}"
            ocr_result_id = f"ocr-seeded-{index}"
            connection.execute(
                """
                INSERT INTO text_blocks (
                    text_block_id,
                    project_id,
                    page_id,
                    reading_order,
                    detection_status,
                    bbox_json,
                    polygon_json,
                    geometry_hash,
                    detection_provider,
                    detection_confidence,
                    active_ocr_result_id,
                    active_translation_result_id,
                    ocr_status,
                    translation_status,
                    translation_check_status,
                    cleaning_status,
                    typesetting_status,
                    review_status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    text_block_id,
                    project_id,
                    page_id,
                    index,
                    "done",
                    "{}",
                    "{}",
                    geometry_hash,
                    "FakeProvider",
                    0.9,
                    "done",
                    "pending",
                    "pending",
                    "pending",
                    "pending",
                    "pending",
                ),
            )
            source_text = f"fake_source_{index}"
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
                    provider_name,
                    model_id,
                    geometry_hash,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    ocr_result_id,
                    project_id,
                    text_block_id,
                    1,
                    "workflow_acceptance",
                    source_text,
                    _hash_text(source_text),
                    "FakeProvider",
                    "fake-model-v0",
                    geometry_hash,
                ),
            )
            connection.execute(
                """
                UPDATE text_blocks
                SET active_ocr_result_id = ?
                WHERE text_block_id = ?
                """,
                (ocr_result_id, text_block_id),
            )


def _seed_locked_translations(
    project_db_path,
    project_id: str,
    page_id: str,
) -> tuple[str, ...]:
    locked_ids: list[str] = []
    with _connection(project_db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                tb.text_block_id,
                tb.active_ocr_result_id,
                ocr.source_text_hash
            FROM text_blocks tb
            JOIN ocr_results ocr
                ON ocr.project_id = tb.project_id
                AND ocr.ocr_result_id = tb.active_ocr_result_id
            WHERE tb.page_id = ?
            ORDER BY tb.reading_order
            """,
            (page_id,),
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            translation_id = f"translation-locked-{index}"
            locked_ids.append(translation_id)
            translation_text = f"locked_translation_{index}"
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
                    translation_id,
                    project_id,
                    row["text_block_id"],
                    1,
                    "user_edit",
                    row["active_ocr_result_id"],
                    row["source_text_hash"],
                    translation_text,
                    _hash_text(translation_text),
                    "glossary-empty-v1",
                ),
            )
            connection.execute(
                """
                UPDATE text_blocks
                SET active_translation_result_id = ?,
                    locked_translation_result_id = ?,
                    translation_status = ?
                WHERE text_block_id = ?
                """,
                (
                    translation_id,
                    translation_id,
                    "done",
                    row["text_block_id"],
                ),
            )
    return tuple(locked_ids)


def _page_reuse_snapshot(project_db_path, page_id: str) -> dict[str, object]:
    with _connection(project_db_path) as connection:
        page = connection.execute(
            """
            SELECT active_cleaned_artifact_id, active_typeset_artifact_id
            FROM pages
            WHERE page_id = ?
            """,
            (page_id,),
        ).fetchone()
        blocks = connection.execute(
            """
            SELECT active_ocr_result_id, active_translation_result_id
            FROM text_blocks
            WHERE page_id = ?
            ORDER BY reading_order
            """,
            (page_id,),
        ).fetchall()
        artifact_counts = {
            row["artifact_type"]: row["count"]
            for row in connection.execute(
                """
                SELECT artifact_type, COUNT(*) AS count
                FROM processing_artifacts
                GROUP BY artifact_type
                """
            ).fetchall()
        }
        decision_types = {
            row["decision_type"]
            for row in connection.execute(
                "SELECT decision_type FROM workflow_decisions"
            ).fetchall()
        }
        reused_attempt_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM workflow_attempts
            WHERE status = 'reused_cached'
            """
        ).fetchone()["count"]
        export_record_table_exists = (
            connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = 'export_records'
                """
            ).fetchone()
            is not None
        )
        ocr_result_count = connection.execute(
            "SELECT COUNT(*) AS count FROM ocr_results"
        ).fetchone()["count"]
        translation_result_count = connection.execute(
            "SELECT COUNT(*) AS count FROM translation_results"
        ).fetchone()["count"]

    return {
        "active_ocr_result_ids": tuple(row["active_ocr_result_id"] for row in blocks),
        "active_translation_result_ids": tuple(
            row["active_translation_result_id"] for row in blocks
        ),
        "active_cleaned_artifact_id": page["active_cleaned_artifact_id"],
        "active_typeset_artifact_id": page["active_typeset_artifact_id"],
        "ocr_result_count": ocr_result_count,
        "translation_result_count": translation_result_count,
        "cleaned_artifact_count": artifact_counts.get("cleaned_image", 0),
        "typeset_artifact_count": artifact_counts.get("typeset_image", 0),
        "export_artifact_count": sum(
            artifact_counts.get(artifact_type, 0)
            for artifact_type in ("export_image", "export_zip", "manifest")
        ),
        "decision_types": decision_types,
        "reused_attempt_count": reused_attempt_count,
        "export_record_table_exists": export_record_table_exists,
    }


def _active_page_artifact_id(project_db_path, page_id: str, pointer_name: str) -> str:
    with _connection(project_db_path) as connection:
        row = connection.execute(
            f"SELECT {pointer_name} AS artifact_id FROM pages WHERE page_id = ?",
            (page_id,),
        ).fetchone()
    assert row["artifact_id"]
    return row["artifact_id"]


def _delete_artifact_file(workspace_path, project_db_path, artifact_id: str) -> None:
    with _connection(project_db_path) as connection:
        artifact = connection.execute(
            """
            SELECT relative_path
            FROM processing_artifacts
            WHERE artifact_id = ?
            """,
            (artifact_id,),
        ).fetchone()
    path = workspace_path / artifact["relative_path"]
    assert path.is_file()
    path.unlink()


def _latest_decision(connection):
    return connection.execute(
        """
        SELECT *
        FROM workflow_decisions
        ORDER BY created_at DESC, decision_id DESC
        LIMIT 1
        """
    ).fetchone()


def _export_artifact_count(connection) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM processing_artifacts
            WHERE artifact_type IN ('export_image', 'export_zip', 'manifest')
            """
        ).fetchone()["count"]
    )


def _connection(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


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
