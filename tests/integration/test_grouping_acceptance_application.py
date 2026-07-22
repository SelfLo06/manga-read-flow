from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import sqlite3
from threading import Barrier, Thread

import pytest

from manga_read_flow.application.accept_grouping_candidate import (
    GROUPING_ACCEPTANCE_CONFLICT,
    GROUPING_ACCEPTANCE_REPLAYED,
    GROUPING_ACCEPTED,
    GROUPING_DECISION_BLOCKED,
    AcceptGroupingCandidateApplicationService,
    AcceptGroupingCandidateCommand,
)
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.domain.grouping import GroupingProducerIdentity
from manga_read_flow.persistence.repository_uow_core import (
    AcceptanceCommand,
    AttemptReservation,
    ExpectedState,
    GroupingCheckExecutionDraft,
    IssueLifecycleChange,
    TaskProgressUpdate,
    WorkflowDecisionDraft,
)
from manga_read_flow.persistence.project_store import AppStore
from tests.integration.test_grouping_candidate_application import (
    PRODUCER_HASH,
    PROFILE_ID,
    _DeterministicGroupingProducer,
    _accept_ocr_v2,
    _check_command,
    _check_service,
    _command,
    _processed_page,
    _service,
)


def test_formal_grouping_acceptance_entry_commits_decision_fact_pointer_and_terminals(
    tmp_path,
):
    context = _checked_candidate(tmp_path)
    command = _accept_command(context, task_suffix="success")

    result = _accept_service(context).accept(command)

    assert result.status == GROUPING_ACCEPTED
    assert result.decision.decision_type == "accept"
    assert result.decision.stage == "grouping"
    assert result.acceptance.snapshot_id == context["candidate"].snapshot_id
    assert result.acceptance.check_result_id == context["checked"].check_result.check_result_id
    assert result.acceptance.accepted_manifest_sha256 == context["candidate"].manifest_artifact_sha256
    assert result.acceptance.accepted_dependency_fingerprint == context["candidate"].dependency_fingerprint
    assert result.current.page_state.active_grouping_snapshot_id == context["candidate"].snapshot_id
    assert result.current.page_state.version == 1
    task = context["repositories"].workflow_execution.get_task(command.task_id)
    assert task.status == "succeeded"
    assert task.current_stage == "grouping"
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT status FROM workflow_attempts WHERE attempt_id = ?",
            (command.attempt_id,),
        ).fetchone() == ("succeeded",)
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_acceptance_executions"
        ).fetchone() == (1,)


def test_warning_that_is_blocking_produces_block_decision_without_acceptance(tmp_path):
    context = _checked_candidate(tmp_path, producer_mode="incomplete")
    issue = context["checked"].quality_issues[0]
    assert issue.severity == "warning"
    assert issue.is_blocking is True

    result = _accept_service(context).accept(
        _accept_command(context, task_suffix="warning-blocker")
    )

    assert result.status == GROUPING_DECISION_BLOCKED
    assert result.decision.decision_type == "block"
    assert result.decision.reason_code == "grouping_blocking_quality_issue"
    assert result.decision.linked_issue_ids == (issue.issue_id,)
    assert result.acceptance is None
    assert result.current is None
    assert context["repositories"].grouping_acceptance.get_page_state(
        context["page_id"]
    ) is None


@pytest.mark.parametrize(
    "status,is_blocking",
    [("open", False), ("resolved", True)],
)
def test_nonblocking_or_resolved_issue_allows_acceptance(
    tmp_path, status, is_blocking
):
    context = _checked_candidate(tmp_path)
    issue_id = _add_formal_grouping_issue(context)
    _change_issue_lifecycle(
        context,
        issue_id=issue_id,
        status=status,
        is_blocking=is_blocking,
    )

    result = _accept_service(context).accept(
        _accept_command(context, task_suffix=f"lifecycle-{status}-{is_blocking}")
    )

    assert result.status == GROUPING_ACCEPTED
    assert result.decision.decision_type == "accept"


def test_exact_replay_preserves_acceptance_and_pointer_version(tmp_path):
    context = _checked_candidate(tmp_path)
    first = _accept_service(context).accept(
        _accept_command(context, task_suffix="replay-1")
    )
    second_command = _accept_command(
        context,
        task_suffix="replay-2",
        expected_active=context["candidate"].snapshot_id,
        expected_version=1,
    )

    second = _accept_service(context).accept(second_command)

    assert first.status == GROUPING_ACCEPTED
    assert second.status == GROUPING_ACCEPTANCE_REPLAYED
    assert second.acceptance.acceptance_id == first.acceptance.acceptance_id
    assert second.current.page_state.version == 1
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_acceptance_executions"
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT COUNT(*) FROM workflow_decisions WHERE stage = 'grouping'"
        ).fetchone() == (2,)


def test_identical_terminal_command_replays_by_exact_read_without_new_writes(tmp_path):
    context = _checked_candidate(tmp_path)
    command = _accept_command(context, task_suffix="identical-replay")
    first = _accept_service(context).accept(command)

    replay = _accept_service(context).accept(command)

    assert first.status == GROUPING_ACCEPTED
    assert replay.status == GROUPING_ACCEPTANCE_REPLAYED
    assert replay.acceptance.acceptance_id == first.acceptance.acceptance_id
    assert replay.current.page_state.version == 1
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_acceptance_executions"
        ).fetchone() == (1,)


def test_terminal_replay_rejects_tampered_manifest_bytes(tmp_path):
    context = _checked_candidate(tmp_path)
    command = _accept_command(context, task_suffix="tampered-terminal-replay")
    _accept_service(context).accept(command)
    artifact = context["repositories"].artifact_metadata.get_artifact(
        context["candidate"].manifest_artifact_id
    )
    (context["project"].workspace_path / artifact.relative_path).write_bytes(b"tampered")

    with pytest.raises(ValueError, match="terminal replay artifact integrity"):
        _accept_service(context).accept(command)
        assert connection.execute(
            "SELECT COUNT(*) FROM workflow_decisions WHERE task_id = ?",
            (command.task_id,),
        ).fetchone() == (1,)


def test_first_acceptance_cas_updates_existing_null_page_state(tmp_path):
    context = _checked_candidate(tmp_path)
    with sqlite3.connect(context["project"].project_db_path) as connection:
        connection.execute(
            """
            INSERT INTO page_grouping_state (
                project_id, page_id, active_grouping_snapshot_id, version, updated_at
            ) VALUES (?, ?, NULL, 3, 'preexisting-null-state')
            """,
            (context["project"].project_id, context["page_id"]),
        )

    result = _accept_service(context).accept(
        _accept_command(
            context,
            task_suffix="null-state",
            expected_active=None,
            expected_version=3,
        )
    )

    assert result.status == GROUPING_ACCEPTED
    assert result.current.page_state.version == 4


def test_replacement_atomically_switches_pointer_and_stales_previous_snapshot(tmp_path):
    context = _checked_candidate(tmp_path)
    first = _accept_service(context).accept(
        _accept_command(context, task_suffix="replacement-first")
    )
    producer = _DeterministicGroupingProducer()
    producer.identity = GroupingProducerIdentity(
        producer_name="deterministic-test-producer",
        producer_version="2",
        implementation_hash=PRODUCER_HASH,
    )
    candidate = _service(
        context["project"],
        context["repositories"],
        context["artifacts"],
        producer,
    ).materialize(
        _command(
            context["page_id"],
            context["dependency_id"],
            run_id="grouping-run-replacement-second",
        )
    ).snapshot
    check_command = replace(
        _check_command(
            candidate,
            context["dependency_id"],
            execution_id="grouping-check-replacement-second",
        ),
        expected_producer_version="2",
    )
    checked = _check_service(
        context["project"], context["repositories"], context["artifacts"]
    ).check(check_command)
    second_context = dict(context, candidate=candidate, checked=checked)
    command = replace(
        _accept_command(
            second_context,
            task_suffix="replacement-second",
            expected_active=first.current.snapshot.snapshot_id,
            expected_version=1,
        ),
        expected_producer_version="2",
    )

    second = _accept_service(second_context).accept(command)

    assert second.status == GROUPING_ACCEPTED
    current = context["repositories"].grouping_acceptance.get_current(context["page_id"])
    assert current.snapshot.snapshot_id == candidate.snapshot_id
    assert current.page_state.version == 2
    stale = context["repositories"].grouping_stale.list_for_snapshot(
        first.current.snapshot.snapshot_id
    )
    assert len(stale) == 1
    assert stale[0].reason_type == "GROUPING_REVISION_SUPERSEDED"
    assert stale[0].replacement_dependency_id == candidate.snapshot_id


def test_pointer_cas_mismatch_has_no_partial_terminal_update(tmp_path):
    context = _checked_candidate(tmp_path)
    _accept_service(context).accept(_accept_command(context, task_suffix="winner"))
    loser = _accept_command(context, task_suffix="loser")

    result = _accept_service(context).accept(loser)

    assert result.status == GROUPING_ACCEPTANCE_CONFLICT
    assert "active_grouping_snapshot_id" in result.conflict_fields
    task = context["repositories"].workflow_execution.get_task(loser.task_id)
    assert task.status == "running"
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT status FROM workflow_attempts WHERE attempt_id = ?",
            (loser.attempt_id,),
        ).fetchone() == ("running",)
        assert connection.execute(
            "SELECT COUNT(*) FROM workflow_decisions WHERE task_id = ?",
            (loser.task_id,),
        ).fetchone() == (0,)


def test_ocr_change_between_decision_read_and_uow_returns_conflict(monkeypatch, tmp_path):
    context = _checked_candidate(tmp_path)
    repositories = context["repositories"]
    original_accept_stage = repositories.uow.accept_stage
    raced = False

    def race(command):
        nonlocal raced
        if command.grouping_context is not None and not raced:
            raced = True
            monkeypatch.setattr(repositories.uow, "accept_stage", original_accept_stage)
            _accept_ocr_v2(repositories, context["candidate"])
        return original_accept_stage(command)

    monkeypatch.setattr(repositories.uow, "accept_stage", race)
    command = _accept_command(context, task_suffix="ocr-race")

    result = _accept_service(context).accept(command)

    assert result.status == GROUPING_ACCEPTANCE_CONFLICT
    assert "grouping_ocr_dependency_state" in result.conflict_fields
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM workflow_decisions WHERE task_id = ?",
            (command.task_id,),
        ).fetchone() == (0,)


def test_profile_change_between_decision_read_and_uow_returns_conflict(monkeypatch, tmp_path):
    context = _checked_candidate(tmp_path)
    repositories = context["repositories"]
    settings_json = '{"retry_budgets":{"grouping":0}}'
    repositories.workflow_execution.ensure_profile_snapshot(
        profile_snapshot_id="profile-concurrent",
        settings_json=settings_json,
        settings_hash=sha256(settings_json.encode()).hexdigest(),
    )
    original_accept_stage = repositories.uow.accept_stage

    def race(command):
        with sqlite3.connect(context["project"].project_db_path) as connection:
            connection.execute(
                "UPDATE processing_tasks SET profile_snapshot_id = 'profile-concurrent' WHERE task_id = ?",
                (command.task_id,),
            )
        return original_accept_stage(command)

    monkeypatch.setattr(repositories.uow, "accept_stage", race)

    result = _accept_service(context).accept(
        _accept_command(context, task_suffix="profile-race")
    )

    assert result.status == GROUPING_ACCEPTANCE_CONFLICT
    assert "grouping_task_binding" in result.conflict_fields


def test_source_change_between_decision_read_and_uow_returns_conflict(monkeypatch, tmp_path):
    context = _checked_candidate(tmp_path)
    repositories = context["repositories"]
    original_accept_stage = repositories.uow.accept_stage

    def race(command):
        with sqlite3.connect(context["project"].project_db_path) as connection:
            connection.execute(
                "UPDATE pages SET original_artifact_id = 'concurrent-source' WHERE page_id = ?",
                (context["page_id"],),
            )
        return original_accept_stage(command)

    monkeypatch.setattr(repositories.uow, "accept_stage", race)

    result = _accept_service(context).accept(
        _accept_command(context, task_suffix="source-race")
    )

    assert result.status == GROUPING_ACCEPTANCE_CONFLICT
    assert "grouping_source_dependency" in result.conflict_fields


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_producer_version", "different-producer-version"),
        ("expected_operation_semantics_version", "different-operation"),
    ],
)
def test_producer_or_operation_incompatibility_persists_block_without_acceptance(
    tmp_path, field, value
):
    context = _checked_candidate(tmp_path)
    command = _accept_command(context, task_suffix=f"incompatible-{field}")
    command = replace(command, **{field: value})

    result = _accept_service(context).accept(command)

    assert result.status == GROUPING_DECISION_BLOCKED
    assert result.decision.reason_code == "grouping_dependencies_changed"
    assert result.acceptance is None


def test_current_selector_fails_closed_after_ocr_dependency_changes(tmp_path):
    context = _checked_candidate(tmp_path)
    _accept_service(context).accept(_accept_command(context, task_suffix="selector"))

    _accept_ocr_v2(context["repositories"], context["candidate"])

    state = context["repositories"].grouping_acceptance.get_page_state(context["page_id"])
    assert state.active_grouping_snapshot_id is None
    assert state.version == 2
    stale = context["repositories"].grouping_stale.list_for_snapshot(
        context["candidate"].snapshot_id
    )
    assert len(stale) == len(context["candidate"].ocr_dependencies)
    assert {fact.reason_type for fact in stale} == {"OCR_DEPENDENCY_CHANGED"}
    with pytest.raises(LookupError, match="not found"):
        context["repositories"].grouping_acceptance.get_current(context["page_id"])


def test_stale_check_after_ocr_change_is_blocked_without_acceptance(tmp_path):
    context = _checked_candidate(tmp_path)
    _accept_ocr_v2(context["repositories"], context["candidate"])

    result = _accept_service(context).accept(
        _accept_command(context, task_suffix="stale-check")
    )

    assert result.status == GROUPING_DECISION_BLOCKED
    assert result.decision.reason_code == "grouping_dependencies_changed"
    assert result.acceptance is None


@pytest.mark.parametrize("binding", ["check_result_id", "check_execution_id"])
def test_missing_check_binding_never_reaches_acceptance(tmp_path, binding):
    context = _checked_candidate(tmp_path)
    command = _accept_command(context, task_suffix=f"missing-{binding}")
    command = replace(command, **{binding: f"missing-{binding}"})

    with pytest.raises(LookupError if binding == "check_result_id" else ValueError):
        _accept_service(context).accept(command)

    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (0,)


def test_missing_explicit_current_detection_dependency_never_accepts(tmp_path):
    context = _checked_candidate(tmp_path)
    command = replace(
        _accept_command(context, task_suffix="missing-detection"),
        current_detection_dependency_id="missing-detection-dependency",
    )

    with pytest.raises(LookupError, match="AcceptedDetectionEvidenceSet not found"):
        _accept_service(context).accept(command)

    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (0,)


@pytest.mark.parametrize("artifact_kind", ["manifest", "check_evidence"])
def test_tampered_candidate_or_check_evidence_blocks_acceptance(tmp_path, artifact_kind):
    context = _checked_candidate(tmp_path)
    artifact_id = (
        context["candidate"].manifest_artifact_id
        if artifact_kind == "manifest"
        else context["checked"].check_result.evidence_artifact_id
    )
    artifact = context["repositories"].artifact_metadata.get_artifact(artifact_id)
    (context["project"].workspace_path / artifact.relative_path).write_bytes(b"tampered")

    command = _accept_command(context, task_suffix=f"tampered-{artifact_kind}")
    if artifact_kind == "check_evidence":
        with pytest.raises(ValueError, match="evidence binding"):
            _accept_service(context).accept(command)
    else:
        result = _accept_service(context).accept(command)
        assert result.status == GROUPING_DECISION_BLOCKED
        assert result.decision.reason_code == "grouping_check_not_applicable"
        assert result.acceptance is None
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (0,)


def test_transaction_failure_rolls_back_decision_acceptance_pointer_and_terminals(
    monkeypatch, tmp_path
):
    context = _checked_candidate(tmp_path)
    command = _accept_command(context, task_suffix="rollback")

    def fail_commit(*args, **kwargs):
        raise sqlite3.OperationalError("injected grouping acceptance failure")

    monkeypatch.setattr(
        "manga_read_flow.persistence.acceptance_repository.persist_grouping_commit",
        fail_commit,
    )

    with pytest.raises(sqlite3.OperationalError, match="injected"):
        _accept_service(context).accept(command)

    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM workflow_decisions WHERE task_id = ?",
            (command.task_id,),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM page_grouping_state"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT status FROM workflow_attempts WHERE attempt_id = ?",
            (command.attempt_id,),
        ).fetchone() == ("running",)


def test_grouping_acceptance_and_execution_rows_are_immutable(tmp_path):
    context = _checked_candidate(tmp_path)
    result = _accept_service(context).accept(
        _accept_command(context, task_suffix="immutable")
    )

    with sqlite3.connect(context["project"].project_db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE grouping_snapshot_acceptances SET accepted_at = 'tampered' WHERE acceptance_id = ?",
                (result.acceptance.acceptance_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM grouping_acceptance_executions WHERE acceptance_id = ?",
                (result.acceptance.acceptance_id,),
            )


def test_concurrent_first_acceptance_has_one_winner_and_does_not_overwrite(monkeypatch, tmp_path):
    context = _checked_candidate(tmp_path)
    project = context["project"]
    opened_a = context["store"].open_project(project.project_id)
    opened_b = context["store"].open_project(project.project_id)
    repos_a = opened_a.repositories()
    repos_b = opened_b.repositories()
    services = []
    commands = []
    barrier = Barrier(2)
    for suffix, repositories in (("a", repos_a), ("b", repos_b)):
        artifacts = ArtifactService(
            project_id=project.project_id,
            project_workspace_path=project.workspace_path,
            artifact_repository=repositories.artifact_metadata,
        )
        local_context = dict(context, repositories=repositories, artifacts=artifacts)
        command = _accept_command(local_context, task_suffix=f"concurrent-{suffix}")
        original = repositories.uow.accept_stage

        def synchronized(value, original=original):
            barrier.wait()
            return original(value)

        monkeypatch.setattr(repositories.uow, "accept_stage", synchronized)
        services.append(_accept_service(local_context))
        commands.append(command)
    results = []

    def run(index):
        results.append(services[index].accept(commands[index]))

    threads = [Thread(target=run, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert {result.status for result in results} == {
        GROUPING_ACCEPTANCE_CONFLICT,
        GROUPING_ACCEPTED,
    }
    current = context["repositories"].grouping_acceptance.get_current(context["page_id"])
    assert current.page_state.version == 1
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM grouping_snapshot_acceptances"
        ).fetchone() == (1,)


def _checked_candidate(
    tmp_path,
    *,
    producer_mode="produced",
):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    producer = _DeterministicGroupingProducer(producer_mode)
    candidate = _service(project, repositories, artifacts, producer).materialize(
        _command(page_id, dependency_id, run_id=f"grouping-run-{producer_mode}")
    ).snapshot
    checked = _check_service(project, repositories, artifacts).check(
        _check_command(
            candidate,
            dependency_id,
            execution_id=f"grouping-check-{producer_mode}",
        )
    )
    return {
        "store": AppStore.initialize(tmp_path / "workspace"),
        "project": project,
        "repositories": repositories,
        "artifacts": artifacts,
        "page_id": page_id,
        "dependency_id": dependency_id,
        "candidate": candidate,
        "checked": checked,
    }


def _accept_service(context):
    return AcceptGroupingCandidateApplicationService(
        project_id=context["project"].project_id,
        repositories=context["repositories"],
        artifact_service=context["artifacts"],
    )


def _accept_command(
    context,
    *,
    task_suffix,
    expected_active=None,
    expected_version=None,
):
    task_id = f"task-grouping-{task_suffix}"
    attempt_id = f"attempt-grouping-{task_suffix}"
    repositories = context["repositories"]
    repositories.workflow_execution.create_task(
        task_id=task_id,
        target_type="page",
        target_id=context["page_id"],
        task_type="accept_grouping_candidate",
        status="queued",
        current_stage="grouping",
        profile_snapshot_id=PROFILE_ID,
    )
    reserved = repositories.uow.reserve_attempt(
        AttemptReservation(
            task_id=task_id,
            attempt_id=attempt_id,
            stage="grouping",
            target_type="page",
            target_id=context["page_id"],
            expected_task_status="queued",
            expected_current_stage="grouping",
            runner_id="test-runner",
        )
    )
    assert reserved.committed
    return AcceptGroupingCandidateCommand(
        page_id=context["page_id"],
        snapshot_id=context["candidate"].snapshot_id,
        check_result_id=context["checked"].check_result.check_result_id,
        check_execution_id=context["checked"].execution.execution_id,
        task_id=task_id,
        attempt_id=attempt_id,
        current_detection_dependency_id=context["dependency_id"],
        current_profile_snapshot_id=PROFILE_ID,
        expected_producer_name="deterministic-test-producer",
        expected_producer_version="1",
        expected_producer_implementation_hash=PRODUCER_HASH,
        expected_operation_semantics_version="grouping-op.v1",
        expected_active_grouping_snapshot_id=expected_active,
        expected_page_grouping_state_version=expected_version,
        decision_execution_id=f"grouping-acceptance-execution-{task_suffix}",
        decision_id=f"decision-grouping-{task_suffix}",
    )


def _change_issue_lifecycle(context, *, issue_id, status, is_blocking):
    repositories = context["repositories"]
    task_id = f"task-issue-{status}-{int(is_blocking)}"
    repositories.workflow_execution.create_task(
        task_id=task_id,
        target_type="page",
        target_id=context["page_id"],
        task_type="review_grouping_issue",
        status="running",
        current_stage="review",
        profile_snapshot_id=PROFILE_ID,
    )
    outcome = repositories.uow.accept_stage(
        AcceptanceCommand(
            task_id=task_id,
            expected=ExpectedState(task_status="running", current_stage="review"),
            accepted_results=(),
            active_pointers=(),
            issue_lifecycle=(
                IssueLifecycleChange(
                    issue_id=issue_id,
                    action="resolve" if status == "resolved" else "update",
                    status=status,
                    issue_type="grouping_unresolved_relation",
                    is_blocking=is_blocking,
                ),
            ),
            workflow_decision=WorkflowDecisionDraft(
                decision_id=f"decision-{task_id}",
                attempt_id=None,
                stage="review",
                decision_type="continue",
                reason_code="grouping_issue_reviewed",
                linked_issue_ids=(issue_id,),
            ),
            retry_budget_after={},
            task_progress=TaskProgressUpdate(
                status="succeeded",
                current_stage="review",
                progress_state="grouping_issue_reviewed",
            ),
            stage_statuses=(),
            attempt_terminal_status=None,
        )
    )
    assert outcome.committed


def _add_formal_grouping_issue(context):
    check_result = context["checked"].check_result
    issue_id = "issue-grouping-lifecycle"
    committed = context["repositories"].uow.commit_grouping_check_evaluation(
        check_result=check_result,
        issue_changes=(
            IssueLifecycleChange(
                issue_id=issue_id,
                action="create",
                status="open",
                issue_type="grouping_review_warning",
                is_blocking=True,
                target_type="frozen_grouping_evidence_snapshot",
                target_id=context["candidate"].snapshot_id,
                page_id=context["page_id"],
                discovered_stage="grouping",
                root_stage="grouping",
                severity="warning",
                message_key="grouping.review_warning",
                message_params_json="{}",
                suggested_action_key="action.review_grouping_candidate",
                applies_to_result_id=check_result.check_result_id,
                input_hash=check_result.input_fingerprint,
                config_hash=check_result.input_fingerprint,
                dedupe_key="grouping-review-warning",
            ),
        ),
        execution=GroupingCheckExecutionDraft(
            execution_id="grouping-check-execution-lifecycle",
            check_result_id=check_result.check_result_id,
            snapshot_id=context["candidate"].snapshot_id,
            page_id=context["page_id"],
            input_fingerprint=check_result.input_fingerprint,
        ),
    )
    assert issue_id in committed.issue_ids
    return issue_id
