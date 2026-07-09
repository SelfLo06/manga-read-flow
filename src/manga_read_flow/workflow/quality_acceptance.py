from __future__ import annotations

import json
from uuid import uuid4

from manga_read_flow.persistence.repository_uow_core import IssueLifecycleChange
from manga_read_flow.quality import IssueDraft


def issue_changes_from_drafts(
    issue_drafts: tuple[IssueDraft, ...],
) -> tuple[IssueLifecycleChange, ...]:
    changes: list[IssueLifecycleChange] = []
    for draft in issue_drafts:
        changes.append(
            IssueLifecycleChange(
                issue_id=f"issue-{draft.issue_type}-{uuid4()}",
                action="create",
                status=draft.status,
                issue_type=draft.issue_type,
                is_blocking=draft.is_blocking,
                target_type=draft.target_type,
                target_id=draft.target_id,
                batch_id=draft.batch_id,
                page_id=draft.page_id,
                text_block_id=draft.text_block_id,
                discovered_stage=draft.discovered_stage,
                root_stage=draft.root_stage,
                error_code=draft.error_code,
                severity=draft.severity,
                message_key=draft.message_key,
                message_params_json=json.dumps(
                    draft.message_params,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                suggested_action_key=draft.suggested_action_key,
                related_attempt_id=draft.related_attempt_id,
                related_tool_run_id=draft.related_tool_run_id,
                related_artifact_id=draft.related_artifact_id,
                applies_to_result_id=draft.applies_to_result_id,
                input_hash=draft.input_hash,
                config_hash=draft.config_hash,
                dedupe_key=draft.dedupe_key,
            )
        )
    return tuple(changes)
