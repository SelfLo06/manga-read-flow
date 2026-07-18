from __future__ import annotations

from pathlib import Path
import sqlite3

from manga_read_flow.persistence.acceptance_repository import (
    AcceptanceCommand,
    AcceptanceOutcome,
    AcceptanceRepository,
    AcceptedResult,
    AcceptedTextBlock,
    ActivePointerUpdate,
    ExpectedState,
    ExpectedStageStatus,
    IssueLifecycleChange,
    PageStatusUpdate,
    StageStatusUpdate,
    TaskProgressUpdate,
    WorkflowDecisionDraft,
)
from manga_read_flow.persistence.artifact_metadata_repository import (
    ArtifactMetadataRepository,
    initialize_artifact_metadata_schema,
)
from manga_read_flow.persistence.content_state_repository import (
    ActiveOcrInput,
    ActiveTranslationInput,
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
    ProcessingProfileSnapshot,
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
from manga_read_flow.persistence.visual_contract_repository import (
    CleaningResultDraft,
    VisualContractRepository,
    initialize_visual_contract_schema,
)
from manga_read_flow.persistence.full_page_cleaning_ledger_repository import (
    CleaningInventoryItemDraft,
    CleaningRecoveryLedger,
    CorrectionChainDraft,
    CorrectionChainSnapshot,
    CorrectionReservationSnapshot,
    FullPageCleaningLedgerRepository,
    InstanceCleaningResultDraft,
    InstanceCleaningResultSnapshot,
    PageCleaningRunDraft,
    PageCleaningRunSnapshot,
    SegmentCleaningDispositionDraft,
    initialize_full_page_cleaning_ledger_schema,
)
from manga_read_flow.persistence.full_page_cleaning_acceptance_repository import (
    CleaningIssueRelationDraft,
    FullPageCleaningAcceptanceCommand,
    FullPageCleaningAcceptanceRepository,
    FullPageCleaningBlockCommand,
    FullPageCleaningTransactionOutcome,
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
        self._full_page_cleaning_ledger = FullPageCleaningLedgerRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self._full_page_cleaning_acceptance = FullPageCleaningAcceptanceRepository(
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

    # Slice 1 ledger facade deliberately excludes acceptance and active-pointer writes.
    def create_or_replay_page_cleaning_run(
        self, draft: PageCleaningRunDraft
    ) -> PageCleaningRunSnapshot:
        return self._full_page_cleaning_ledger.create_or_replay_page_cleaning_run(draft)

    def freeze_cleaning_inventory(
        self,
        *,
        page_cleaning_run_id: str,
        inventory_fingerprint: str,
        items: tuple[CleaningInventoryItemDraft, ...],
    ) -> tuple[CleaningInventoryItemDraft, ...]:
        return self._full_page_cleaning_ledger.freeze_cleaning_inventory(
            page_cleaning_run_id=page_cleaning_run_id,
            inventory_fingerprint=inventory_fingerprint,
            items=items,
        )

    def transition_page_cleaning_run(
        self, *, page_cleaning_run_id: str, target_status: str
    ) -> PageCleaningRunSnapshot:
        return self._full_page_cleaning_ledger.transition_page_cleaning_run(
            page_cleaning_run_id=page_cleaning_run_id,
            target_status=target_status,
        )

    def load_page_cleaning_inventory(
        self, *, page_cleaning_run_id: str
    ) -> tuple[CleaningInventoryItemDraft, ...]:
        return self._full_page_cleaning_ledger.load_page_cleaning_inventory(
            page_cleaning_run_id=page_cleaning_run_id
        )

    def append_instance_cleaning_result(
        self,
        draft: InstanceCleaningResultDraft,
        *,
        inventory_item_ids: tuple[str, ...],
    ) -> InstanceCleaningResultSnapshot:
        return self._full_page_cleaning_ledger.append_instance_cleaning_result(
            draft,
            inventory_item_ids=inventory_item_ids,
        )

    def record_or_supersede_segment_disposition(
        self, draft: SegmentCleaningDispositionDraft
    ) -> None:
        self._full_page_cleaning_ledger.record_or_supersede_segment_disposition(draft)

    def list_current_segment_cleaning_dispositions(
        self, *, page_cleaning_run_id: str
    ):
        return self._full_page_cleaning_ledger.list_current_segment_cleaning_dispositions(
            page_cleaning_run_id=page_cleaning_run_id
        )

    def reserve_or_replay_cleaning_correction(
        self,
        *,
        chain: CorrectionChainDraft,
        correction_reservation_id: str,
        idempotency_key: str,
        reserved_attempt_id: str | None,
    ) -> CorrectionReservationSnapshot:
        return self._full_page_cleaning_ledger.reserve_or_replay_correction(
            chain=chain,
            correction_reservation_id=correction_reservation_id,
            idempotency_key=idempotency_key,
            reserved_attempt_id=reserved_attempt_id,
        )

    def reject_second_automatic_cleaning_correction(
        self, *, correction_chain_id: str
    ) -> None:
        self._full_page_cleaning_ledger.reject_second_automatic_correction(
            correction_chain_id=correction_chain_id
        )

    def mark_cleaning_correction_executing(
        self, *, correction_reservation_id: str
    ) -> CorrectionReservationSnapshot:
        return self._full_page_cleaning_ledger.mark_correction_reservation_executing(
            correction_reservation_id=correction_reservation_id
        )

    def complete_cleaning_correction(
        self, *, correction_reservation_id: str
    ) -> CorrectionReservationSnapshot:
        return self._full_page_cleaning_ledger.complete_correction_reservation(
            correction_reservation_id=correction_reservation_id
        )

    def abandon_cleaning_correction_after_crash(
        self, *, correction_reservation_id: str
    ) -> CorrectionReservationSnapshot:
        return self._full_page_cleaning_ledger.abandon_correction_reservation_after_crash(
            correction_reservation_id=correction_reservation_id
        )

    def load_full_page_cleaning_recovery(
        self, *, page_cleaning_run_id: str
    ) -> CleaningRecoveryLedger:
        return self._full_page_cleaning_ledger.load_recovery_ledger(
            page_cleaning_run_id=page_cleaning_run_id
        )

    def load_page_cleaning_recovery_ledger(
        self, *, page_cleaning_run_id: str
    ) -> CleaningRecoveryLedger:
        return self._full_page_cleaning_ledger.load_page_cleaning_recovery_ledger(
            page_cleaning_run_id=page_cleaning_run_id
        )

    def mark_unaccepted_cleaning_run_stale(
        self, *, page_cleaning_run_id: str, dependency_fingerprint: str
    ) -> str:
        return self._full_page_cleaning_ledger.mark_unaccepted_cleaning_run_stale(
            page_cleaning_run_id=page_cleaning_run_id,
            dependency_fingerprint=dependency_fingerprint,
        )

    def accept_page_cleaning_atomically(
        self, command: FullPageCleaningAcceptanceCommand
    ) -> FullPageCleaningTransactionOutcome:
        return self._full_page_cleaning_acceptance.accept_page_cleaning_atomically(command)

    def validate_active_cleaned_pointer_eligibility(
        self, command: FullPageCleaningAcceptanceCommand
    ) -> FullPageCleaningTransactionOutcome:
        return self._full_page_cleaning_acceptance.validate_active_cleaned_pointer_eligibility(
            command
        )

    def persist_cleaning_issue_lifecycle(
        self,
        *,
        issue_changes: tuple[IssueLifecycleChange, ...],
        relations: tuple[CleaningIssueRelationDraft, ...],
    ) -> None:
        self._full_page_cleaning_acceptance.persist_cleaning_issue_lifecycle(
            issue_changes=issue_changes,
            relations=relations,
        )

    def block_page_cleaning_atomically(
        self, command: FullPageCleaningBlockCommand
    ) -> FullPageCleaningTransactionOutcome:
        return self._full_page_cleaning_acceptance.block_page_cleaning_atomically(command)

    def mark_cleaning_facts_stale_and_clear_active_pointer_atomically(
        self,
        *,
        page_cleaning_run_id: str,
        expected_active_cleaned_artifact_id: str,
        dependency_fingerprint: str,
    ) -> FullPageCleaningTransactionOutcome:
        return self._full_page_cleaning_acceptance.mark_cleaning_facts_stale_and_clear_active_pointer_atomically(
            page_cleaning_run_id=page_cleaning_run_id,
            expected_active_cleaned_artifact_id=expected_active_cleaned_artifact_id,
            dependency_fingerprint=dependency_fingerprint,
        )


def initialize_repository_core_schema(connection: sqlite3.Connection) -> None:
    initialize_content_state_schema(connection)
    initialize_workflow_execution_schema(connection)
    initialize_artifact_metadata_schema(connection)
    initialize_visual_contract_schema(connection)
    initialize_full_page_cleaning_ledger_schema(connection)


__all__ = [
    "AcceptanceCommand",
    "AcceptanceOutcome",
    "AcceptedResult",
    "AcceptedTextBlock",
    "ActiveOcrInput",
    "ActivePointerUpdate",
    "ActiveTranslationInput",
    "ArtifactMetadataRepository",
    "AttemptEvidence",
    "AttemptReservation",
    "AttemptSnapshot",
    "BatchSnapshot",
    "ContentStateRepository",
    "ExpectedState",
    "ExpectedStageStatus",
    "GlossaryRepository",
    "ImportPageStateCommand",
    "ImportPageStateOutcome",
    "IssueLifecycleChange",
    "PageStatusUpdate",
    "PageSnapshot",
    "ProcessingTaskSnapshot",
    "ProcessingProfileSnapshot",
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
    "CleaningResultDraft",
    "VisualContractRepository",
    "FullPageCleaningLedgerRepository",
    "FullPageCleaningAcceptanceCommand",
    "CleaningIssueRelationDraft",
    "FullPageCleaningBlockCommand",
    "FullPageCleaningTransactionOutcome",
    "CleaningInventoryItemDraft",
    "CleaningRecoveryLedger",
    "CorrectionChainDraft",
    "CorrectionChainSnapshot",
    "CorrectionReservationSnapshot",
    "InstanceCleaningResultDraft",
    "InstanceCleaningResultSnapshot",
    "PageCleaningRunDraft",
    "PageCleaningRunSnapshot",
    "SegmentCleaningDispositionDraft",
    "initialize_repository_core_schema",
]
