from __future__ import annotations

from dataclasses import fields
from hashlib import sha256
import importlib
import inspect
import json
import sqlite3
import struct
import zlib

from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.persistence.project_store import AppStore, ProjectOpenStatus
from manga_read_flow.providers.fake import FakeProvider
from manga_read_flow.quality import QualityCheckInput, QualityCheckService
from manga_read_flow.workflow.engine import WorkflowLoopEngine
from manga_read_flow.workflow.stage_executor import StageExecutor


def test_invalid_translation_persists_blocking_quality_issue_and_decision_link(
    tmp_path,
):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)

    result = _run_page_workflow(
        repositories,
        artifact_service,
        page_id=page_id,
        fake_mode="translation_invalid_json",
        allow_warning_export=False,
    )

    assert result.task_status == "blocked"
    assert result.page_status == "blocked"
    with _connection(project.project_db_path) as connection:
        issue = _single_issue(connection)
        decision = _latest_decision(connection)
        links = _decision_issue_links(connection)
        translation_results = _translation_results(connection)

    assert issue["target_type"] == "page"
    assert issue["target_id"] == page_id
    assert issue["discovered_stage"] == "translation"
    assert issue["root_stage"] == "translation"
    assert issue["issue_type"] == "stage_output_invalid"
    assert issue["error_code"] == "translation_invalid_json"
    assert issue["severity"] == "error"
    assert issue["is_blocking"] == 1
    assert issue["status"] == "open"
    assert issue["suggested_action_key"] == "action.retry_or_manual_translate"
    assert issue["related_attempt_id"]
    assert issue["related_tool_run_id"]
    assert issue["dedupe_key"]
    assert decision["stage"] == "translation"
    assert decision["decision_type"] in {"block", "pause_for_user"}
    assert links == [(decision["decision_id"], issue["issue_id"], "caused_by")]
    assert translation_results == []


def test_partial_translation_accepts_valid_blocks_and_issues_missing_block(
    tmp_path,
):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)

    result = _run_page_workflow(
        repositories,
        artifact_service,
        page_id=page_id,
        fake_mode="translation_partial",
        allow_warning_export=False,
    )

    assert result.task_status == "blocked"
    assert result.page_status == "blocked"
    with _connection(project.project_db_path) as connection:
        issues = _issues(connection)
        translations = _translation_results(connection)
        blocks = connection.execute(
            """
            SELECT text_block_id, active_translation_result_id, translation_status
            FROM text_blocks
            WHERE page_id = ?
            ORDER BY reading_order
            """,
            (page_id,),
        ).fetchall()

    assert len(translations) == 1
    assert translations[0]["translation_text"] == "fake_translation_1"
    assert blocks[0]["active_translation_result_id"] == translations[0]["translation_result_id"]
    assert blocks[0]["translation_status"] == "done"
    assert blocks[1]["active_translation_result_id"] is None
    assert blocks[1]["translation_status"] == "blocked"
    assert len(issues) == 1
    assert issues[0]["target_type"] == "text_block"
    assert issues[0]["target_id"] == blocks[1]["text_block_id"]
    assert issues[0]["discovered_stage"] == "translation_check"
    assert issues[0]["root_stage"] == "translation"
    assert issues[0]["issue_type"] == "translation_missing_block"
    assert issues[0]["error_code"] == "translation_missing_text_block"
    assert issues[0]["is_blocking"] == 1


def test_provider_refusal_is_first_class_workflow_evidence_without_evasion(
    tmp_path,
):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)

    result = _run_page_workflow(
        repositories,
        artifact_service,
        page_id=page_id,
        fake_mode="translation_refusal",
        allow_warning_export=False,
    )

    assert result.task_status == "blocked"
    with _connection(project.project_db_path) as connection:
        issue = _single_issue(connection)
        decision = _latest_decision(connection)
        links = _decision_issue_links(connection)
        refused_attempts = connection.execute(
            """
            SELECT attempt_id, status, error_code, sanitized_message
            FROM workflow_attempts
            WHERE stage = 'translation'
            ORDER BY attempt_number
            """
        ).fetchall()
        tool_logs = connection.execute(
            """
            SELECT status, error_code, error_class, is_provider_refusal, sanitized_message
            FROM tool_run_logs
            WHERE stage = 'translation'
            """
        ).fetchall()
        db_text = project.project_db_path.read_text(errors="ignore").lower()

    assert len(refused_attempts) == 1
    assert refused_attempts[0]["status"] == "refused"
    assert refused_attempts[0]["error_code"] == "translation_provider_refused"
    assert len(tool_logs) == 1
    assert tool_logs[0]["status"] == "refused"
    assert tool_logs[0]["is_provider_refusal"] == 1
    assert tool_logs[0]["error_code"] == "translation_provider_refused"
    assert issue["issue_type"] == "provider_refusal"
    assert issue["root_stage"] == "provider_policy"
    assert issue["message_key"] == "provider.refused.translation"
    assert issue["suggested_action_key"] == "action.use_allowed_alternative_or_manual"
    assert decision["decision_type"] in {"block", "pause_for_user"}
    assert links == [(decision["decision_id"], issue["issue_id"], "caused_by")]
    for forbidden in ("bypass", "evasion", "jailbreak", "obfuscation"):
        assert forbidden not in db_text


def test_cleaning_skip_stays_visible_and_cannot_be_pure_ready(tmp_path):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)

    result = _run_page_workflow(
        repositories,
        artifact_service,
        page_id=page_id,
        fake_mode="cleaning_skip",
        allow_warning_export=False,
    )

    assert result.task_status == "blocked"
    assert result.page_status == "blocked"
    with _connection(project.project_db_path) as connection:
        issue = _single_issue(connection)
        decisions = _decisions(connection)
        export_artifacts = _export_artifact_count(connection)

    assert issue["issue_type"] == "cleaning_skipped_complex_region"
    assert issue["severity"] == "warning"
    assert issue["is_blocking"] == 0
    assert issue["status"] in {"open", "accepted_warning"}
    assert issue["suggested_action_key"] == "action.review_skip_or_retry_cleaning"
    assert "finish_ready_for_export" not in {row["decision_type"] for row in decisions}
    assert export_artifacts == 0


def test_warning_readiness_requires_processing_profile_policy(tmp_path):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)

    result = _run_page_workflow(
        repositories,
        artifact_service,
        page_id=page_id,
        fake_mode="cleaning_skip",
        allow_warning_export=True,
    )

    assert result.task_status == "succeeded_with_warnings"
    assert result.page_status == "ready_for_export_with_warnings"
    assert result.final_decision == "finish_ready_for_export_with_warnings"
    with _connection(project.project_db_path) as connection:
        issue = _single_issue(connection)
        decision = _latest_decision(connection)
        artifacts = _artifact_types(connection)

    assert issue["issue_type"] == "cleaning_skipped_complex_region"
    assert issue["is_blocking"] == 0
    assert decision["decision_type"] == "finish_ready_for_export_with_warnings"
    assert {"export_image", "export_zip", "manifest"}.isdisjoint(artifacts)


def test_typesetting_overflow_blocks_or_warning_readies_by_policy(tmp_path):
    blocked_project, blocked_repositories, blocked_artifacts, blocked_page_id = (
        _ready_imported_page(tmp_path / "blocked")
    )
    blocked = _run_page_workflow(
        blocked_repositories,
        blocked_artifacts,
        page_id=blocked_page_id,
        fake_mode="typesetting_overflow",
        allow_warning_export=False,
    )
    assert blocked.task_status == "blocked"
    assert blocked.page_status == "blocked"
    with _connection(blocked_project.project_db_path) as connection:
        blocked_issue = _single_issue(connection)
        blocked_decisions = _decisions(connection)

    assert blocked_issue["issue_type"] == "typesetting_overflow"
    assert blocked_issue["error_code"] == "typeset_overflow"
    assert blocked_issue["severity"] == "warning"
    assert "finish_ready_for_export" not in {
        row["decision_type"] for row in blocked_decisions
    }

    warning_project, warning_repositories, warning_artifacts, warning_page_id = (
        _ready_imported_page(tmp_path / "warning")
    )
    warning = _run_page_workflow(
        warning_repositories,
        warning_artifacts,
        page_id=warning_page_id,
        fake_mode="typesetting_overflow",
        allow_warning_export=True,
    )

    assert warning.task_status == "succeeded_with_warnings"
    assert warning.page_status == "ready_for_export_with_warnings"
    with _connection(warning_project.project_db_path) as connection:
        issue = _single_issue(connection)
        page = connection.execute(
            """
            SELECT active_typeset_artifact_id
            FROM pages
            WHERE page_id = ?
            """,
            (warning_page_id,),
        ).fetchone()
        artifact_type = connection.execute(
            """
            SELECT artifact_type
            FROM processing_artifacts
            WHERE artifact_id = ?
            """,
            (page["active_typeset_artifact_id"],),
        ).fetchone()["artifact_type"]

    assert issue["issue_type"] == "typesetting_overflow"
    assert page["active_typeset_artifact_id"]
    assert artifact_type == "typeset_preview_image"


def test_seeded_open_blocking_quality_issue_blocks_pure_readiness(tmp_path):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)
    _run_page_workflow(
        repositories,
        artifact_service,
        page_id=page_id,
        fake_mode="happy_path",
        allow_warning_export=False,
    )
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
                is_blocking,
                status,
                message_key,
                suggested_action_key,
                dedupe_key,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                "issue-seeded-blocker",
                project.project_id,
                "page",
                page_id,
                page_id,
                "export_check",
                "workflow",
                "export_precondition_failed",
                "export_blocked_by_open_issue",
                "blocking",
                1,
                "open",
                "export.blocked_by_open_issue",
                "action.review_warning",
                f"{page_id}:seeded-blocker",
            ),
        )
    repositories.workflow_execution.create_task(
        task_id="task-seeded-blocker",
        target_type="page",
        target_id=page_id,
        task_type="process_page",
        status="queued",
        current_stage="export_check",
        profile_snapshot_id=_ensure_profile_snapshot(
            repositories,
            allow_warning_export=True,
            snapshot_id="profile-seeded-blocker",
        ),
    )

    result = _engine(repositories, artifact_service, "happy_path").run_task(
        "task-seeded-blocker"
    )

    assert result.task_status == "blocked"
    assert result.page_status == "blocked"
    with _connection(project.project_db_path) as connection:
        assert _export_artifact_count(connection) == 0


def test_quality_check_service_is_repository_free_and_state_neutral(tmp_path):
    project, repositories, artifact_service, page_id = _ready_imported_page(tmp_path)
    before_counts = _table_counts(
        project.project_db_path,
        ("quality_issues", "workflow_decisions", "workflow_decision_issues"),
    )
    service = QualityCheckService()
    report = service.check(
        QualityCheckInput(
            stage="translation",
            target_type="page",
            target_id=page_id,
            page_id=page_id,
            provider_outcome="invalid_output",
            error_kind="invalid_output",
            error_code="translation_invalid_json",
            is_provider_refusal=False,
            workflow_attempt_id="attempt-probe",
            tool_run_id="tool-probe",
            input_hash="input-probe",
            config_hash="config-probe",
        )
    )
    after_counts = _table_counts(
        project.project_db_path,
        ("quality_issues", "workflow_decisions", "workflow_decision_issues"),
    )
    module_source = inspect.getsource(importlib.import_module("manga_read_flow.quality"))
    service_fields = {field.name for field in fields(QualityCheckInput)}

    assert report.issue_drafts[0].issue_type == "stage_output_invalid"
    assert before_counts == after_counts
    assert "manga_read_flow.persistence" not in module_source
    assert "sqlite3" not in module_source
    assert "repository" not in module_source.lower()
    assert "workflow_decision" not in service_fields


def test_provider_and_stage_executor_do_not_create_issues_or_decisions():
    provider_source = inspect.getsource(importlib.import_module("manga_read_flow.providers.fake"))
    stage_executor_source = inspect.getsource(
        importlib.import_module("manga_read_flow.workflow.stage_executor")
    )

    assert "QualityIssue" not in provider_source
    assert "WorkflowDecision" not in provider_source
    assert "quality_issues" not in provider_source
    assert "workflow_decisions" not in provider_source
    assert "QualityIssue" not in stage_executor_source
    assert "WorkflowDecision" not in stage_executor_source
    assert "quality_issues" not in stage_executor_source
    assert "workflow_decisions" not in stage_executor_source


def _ready_imported_page(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Quality Issues",
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
            batch_id="batch-quality",
            batch_name="Quality",
            page_id="page-quality",
            page_index=1,
        )
    )
    return project, repositories, artifact_service, imported.page.page_id


def _run_page_workflow(
    repositories,
    artifact_service,
    *,
    page_id: str,
    fake_mode: str,
    allow_warning_export: bool,
):
    snapshot_id = f"profile-{fake_mode}-{int(allow_warning_export)}"
    repositories.workflow_execution.create_task(
        task_id=f"task-{fake_mode}-{int(allow_warning_export)}",
        target_type="page",
        target_id=page_id,
        task_type="process_page",
        status="queued",
        current_stage="detection",
        profile_snapshot_id=_ensure_profile_snapshot(
            repositories,
            allow_warning_export=allow_warning_export,
            snapshot_id=snapshot_id,
        ),
    )
    return _engine(repositories, artifact_service, fake_mode).run_task(
        f"task-{fake_mode}-{int(allow_warning_export)}"
    )


def _ensure_profile_snapshot(
    repositories,
    *,
    allow_warning_export: bool,
    snapshot_id: str,
) -> str:
    settings = {
        "snapshot_schema_version": "slice06.v1",
        "source_profile_id": "fakeprovider_default",
        "source_profile_version": "1",
        "allow_warning_export": allow_warning_export,
        "retry_budgets": {
            "detection": 0,
            "ocr": 0,
            "translation": 0,
            "translation_check": 0,
            "cleaning": 0,
            "typesetting": 0,
            "export_check": 0,
        },
    }
    settings_json = json.dumps(settings, sort_keys=True, separators=(",", ":"))
    settings_hash = sha256(settings_json.encode("utf-8")).hexdigest()
    repositories.workflow_execution.ensure_profile_snapshot(
        profile_snapshot_id=snapshot_id,
        settings_json=settings_json,
        settings_hash=settings_hash,
    )
    return snapshot_id


def _engine(repositories, artifact_service, fake_mode: str) -> WorkflowLoopEngine:
    return WorkflowLoopEngine(
        repositories=repositories,
        artifact_service=artifact_service,
        stage_executor=StageExecutor(
            attempt_recorder=repositories.workflow_execution,
            evidence_writer=repositories.stage_evidence_writer,
            artifact_service=artifact_service,
        ),
        provider=FakeProvider(fake_mode=fake_mode),
    )


def _connection(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _issues(connection):
    return connection.execute(
        """
        SELECT *
        FROM quality_issues
        ORDER BY created_at, issue_id
        """
    ).fetchall()


def _single_issue(connection):
    issues = _issues(connection)
    assert len(issues) == 1
    return issues[0]


def _latest_decision(connection):
    return connection.execute(
        """
        SELECT *
        FROM workflow_decisions
        ORDER BY created_at DESC, decision_id DESC
        LIMIT 1
        """
    ).fetchone()


def _decisions(connection):
    return connection.execute(
        """
        SELECT *
        FROM workflow_decisions
        ORDER BY created_at, decision_id
        """
    ).fetchall()


def _decision_issue_links(connection):
    return [
        (row["decision_id"], row["issue_id"], row["relation_type"])
        for row in connection.execute(
            """
            SELECT decision_id, issue_id, relation_type
            FROM workflow_decision_issues
            ORDER BY created_at, decision_id, issue_id
            """
        ).fetchall()
    ]


def _translation_results(connection):
    return connection.execute(
        """
        SELECT translation_result_id, text_block_id, translation_text
        FROM translation_results
        ORDER BY text_block_id, version_number
        """
    ).fetchall()


def _artifact_types(connection) -> set[str]:
    return {
        row["artifact_type"]
        for row in connection.execute(
            """
            SELECT artifact_type
            FROM processing_artifacts
            """
        ).fetchall()
    }


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


def _table_counts(project_db_path, table_names: tuple[str, ...]) -> dict[str, int]:
    with _connection(project_db_path) as connection:
        return {
            table_name: int(
                connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()[
                    "count"
                ]
            )
            for table_name in table_names
        }


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
