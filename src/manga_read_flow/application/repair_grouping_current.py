from __future__ import annotations

from dataclasses import dataclass

from manga_read_flow.persistence.grouping_acceptance_repository import GroupingRepairOutcome


@dataclass(frozen=True)
class RepairGroupingCurrentCommand:
    page_id: str
    expected_active_grouping_snapshot_id: str
    expected_page_grouping_state_version: int
    triggering_operation_id: str


class RepairGroupingCurrentApplicationService:
    """Fail-closed recovery for a legacy current pointer with stale dependencies."""

    def __init__(self, *, repositories) -> None:
        self._repositories = repositories

    def repair(self, command: RepairGroupingCurrentCommand) -> GroupingRepairOutcome:
        if (
            not command.page_id
            or not command.expected_active_grouping_snapshot_id
            or command.expected_page_grouping_state_version < 1
            or not command.triggering_operation_id
        ):
            raise ValueError("Grouping repair command is incomplete.")
        return self._repositories.grouping_acceptance.repair_dependency_mismatch(
            page_id=command.page_id,
            expected_active_grouping_snapshot_id=command.expected_active_grouping_snapshot_id,
            expected_page_grouping_state_version=command.expected_page_grouping_state_version,
            triggering_operation_id=command.triggering_operation_id,
        )
