from __future__ import annotations

import sqlite3

import pytest

from manga_read_flow.domain.artifacts import ArtifactSafetyMetadata, RegisterArtifactMetadata
from manga_read_flow.persistence.acceptance_repository import IssueLifecycleChange
from manga_read_flow.persistence.full_page_cleaning_acceptance_repository import (
    CleanedPassDispositionDraft,
    CleaningIssueRelationDraft,
    CombinedCleaningCandidateDraft,
    CombinedCleaningCandidateMemberDraft,
    FullPageCleaningAcceptanceCommand,
    FullPageCleaningBlockCommand,
    PageCleaningValidationDraft,
)
from manga_read_flow.persistence.full_page_cleaning_ledger_repository import (
    CleaningInventoryItemDraft,
    InstanceCleaningResultDraft,
    PageCleaningRunDraft,
)
from manga_read_flow.persistence.project_store import AppStore, ProjectOpenStatus


def test_candidate_membership_and_validation_are_normalized_and_replayable(tmp_path):
    context = _ready_candidate(tmp_path)
    repository = context["repositories"].full_page_cleaning_acceptance

    replayed = repository.create_combined_candidate_with_members(
        context["candidate"], context["members"]
    )
    validation = repository.append_page_cleaning_validation(context["validation"])
    replayed_validation = repository.append_page_cleaning_validation(context["validation"])

    assert replayed.combined_cleaning_candidate_id == "candidate-page"
    assert replayed.member_result_ids == ("result-a", "result-b")
    assert validation.status == "pass"
    assert replayed_validation == validation
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM combined_cleaning_candidate_members"
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT COUNT(*) FROM page_cleaning_validation_records"
        ).fetchone() == (1,)


def test_passing_validation_cannot_hide_a_failed_page_predicate(tmp_path):
    context = _ready_candidate(tmp_path)
    invalid = PageCleaningValidationDraft(
        **{
            **context["validation"].__dict__,
            "page_cleaning_validation_record_id": "invalid-validation",
            "validation_fingerprint": "invalid-validation-fingerprint",
            "wrong_instance_write_pixel_count": 1,
        }
    )

    with pytest.raises(ValueError, match="passing page validation"):
        context["repositories"].full_page_cleaning_acceptance.append_page_cleaning_validation(
            invalid
        )


def test_official_unselected_recovery_and_acceptance_replay_are_deterministic(tmp_path):
    context = _ready_candidate(tmp_path)
    repository = context["repositories"].full_page_cleaning_acceptance
    before = repository.load_page_cleaning_acceptance_recovery(
        page_cleaning_run_id="run"
    )
    eligibility = context[
        "repositories"
    ].uow.validate_active_cleaned_pointer_eligibility(
        _acceptance_command(context, decision_id="decision-eligibility")
    )

    first = context["repositories"].uow.accept_page_cleaning_atomically(
        _acceptance_command(context, decision_id="decision-accepted")
    )
    replay = context["repositories"].uow.accept_page_cleaning_atomically(
        _acceptance_command(context, decision_id="decision-accepted")
    )
    after = repository.load_page_cleaning_acceptance_recovery(
        page_cleaning_run_id="run"
    )

    assert before.candidates[0].status == "validated"
    assert eligibility.result_code == "ELIGIBLE"
    assert before.acceptance_id is None
    assert before.accepted_disposition_ids == ()
    assert first.result_code == "ACCEPTED"
    assert replay.result_code == "ALREADY_ACCEPTED"
    assert replay.active_cleaned_artifact_id == "combined-artifact"
    assert after.candidates[0].status == "accepted"
    assert after.acceptance_status == "accepted"
    assert after.accepted_disposition_ids == ("pass-a", "pass-b")
    assert tuple(
        disposition.cleaning_inventory_item_id
        for disposition in after.accepted_dispositions
    ) == ("item-a", "item-b")


def test_unresolved_related_blocker_rejects_then_resolved_issue_accepts_atomically(tmp_path):
    context = _ready_candidate(tmp_path)
    repository = context["repositories"].full_page_cleaning_acceptance
    repository.persist_cleaning_issue_lifecycle(
        issue_changes=(_issue("issue-blocker", status="open", action="create"),),
        relations=(
            CleaningIssueRelationDraft(
                cleaning_quality_issue_relation_id="relation-blocker",
                issue_id="issue-blocker",
                relation_type="blocks",
                combined_cleaning_candidate_id="candidate-page",
            ),
        ),
    )

    blocked = context["repositories"].uow.accept_page_cleaning_atomically(
        _acceptance_command(context, decision_id="decision-blocked")
    )
    accepted = context["repositories"].uow.accept_page_cleaning_atomically(
        _acceptance_command(
            context,
            decision_id="decision-accepted",
            issue_changes=(
                _issue("issue-blocker", status="resolved", action="resolve", blocking=False),
            ),
        )
    )

    assert blocked.committed is False
    assert blocked.result_code == "UNRESOLVED_BLOCKING_ISSUE"
    assert accepted.committed is True
    assert accepted.result_code == "ACCEPTED"
    assert accepted.cleaned_pass_count == 2
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT active_cleaned_artifact_id FROM pages WHERE page_id = 'page'"
        ).fetchone() == ("combined-artifact",)
        assert connection.execute(
            "SELECT status FROM pages WHERE page_id = 'page'"
        ).fetchone() == ("cleaned",)
        assert connection.execute(
            "SELECT status FROM page_cleaning_runs WHERE page_cleaning_run_id = 'run'"
        ).fetchone() == ("accepted",)
        assert connection.execute(
            "SELECT status FROM combined_cleaning_candidates WHERE combined_cleaning_candidate_id = 'candidate-page'"
        ).fetchone() == ("accepted",)
        assert connection.execute(
            "SELECT selection_status FROM page_cleaning_validation_records"
        ).fetchone() == ("accepted",)
        assert connection.execute(
            "SELECT status, is_blocking FROM quality_issues WHERE issue_id = 'issue-blocker'"
        ).fetchone() == ("resolved", 0)
        assert connection.execute(
            "SELECT COUNT(*) FROM accepted_segment_cleaning_dispositions WHERE disposition_code = 'CLEANED_PASS'"
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT status, progress_state, retry_budget_json FROM processing_tasks WHERE task_id = 'task'"
        ).fetchone() == ("succeeded", "cleaning_accepted", "{}")


def test_cleaned_pass_without_accepted_combined_member_is_rejected_by_schema(tmp_path):
    context = _ready_candidate(tmp_path)

    with sqlite3.connect(context["project"].project_db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError, match="accepted combined member"):
            connection.execute(
                """
                INSERT INTO accepted_segment_cleaning_dispositions (
                    accepted_segment_cleaning_disposition_id, project_id,
                    page_cleaning_run_id, cleaning_inventory_item_id,
                    instance_cleaning_result_id, combined_cleaning_candidate_id,
                    page_cleaning_validation_record_id, disposition_code,
                    dependency_fingerprint, stale_by_dependency_fingerprint, created_at
                ) VALUES ('illegal-pass', ?, 'run', 'item-a', 'result-a',
                          'candidate-page', 'validation-page', 'CLEANED_PASS',
                          'dep-a', NULL, 'now')
                """,
                (context["project"].project_id,),
            )


def test_acceptance_conflict_and_database_failure_leave_no_partial_state(tmp_path):
    context = _ready_candidate(tmp_path)
    repositories = context["repositories"]

    conflict = repositories.uow.accept_page_cleaning_atomically(
        _acceptance_command(
            context,
            decision_id="decision-conflict",
            expected_active_cleaned_artifact_id="stale-pointer",
        )
    )
    with sqlite3.connect(context["project"].project_db_path) as connection:
        connection.execute(
            "INSERT INTO workflow_decisions(decision_id, project_id, task_id, attempt_id, stage, decision_type, reason_code, created_at) "
            "VALUES ('duplicate-decision', ?, 'task', NULL, 'cleaning', 'block', 'seed', 'now')",
            (context["project"].project_id,),
        )
    failed = repositories.uow.accept_page_cleaning_atomically(
        _acceptance_command(context, decision_id="duplicate-decision")
    )

    assert conflict.result_code == "ACTIVE_POINTER_CONFLICT"
    assert failed.result_code == "TRANSACTION_FAILED"
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT active_cleaned_artifact_id FROM pages WHERE page_id = 'page'"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT status FROM pages WHERE page_id = 'page'"
        ).fetchone() == ("uploaded",)
        assert connection.execute(
            "SELECT status FROM combined_cleaning_candidates"
        ).fetchone() == ("validated",)
        assert connection.execute(
            "SELECT COUNT(*) FROM accepted_segment_cleaning_dispositions"
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            "UPDATE processing_artifacts SET storage_state = 'missing' "
            "WHERE artifact_id = 'combined-artifact'",
            "ARTIFACT_INTEGRITY_INVALID",
        ),
        (
            "UPDATE instance_cleaning_results SET status = 'stale', "
            "stale_by_dependency_fingerprint = 'dependency-v2' "
            "WHERE instance_cleaning_result_id = 'result-a'",
            "MEMBER_NOT_FRESH_VALIDATED",
        ),
        (
            "UPDATE processing_artifacts SET storage_state = 'missing' "
            "WHERE artifact_id = 'combined-delta'",
            "ARTIFACT_INTEGRITY_INVALID",
        ),
        (
            "UPDATE processing_artifacts SET storage_state = 'missing' "
            "WHERE artifact_id = 'actual-a'",
            "ARTIFACT_INTEGRITY_INVALID",
        ),
        (
            "UPDATE page_cleaning_validation_records SET residue_pixel_count = 1 "
            "WHERE page_cleaning_validation_record_id = 'validation-page'",
            "PAGE_VALIDATION_NOT_ACCEPTABLE",
        ),
    ],
)
def test_acceptance_rechecks_artifact_integrity_and_member_freshness(
    tmp_path, mutation, expected_code
):
    context = _ready_candidate(tmp_path)
    with sqlite3.connect(context["project"].project_db_path) as connection:
        connection.execute(mutation)

    outcome = context["repositories"].uow.accept_page_cleaning_atomically(
        _acceptance_command(context, decision_id="decision-invalid")
    )

    assert outcome.committed is False
    assert outcome.result_code == expected_code
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT active_cleaned_artifact_id FROM pages WHERE page_id = 'page'"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT status FROM pages WHERE page_id = 'page'"
        ).fetchone() == ("uploaded",)
        assert connection.execute(
            "SELECT COUNT(*) FROM accepted_segment_cleaning_dispositions"
        ).fetchone() == (0,)


def test_stale_repair_uses_pointer_cas_and_clears_all_accepted_facts_atomically(tmp_path):
    context = _ready_candidate(tmp_path)
    repositories = context["repositories"]
    accepted = repositories.uow.accept_page_cleaning_atomically(
        _acceptance_command(context, decision_id="decision-accepted")
    )
    assert accepted.committed

    conflict = repositories.uow.mark_cleaning_facts_stale_and_clear_active_pointer_atomically(
        page_cleaning_run_id="run",
        expected_active_cleaned_artifact_id="wrong-artifact",
        dependency_fingerprint="dependency-v2",
    )
    repaired = repositories.uow.mark_cleaning_facts_stale_and_clear_active_pointer_atomically(
        page_cleaning_run_id="run",
        expected_active_cleaned_artifact_id="combined-artifact",
        dependency_fingerprint="dependency-v2",
    )

    assert conflict.result_code == "ACTIVE_POINTER_CONFLICT"
    assert repaired.committed is True
    assert repaired.result_code == "STALE_AND_POINTER_CLEARED"
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT active_cleaned_artifact_id FROM pages WHERE page_id = 'page'"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT status FROM pages WHERE page_id = 'page'"
        ).fetchone() == ("review_required",)
        assert connection.execute("SELECT status FROM page_cleaning_runs").fetchone() == ("stale",)
        assert connection.execute("SELECT status FROM combined_cleaning_candidates").fetchone() == ("stale",)
        assert connection.execute("SELECT status FROM page_cleaning_acceptances").fetchone() == ("stale",)
        assert connection.execute(
            "SELECT COUNT(*) FROM accepted_segment_cleaning_dispositions WHERE stale_by_dependency_fingerprint = 'dependency-v2'"
        ).fetchone() == (2,)


def test_block_transaction_persists_issue_decision_and_never_updates_pointer(tmp_path):
    context = _ready_candidate(tmp_path)

    outcome = context["repositories"].uow.block_page_cleaning_atomically(
        FullPageCleaningBlockCommand(
            page_cleaning_run_id="run",
            page_id="page",
            task_id="task",
            expected_task_status="running",
            expected_task_stage="cleaning",
            workflow_decision_id="decision-block",
            reason_code="page_validation_failed",
            issue_changes=(_issue("issue-validation", status="open", action="create"),),
            issue_relations=(
                CleaningIssueRelationDraft(
                    cleaning_quality_issue_relation_id="relation-validation",
                    issue_id="issue-validation",
                    relation_type="caused_by",
                    page_cleaning_validation_record_id="validation-page",
                ),
                CleaningIssueRelationDraft(
                    cleaning_quality_issue_relation_id="relation-validation-decision",
                    issue_id="issue-validation",
                    relation_type="decided_by",
                    workflow_decision_id="decision-block",
                ),
            ),
        )
    )

    assert outcome.committed is True
    assert outcome.result_code == "BLOCKED"
    with sqlite3.connect(context["project"].project_db_path) as connection:
        assert connection.execute(
            "SELECT active_cleaned_artifact_id FROM pages WHERE page_id = 'page'"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT status FROM pages WHERE page_id = 'page'"
        ).fetchone() == ("review_required",)
        assert connection.execute("SELECT status FROM page_cleaning_runs").fetchone() == ("blocked",)
        assert connection.execute("SELECT decision_type FROM workflow_decisions").fetchone() == ("block",)
        assert connection.execute(
            "SELECT COUNT(*) FROM cleaning_quality_issue_relations WHERE issue_id = 'issue-validation'"
        ).fetchone() == (2,)


def _ready_candidate(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="整页验收测试", source_language="ja", target_language="zh-CN"
    )
    opened = store.open_project(project.project_id)
    assert opened.status is ProjectOpenStatus.READY
    repositories = opened.repositories()
    repositories.content_state.create_page(
        page_id="page", batch_id="batch", original_artifact_id="original", status="uploaded"
    )
    for artifact_id, file_hash, artifact_type in (
        ("original", "source-hash", "original_image"),
        ("candidate-a", "candidate-a-hash", "cleaned_instance_candidate"),
        ("candidate-b", "candidate-b-hash", "cleaned_instance_candidate"),
        ("actual-a", "actual-a-hash", "actual_changed_mask"),
        ("actual-b", "actual-b-hash", "actual_changed_mask"),
        ("combined-artifact", "combined-hash", "full_page_cleaned_candidate"),
        ("combined-delta", "combined-delta-hash", "actual_changed_mask"),
    ):
        repositories.artifact_metadata.register_artifact(
            RegisterArtifactMetadata(
                artifact_id=artifact_id,
                batch_id="batch",
                page_id="page",
                owner_type="page",
                owner_id="page",
                artifact_type=artifact_type,
                source_stage="cleaning",
                relative_path=f"artifacts/{artifact_id}.png",
                file_hash=file_hash,
                hash_algorithm="sha256",
                byte_size=1,
                mime_type="image/png",
                width=1,
                height=1,
                retention_class="stage_output",
                storage_state="present",
                safety=ArtifactSafetyMetadata(),
            )
        )
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "INSERT INTO page_visual_contract_state(project_id, page_id, active_visual_contract_revision_id, input_hash, updated_at) "
            "VALUES (?, 'page', 'visual-v1', 'visual-hash', 'now')",
            (project.project_id,),
        )
        connection.execute(
            """
            INSERT INTO processing_tasks(
                task_id, project_id, target_type, target_id, task_type, status,
                current_stage, profile_snapshot_id, progress_state,
                retry_budget_json, heartbeat_at, created_at, updated_at
            ) VALUES ('task', ?, 'page', 'page', 'process_page', 'running',
                      'cleaning', NULL, 'running', '{}', NULL, 'now', 'now')
            """,
            (project.project_id,),
        )
    ledger = repositories.full_page_cleaning_ledger
    ledger.create_or_replay_page_cleaning_run(
        PageCleaningRunDraft(
            "run", "batch", "page", "visual-v1", "original", "source-hash",
            None, "config", "run-key",
        )
    )
    items = (
        CleaningInventoryItemDraft(
            "item-a", "segment-a", "segment-revision-a", "instance-a", "instance-revision-a",
            "assignment-a", "ordinary_dialogue", "E1", "required", "dep-a", None, 1,
        ),
        CleaningInventoryItemDraft(
            "item-b", "segment-b", "segment-revision-b", "instance-b", "instance-revision-b",
            "assignment-b", "ordinary_dialogue", "E1", "required", "dep-b", None, 2,
        ),
    )
    ledger.freeze_cleaning_inventory(
        page_cleaning_run_id="run", inventory_fingerprint="inventory-fingerprint", items=items
    )
    ledger.transition_page_cleaning_run(page_cleaning_run_id="run", target_status="executing")
    for suffix in ("a", "b"):
        ledger.append_instance_cleaning_result(
            InstanceCleaningResultDraft(
                instance_cleaning_result_id=f"result-{suffix}",
                page_cleaning_run_id="run",
                bubble_instance_id=f"instance-{suffix}",
                bubble_instance_revision_id=f"instance-revision-{suffix}",
                source_artifact_id="original",
                source_hash="source-hash",
                dependency_fingerprint=f"dep-{suffix}",
                config_hash="config",
                state="validated",
                official_candidate_artifact_id=f"candidate-{suffix}",
                actual_changed_artifact_id=f"actual-{suffix}",
                validator_evidence_artifact_id=None,
                actual_changed_pixel_count=1,
                unsafe_required_pixel_count=0,
                residue_pixel_count=0,
                validator_summary="pass",
            ),
            inventory_item_ids=(f"item-{suffix}",),
        )
    candidate = CombinedCleaningCandidateDraft(
        combined_cleaning_candidate_id="candidate-page",
        page_cleaning_run_id="run",
        source_artifact_id="original",
        source_hash="source-hash",
        combined_artifact_id="combined-artifact",
        combined_hash="combined-hash",
        combined_delta_artifact_id="combined-delta",
        combined_delta_hash="combined-delta-hash",
        composition_config_hash="composition-config",
        member_set_fingerprint="member-set",
    )
    members = (
        CombinedCleaningCandidateMemberDraft(
            "result-a", "instance-revision-a", "01/a", "actual-a", "actual-a-hash"
        ),
        CombinedCleaningCandidateMemberDraft(
            "result-b", "instance-revision-b", "02/b", "actual-b", "actual-b-hash"
        ),
    )
    repositories.full_page_cleaning_acceptance.create_combined_candidate_with_members(
        candidate, members
    )
    validation = PageCleaningValidationDraft(
        page_cleaning_validation_record_id="validation-page",
        page_cleaning_run_id="run",
        combined_cleaning_candidate_id="candidate-page",
        validation_fingerprint="validation-fingerprint",
        status="pass",
        inventory_complete=True,
        dispositions_unique=True,
        missing_attribution_count=0,
        duplicate_attribution_count=0,
        pairwise_overlap_pixel_count=0,
        wrong_instance_write_pixel_count=0,
        outside_safe_pixel_count=0,
        protected_pixel_count=0,
        uncertainty_pixel_count=0,
        boundary_damage_pixel_count=0,
        residue_pixel_count=0,
        combined_delta_matches_member_union=True,
        source_integrity_valid=True,
        combined_integrity_valid=True,
        dependencies_fresh=True,
        evidence_artifact_id=None,
        overlap_evidence_artifact_id=None,
        wrong_instance_evidence_artifact_id=None,
        validator_summary="pass",
    )
    repositories.full_page_cleaning_acceptance.append_page_cleaning_validation(validation)
    return {
        "store": store,
        "project": project,
        "repositories": repositories,
        "candidate": candidate,
        "members": members,
        "validation": validation,
    }


def _acceptance_command(
    context,
    *,
    decision_id,
    expected_active_cleaned_artifact_id=None,
    issue_changes=(),
):
    return FullPageCleaningAcceptanceCommand(
        page_cleaning_acceptance_id="acceptance-page",
        idempotency_key="acceptance-key",
        page_cleaning_run_id="run",
        page_id="page",
        combined_cleaning_candidate_id="candidate-page",
        page_cleaning_validation_record_id="validation-page",
        cleaned_artifact_id="combined-artifact",
        expected_active_cleaned_artifact_id=expected_active_cleaned_artifact_id,
        expected_original_artifact_id="original",
        expected_visual_contract_revision_id="visual-v1",
        task_id="task",
        expected_task_status="running",
        expected_task_stage="cleaning",
        workflow_decision_id=decision_id,
        reason_code="full_page_cleaning_accepted",
        cleaned_pass_dispositions=(
            CleanedPassDispositionDraft("pass-a", "item-a", "result-a", "dep-a"),
            CleanedPassDispositionDraft("pass-b", "item-b", "result-b", "dep-b"),
        ),
        issue_changes=issue_changes,
        issue_relations=(),
    )


def _issue(issue_id, *, status, action, blocking=True):
    return IssueLifecycleChange(
        issue_id=issue_id,
        action=action,
        status=status,
        issue_type="full_page_cleaning_validation",
        is_blocking=blocking,
        target_type="page",
        target_id="page",
        page_id="page",
        discovered_stage="cleaning",
        root_stage="cleaning",
        severity="blocking" if blocking else "info",
    )
