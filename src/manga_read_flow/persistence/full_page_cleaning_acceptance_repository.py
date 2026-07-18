from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from manga_read_flow.persistence.acceptance_repository import (
    IssueLifecycleChange,
    _apply_issue_change,
)
from manga_read_flow.persistence.sqlite_repository_helpers import connect_existing, utc_now


@dataclass(frozen=True)
class CombinedCleaningCandidateDraft:
    combined_cleaning_candidate_id: str
    page_cleaning_run_id: str
    source_artifact_id: str
    source_hash: str
    combined_artifact_id: str
    combined_hash: str
    combined_delta_artifact_id: str
    combined_delta_hash: str
    composition_config_hash: str
    member_set_fingerprint: str


@dataclass(frozen=True)
class CombinedCleaningCandidateMemberDraft:
    instance_cleaning_result_id: str
    bubble_instance_revision_id: str
    composition_key: str
    actual_changed_artifact_id: str
    actual_changed_hash: str


@dataclass(frozen=True)
class CombinedCleaningCandidateSnapshot:
    combined_cleaning_candidate_id: str
    page_cleaning_run_id: str
    source_artifact_id: str
    source_hash: str
    combined_artifact_id: str
    combined_hash: str
    combined_delta_artifact_id: str
    combined_delta_hash: str
    composition_config_hash: str
    member_set_fingerprint: str
    status: str
    member_result_ids: tuple[str, ...]


@dataclass(frozen=True)
class PageCleaningValidationDraft:
    page_cleaning_validation_record_id: str
    page_cleaning_run_id: str
    combined_cleaning_candidate_id: str
    validation_fingerprint: str
    status: str
    inventory_complete: bool
    dispositions_unique: bool
    missing_attribution_count: int
    duplicate_attribution_count: int
    pairwise_overlap_pixel_count: int
    wrong_instance_write_pixel_count: int
    outside_safe_pixel_count: int
    protected_pixel_count: int
    uncertainty_pixel_count: int
    boundary_damage_pixel_count: int
    residue_pixel_count: int
    combined_delta_matches_member_union: bool
    source_integrity_valid: bool
    combined_integrity_valid: bool
    dependencies_fresh: bool
    evidence_artifact_id: str | None
    overlap_evidence_artifact_id: str | None
    wrong_instance_evidence_artifact_id: str | None
    validator_summary: str


@dataclass(frozen=True)
class PageCleaningValidationSnapshot:
    page_cleaning_validation_record_id: str
    page_cleaning_run_id: str
    combined_cleaning_candidate_id: str
    validation_fingerprint: str
    status: str
    selection_status: str


@dataclass(frozen=True)
class CleaningIssueRelationDraft:
    cleaning_quality_issue_relation_id: str
    issue_id: str
    relation_type: str
    page_cleaning_run_id: str | None = None
    cleaning_inventory_item_id: str | None = None
    instance_cleaning_result_id: str | None = None
    combined_cleaning_candidate_id: str | None = None
    page_cleaning_validation_record_id: str | None = None
    correction_reservation_id: str | None = None
    workflow_decision_id: str | None = None


@dataclass(frozen=True)
class CleanedPassDispositionDraft:
    accepted_segment_cleaning_disposition_id: str
    cleaning_inventory_item_id: str
    instance_cleaning_result_id: str
    dependency_fingerprint: str


@dataclass(frozen=True)
class FullPageCleaningAcceptanceCommand:
    page_cleaning_acceptance_id: str
    idempotency_key: str
    page_cleaning_run_id: str
    page_id: str
    combined_cleaning_candidate_id: str
    page_cleaning_validation_record_id: str
    cleaned_artifact_id: str
    expected_active_cleaned_artifact_id: str | None
    expected_original_artifact_id: str
    expected_visual_contract_revision_id: str
    task_id: str
    expected_task_status: str
    expected_task_stage: str
    workflow_decision_id: str
    reason_code: str
    cleaned_pass_dispositions: tuple[CleanedPassDispositionDraft, ...]
    issue_changes: tuple[IssueLifecycleChange, ...] = ()
    issue_relations: tuple[CleaningIssueRelationDraft, ...] = ()
    attempt_id: str | None = None
    expected_attempt_status: str = "running"
    retry_budget_after_json: str = "{}"


@dataclass(frozen=True)
class FullPageCleaningBlockCommand:
    page_cleaning_run_id: str
    page_id: str
    task_id: str
    expected_task_status: str
    expected_task_stage: str
    workflow_decision_id: str
    reason_code: str
    issue_changes: tuple[IssueLifecycleChange, ...]
    issue_relations: tuple[CleaningIssueRelationDraft, ...]
    attempt_id: str | None = None
    expected_attempt_status: str = "running"


@dataclass(frozen=True)
class FullPageCleaningTransactionOutcome:
    committed: bool
    result_code: str
    reload_required: bool = False
    active_cleaned_artifact_id: str | None = None
    cleaned_pass_count: int = 0


@dataclass(frozen=True)
class FullPageCleaningAcceptanceRecovery:
    candidates: tuple[CombinedCleaningCandidateSnapshot, ...]
    validations: tuple[PageCleaningValidationSnapshot, ...]
    accepted_disposition_ids: tuple[str, ...]
    accepted_dispositions: tuple[CleanedPassDispositionDraft, ...]
    acceptance_id: str | None
    acceptance_status: str | None
    issue_relation_ids: tuple[str, ...]


class FullPageCleaningAcceptanceRepository:
    """Slice 2 persistence and short atomic decision transactions."""

    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def create_combined_candidate_with_members(
        self,
        draft: CombinedCleaningCandidateDraft,
        members: tuple[CombinedCleaningCandidateMemberDraft, ...],
    ) -> CombinedCleaningCandidateSnapshot:
        if not members:
            raise ValueError("Combined candidate requires at least one member.")
        if len({member.instance_cleaning_result_id for member in members}) != len(members):
            raise ValueError("Combined candidate result members must be unique.")
        if len({member.bubble_instance_revision_id for member in members}) != len(members):
            raise ValueError("Combined candidate instance revisions must be unique.")
        if len({member.composition_key for member in members}) != len(members):
            raise ValueError("Combined candidate composition keys must be unique.")
        ordered = tuple(sorted(members, key=lambda member: member.composition_key))
        with connect_existing(self._project_db_path) as connection:
            existing = connection.execute(
                "SELECT * FROM combined_cleaning_candidates WHERE project_id = ? "
                "AND member_set_fingerprint = ? AND page_cleaning_run_id = ?",
                (self._project_id, draft.member_set_fingerprint, draft.page_cleaning_run_id),
            ).fetchone()
            if existing is not None:
                snapshot = _candidate_snapshot(connection, existing)
                _verify_candidate_replay(snapshot, draft, ordered, connection)
                return snapshot

            run = connection.execute(
                "SELECT * FROM page_cleaning_runs WHERE project_id = ? AND page_cleaning_run_id = ?",
                (self._project_id, draft.page_cleaning_run_id),
            ).fetchone()
            if run is None or run["status"] != "executing":
                raise ValueError("Combined candidate requires an executing PageCleaningRun.")
            if (
                run["source_artifact_id"] != draft.source_artifact_id
                or run["source_hash"] != draft.source_hash
            ):
                raise ValueError("Combined candidate source must match its run.")
            _require_artifact(
                connection,
                self._project_id,
                draft.combined_artifact_id,
                draft.combined_hash,
            )
            _require_artifact(
                connection,
                self._project_id,
                draft.combined_delta_artifact_id,
                draft.combined_delta_hash,
            )
            for member in ordered:
                result = connection.execute(
                    "SELECT * FROM instance_cleaning_results WHERE project_id = ? "
                    "AND instance_cleaning_result_id = ?",
                    (self._project_id, member.instance_cleaning_result_id),
                ).fetchone()
                if result is None:
                    raise ValueError("Combined member result is missing.")
                if (
                    result["page_cleaning_run_id"] != draft.page_cleaning_run_id
                    or result["bubble_instance_revision_id"] != member.bubble_instance_revision_id
                    or result["source_hash"] != draft.source_hash
                    or result["status"] not in {"validated", "ready_for_composition"}
                    or result["stale_by_dependency_fingerprint"] is not None
                    or result["actual_changed_artifact_id"] != member.actual_changed_artifact_id
                ):
                    raise ValueError("Combined member is not a fresh validated result for this run.")
                _require_artifact(
                    connection,
                    self._project_id,
                    member.actual_changed_artifact_id,
                    member.actual_changed_hash,
                )
            connection.execute(
                """
                INSERT INTO combined_cleaning_candidates (
                    combined_cleaning_candidate_id, project_id, page_cleaning_run_id,
                    source_artifact_id, source_hash, combined_artifact_id, combined_hash,
                    combined_delta_artifact_id, combined_delta_hash,
                    composition_config_hash, member_set_fingerprint, status,
                    accepted_validation_record_id, supersedes_candidate_id,
                    stale_by_dependency_fingerprint, created_at, accepted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'official_unselected',
                          NULL, NULL, NULL, ?, NULL)
                """,
                (
                    draft.combined_cleaning_candidate_id,
                    self._project_id,
                    draft.page_cleaning_run_id,
                    draft.source_artifact_id,
                    draft.source_hash,
                    draft.combined_artifact_id,
                    draft.combined_hash,
                    draft.combined_delta_artifact_id,
                    draft.combined_delta_hash,
                    draft.composition_config_hash,
                    draft.member_set_fingerprint,
                    utc_now(),
                ),
            )
            for member in ordered:
                connection.execute(
                    """
                    INSERT INTO combined_cleaning_candidate_members (
                        combined_cleaning_candidate_id, instance_cleaning_result_id,
                        project_id, page_cleaning_run_id, bubble_instance_revision_id,
                        composition_key, actual_changed_artifact_id, actual_changed_hash,
                        selection_status, accepted_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed', NULL, ?)
                    """,
                    (
                        draft.combined_cleaning_candidate_id,
                        member.instance_cleaning_result_id,
                        self._project_id,
                        draft.page_cleaning_run_id,
                        member.bubble_instance_revision_id,
                        member.composition_key,
                        member.actual_changed_artifact_id,
                        member.actual_changed_hash,
                        utc_now(),
                    ),
                )
            connection.execute(
                "UPDATE page_cleaning_runs SET status = 'validating' "
                "WHERE project_id = ? AND page_cleaning_run_id = ?",
                (self._project_id, draft.page_cleaning_run_id),
            )
            row = connection.execute(
                "SELECT * FROM combined_cleaning_candidates WHERE combined_cleaning_candidate_id = ?",
                (draft.combined_cleaning_candidate_id,),
            ).fetchone()
            return _candidate_snapshot(connection, row)

    def append_page_cleaning_validation(
        self,
        draft: PageCleaningValidationDraft,
    ) -> PageCleaningValidationSnapshot:
        if draft.status not in {"pass", "fail"}:
            raise ValueError("Page validation status must be pass or fail.")
        if draft.status == "pass" and not _draft_is_passing_validation(draft):
            raise ValueError("A passing page validation cannot contain failed predicates.")
        with connect_existing(self._project_db_path) as connection:
            existing = connection.execute(
                "SELECT * FROM page_cleaning_validation_records WHERE project_id = ? "
                "AND combined_cleaning_candidate_id = ? AND validation_fingerprint = ?",
                (
                    self._project_id,
                    draft.combined_cleaning_candidate_id,
                    draft.validation_fingerprint,
                ),
            ).fetchone()
            if existing is not None:
                _verify_validation_replay(existing, draft)
                return _validation_snapshot(existing)
            candidate = connection.execute(
                "SELECT * FROM combined_cleaning_candidates WHERE project_id = ? "
                "AND combined_cleaning_candidate_id = ?",
                (self._project_id, draft.combined_cleaning_candidate_id),
            ).fetchone()
            if candidate is None or candidate["page_cleaning_run_id"] != draft.page_cleaning_run_id:
                raise ValueError("Page validation candidate does not belong to its run.")
            connection.execute(
                """
                INSERT INTO page_cleaning_validation_records (
                    page_cleaning_validation_record_id, project_id,
                    page_cleaning_run_id, combined_cleaning_candidate_id,
                    validation_fingerprint, status, selection_status,
                    inventory_complete, dispositions_unique,
                    missing_attribution_count, duplicate_attribution_count,
                    pairwise_overlap_pixel_count, wrong_instance_write_pixel_count,
                    outside_safe_pixel_count, protected_pixel_count,
                    uncertainty_pixel_count, boundary_damage_pixel_count,
                    residue_pixel_count, combined_delta_matches_member_union,
                    source_integrity_valid, combined_integrity_valid,
                    dependencies_fresh, evidence_artifact_id,
                    overlap_evidence_artifact_id, wrong_instance_evidence_artifact_id,
                    validator_summary, stale_by_dependency_fingerprint,
                    created_at, accepted_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'recorded', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL)
                """,
                _validation_insert_values(self._project_id, draft),
            )
            if draft.status == "pass":
                connection.execute(
                    "UPDATE combined_cleaning_candidates SET status = 'validated' "
                    "WHERE project_id = ? AND combined_cleaning_candidate_id = ?",
                    (self._project_id, draft.combined_cleaning_candidate_id),
                )
                connection.execute(
                    "UPDATE page_cleaning_runs SET status = 'candidate_ready' "
                    "WHERE project_id = ? AND page_cleaning_run_id = ?",
                    (self._project_id, draft.page_cleaning_run_id),
                )
            row = connection.execute(
                "SELECT * FROM page_cleaning_validation_records "
                "WHERE page_cleaning_validation_record_id = ?",
                (draft.page_cleaning_validation_record_id,),
            ).fetchone()
            return _validation_snapshot(row)

    def persist_cleaning_issue_lifecycle(
        self,
        *,
        issue_changes: tuple[IssueLifecycleChange, ...],
        relations: tuple[CleaningIssueRelationDraft, ...],
    ) -> None:
        with connect_existing(self._project_db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            for change in issue_changes:
                _apply_issue_change(connection, self._project_id, change)
            for relation in relations:
                _insert_issue_relation(connection, self._project_id, relation)

    def load_page_cleaning_acceptance_recovery(
        self, *, page_cleaning_run_id: str
    ) -> FullPageCleaningAcceptanceRecovery:
        with connect_existing(self._project_db_path) as connection:
            candidate_rows = connection.execute(
                "SELECT * FROM combined_cleaning_candidates WHERE project_id = ? "
                "AND page_cleaning_run_id = ? ORDER BY created_at, combined_cleaning_candidate_id",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
            member_rows = connection.execute(
                "SELECT combined_cleaning_candidate_id, instance_cleaning_result_id "
                "FROM combined_cleaning_candidate_members WHERE project_id = ? "
                "AND page_cleaning_run_id = ? ORDER BY composition_key",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
            validation_rows = connection.execute(
                "SELECT * FROM page_cleaning_validation_records WHERE project_id = ? "
                "AND page_cleaning_run_id = ? ORDER BY created_at, page_cleaning_validation_record_id",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
            disposition_rows = connection.execute(
                "SELECT accepted_segment_cleaning_disposition_id, "
                "cleaning_inventory_item_id, instance_cleaning_result_id, "
                "dependency_fingerprint "
                "FROM accepted_segment_cleaning_dispositions WHERE project_id = ? "
                "AND page_cleaning_run_id = ? ORDER BY accepted_segment_cleaning_disposition_id",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
            acceptance = connection.execute(
                "SELECT page_cleaning_acceptance_id, status FROM page_cleaning_acceptances "
                "WHERE project_id = ? AND page_cleaning_run_id = ?",
                (self._project_id, page_cleaning_run_id),
            ).fetchone()
            relation_rows = connection.execute(
                """
                SELECT cleaning_quality_issue_relation_id
                FROM cleaning_quality_issue_relations
                WHERE project_id = ? AND (
                    page_cleaning_run_id = ? OR
                    combined_cleaning_candidate_id IN (
                        SELECT combined_cleaning_candidate_id
                        FROM combined_cleaning_candidates
                        WHERE project_id = ? AND page_cleaning_run_id = ?
                    ) OR
                    page_cleaning_validation_record_id IN (
                        SELECT page_cleaning_validation_record_id
                        FROM page_cleaning_validation_records
                        WHERE project_id = ? AND page_cleaning_run_id = ?
                    )
                )
                ORDER BY cleaning_quality_issue_relation_id
                """,
                (
                    self._project_id,
                    page_cleaning_run_id,
                    self._project_id,
                    page_cleaning_run_id,
                    self._project_id,
                    page_cleaning_run_id,
                ),
            ).fetchall()
        members_by_candidate: dict[str, list[str]] = {}
        for row in member_rows:
            members_by_candidate.setdefault(
                row["combined_cleaning_candidate_id"], []
            ).append(row["instance_cleaning_result_id"])
        return FullPageCleaningAcceptanceRecovery(
            candidates=tuple(
                _candidate_snapshot_from_member_ids(
                    row,
                    tuple(
                        members_by_candidate.get(
                            row["combined_cleaning_candidate_id"], []
                        )
                    ),
                )
                for row in candidate_rows
            ),
            validations=tuple(_validation_snapshot(row) for row in validation_rows),
            accepted_disposition_ids=tuple(row[0] for row in disposition_rows),
            accepted_dispositions=tuple(
                CleanedPassDispositionDraft(
                    row["accepted_segment_cleaning_disposition_id"],
                    row["cleaning_inventory_item_id"],
                    row["instance_cleaning_result_id"],
                    row["dependency_fingerprint"],
                )
                for row in disposition_rows
            ),
            acceptance_id=None if acceptance is None else acceptance[0],
            acceptance_status=None if acceptance is None else acceptance[1],
            issue_relation_ids=tuple(row[0] for row in relation_rows),
        )

    def accept_page_cleaning_atomically(
        self,
        command: FullPageCleaningAcceptanceCommand,
    ) -> FullPageCleaningTransactionOutcome:
        try:
            with connect_existing(self._project_db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                replay = connection.execute(
                    "SELECT * FROM page_cleaning_acceptances WHERE project_id = ? "
                    "AND idempotency_key = ?",
                    (self._project_id, command.idempotency_key),
                ).fetchone()
                if replay is not None:
                    if (
                        replay["page_cleaning_acceptance_id"] != command.page_cleaning_acceptance_id
                        or replay["page_cleaning_run_id"] != command.page_cleaning_run_id
                        or replay["combined_cleaning_candidate_id"] != command.combined_cleaning_candidate_id
                    ):
                        connection.rollback()
                        return _outcome("IDEMPOTENCY_CONFLICT", reload=True)
                    connection.rollback()
                    return FullPageCleaningTransactionOutcome(
                        True,
                        "ALREADY_ACCEPTED",
                        active_cleaned_artifact_id=replay["cleaned_artifact_id"],
                        cleaned_pass_count=len(command.cleaned_pass_dispositions),
                    )

                precondition = self._acceptance_precondition(connection, command)
                if precondition is not None:
                    connection.rollback()
                    return _outcome(precondition, reload=precondition.endswith("CONFLICT"))

                for change in command.issue_changes:
                    _apply_issue_change(connection, self._project_id, change)
                _insert_decision(
                    connection,
                    self._project_id,
                    command.task_id,
                    command.workflow_decision_id,
                    command.attempt_id,
                    "continue",
                    command.reason_code,
                )
                for relation in command.issue_relations:
                    _insert_issue_relation(connection, self._project_id, relation)
                if _has_unresolved_blocker(
                    connection,
                    self._project_id,
                    command.page_cleaning_run_id,
                    command.combined_cleaning_candidate_id,
                    command.page_cleaning_validation_record_id,
                ):
                    connection.rollback()
                    return _outcome("UNRESOLVED_BLOCKING_ISSUE")

                now = utc_now()
                connection.execute(
                    "UPDATE combined_cleaning_candidates SET status = 'accepted', "
                    "accepted_validation_record_id = ?, accepted_at = ? "
                    "WHERE project_id = ? AND combined_cleaning_candidate_id = ?",
                    (
                        command.page_cleaning_validation_record_id,
                        now,
                        self._project_id,
                        command.combined_cleaning_candidate_id,
                    ),
                )
                connection.execute(
                    "UPDATE combined_cleaning_candidate_members SET "
                    "selection_status = 'accepted', accepted_at = ? "
                    "WHERE project_id = ? AND combined_cleaning_candidate_id = ?",
                    (now, self._project_id, command.combined_cleaning_candidate_id),
                )
                connection.execute(
                    "UPDATE page_cleaning_validation_records SET "
                    "selection_status = 'accepted', accepted_at = ? "
                    "WHERE project_id = ? AND page_cleaning_validation_record_id = ?",
                    (now, self._project_id, command.page_cleaning_validation_record_id),
                )
                for disposition in command.cleaned_pass_dispositions:
                    connection.execute(
                        """
                        INSERT INTO accepted_segment_cleaning_dispositions (
                            accepted_segment_cleaning_disposition_id, project_id,
                            page_cleaning_run_id, cleaning_inventory_item_id,
                            instance_cleaning_result_id, combined_cleaning_candidate_id,
                            page_cleaning_validation_record_id, disposition_code,
                            dependency_fingerprint, stale_by_dependency_fingerprint, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'CLEANED_PASS', ?, NULL, ?)
                        """,
                        (
                            disposition.accepted_segment_cleaning_disposition_id,
                            self._project_id,
                            command.page_cleaning_run_id,
                            disposition.cleaning_inventory_item_id,
                            disposition.instance_cleaning_result_id,
                            command.combined_cleaning_candidate_id,
                            command.page_cleaning_validation_record_id,
                            disposition.dependency_fingerprint,
                            now,
                        ),
                    )
                connection.execute(
                    "UPDATE page_cleaning_runs SET status = 'accepted', completed_at = ? "
                    "WHERE project_id = ? AND page_cleaning_run_id = ?",
                    (now, self._project_id, command.page_cleaning_run_id),
                )
                pointer_update = connection.execute(
                    "UPDATE pages SET active_cleaned_artifact_id = ?, updated_at = ? "
                    "WHERE project_id = ? AND page_id = ? "
                    "AND active_cleaned_artifact_id IS ?",
                    (
                        command.cleaned_artifact_id,
                        now,
                        self._project_id,
                        command.page_id,
                        command.expected_active_cleaned_artifact_id,
                    ),
                )
                if pointer_update.rowcount != 1:
                    connection.rollback()
                    return _outcome("ACTIVE_POINTER_CONFLICT", reload=True)
                connection.execute(
                    """
                    INSERT INTO page_cleaning_acceptances (
                        page_cleaning_acceptance_id, project_id, page_cleaning_run_id,
                        combined_cleaning_candidate_id, page_cleaning_validation_record_id,
                        cleaned_artifact_id, workflow_decision_id, task_id,
                        idempotency_key, status, accepted_at, stale_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?, NULL)
                    """,
                    (
                        command.page_cleaning_acceptance_id,
                        self._project_id,
                        command.page_cleaning_run_id,
                        command.combined_cleaning_candidate_id,
                        command.page_cleaning_validation_record_id,
                        command.cleaned_artifact_id,
                        command.workflow_decision_id,
                        command.task_id,
                        command.idempotency_key,
                        now,
                    ),
                )
                connection.execute(
                    "UPDATE processing_tasks SET status = 'succeeded', current_stage = 'cleaning', "
                    "progress_state = 'cleaning_accepted', retry_budget_json = ?, updated_at = ? "
                    "WHERE project_id = ? AND task_id = ?",
                    (
                        command.retry_budget_after_json,
                        now,
                        self._project_id,
                        command.task_id,
                    ),
                )
                _update_accepted_content_summaries(
                    connection,
                    self._project_id,
                    command.page_cleaning_run_id,
                    command.page_id,
                    now,
                )
                if command.attempt_id is not None:
                    connection.execute(
                        "UPDATE workflow_attempts SET status = 'succeeded', updated_at = ? "
                        "WHERE project_id = ? AND attempt_id = ?",
                        (now, self._project_id, command.attempt_id),
                    )
            return FullPageCleaningTransactionOutcome(
                True,
                "ACCEPTED",
                active_cleaned_artifact_id=command.cleaned_artifact_id,
                cleaned_pass_count=len(command.cleaned_pass_dispositions),
            )
        except sqlite3.DatabaseError:
            return _outcome("TRANSACTION_FAILED")

    def validate_active_cleaned_pointer_eligibility(
        self, command: FullPageCleaningAcceptanceCommand
    ) -> FullPageCleaningTransactionOutcome:
        with connect_existing(self._project_db_path) as connection:
            precondition = self._acceptance_precondition(connection, command)
            if precondition is not None:
                return _outcome(
                    precondition,
                    reload=precondition.endswith("CONFLICT"),
                )
            if _has_unresolved_blocker(
                connection,
                self._project_id,
                command.page_cleaning_run_id,
                command.combined_cleaning_candidate_id,
                command.page_cleaning_validation_record_id,
            ):
                return _outcome("UNRESOLVED_BLOCKING_ISSUE")
        return _outcome("ELIGIBLE")

    def block_page_cleaning_atomically(
        self,
        command: FullPageCleaningBlockCommand,
    ) -> FullPageCleaningTransactionOutcome:
        try:
            with connect_existing(self._project_db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                page = connection.execute(
                    "SELECT active_cleaned_artifact_id FROM pages WHERE project_id = ? AND page_id = ?",
                    (self._project_id, command.page_id),
                ).fetchone()
                run = connection.execute(
                    "SELECT page_id FROM page_cleaning_runs WHERE project_id = ? AND page_cleaning_run_id = ?",
                    (self._project_id, command.page_cleaning_run_id),
                ).fetchone()
                task = connection.execute(
                    "SELECT status, current_stage FROM processing_tasks WHERE project_id = ? AND task_id = ?",
                    (self._project_id, command.task_id),
                ).fetchone()
                if page is None or run is None or run["page_id"] != command.page_id:
                    connection.rollback()
                    return _outcome("RUN_PAGE_CONFLICT", reload=True)
                if task is None or (
                    task["status"], task["current_stage"]
                ) != (command.expected_task_status, command.expected_task_stage):
                    connection.rollback()
                    return _outcome("TASK_STATE_CONFLICT", reload=True)
                if command.attempt_id is not None:
                    attempt = connection.execute(
                        "SELECT status FROM workflow_attempts WHERE project_id = ? AND attempt_id = ?",
                        (self._project_id, command.attempt_id),
                    ).fetchone()
                    if attempt is None or attempt["status"] != command.expected_attempt_status:
                        connection.rollback()
                        return _outcome("ATTEMPT_STATE_CONFLICT", reload=True)
                for change in command.issue_changes:
                    _apply_issue_change(connection, self._project_id, change)
                _insert_decision(
                    connection,
                    self._project_id,
                    command.task_id,
                    command.workflow_decision_id,
                    command.attempt_id,
                    "block",
                    command.reason_code,
                )
                for relation in command.issue_relations:
                    _insert_issue_relation(connection, self._project_id, relation)
                now = utc_now()
                connection.execute(
                    "UPDATE page_cleaning_runs SET status = 'blocked', completed_at = ? "
                    "WHERE project_id = ? AND page_cleaning_run_id = ?",
                    (now, self._project_id, command.page_cleaning_run_id),
                )
                connection.execute(
                    "UPDATE processing_tasks SET status = 'blocked', progress_state = 'blocked', "
                    "updated_at = ? WHERE project_id = ? AND task_id = ?",
                    (now, self._project_id, command.task_id),
                )
                connection.execute(
                    "UPDATE pages SET status = 'review_required', updated_at = ? "
                    "WHERE project_id = ? AND page_id = ?",
                    (now, self._project_id, command.page_id),
                )
                if command.attempt_id is not None:
                    connection.execute(
                        "UPDATE workflow_attempts SET status = 'failed', updated_at = ? "
                        "WHERE project_id = ? AND attempt_id = ?",
                        (now, self._project_id, command.attempt_id),
                    )
            return FullPageCleaningTransactionOutcome(
                True,
                "BLOCKED",
                active_cleaned_artifact_id=page["active_cleaned_artifact_id"],
            )
        except sqlite3.DatabaseError:
            return _outcome("TRANSACTION_FAILED")

    def mark_cleaning_facts_stale_and_clear_active_pointer_atomically(
        self,
        *,
        page_cleaning_run_id: str,
        expected_active_cleaned_artifact_id: str,
        dependency_fingerprint: str,
    ) -> FullPageCleaningTransactionOutcome:
        try:
            with connect_existing(self._project_db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                run = connection.execute(
                    "SELECT page_id, status FROM page_cleaning_runs WHERE project_id = ? "
                    "AND page_cleaning_run_id = ?",
                    (self._project_id, page_cleaning_run_id),
                ).fetchone()
                if run is None or run["status"] != "accepted":
                    connection.rollback()
                    return _outcome("ACCEPTED_RUN_REQUIRED")
                pointer = connection.execute(
                    "SELECT active_cleaned_artifact_id FROM pages WHERE project_id = ? AND page_id = ?",
                    (self._project_id, run["page_id"]),
                ).fetchone()
                if pointer is None or pointer["active_cleaned_artifact_id"] != expected_active_cleaned_artifact_id:
                    connection.rollback()
                    return _outcome("ACTIVE_POINTER_CONFLICT", reload=True)
                acceptance = connection.execute(
                    "SELECT cleaned_artifact_id, status FROM page_cleaning_acceptances "
                    "WHERE project_id = ? AND page_cleaning_run_id = ?",
                    (self._project_id, page_cleaning_run_id),
                ).fetchone()
                if (
                    acceptance is None
                    or acceptance["status"] != "accepted"
                    or acceptance["cleaned_artifact_id"]
                    != expected_active_cleaned_artifact_id
                ):
                    connection.rollback()
                    return _outcome("ACCEPTANCE_ARTIFACT_CONFLICT", reload=True)
                now = utc_now()
                update = connection.execute(
                    "UPDATE pages SET active_cleaned_artifact_id = NULL, updated_at = ? "
                    "WHERE project_id = ? AND page_id = ? AND active_cleaned_artifact_id = ?",
                    (now, self._project_id, run["page_id"], expected_active_cleaned_artifact_id),
                )
                if update.rowcount != 1:
                    connection.rollback()
                    return _outcome("ACTIVE_POINTER_CONFLICT", reload=True)
                _mark_run_facts_stale(
                    connection,
                    self._project_id,
                    page_cleaning_run_id,
                    dependency_fingerprint,
                    now,
                )
            return _outcome("STALE_AND_POINTER_CLEARED", committed=True)
        except sqlite3.DatabaseError:
            return _outcome("TRANSACTION_FAILED")

    def _acceptance_precondition(
        self,
        connection: sqlite3.Connection,
        command: FullPageCleaningAcceptanceCommand,
    ) -> str | None:
        page = connection.execute(
            "SELECT original_artifact_id, active_cleaned_artifact_id FROM pages "
            "WHERE project_id = ? AND page_id = ?",
            (self._project_id, command.page_id),
        ).fetchone()
        if page is None:
            return "RUN_PAGE_CONFLICT"
        if page["active_cleaned_artifact_id"] != command.expected_active_cleaned_artifact_id:
            return "ACTIVE_POINTER_CONFLICT"
        if page["original_artifact_id"] != command.expected_original_artifact_id:
            return "ORIGINAL_POINTER_CONFLICT"
        visual = connection.execute(
            "SELECT active_visual_contract_revision_id FROM page_visual_contract_state "
            "WHERE project_id = ? AND page_id = ?",
            (self._project_id, command.page_id),
        ).fetchone()
        if visual is None or visual["active_visual_contract_revision_id"] != command.expected_visual_contract_revision_id:
            return "VISUAL_REVISION_CONFLICT"
        task = connection.execute(
            "SELECT status, current_stage FROM processing_tasks WHERE project_id = ? AND task_id = ?",
            (self._project_id, command.task_id),
        ).fetchone()
        if task is None or (task["status"], task["current_stage"]) != (
            command.expected_task_status,
            command.expected_task_stage,
        ):
            return "TASK_STATE_CONFLICT"
        if command.attempt_id is not None:
            attempt = connection.execute(
                "SELECT status FROM workflow_attempts WHERE project_id = ? AND attempt_id = ?",
                (self._project_id, command.attempt_id),
            ).fetchone()
            if attempt is None or attempt["status"] != command.expected_attempt_status:
                return "ATTEMPT_STATE_CONFLICT"
        run = connection.execute(
            "SELECT * FROM page_cleaning_runs WHERE project_id = ? AND page_cleaning_run_id = ?",
            (self._project_id, command.page_cleaning_run_id),
        ).fetchone()
        if (
            run is None
            or run["page_id"] != command.page_id
            or run["status"] != "candidate_ready"
            or run["visual_contract_revision_id"] != command.expected_visual_contract_revision_id
            or run["source_artifact_id"] != command.expected_original_artifact_id
        ):
            return "RUN_NOT_ACCEPTABLE"
        candidate = connection.execute(
            "SELECT * FROM combined_cleaning_candidates WHERE project_id = ? "
            "AND combined_cleaning_candidate_id = ?",
            (self._project_id, command.combined_cleaning_candidate_id),
        ).fetchone()
        if (
            candidate is None
            or candidate["page_cleaning_run_id"] != command.page_cleaning_run_id
            or candidate["status"] != "validated"
            or candidate["combined_artifact_id"] != command.cleaned_artifact_id
            or candidate["stale_by_dependency_fingerprint"] is not None
        ):
            return "CANDIDATE_NOT_ACCEPTABLE"
        validation = connection.execute(
            "SELECT * FROM page_cleaning_validation_records WHERE project_id = ? "
            "AND page_cleaning_validation_record_id = ?",
            (self._project_id, command.page_cleaning_validation_record_id),
        ).fetchone()
        if (
            validation is None
            or validation["combined_cleaning_candidate_id"] != command.combined_cleaning_candidate_id
            or validation["status"] != "pass"
            or validation["selection_status"] != "recorded"
            or validation["stale_by_dependency_fingerprint"] is not None
            or not _row_is_passing_validation(validation)
        ):
            return "PAGE_VALIDATION_NOT_ACCEPTABLE"
        try:
            _require_artifact(
                connection,
                self._project_id,
                candidate["combined_artifact_id"],
                candidate["combined_hash"],
            )
            _require_artifact(
                connection,
                self._project_id,
                candidate["combined_delta_artifact_id"],
                candidate["combined_delta_hash"],
            )
            _require_artifact(
                connection,
                self._project_id,
                run["source_artifact_id"],
                run["source_hash"],
            )
        except ValueError:
            return "ARTIFACT_INTEGRITY_INVALID"
        return _validate_inventory_acceptance(
            connection,
            self._project_id,
            command,
        )


def _validate_inventory_acceptance(
    connection: sqlite3.Connection,
    project_id: str,
    command: FullPageCleaningAcceptanceCommand,
) -> str | None:
    inventory = connection.execute(
        "SELECT cleaning_inventory_item_id FROM page_cleaning_inventory_items "
        "WHERE project_id = ? AND page_cleaning_run_id = ?",
        (project_id, command.page_cleaning_run_id),
    ).fetchall()
    inventory_ids = {row["cleaning_inventory_item_id"] for row in inventory}
    member_targets = connection.execute(
        """
        SELECT m.instance_cleaning_result_id, t.cleaning_inventory_item_id,
               r.status, r.dependency_fingerprint,
               r.stale_by_dependency_fingerprint,
               m.actual_changed_artifact_id, m.actual_changed_hash
        FROM combined_cleaning_candidate_members m
        JOIN instance_cleaning_results r
          ON r.instance_cleaning_result_id = m.instance_cleaning_result_id
        JOIN instance_result_inventory_targets t
          ON t.instance_cleaning_result_id = m.instance_cleaning_result_id
        WHERE m.project_id = ? AND m.combined_cleaning_candidate_id = ?
        """,
        (project_id, command.combined_cleaning_candidate_id),
    ).fetchall()
    target_to_results: dict[str, list[str]] = {item_id: [] for item_id in inventory_ids}
    result_fingerprints = {}
    for row in member_targets:
        if row["status"] not in {"validated", "ready_for_composition"} or row["stale_by_dependency_fingerprint"] is not None:
            return "MEMBER_NOT_FRESH_VALIDATED"
        if row["cleaning_inventory_item_id"] not in target_to_results:
            return "MEMBER_TARGET_OUTSIDE_INVENTORY"
        if not _artifact_is_valid(
            connection,
            project_id,
            row["actual_changed_artifact_id"],
            row["actual_changed_hash"],
        ):
            return "ARTIFACT_INTEGRITY_INVALID"
        target_to_results[row["cleaning_inventory_item_id"]].append(
            row["instance_cleaning_result_id"]
        )
        result_fingerprints[row["instance_cleaning_result_id"]] = row[
            "dependency_fingerprint"
        ]
    requested = {
        disposition.cleaning_inventory_item_id: disposition
        for disposition in command.cleaned_pass_dispositions
    }
    if len(requested) != len(command.cleaned_pass_dispositions):
        return "CLEANED_PASS_DUPLICATE"
    current_dispositions = {
        row["cleaning_inventory_item_id"]: row
        for row in connection.execute(
            "SELECT * FROM segment_cleaning_dispositions WHERE project_id = ? "
            "AND superseded_by_disposition_id IS NULL AND cleaning_inventory_item_id IN "
            "(SELECT cleaning_inventory_item_id FROM page_cleaning_inventory_items "
            "WHERE project_id = ? AND page_cleaning_run_id = ?)",
            (project_id, project_id, command.page_cleaning_run_id),
        ).fetchall()
    }
    allowed_unsupported = {
        "UNSUPPORTED_E2",
        "UNSUPPORTED_E3",
        "UNSUPPORTED_FREE_TEXT",
        "UNSUPPORTED_SFX",
        "EXCLUDED_NON_TEXT",
    }
    for item_id, result_ids in target_to_results.items():
        if len(result_ids) == 1:
            disposition = requested.get(item_id)
            if disposition is None or disposition.instance_cleaning_result_id != result_ids[0]:
                return "CLEANED_PASS_MEMBER_MISMATCH"
            if disposition.dependency_fingerprint != result_fingerprints[result_ids[0]]:
                return "CLEANED_PASS_FINGERPRINT_MISMATCH"
            if item_id in current_dispositions:
                return "DISPOSITION_DUPLICATE"
        elif len(result_ids) > 1:
            return "DUPLICATE_MEMBER_ATTRIBUTION"
        else:
            durable = current_dispositions.get(item_id)
            if (
                durable is None
                or bool(durable["is_blocking"])
                or durable["disposition_code"] not in allowed_unsupported
            ):
                return "INVENTORY_INCOMPLETE"
    if set(requested) != {
        item_id for item_id, result_ids in target_to_results.items() if len(result_ids) == 1
    }:
        return "CLEANED_PASS_OUTSIDE_MEMBER_SET"
    return None


def _mark_run_facts_stale(
    connection: sqlite3.Connection,
    project_id: str,
    run_id: str,
    fingerprint: str,
    now: str,
) -> None:
    connection.execute(
        "UPDATE page_cleaning_runs SET status = 'stale', stale_by_dependency_fingerprint = ? "
        "WHERE project_id = ? AND page_cleaning_run_id = ?",
        (fingerprint, project_id, run_id),
    )
    connection.execute(
        "UPDATE instance_cleaning_results SET status = 'stale', stale_by_dependency_fingerprint = ? "
        "WHERE project_id = ? AND page_cleaning_run_id = ?",
        (fingerprint, project_id, run_id),
    )
    connection.execute(
        "UPDATE segment_cleaning_dispositions SET stale_by_dependency_fingerprint = ? "
        "WHERE project_id = ? AND cleaning_inventory_item_id IN "
        "(SELECT cleaning_inventory_item_id FROM page_cleaning_inventory_items "
        "WHERE project_id = ? AND page_cleaning_run_id = ?)",
        (fingerprint, project_id, project_id, run_id),
    )
    connection.execute(
        "UPDATE combined_cleaning_candidates SET status = 'stale', "
        "stale_by_dependency_fingerprint = ? WHERE project_id = ? AND page_cleaning_run_id = ?",
        (fingerprint, project_id, run_id),
    )
    connection.execute(
        "UPDATE combined_cleaning_candidate_members SET selection_status = 'stale' "
        "WHERE project_id = ? AND page_cleaning_run_id = ?",
        (project_id, run_id),
    )
    connection.execute(
        "UPDATE page_cleaning_validation_records SET status = 'stale', "
        "selection_status = 'stale', stale_by_dependency_fingerprint = ? "
        "WHERE project_id = ? AND page_cleaning_run_id = ?",
        (fingerprint, project_id, run_id),
    )
    connection.execute(
        "UPDATE accepted_segment_cleaning_dispositions SET stale_by_dependency_fingerprint = ? "
        "WHERE project_id = ? AND page_cleaning_run_id = ?",
        (fingerprint, project_id, run_id),
    )
    connection.execute(
        "UPDATE page_cleaning_acceptances SET status = 'stale', stale_at = ? "
        "WHERE project_id = ? AND page_cleaning_run_id = ?",
        (now, project_id, run_id),
    )
    connection.execute(
        "UPDATE cleaning_correction_chains SET status = 'stale', "
        "stale_by_dependency_fingerprint = ? WHERE project_id = ? "
        "AND page_cleaning_run_id = ?",
        (fingerprint, project_id, run_id),
    )
    connection.execute(
        "UPDATE cleaning_correction_reservations SET status = 'stale' "
        "WHERE project_id = ? AND correction_chain_id IN "
        "(SELECT correction_chain_id FROM cleaning_correction_chains "
        "WHERE project_id = ? AND page_cleaning_run_id = ?)",
        (project_id, project_id, run_id),
    )
    connection.execute(
        """
        UPDATE quality_issues
        SET status = 'stale', is_blocking = 0, updated_at = ?
        WHERE project_id = ? AND issue_id IN (
            SELECT issue_id FROM cleaning_quality_issue_relations
            WHERE project_id = ? AND (
                page_cleaning_run_id = ? OR
                combined_cleaning_candidate_id IN (
                    SELECT combined_cleaning_candidate_id
                    FROM combined_cleaning_candidates
                    WHERE project_id = ? AND page_cleaning_run_id = ?
                ) OR
                page_cleaning_validation_record_id IN (
                    SELECT page_cleaning_validation_record_id
                    FROM page_cleaning_validation_records
                    WHERE project_id = ? AND page_cleaning_run_id = ?
                )
            )
        )
        """,
        (now, project_id, project_id, run_id, project_id, run_id, project_id, run_id),
    )
    connection.execute(
        "UPDATE pages SET status = 'review_required', updated_at = ? "
        "WHERE project_id = ? AND page_id = "
        "(SELECT page_id FROM page_cleaning_runs WHERE project_id = ? "
        "AND page_cleaning_run_id = ?)",
        (now, project_id, project_id, run_id),
    )
    connection.execute(
        """
        UPDATE text_blocks
        SET cleaning_status = 'stale', updated_at = ?
        WHERE project_id = ? AND text_block_id IN (
            SELECT ts.source_text_block_id
            FROM text_segment_revisions ts
            JOIN page_cleaning_inventory_items i
              ON i.text_segment_revision_id = ts.text_segment_revision_id
            WHERE i.project_id = ? AND i.page_cleaning_run_id = ?
        )
        """,
        (now, project_id, project_id, run_id),
    )


def _update_accepted_content_summaries(
    connection: sqlite3.Connection,
    project_id: str,
    run_id: str,
    page_id: str,
    now: str,
) -> None:
    connection.execute(
        "UPDATE pages SET status = 'cleaned', updated_at = ? "
        "WHERE project_id = ? AND page_id = ?",
        (now, project_id, page_id),
    )
    connection.execute(
        """
        UPDATE text_blocks
        SET cleaning_status = 'done', updated_at = ?
        WHERE project_id = ? AND text_block_id IN (
            SELECT ts.source_text_block_id
            FROM text_segment_revisions ts
            JOIN page_cleaning_inventory_items i
              ON i.text_segment_revision_id = ts.text_segment_revision_id
            JOIN accepted_segment_cleaning_dispositions d
              ON d.cleaning_inventory_item_id = i.cleaning_inventory_item_id
            WHERE i.project_id = ? AND i.page_cleaning_run_id = ?
              AND d.stale_by_dependency_fingerprint IS NULL
        )
        """,
        (now, project_id, project_id, run_id),
    )


def _candidate_snapshot(connection, row) -> CombinedCleaningCandidateSnapshot:
    members = connection.execute(
        "SELECT instance_cleaning_result_id FROM combined_cleaning_candidate_members "
        "WHERE combined_cleaning_candidate_id = ? ORDER BY composition_key",
        (row["combined_cleaning_candidate_id"],),
    ).fetchall()
    return CombinedCleaningCandidateSnapshot(
        row["combined_cleaning_candidate_id"],
        row["page_cleaning_run_id"],
        row["source_artifact_id"],
        row["source_hash"],
        row["combined_artifact_id"],
        row["combined_hash"],
        row["combined_delta_artifact_id"],
        row["combined_delta_hash"],
        row["composition_config_hash"],
        row["member_set_fingerprint"],
        row["status"],
        tuple(member["instance_cleaning_result_id"] for member in members),
    )


def _candidate_snapshot_from_member_ids(row, member_ids) -> CombinedCleaningCandidateSnapshot:
    return CombinedCleaningCandidateSnapshot(
        row["combined_cleaning_candidate_id"],
        row["page_cleaning_run_id"],
        row["source_artifact_id"],
        row["source_hash"],
        row["combined_artifact_id"],
        row["combined_hash"],
        row["combined_delta_artifact_id"],
        row["combined_delta_hash"],
        row["composition_config_hash"],
        row["member_set_fingerprint"],
        row["status"],
        member_ids,
    )


def _validation_snapshot(row) -> PageCleaningValidationSnapshot:
    return PageCleaningValidationSnapshot(
        row["page_cleaning_validation_record_id"],
        row["page_cleaning_run_id"],
        row["combined_cleaning_candidate_id"],
        row["validation_fingerprint"],
        row["status"],
        row["selection_status"],
    )


def _require_artifact(connection, project_id: str, artifact_id: str, expected_hash: str) -> None:
    if not _artifact_is_valid(connection, project_id, artifact_id, expected_hash):
        raise ValueError("Artifact is not present with the expected hash.")


def _artifact_is_valid(
    connection, project_id: str, artifact_id: str, expected_hash: str
) -> bool:
    row = connection.execute(
        "SELECT file_hash, storage_state FROM processing_artifacts "
        "WHERE project_id = ? AND artifact_id = ?",
        (project_id, artifact_id),
    ).fetchone()
    return bool(
        row is not None
        and row["file_hash"] == expected_hash
        and row["storage_state"] == "present"
    )


def _insert_issue_relation(connection, project_id: str, relation: CleaningIssueRelationDraft) -> None:
    connection.execute(
        """
        INSERT INTO cleaning_quality_issue_relations (
            cleaning_quality_issue_relation_id, project_id, issue_id, relation_type,
            page_cleaning_run_id, cleaning_inventory_item_id,
            instance_cleaning_result_id, combined_cleaning_candidate_id,
            page_cleaning_validation_record_id, correction_reservation_id,
            workflow_decision_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            relation.cleaning_quality_issue_relation_id,
            project_id,
            relation.issue_id,
            relation.relation_type,
            relation.page_cleaning_run_id,
            relation.cleaning_inventory_item_id,
            relation.instance_cleaning_result_id,
            relation.combined_cleaning_candidate_id,
            relation.page_cleaning_validation_record_id,
            relation.correction_reservation_id,
            relation.workflow_decision_id,
            utc_now(),
        ),
    )


def _insert_decision(
    connection,
    project_id: str,
    task_id: str,
    decision_id: str,
    attempt_id: str | None,
    decision_type: str,
    reason_code: str,
) -> None:
    connection.execute(
        "INSERT INTO workflow_decisions(decision_id, project_id, task_id, attempt_id, "
        "stage, decision_type, reason_code, created_at) VALUES (?, ?, ?, ?, 'cleaning', ?, ?, ?)",
        (decision_id, project_id, task_id, attempt_id, decision_type, reason_code, utc_now()),
    )


def _has_unresolved_blocker(connection, project_id: str, run_id: str, candidate_id: str, validation_id: str) -> bool:
    return connection.execute(
        """
        SELECT 1
        FROM quality_issues q
        JOIN cleaning_quality_issue_relations r ON r.issue_id = q.issue_id
        WHERE q.project_id = ? AND q.is_blocking = 1
          AND q.status NOT IN ('resolved', 'superseded', 'stale')
          AND (
            r.page_cleaning_run_id = ? OR
            r.combined_cleaning_candidate_id = ? OR
            r.page_cleaning_validation_record_id = ? OR
            r.cleaning_inventory_item_id IN (
              SELECT cleaning_inventory_item_id FROM page_cleaning_inventory_items
              WHERE project_id = ? AND page_cleaning_run_id = ?
            ) OR
            r.instance_cleaning_result_id IN (
              SELECT instance_cleaning_result_id FROM instance_cleaning_results
              WHERE project_id = ? AND page_cleaning_run_id = ?
            )
          )
        LIMIT 1
        """,
        (project_id, run_id, candidate_id, validation_id, project_id, run_id, project_id, run_id),
    ).fetchone() is not None


def _draft_is_passing_validation(draft: PageCleaningValidationDraft) -> bool:
    return all(
        (
            draft.inventory_complete,
            draft.dispositions_unique,
            draft.missing_attribution_count == 0,
            draft.duplicate_attribution_count == 0,
            draft.pairwise_overlap_pixel_count == 0,
            draft.wrong_instance_write_pixel_count == 0,
            draft.outside_safe_pixel_count == 0,
            draft.protected_pixel_count == 0,
            draft.uncertainty_pixel_count == 0,
            draft.boundary_damage_pixel_count == 0,
            draft.residue_pixel_count == 0,
            draft.combined_delta_matches_member_union,
            draft.source_integrity_valid,
            draft.combined_integrity_valid,
            draft.dependencies_fresh,
        )
    )


def _row_is_passing_validation(row) -> bool:
    return all(
        (
            bool(row["inventory_complete"]),
            bool(row["dispositions_unique"]),
            row["missing_attribution_count"] == 0,
            row["duplicate_attribution_count"] == 0,
            row["pairwise_overlap_pixel_count"] == 0,
            row["wrong_instance_write_pixel_count"] == 0,
            row["outside_safe_pixel_count"] == 0,
            row["protected_pixel_count"] == 0,
            row["uncertainty_pixel_count"] == 0,
            row["boundary_damage_pixel_count"] == 0,
            row["residue_pixel_count"] == 0,
            bool(row["combined_delta_matches_member_union"]),
            bool(row["source_integrity_valid"]),
            bool(row["combined_integrity_valid"]),
            bool(row["dependencies_fresh"]),
        )
    )


def _validation_insert_values(project_id: str, draft: PageCleaningValidationDraft):
    return (
        draft.page_cleaning_validation_record_id,
        project_id,
        draft.page_cleaning_run_id,
        draft.combined_cleaning_candidate_id,
        draft.validation_fingerprint,
        draft.status,
        int(draft.inventory_complete),
        int(draft.dispositions_unique),
        draft.missing_attribution_count,
        draft.duplicate_attribution_count,
        draft.pairwise_overlap_pixel_count,
        draft.wrong_instance_write_pixel_count,
        draft.outside_safe_pixel_count,
        draft.protected_pixel_count,
        draft.uncertainty_pixel_count,
        draft.boundary_damage_pixel_count,
        draft.residue_pixel_count,
        int(draft.combined_delta_matches_member_union),
        int(draft.source_integrity_valid),
        int(draft.combined_integrity_valid),
        int(draft.dependencies_fresh),
        draft.evidence_artifact_id,
        draft.overlap_evidence_artifact_id,
        draft.wrong_instance_evidence_artifact_id,
        draft.validator_summary,
        utc_now(),
    )


def _verify_candidate_replay(snapshot, draft, members, connection) -> None:
    expected = (
        draft.combined_cleaning_candidate_id,
        draft.page_cleaning_run_id,
        draft.source_artifact_id,
        draft.source_hash,
        draft.combined_artifact_id,
        draft.combined_hash,
        draft.combined_delta_artifact_id,
        draft.combined_delta_hash,
        draft.composition_config_hash,
        draft.member_set_fingerprint,
        tuple(member.instance_cleaning_result_id for member in members),
    )
    durable = (
        snapshot.combined_cleaning_candidate_id,
        snapshot.page_cleaning_run_id,
        snapshot.source_artifact_id,
        snapshot.source_hash,
        snapshot.combined_artifact_id,
        snapshot.combined_hash,
        snapshot.combined_delta_artifact_id,
        snapshot.combined_delta_hash,
        snapshot.composition_config_hash,
        snapshot.member_set_fingerprint,
        snapshot.member_result_ids,
    )
    if durable != expected:
        raise ValueError("Conflicting replay for CombinedCleaningCandidate.")


def _verify_validation_replay(row, draft) -> None:
    if (
        row["page_cleaning_validation_record_id"],
        row["page_cleaning_run_id"],
        row["status"],
        row["validator_summary"],
    ) != (
        draft.page_cleaning_validation_record_id,
        draft.page_cleaning_run_id,
        draft.status,
        draft.validator_summary,
    ):
        raise ValueError("Conflicting replay for PageCleaningValidation.")


def _outcome(code: str, *, committed: bool = False, reload: bool = False):
    return FullPageCleaningTransactionOutcome(committed, code, reload_required=reload)


__all__ = [
    "CleanedPassDispositionDraft",
    "CleaningIssueRelationDraft",
    "CombinedCleaningCandidateDraft",
    "CombinedCleaningCandidateMemberDraft",
    "CombinedCleaningCandidateSnapshot",
    "FullPageCleaningAcceptanceCommand",
    "FullPageCleaningAcceptanceRepository",
    "FullPageCleaningAcceptanceRecovery",
    "FullPageCleaningBlockCommand",
    "FullPageCleaningTransactionOutcome",
    "PageCleaningValidationDraft",
    "PageCleaningValidationSnapshot",
]
