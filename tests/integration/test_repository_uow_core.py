from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from manga_read_flow.persistence.project_store import (
    AppStore,
    ProjectOpenStatus,
    ProjectStoreNotReadyError,
)
from manga_read_flow.persistence.repository_uow_core import (
    AcceptanceCommand,
    AcceptedResult,
    ActivePointerUpdate,
    AttemptEvidence,
    AttemptReservation,
    ExpectedState,
    IssueLifecycleChange,
    StageStatusUpdate,
    TaskProgressUpdate,
    ToolRunOutcome,
    ToolRunStart,
    WorkflowDecisionDraft,
)


def test_project_repositories_expose_named_groups_without_persistence_handles(tmp_path):
    repositories = _ready_repositories(tmp_path)

    required_groups = {
        "identity": "ProjectIdentityRepository",
        "content_state": "ContentStateRepository",
        "result_versions": "ResultVersionRepository",
        "glossary": "GlossaryRepository",
        "workflow_execution": "WorkflowExecutionRepository",
        "quality_issues": "QualityIssueRepository",
        "artifact_metadata": "ArtifactMetadataRepository",
        "readiness": "ReadinessQueryRepository",
        "uow": "ProjectUnitOfWork",
        "stage_evidence_writer": "StageEvidenceWriter",
    }

    for attribute, class_name in required_groups.items():
        group = getattr(repositories, attribute)
        assert type(group).__name__ == class_name
        assert _public_names(group).isdisjoint(
            {"connection", "cursor", "session", "execute", "query"}
        )

    page = repositories.content_state.create_page(
        page_id="page-contract",
        batch_id="batch-contract",
        original_artifact_id="artifact-original",
        status="uploaded",
    )
    block = repositories.content_state.create_text_block(
        text_block_id="tb-contract",
        page_id=page.page_id,
        reading_order=1,
        ocr_status="pending",
        translation_status="pending",
    )
    task = repositories.workflow_execution.create_task(
        task_id="task-contract",
        target_type="page",
        target_id=page.page_id,
        task_type="process_page",
        status="queued",
        current_stage="ocr",
    )

    readiness = repositories.readiness.get_task_readiness(task.task_id)

    assert readiness.task_id == task.task_id
    assert readiness.task_status == "queued"
    assert readiness.current_stage == "ocr"
    assert readiness.page_id == page.page_id
    assert block.active_ocr_result_id is None


def test_project_repository_context_requires_verified_project_readiness(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")

    not_ready = store.open_project("missing-project")

    assert not_ready.status is not ProjectOpenStatus.READY
    with pytest.raises(ProjectStoreNotReadyError):
        not_ready.repositories()


def test_attempt_reservation_uses_expected_task_guards_to_avoid_duplicate_claims(tmp_path):
    repositories = _ready_repositories(tmp_path)
    repositories.content_state.create_page(
        page_id="page-claim",
        batch_id="batch-claim",
        original_artifact_id="artifact-original",
        status="uploaded",
    )
    repositories.workflow_execution.create_task(
        task_id="task-claim",
        target_type="page",
        target_id="page-claim",
        task_type="process_page",
        status="queued",
        current_stage="ocr",
    )

    first_claim = repositories.uow.reserve_attempt(
        AttemptReservation(
            task_id="task-claim",
            attempt_id="attempt-claim-1",
            stage="ocr",
            target_type="page",
            target_id="page-claim",
            expected_task_status="queued",
            expected_current_stage="ocr",
            runner_id="runner-a",
        )
    )
    duplicate_claim = repositories.uow.reserve_attempt(
        AttemptReservation(
            task_id="task-claim",
            attempt_id="attempt-claim-2",
            stage="ocr",
            target_type="page",
            target_id="page-claim",
            expected_task_status="queued",
            expected_current_stage="ocr",
            runner_id="runner-b",
        )
    )

    assert first_claim.committed
    assert first_claim.attempt_id == "attempt-claim-1"
    assert not duplicate_claim.committed
    assert duplicate_claim.reload_required
    assert "task_status" in duplicate_claim.conflict_fields


def test_stage_evidence_writer_is_narrow_and_records_tool_evidence(tmp_path):
    repositories = _ready_repositories(tmp_path)
    _create_running_attempt(repositories)

    writer = repositories.stage_evidence_writer
    started = writer.start_tool_run(
        ToolRunStart(
            tool_run_id="tool-run-1",
            task_id="task-running",
            attempt_id="attempt-running",
            stage="ocr",
            tool_name="fake-ocr",
            tool_version="0.1",
            provider_name="FakeProvider",
            model_id="fake-model",
            input_hash="input-hash",
            config_hash="config-hash",
        )
    )
    outcome = writer.record_tool_outcome(
        ToolRunOutcome(
            tool_run_id=started.tool_run_id,
            status="refused",
            error_code="provider_refusal",
            error_class="provider_policy",
            is_provider_refusal=True,
            sanitized_message="provider declined this request",
        )
    )
    attempt = writer.record_attempt_evidence(
        AttemptEvidence(
            attempt_id="attempt-running",
            provider_name="FakeProvider",
            model_id="fake-model",
            tool_name="fake-ocr",
            status="refused",
            error_code="provider_refusal",
            sanitized_message="provider declined this request",
        )
    )

    assert started.status == "running"
    assert outcome.status == "refused"
    assert outcome.is_provider_refusal
    assert attempt.status == "refused"
    assert attempt.provider_name == "FakeProvider"

    forbidden_operations = {
        "accept",
        "active",
        "quality",
        "decision",
        "retry",
        "stage_completion",
        "complete_stage",
        "result_version",
    }
    public_names = _public_names(writer)

    assert all(
        not any(forbidden in name for forbidden in forbidden_operations)
        for name in public_names
    )


def test_acceptance_transaction_placeholder_commits_expected_shape_and_conflicts(tmp_path):
    repositories = _ready_repositories(tmp_path)
    _create_running_attempt(repositories)

    command = AcceptanceCommand(
        task_id="task-running",
        expected=ExpectedState(
            task_status="running",
            current_stage="ocr",
            active_ocr_result_ids={"tb-running": None},
            active_translation_result_ids={},
            page_artifact_ids={
                "page-running": {
                    "active_cleaned_artifact_id": None,
                    "active_typeset_artifact_id": None,
                }
            },
        ),
        accepted_results=(
            AcceptedResult(
                result_type="ocr",
                result_id="ocr-result-1",
                target_type="text_block",
                target_id="tb-running",
            ),
        ),
        active_pointers=(
            ActivePointerUpdate(
                owner_type="text_block",
                owner_id="tb-running",
                pointer_name="active_ocr_result_id",
                value_id="ocr-result-1",
            ),
        ),
        issue_lifecycle=(
            IssueLifecycleChange(
                issue_id="issue-1",
                action="create",
                status="open",
                issue_type="ocr_low_confidence",
                is_blocking=False,
            ),
        ),
        workflow_decision=WorkflowDecisionDraft(
            decision_id="decision-1",
            attempt_id="attempt-running",
            stage="ocr",
            decision_type="continue",
            reason_code="accepted_ocr",
        ),
        retry_budget_after={"ocr": 1},
        task_progress=TaskProgressUpdate(
            status="running",
            current_stage="translation",
            progress_state="ocr_done",
        ),
        stage_statuses=(
            StageStatusUpdate(
                target_type="text_block",
                target_id="tb-running",
                stage="ocr",
                status="done",
            ),
        ),
    )

    committed = repositories.uow.accept_stage(command)
    stale_pointer_conflict = repositories.uow.accept_stage(
        AcceptanceCommand(
            task_id="task-running",
            expected=ExpectedState(
                task_status="running",
                current_stage="translation",
                active_ocr_result_ids={"tb-running": None},
                active_translation_result_ids={},
                page_artifact_ids={},
            ),
            accepted_results=(),
            active_pointers=(),
            issue_lifecycle=(),
            workflow_decision=WorkflowDecisionDraft(
                decision_id="decision-stale",
                attempt_id="attempt-running",
                stage="translation",
                decision_type="continue",
                reason_code="stale_pointer",
            ),
            retry_budget_after={"translation": 1},
            task_progress=TaskProgressUpdate(
                status="running",
                current_stage="typesetting",
                progress_state="translation_done",
            ),
            stage_statuses=(),
        )
    )

    assert committed.committed
    assert committed.accepted_result_ids == ("ocr-result-1",)
    assert committed.active_pointer_updates == ("text_block:tb-running:active_ocr_result_id",)
    assert committed.issue_changes == ("create:issue-1",)
    assert committed.workflow_decision_id == "decision-1"
    assert committed.retry_budget_after == {"ocr": 1}
    assert committed.task_status == "running"
    assert committed.current_stage == "translation"
    assert committed.stage_status_updates == ("text_block:tb-running:ocr",)

    assert not stale_pointer_conflict.committed
    assert stale_pointer_conflict.reload_required
    assert "active_ocr_result_id" in stale_pointer_conflict.conflict_fields


def test_provider_contract_import_path_has_no_persistence_dependency():
    module = importlib.import_module("manga_read_flow.domain.provider_contracts")
    source = Path(module.__file__).read_text()

    assert "manga_read_flow.persistence" not in source
    assert "sqlite3" not in source


def test_no_generic_repository_abstraction_exists():
    source_root = Path(__file__).resolve().parents[2] / "src" / "manga_read_flow"

    for path in source_root.rglob("*.py"):
        source = path.read_text()
        tree = ast.parse(source)
        class_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

        assert "Repository" not in class_names
        assert "Repository[" not in source


def _ready_repositories(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    created = store.create_project(
        name="Reader Project",
        source_language="ja",
        target_language="zh-Hans",
    )
    opened = store.open_project(created.project_id)

    assert opened.status is ProjectOpenStatus.READY
    return opened.repositories()


def _create_running_attempt(repositories):
    repositories.content_state.create_page(
        page_id="page-running",
        batch_id="batch-running",
        original_artifact_id="artifact-original",
        status="uploaded",
    )
    repositories.content_state.create_text_block(
        text_block_id="tb-running",
        page_id="page-running",
        reading_order=1,
        ocr_status="pending",
        translation_status="pending",
    )
    repositories.workflow_execution.create_task(
        task_id="task-running",
        target_type="page",
        target_id="page-running",
        task_type="process_page",
        status="queued",
        current_stage="ocr",
    )
    return repositories.uow.reserve_attempt(
        AttemptReservation(
            task_id="task-running",
            attempt_id="attempt-running",
            stage="ocr",
            target_type="page",
            target_id="page-running",
            expected_task_status="queued",
            expected_current_stage="ocr",
            runner_id="runner-a",
        )
    )


def _public_names(value):
    return {
        name
        for name in dir(value)
        if not name.startswith("_") and callable(getattr(value, name))
    }
