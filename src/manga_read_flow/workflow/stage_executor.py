from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from manga_read_flow.artifacts.service import ArtifactRegistrationError
from manga_read_flow.domain.artifacts import ArtifactSafetyMetadata
from manga_read_flow.domain.artifacts import ProcessingArtifactSnapshot
from manga_read_flow.domain.provider_contracts import (
    ProviderIdentity,
    ProviderOutcome,
    ProviderRequest,
    ProviderResult,
    ProviderTempFileRef,
    StageProvider,
)
from manga_read_flow.persistence.repository_uow_core import (
    AttemptEvidence,
    AttemptReservation,
    ToolRunOutcome,
    ToolRunStart,
    UnitOfWorkOutcome,
)


class AttemptRecorder(Protocol):
    def reserve_attempt(self, command: AttemptReservation) -> UnitOfWorkOutcome:
        raise NotImplementedError


class StageExecutionConflictError(RuntimeError):
    """Raised when attempt reservation rejects the supplied execution context."""


@dataclass(frozen=True)
class StageExecutionContext:
    project_id: str
    task_id: str
    attempt_id: str
    tool_run_id: str
    request_id: str
    stage: str
    target_type: str
    target_id: str
    batch_id: str
    page_id: str
    text_block_ids: tuple[str, ...]
    expected_task_status: str
    expected_current_stage: str
    runner_id: str
    attempt_temp_root: Path
    input_hash: str
    config_hash: str
    context_hash: str
    source_language: str
    target_language: str
    inputs: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StageArtifactError:
    temp_ref_id: str
    code: str
    sanitized_message: str


@dataclass(frozen=True)
class StageResult:
    status: str
    stage: str
    task_id: str
    attempt_id: str
    target_type: str
    target_id: str
    provider_called: bool
    provider_result: ProviderResult
    candidate_outputs: dict[str, object]
    registered_artifacts: tuple[ProcessingArtifactSnapshot, ...] = ()
    artifact_errors: tuple[StageArtifactError, ...] = ()
    tool_run_id: str | None = None


class StageExecutor:
    def __init__(self, *, attempt_recorder, evidence_writer, artifact_service) -> None:
        self._attempt_recorder: AttemptRecorder = attempt_recorder
        self._evidence_writer = evidence_writer
        self._artifact_service = artifact_service

    def execute(self, context: StageExecutionContext, provider: StageProvider) -> StageResult:
        provider_identity = provider.identity
        context.attempt_temp_root.mkdir(parents=True, exist_ok=True)
        reservation = self._attempt_recorder.reserve_attempt(
            AttemptReservation(
                task_id=context.task_id,
                attempt_id=context.attempt_id,
                stage=context.stage,
                target_type=context.target_type,
                target_id=context.target_id,
                expected_task_status=context.expected_task_status,
                expected_current_stage=context.expected_current_stage,
                runner_id=context.runner_id,
            )
        )
        if not reservation.committed:
            conflicts = ", ".join(reservation.conflict_fields) or "unknown"
            raise StageExecutionConflictError(
                f"Stage attempt reservation was rejected: {conflicts}"
            )

        self._evidence_writer.start_tool_run(
            ToolRunStart(
                tool_run_id=context.tool_run_id,
                task_id=context.task_id,
                attempt_id=context.attempt_id,
                stage=context.stage,
                tool_name=provider_identity.tool_name,
                tool_version=provider_identity.tool_version,
                provider_name=provider_identity.provider_name,
                model_id=provider_identity.model_id,
                input_hash=context.input_hash,
                config_hash=context.config_hash,
            )
        )

        provider_result = _result_with_provider_identity(
            provider.run(_provider_request(context)),
            provider_identity,
        )
        provider_status = _status_for_outcome(provider_result.outcome)
        error = provider_result.error
        self._evidence_writer.record_tool_outcome(
            ToolRunOutcome(
                tool_run_id=context.tool_run_id,
                status=provider_status,
                error_code=error.code if error is not None else None,
                error_class=error.kind if error is not None else None,
                is_provider_refusal=error.is_provider_refusal
                if error is not None
                else False,
                sanitized_message=error.sanitized_message if error is not None else None,
            )
        )
        registered_artifacts, artifact_errors = _register_temp_artifacts(
            artifact_service=self._artifact_service,
            context=context,
            temp_files=provider_result.temp_files,
        )
        stage_status = "failed" if artifact_errors else provider_status
        attempt_error_code = error.code if error is not None else None
        attempt_message = error.sanitized_message if error is not None else None
        if artifact_errors:
            attempt_error_code = "artifact_registration_failed"
            attempt_message = "stage output artifact registration failed"

        self._evidence_writer.record_attempt_evidence(
            AttemptEvidence(
                attempt_id=context.attempt_id,
                provider_name=provider_result.provider_name,
                model_id=provider_result.model_id,
                tool_name=provider_identity.tool_name,
                status=stage_status,
                error_code=attempt_error_code,
                sanitized_message=attempt_message,
            )
        )

        return StageResult(
            status=stage_status,
            stage=context.stage,
            task_id=context.task_id,
            attempt_id=context.attempt_id,
            target_type=context.target_type,
            target_id=context.target_id,
            provider_called=True,
            provider_result=provider_result,
            candidate_outputs=provider_result.payload,
            registered_artifacts=registered_artifacts,
            artifact_errors=artifact_errors,
            tool_run_id=context.tool_run_id,
        )


def _provider_request(context: StageExecutionContext) -> ProviderRequest:
    return ProviderRequest(
        request_id=context.request_id,
        stage=context.stage,
        target_type=context.target_type,
        target_id=context.target_id,
        page_id=context.page_id,
        text_block_ids=context.text_block_ids,
        attempt_temp_root=context.attempt_temp_root,
        input_hash=context.input_hash,
        config_hash=context.config_hash,
        context_hash=context.context_hash,
        source_language=context.source_language,
        target_language=context.target_language,
        inputs=context.inputs,
    )


def _status_for_outcome(outcome: ProviderOutcome) -> str:
    return {
        ProviderOutcome.SUCCESS: "succeeded",
        ProviderOutcome.PARTIAL_SUCCESS: "partial_success",
        ProviderOutcome.FAILURE: "failed",
        ProviderOutcome.REFUSAL: "refused",
        ProviderOutcome.INVALID_OUTPUT: "invalid_output",
    }[outcome]


def _result_with_provider_identity(
    result: ProviderResult,
    provider_identity: ProviderIdentity,
) -> ProviderResult:
    if (
        result.provider_name == provider_identity.provider_name
        and result.model_id == provider_identity.model_id
    ):
        return result
    return replace(
        result,
        provider_name=provider_identity.provider_name,
        model_id=provider_identity.model_id,
    )


def _register_temp_artifacts(
    *,
    artifact_service,
    context: StageExecutionContext,
    temp_files: tuple[ProviderTempFileRef, ...],
) -> tuple[tuple[ProcessingArtifactSnapshot, ...], tuple[StageArtifactError, ...]]:
    registered_artifacts: list[ProcessingArtifactSnapshot] = []
    artifact_errors: list[StageArtifactError] = []
    for temp_file in temp_files:
        if temp_file.expected_artifact_type is None:
            continue
        try:
            _require_attempt_temp_path(temp_file.temp_path, context.attempt_temp_root)
            if temp_file.media_type == "application/json":
                artifact = artifact_service.register_stage_json(
                    temp_path=temp_file.temp_path,
                    batch_id=context.batch_id,
                    page_id=context.page_id,
                    owner_type="page",
                    owner_id=context.page_id,
                    artifact_type=temp_file.expected_artifact_type,
                    source_stage=context.stage,
                    safety=_artifact_safety(temp_file.safety_flags),
                    dependency_hash=context.input_hash,
                )
            else:
                artifact = artifact_service.register_stage_output(
                    temp_path=temp_file.temp_path,
                    batch_id=context.batch_id,
                    page_id=context.page_id,
                    owner_type="page",
                    owner_id=context.page_id,
                    artifact_type=temp_file.expected_artifact_type,
                    source_stage=context.stage,
                    media_type=temp_file.media_type,
                    safety=_artifact_safety(temp_file.safety_flags),
                    dependency_hash=context.input_hash,
                )
            registered_artifacts.append(artifact)
        except (ArtifactRegistrationError, ValueError):
            artifact_errors.append(
                StageArtifactError(
                    temp_ref_id=temp_file.temp_ref_id,
                    code="artifact_registration_failed",
                    sanitized_message="stage output artifact registration failed",
                )
            )
    return tuple(registered_artifacts), tuple(artifact_errors)


def _require_attempt_temp_path(temp_path: Path, attempt_temp_root: Path) -> None:
    resolved_temp_path = temp_path.resolve(strict=False)
    resolved_root = attempt_temp_root.resolve(strict=False)
    try:
        resolved_temp_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ArtifactRegistrationError(
            "Provider temp file must stay under the attempt temp root."
        ) from exc


def _artifact_safety(safety_flags: dict[str, bool]) -> ArtifactSafetyMetadata:
    allowed = ArtifactSafetyMetadata.__dataclass_fields__
    return ArtifactSafetyMetadata(
        **{
            field_name: bool(value)
            for field_name, value in safety_flags.items()
            if field_name in allowed
        }
    )
