from __future__ import annotations

import pytest

from manga_read_flow.workflow.engine import (
    GroupingWorkflowDecisionInput,
    GroupingWorkflowIssue,
    WorkflowLoopEngine,
)


def test_grouping_workflow_accepts_only_produced_current_candidate_without_blockers():
    decision = WorkflowLoopEngine.decide_grouping(_input())

    assert decision.decision_type == "accept"
    assert decision.reason_code == "grouping_candidate_accepted"


@pytest.mark.parametrize(
    "issue",
    [
        GroupingWorkflowIssue("warning-blocker", "open", True),
        GroupingWorkflowIssue("blocking-severity", "open", True),
    ],
)
def test_grouping_workflow_uses_is_blocking_and_lifecycle_not_severity(issue):
    decision = WorkflowLoopEngine.decide_grouping(_input(issues=(issue,)))

    assert decision.decision_type == "block"
    assert decision.reason_code == "grouping_blocking_quality_issue"


@pytest.mark.parametrize(
    "issue",
    [
        GroupingWorkflowIssue("warning", "open", False),
        GroupingWorkflowIssue("resolved-blocker", "resolved", True),
    ],
)
def test_grouping_workflow_accepts_nonblocking_or_resolved_issue(issue):
    decision = WorkflowLoopEngine.decide_grouping(_input(issues=(issue,)))

    assert decision.decision_type == "accept"
    assert decision.linked_issue_ids == (issue.issue_id,)


def test_grouping_workflow_blocks_dependency_drift_and_stale_check():
    dependency = WorkflowLoopEngine.decide_grouping(_input(dependencies_valid=False))
    check = WorkflowLoopEngine.decide_grouping(_input(check_applicable=False))

    assert dependency.reason_code == "grouping_dependencies_changed"
    assert check.reason_code == "grouping_check_not_applicable"


def test_grouping_workflow_blocks_incomplete_candidate_without_inventing_fallback():
    decision = WorkflowLoopEngine.decide_grouping(
        _input(candidate_disposition="INCOMPLETE", retry_budget=2)
    )

    assert decision.decision_type == "block"
    assert decision.reason_code == "grouping_candidate_not_acceptable"


def _input(
    *,
    issues=(),
    dependencies_valid=True,
    check_applicable=True,
    candidate_disposition="PRODUCED",
    retry_budget=0,
):
    return GroupingWorkflowDecisionInput(
        snapshot_id="snapshot",
        check_result_id="check",
        execution_id="execution",
        candidate_disposition=candidate_disposition,
        related_issues=issues,
        retry_budget=retry_budget,
        dependencies_valid=dependencies_valid,
        check_applicable=check_applicable,
        expected_active_grouping_snapshot_id=None,
        expected_page_grouping_state_version=None,
    )
