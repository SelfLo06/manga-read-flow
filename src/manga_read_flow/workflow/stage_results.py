from __future__ import annotations

from manga_read_flow.domain.provider_contracts import ProviderOutcome, ProviderResult
from manga_read_flow.workflow.stage_executor import StageResult


def stage_error_code(stage_result: StageResult) -> str:
    if stage_result.artifact_errors:
        return stage_result.artifact_errors[0].code
    if stage_result.provider_result.error is not None:
        return stage_result.provider_result.error.code
    return "stage_failed"


def synthetic_stage_result(
    *,
    task_id: str,
    stage: str,
    page_id: str,
    attempt_id: str | None,
) -> StageResult:
    return StageResult(
        status="failed",
        stage=stage,
        task_id=task_id,
        attempt_id=attempt_id,
        target_type="page",
        target_id=page_id,
        provider_called=False,
        provider_result=ProviderResult(
            outcome=ProviderOutcome.FAILURE,
            provider_name="workflow-loop",
        ),
        candidate_outputs={},
    )
