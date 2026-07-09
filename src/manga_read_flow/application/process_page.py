from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from uuid import uuid4

from manga_read_flow.domain.provider_contracts import StageProvider
from manga_read_flow.workflow.engine import ProcessPageResult, WorkflowLoopEngine
from manga_read_flow.workflow.stage_executor import StageExecutor


@dataclass(frozen=True)
class ProcessPageCommand:
    page_id: str
    task_id: str | None = None


class ProcessPageService:
    def __init__(
        self,
        *,
        project_id: str,
        repositories,
        artifact_service,
        provider: StageProvider,
    ) -> None:
        self._project_id = project_id
        self._repositories = repositories
        self._artifact_service = artifact_service
        self._provider = provider

    def process_page(self, command: ProcessPageCommand) -> ProcessPageResult:
        profile_snapshot = self._ensure_fake_profile_snapshot()
        task_id = command.task_id or f"task-{uuid4()}"
        self._repositories.workflow_execution.create_task(
            task_id=task_id,
            target_type="page",
            target_id=command.page_id,
            task_type="process_page",
            status="queued",
            current_stage="detection",
            profile_snapshot_id=profile_snapshot.profile_snapshot_id,
        )
        stage_executor = StageExecutor(
            attempt_recorder=self._repositories.workflow_execution,
            evidence_writer=self._repositories.stage_evidence_writer,
            artifact_service=self._artifact_service,
        )
        engine = WorkflowLoopEngine(
            repositories=self._repositories,
            artifact_service=self._artifact_service,
            stage_executor=stage_executor,
            provider=self._provider,
        )
        return engine.run_task(task_id)

    def _ensure_fake_profile_snapshot(self):
        provider_identity = self._provider.identity
        settings = {
            "snapshot_schema_version": "slice05.v1",
            "source_profile_id": "fakeprovider_default",
            "source_profile_version": "1",
            "provider": {
                "name": provider_identity.provider_name,
                "model_id": provider_identity.model_id,
            },
            "retry_budgets": {
                "detection": 0,
                "ocr": 0,
                "translation": 0,
                "translation_check": 0,
                "cleaning": 0,
                "typesetting": 0,
                "export_check": 0,
            },
            "allow_warning_export": False,
            "retention": {
                "failed_attempt_artifacts": "retain",
                "successful_payloads": "metadata_only_allowed",
            },
        }
        settings_json = json.dumps(settings, sort_keys=True, separators=(",", ":"))
        settings_hash = sha256(settings_json.encode("utf-8")).hexdigest()
        return self._repositories.workflow_execution.ensure_profile_snapshot(
            profile_snapshot_id="profile-snapshot-fakeprovider-default",
            settings_json=settings_json,
            settings_hash=settings_hash,
        )
