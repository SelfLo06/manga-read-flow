from __future__ import annotations

from pathlib import Path
import sqlite3

from manga_read_flow.persistence.acceptance_repository import (
    AcceptanceCommand,
    AcceptanceOutcome,
    AcceptanceRepository,
    AcceptedResult,
    ActivePointerUpdate,
    ExpectedState,
    IssueLifecycleChange,
    StageStatusUpdate,
    TaskProgressUpdate,
    WorkflowDecisionDraft,
)
from manga_read_flow.persistence.artifact_metadata_repository import (
    ArtifactMetadataRepository,
    initialize_artifact_metadata_schema,
)
from manga_read_flow.persistence.content_state_repository import (
    BatchSnapshot,
    ContentStateRepository,
    GlossaryRepository,
    ImportPageStateCommand,
    ImportPageStateOutcome,
    PageSnapshot,
    ResultVersionRepository,
    TextBlockSnapshot,
    initialize_content_state_schema,
)
from manga_read_flow.persistence.workflow_execution_repository import (
    AttemptEvidence,
    AttemptReservation,
    AttemptSnapshot,
    ProcessingTaskSnapshot,
    QualityIssueRepository,
    ReadinessQueryRepository,
    ReadinessSnapshot,
    StageEvidenceWriter,
    ToolRunOutcome,
    ToolRunSnapshot,
    ToolRunStart,
    UnitOfWorkOutcome,
    WorkflowExecutionRepository,
    initialize_workflow_execution_schema,
)


class ProjectUnitOfWork:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._content_state = ContentStateRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self._workflow_execution = WorkflowExecutionRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self._acceptance = AcceptanceRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )

    def import_page_original(
        self,
        command: ImportPageStateCommand,
    ) -> ImportPageStateOutcome:
        return self._content_state.import_page_original(command)

    def reserve_attempt(self, command: AttemptReservation) -> UnitOfWorkOutcome:
        return self._workflow_execution.reserve_attempt(command)

    def accept_stage(self, command: AcceptanceCommand) -> AcceptanceOutcome:
        return self._acceptance.accept_stage(command)


def initialize_repository_core_schema(connection: sqlite3.Connection) -> None:
    initialize_content_state_schema(connection)
    initialize_workflow_execution_schema(connection)
    initialize_artifact_metadata_schema(connection)


__all__ = [
    "AcceptanceCommand",
    "AcceptanceOutcome",
    "AcceptedResult",
    "ActivePointerUpdate",
    "ArtifactMetadataRepository",
    "AttemptEvidence",
    "AttemptReservation",
    "AttemptSnapshot",
    "BatchSnapshot",
    "ContentStateRepository",
    "ExpectedState",
    "GlossaryRepository",
    "ImportPageStateCommand",
    "ImportPageStateOutcome",
    "IssueLifecycleChange",
    "PageSnapshot",
    "ProcessingTaskSnapshot",
    "ProjectUnitOfWork",
    "QualityIssueRepository",
    "ReadinessQueryRepository",
    "ReadinessSnapshot",
    "ResultVersionRepository",
    "StageEvidenceWriter",
    "StageStatusUpdate",
    "TaskProgressUpdate",
    "TextBlockSnapshot",
    "ToolRunOutcome",
    "ToolRunSnapshot",
    "ToolRunStart",
    "UnitOfWorkOutcome",
    "WorkflowDecisionDraft",
    "WorkflowExecutionRepository",
    "initialize_repository_core_schema",
]
