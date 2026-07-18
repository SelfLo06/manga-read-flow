from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from manga_read_flow.persistence.sqlite_repository_helpers import connect_existing, utc_now


@dataclass(frozen=True)
class PageCleaningRunDraft:
    page_cleaning_run_id: str
    batch_id: str
    page_id: str
    visual_contract_revision_id: str
    source_artifact_id: str
    source_hash: str
    profile_snapshot_id: str | None
    config_hash: str
    idempotency_key: str
    status: str = "planned"
    supersedes_run_id: str | None = None


@dataclass(frozen=True)
class PageCleaningRunSnapshot:
    page_cleaning_run_id: str
    batch_id: str
    page_id: str
    visual_contract_revision_id: str
    source_artifact_id: str
    source_hash: str
    profile_snapshot_id: str | None
    config_hash: str
    idempotency_key: str
    status: str
    supersedes_run_id: str | None


@dataclass(frozen=True)
class CleaningInventoryItemDraft:
    cleaning_inventory_item_id: str
    text_segment_id: str
    text_segment_revision_id: str
    bubble_instance_id: str | None
    bubble_instance_revision_id: str | None
    assignment_id: str | None
    target_class: str
    eligibility: str
    support_policy: str
    dependency_fingerprint: str
    evidence_artifact_id: str | None
    inventory_ordinal: int


@dataclass(frozen=True)
class CorrectionChainDraft:
    correction_chain_id: str
    page_cleaning_run_id: str
    page_id: str
    affected_target_scope_hash: str
    source_fingerprint: str
    target_fingerprint: str
    policy_config_identity: str


@dataclass(frozen=True)
class CorrectionReservationSnapshot:
    correction_reservation_id: str
    correction_chain_id: str
    ordinal: int
    idempotency_key: str
    status: str
    budget_before: int
    budget_after: int


@dataclass(frozen=True)
class CorrectionChainSnapshot:
    correction_chain_id: str
    page_cleaning_run_id: str
    affected_target_scope_hash: str
    source_fingerprint: str
    target_fingerprint: str
    policy_config_identity: str
    status: str
    max_automatic_corrections: int


@dataclass(frozen=True)
class SegmentCleaningDispositionDraft:
    segment_cleaning_disposition_id: str
    cleaning_inventory_item_id: str
    disposition_code: str
    reason_code: str
    root_stage: str
    is_blocking: bool
    policy_snapshot: str
    dependency_fingerprint: str
    evidence_artifact_id: str | None = None
    instance_cleaning_result_id: str | None = None


@dataclass(frozen=True)
class InstanceCleaningResultDraft:
    instance_cleaning_result_id: str
    page_cleaning_run_id: str
    bubble_instance_id: str
    bubble_instance_revision_id: str
    source_artifact_id: str
    source_hash: str
    dependency_fingerprint: str
    config_hash: str
    state: str
    official_candidate_artifact_id: str | None
    actual_changed_artifact_id: str | None
    validator_evidence_artifact_id: str | None
    actual_changed_pixel_count: int
    unsafe_required_pixel_count: int
    residue_pixel_count: int
    validator_summary: str
    workflow_attempt_id: str | None = None
    provider_name: str | None = None
    profile_snapshot_id: str | None = None
    provider_candidate_artifact_id: str | None = None
    required_support_artifact_id: str | None = None
    safe_edit_artifact_id: str | None = None
    protected_artifact_id: str | None = None
    uncertainty_artifact_id: str | None = None
    visible_support_artifact_id: str | None = None
    residue_artifact_id: str | None = None
    boundary_damage_artifact_id: str | None = None
    background_difference_artifact_id: str | None = None


@dataclass(frozen=True)
class InstanceCleaningResultSnapshot:
    instance_cleaning_result_id: str
    page_cleaning_run_id: str
    bubble_instance_id: str
    bubble_instance_revision_id: str
    source_artifact_id: str
    source_hash: str
    dependency_fingerprint: str
    config_hash: str
    state: str
    workflow_attempt_id: str | None
    provider_name: str | None
    profile_snapshot_id: str | None
    provider_candidate_artifact_id: str | None
    official_candidate_artifact_id: str | None
    actual_changed_artifact_id: str | None
    required_support_artifact_id: str | None
    safe_edit_artifact_id: str | None
    protected_artifact_id: str | None
    uncertainty_artifact_id: str | None
    visible_support_artifact_id: str | None
    residue_artifact_id: str | None
    boundary_damage_artifact_id: str | None
    background_difference_artifact_id: str | None
    validator_evidence_artifact_id: str | None
    actual_changed_pixel_count: int
    unsafe_required_pixel_count: int
    residue_pixel_count: int
    inventory_item_ids: tuple[str, ...]


@dataclass(frozen=True)
class SegmentCleaningDispositionSnapshot:
    segment_cleaning_disposition_id: str
    cleaning_inventory_item_id: str
    disposition_code: str
    reason_code: str
    root_stage: str
    is_blocking: bool
    policy_snapshot: str
    dependency_fingerprint: str
    evidence_artifact_id: str | None
    instance_cleaning_result_id: str | None
    stale_by_dependency_fingerprint: str | None
    supersedes_disposition_id: str | None


@dataclass(frozen=True)
class CleaningRecoveryLedger:
    run: PageCleaningRunSnapshot
    inventory: tuple[CleaningInventoryItemDraft, ...]
    instance_results: tuple[InstanceCleaningResultSnapshot, ...]
    current_dispositions: tuple[SegmentCleaningDispositionSnapshot, ...]
    correction_chains: tuple[CorrectionChainSnapshot, ...]
    correction_reservations: tuple[CorrectionReservationSnapshot, ...]


class FullPageCleaningLedgerRepository:
    """Durable Slice 1 facts for a page-scoped Cleaning ledger.

    This repository intentionally has no acceptance or active-pointer API.
    Those decisions belong to the Slice 2 page validation transaction.
    """

    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def create_or_replay_page_cleaning_run(
        self,
        draft: PageCleaningRunDraft,
    ) -> PageCleaningRunSnapshot:
        if draft.status != "planned":
            raise ValueError("Slice 1 creates PageCleaningRun in planned state only.")
        with connect_existing(self._project_db_path) as connection:
            page = connection.execute(
                "SELECT batch_id FROM pages WHERE project_id = ? AND page_id = ?",
                (self._project_id, draft.page_id),
            ).fetchone()
            if page is None or page["batch_id"] != draft.batch_id:
                raise ValueError("PageCleaningRun must reference its project's page and batch.")
            existing = connection.execute(
                "SELECT * FROM page_cleaning_runs WHERE project_id = ? AND idempotency_key = ?",
                (self._project_id, draft.idempotency_key),
            ).fetchone()
            if existing is not None:
                snapshot = _run_snapshot(existing)
                _verify_same_run(snapshot, draft)
                return snapshot
            connection.execute(
                """
                INSERT INTO page_cleaning_runs (
                    page_cleaning_run_id, project_id, batch_id, page_id,
                    visual_contract_revision_id, source_artifact_id, source_hash,
                    profile_snapshot_id, config_hash, idempotency_key, status,
                    supersedes_run_id, stale_by_dependency_fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    draft.page_cleaning_run_id,
                    self._project_id,
                    draft.batch_id,
                    draft.page_id,
                    draft.visual_contract_revision_id,
                    draft.source_artifact_id,
                    draft.source_hash,
                    draft.profile_snapshot_id,
                    draft.config_hash,
                    draft.idempotency_key,
                    draft.status,
                    draft.supersedes_run_id,
                    utc_now(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM page_cleaning_runs WHERE project_id = ? AND page_cleaning_run_id = ?",
                (self._project_id, draft.page_cleaning_run_id),
            ).fetchone()
        return _run_snapshot(row)

    def freeze_cleaning_inventory(
        self,
        *,
        page_cleaning_run_id: str,
        inventory_fingerprint: str,
        items: tuple[CleaningInventoryItemDraft, ...],
    ) -> tuple[CleaningInventoryItemDraft, ...]:
        if not items or len({item.text_segment_revision_id for item in items}) != len(items):
            raise ValueError("Frozen inventory requires unique segment revisions.")
        if len({item.inventory_ordinal for item in items}) != len(items):
            raise ValueError("Frozen inventory requires unique ordinals.")
        with connect_existing(self._project_db_path) as connection:
            run = connection.execute(
                "SELECT status, page_id, inventory_fingerprint FROM page_cleaning_runs WHERE project_id = ? AND page_cleaning_run_id = ?",
                (self._project_id, page_cleaning_run_id),
            ).fetchone()
            if run is None:
                raise ValueError("Unknown PageCleaningRun.")
            existing = connection.execute(
                "SELECT * FROM page_cleaning_inventory_items WHERE project_id = ? AND page_cleaning_run_id = ? ORDER BY inventory_ordinal",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
            if existing:
                current = tuple(_inventory_draft(row) for row in existing)
                if (
                    current != tuple(sorted(items, key=lambda item: item.inventory_ordinal))
                    or run["inventory_fingerprint"] != inventory_fingerprint
                ):
                    raise ValueError("Frozen inventory replay conflicts with durable inventory.")
                return current
            if run["status"] != "planned":
                raise ValueError("Only planned PageCleaningRun may freeze inventory.")
            for item in items:
                connection.execute(
                    """INSERT INTO page_cleaning_inventory_items (
                    cleaning_inventory_item_id, project_id, page_cleaning_run_id, page_id,
                    text_segment_id, text_segment_revision_id, bubble_instance_id,
                    bubble_instance_revision_id, assignment_id, target_class, eligibility,
                    support_policy, dependency_fingerprint, evidence_artifact_id,
                    inventory_ordinal, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item.cleaning_inventory_item_id, self._project_id, page_cleaning_run_id, run["page_id"],
                     item.text_segment_id, item.text_segment_revision_id, item.bubble_instance_id,
                     item.bubble_instance_revision_id, item.assignment_id, item.target_class,
                     item.eligibility, item.support_policy, item.dependency_fingerprint,
                     item.evidence_artifact_id, item.inventory_ordinal, utc_now()),
                )
            connection.execute(
                "UPDATE page_cleaning_runs SET status = 'inventory_frozen', "
                "inventory_fingerprint = ?, started_at = COALESCE(started_at, ?) "
                "WHERE project_id = ? AND page_cleaning_run_id = ?",
                (inventory_fingerprint, utc_now(), self._project_id, page_cleaning_run_id),
            )
        return tuple(sorted(items, key=lambda item: item.inventory_ordinal))

    def transition_page_cleaning_run(
        self, *, page_cleaning_run_id: str, target_status: str
    ) -> PageCleaningRunSnapshot:
        """Persist only Slice 1 run lifecycle transitions; acceptance stays in Slice 2."""
        allowed = {
            "inventory_frozen": {"executing", "abandoned_after_crash", "stale"},
            "executing": {"blocked", "abandoned_after_crash", "stale"},
            "blocked": {"stale"},
            "planned": {"abandoned_after_crash", "stale"},
        }
        if target_status in {"accepted", "validating", "candidate_ready"}:
            raise ValueError(f"Run status {target_status} belongs to Slice 2.")
        with connect_existing(self._project_db_path) as connection:
            row = connection.execute(
                "SELECT * FROM page_cleaning_runs WHERE project_id = ? "
                "AND page_cleaning_run_id = ?",
                (self._project_id, page_cleaning_run_id),
            ).fetchone()
            if row is None:
                raise ValueError("Unknown PageCleaningRun.")
            if target_status not in allowed.get(row["status"], set()):
                raise ValueError(
                    f"Invalid Slice 1 PageCleaningRun transition: "
                    f"{row['status']} -> {target_status}."
                )
            completion = utc_now() if target_status in {"blocked", "abandoned_after_crash"} else None
            connection.execute(
                "UPDATE page_cleaning_runs SET status = ?, "
                "completed_at = COALESCE(?, completed_at) "
                "WHERE project_id = ? AND page_cleaning_run_id = ?",
                (target_status, completion, self._project_id, page_cleaning_run_id),
            )
            updated = connection.execute(
                "SELECT * FROM page_cleaning_runs WHERE project_id = ? "
                "AND page_cleaning_run_id = ?",
                (self._project_id, page_cleaning_run_id),
            ).fetchone()
        return _run_snapshot(updated)

    def load_page_cleaning_inventory(
        self, *, page_cleaning_run_id: str
    ) -> tuple[CleaningInventoryItemDraft, ...]:
        with connect_existing(self._project_db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM page_cleaning_inventory_items WHERE project_id = ? "
                "AND page_cleaning_run_id = ? ORDER BY inventory_ordinal",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
        return tuple(_inventory_draft(row) for row in rows)

    def list_current_segment_cleaning_dispositions(
        self, *, page_cleaning_run_id: str
    ) -> tuple[SegmentCleaningDispositionSnapshot, ...]:
        with connect_existing(self._project_db_path) as connection:
            rows = connection.execute(
                "SELECT d.* FROM segment_cleaning_dispositions d "
                "JOIN page_cleaning_inventory_items i ON "
                "i.cleaning_inventory_item_id = d.cleaning_inventory_item_id "
                "WHERE d.project_id = ? AND i.page_cleaning_run_id = ? "
                "AND d.superseded_by_disposition_id IS NULL "
                "ORDER BY d.cleaning_inventory_item_id",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
        return tuple(_disposition_snapshot(row) for row in rows)

    def reserve_or_replay_correction(
        self,
        *,
        chain: CorrectionChainDraft,
        correction_reservation_id: str,
        idempotency_key: str,
        reserved_attempt_id: str | None,
    ) -> CorrectionReservationSnapshot:
        """Reserve exactly ordinal one; idempotent replay never consumes budget again."""
        with connect_existing(self._project_db_path) as connection:
            existing = connection.execute(
                "SELECT * FROM cleaning_correction_reservations "
                "WHERE project_id = ? AND idempotency_key = ?",
                (self._project_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if (
                    existing["correction_reservation_id"] != correction_reservation_id
                    or existing["correction_chain_id"] != chain.correction_chain_id
                    or existing["reserved_attempt_id"] != reserved_attempt_id
                ):
                    raise ValueError("Conflicting replay for correction reservation idempotency key.")
                return _reservation_snapshot(existing)

            run = connection.execute(
                "SELECT page_id, status FROM page_cleaning_runs WHERE project_id = ? "
                "AND page_cleaning_run_id = ?",
                (self._project_id, chain.page_cleaning_run_id),
            ).fetchone()
            if run is None or run["page_id"] != chain.page_id:
                raise ValueError("CorrectionChain must reference its PageCleaningRun and page.")
            if run["status"] not in {"inventory_frozen", "executing"}:
                raise ValueError("CorrectionChain cannot reserve against a non-active run.")

            chain_row = connection.execute(
                "SELECT * FROM cleaning_correction_chains WHERE project_id = ? "
                "AND correction_chain_id = ?",
                (self._project_id, chain.correction_chain_id),
            ).fetchone()
            if chain_row is None:
                connection.execute(
                    """
                    INSERT INTO cleaning_correction_chains (
                        correction_chain_id, project_id, page_cleaning_run_id, page_id,
                        affected_target_scope_hash, source_fingerprint, target_fingerprint,
                        policy_config_identity, max_automatic_corrections, status,
                        supersedes_chain_id, stale_by_dependency_fingerprint, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'active', NULL, NULL, ?)
                    """,
                    (
                        chain.correction_chain_id, self._project_id,
                        chain.page_cleaning_run_id, chain.page_id,
                        chain.affected_target_scope_hash, chain.source_fingerprint,
                        chain.target_fingerprint, chain.policy_config_identity, utc_now(),
                    ),
                )
            else:
                _verify_same_correction_chain(chain_row, chain)
                if chain_row["status"] == "stale":
                    raise ValueError("Stale CorrectionChain cannot reserve a correction.")

            if connection.execute(
                "SELECT 1 FROM cleaning_correction_reservations "
                "WHERE correction_chain_id = ?",
                (chain.correction_chain_id,),
            ).fetchone() is not None:
                raise ValueError("Second automatic correction is rejected for this chain.")
            connection.execute(
                """
                INSERT INTO cleaning_correction_reservations (
                    correction_reservation_id, project_id, correction_chain_id, ordinal,
                    idempotency_key, reserved_attempt_id, workflow_decision_id, status,
                    budget_before, budget_after, created_at
                ) VALUES (?, ?, ?, 1, ?, ?, NULL, 'reserved', 1, 0, ?)
                """,
                (
                    correction_reservation_id, self._project_id,
                    chain.correction_chain_id, idempotency_key, reserved_attempt_id,
                    utc_now(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM cleaning_correction_reservations "
                "WHERE correction_reservation_id = ?",
                (correction_reservation_id,),
            ).fetchone()
        return _reservation_snapshot(row)

    def mark_correction_reservation_executing(
        self, *, correction_reservation_id: str
    ) -> CorrectionReservationSnapshot:
        return self._transition_correction_reservation(
            correction_reservation_id=correction_reservation_id,
            expected_status="reserved",
            target_status="executing",
            timestamp_column="started_at",
        )

    def reject_second_automatic_correction(
        self, *, correction_chain_id: str
    ) -> None:
        with connect_existing(self._project_db_path) as connection:
            chain = connection.execute(
                "SELECT 1 FROM cleaning_correction_chains WHERE project_id = ? "
                "AND correction_chain_id = ?",
                (self._project_id, correction_chain_id),
            ).fetchone()
            reservation = connection.execute(
                "SELECT 1 FROM cleaning_correction_reservations WHERE project_id = ? "
                "AND correction_chain_id = ?",
                (self._project_id, correction_chain_id),
            ).fetchone()
        if chain is None:
            raise ValueError("Unknown CorrectionChain.")
        if reservation is None:
            raise ValueError("CorrectionChain has not consumed its automatic correction.")
        raise ValueError("Second automatic correction is rejected for this chain.")

    def complete_correction_reservation(
        self, *, correction_reservation_id: str
    ) -> CorrectionReservationSnapshot:
        return self._transition_correction_reservation(
            correction_reservation_id=correction_reservation_id,
            expected_status="executing",
            target_status="completed",
            timestamp_column="completed_at",
        )

    def abandon_correction_reservation_after_crash(
        self, *, correction_reservation_id: str
    ) -> CorrectionReservationSnapshot:
        return self._transition_correction_reservation(
            correction_reservation_id=correction_reservation_id,
            expected_status="executing",
            target_status="abandoned_after_crash",
            timestamp_column="completed_at",
        )

    def _transition_correction_reservation(
        self,
        *,
        correction_reservation_id: str,
        expected_status: str,
        target_status: str,
        timestamp_column: str,
    ) -> CorrectionReservationSnapshot:
        with connect_existing(self._project_db_path) as connection:
            updated = connection.execute(
                f"UPDATE cleaning_correction_reservations SET status = ?, {timestamp_column} = ? "
                "WHERE project_id = ? AND correction_reservation_id = ? AND status = ?",
                (
                    target_status, utc_now(), self._project_id,
                    correction_reservation_id, expected_status,
                ),
            ).rowcount
            row = connection.execute(
                "SELECT * FROM cleaning_correction_reservations "
                "WHERE project_id = ? AND correction_reservation_id = ?",
                (self._project_id, correction_reservation_id),
            ).fetchone()
        if row is None:
            raise ValueError("Unknown correction reservation.")
        if updated != 1:
            raise ValueError(
                f"Correction reservation cannot transition from {row['status']} to {target_status}."
            )
        return _reservation_snapshot(row)

    def record_or_supersede_segment_disposition(self, draft: SegmentCleaningDispositionDraft) -> None:
        if draft.disposition_code in {"CLEANED_PASS", "OUT_OF_SLICE"}:
            raise ValueError("CLEANED_PASS requires Slice 2 acceptance; OUT_OF_SLICE is not a ledger disposition.")
        with connect_existing(self._project_db_path) as connection:
            inventory = connection.execute(
                "SELECT page_cleaning_run_id FROM page_cleaning_inventory_items "
                "WHERE project_id = ? AND cleaning_inventory_item_id = ?",
                (self._project_id, draft.cleaning_inventory_item_id),
            ).fetchone()
            if inventory is None:
                raise ValueError("Disposition requires a frozen inventory item.")
            if draft.instance_cleaning_result_id is not None:
                result = connection.execute(
                    "SELECT page_cleaning_run_id FROM instance_cleaning_results "
                    "WHERE project_id = ? AND instance_cleaning_result_id = ?",
                    (self._project_id, draft.instance_cleaning_result_id),
                ).fetchone()
                if result is None or result["page_cleaning_run_id"] != inventory["page_cleaning_run_id"]:
                    raise ValueError("Disposition result must belong to the inventory item's run.")
                attribution = connection.execute(
                    "SELECT 1 FROM instance_result_inventory_targets "
                    "WHERE instance_cleaning_result_id = ? "
                    "AND cleaning_inventory_item_id = ?",
                    (
                        draft.instance_cleaning_result_id,
                        draft.cleaning_inventory_item_id,
                    ),
                ).fetchone()
                if attribution is None:
                    raise ValueError("Disposition result must cover its inventory item.")
            old = connection.execute("SELECT segment_cleaning_disposition_id FROM segment_cleaning_dispositions WHERE project_id = ? AND cleaning_inventory_item_id = ? AND superseded_by_disposition_id IS NULL", (self._project_id, draft.cleaning_inventory_item_id)).fetchone()
            if old is not None:
                connection.execute("UPDATE segment_cleaning_dispositions SET superseded_by_disposition_id = ? WHERE segment_cleaning_disposition_id = ?", (draft.segment_cleaning_disposition_id, old["segment_cleaning_disposition_id"]))
            connection.execute("INSERT INTO segment_cleaning_dispositions (segment_cleaning_disposition_id, project_id, cleaning_inventory_item_id, disposition_code, reason_code, root_stage, is_blocking, policy_snapshot, dependency_fingerprint, evidence_artifact_id, instance_cleaning_result_id, quality_issue_id, workflow_decision_id, supersedes_disposition_id, superseded_by_disposition_id, stale_by_dependency_fingerprint, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, ?)", (draft.segment_cleaning_disposition_id, self._project_id, draft.cleaning_inventory_item_id, draft.disposition_code, draft.reason_code, draft.root_stage, int(draft.is_blocking), draft.policy_snapshot, draft.dependency_fingerprint, draft.evidence_artifact_id, draft.instance_cleaning_result_id, old["segment_cleaning_disposition_id"] if old else None, utc_now()))

    def append_instance_cleaning_result(self, draft: InstanceCleaningResultDraft, *, inventory_item_ids: tuple[str, ...]) -> InstanceCleaningResultSnapshot:
        if draft.state not in {"validated", "ready_for_composition"} or not inventory_item_ids:
            raise ValueError("Slice 1 results must be validated/ready_for_composition with attribution.")
        if len(set(inventory_item_ids)) != len(inventory_item_ids):
            raise ValueError("Instance result attribution must not repeat an inventory item.")
        with connect_existing(self._project_db_path) as connection:
            run = connection.execute(
                "SELECT status FROM page_cleaning_runs WHERE project_id = ? "
                "AND page_cleaning_run_id = ?",
                (self._project_id, draft.page_cleaning_run_id),
            ).fetchone()
            if run is None:
                raise ValueError("Unknown PageCleaningRun.")
            if run["status"] not in {"inventory_frozen", "executing"}:
                raise ValueError("InstanceCleaningResult cannot append to a non-active run.")
            existing = connection.execute("SELECT * FROM instance_cleaning_results WHERE project_id = ? AND instance_cleaning_result_id = ?", (self._project_id, draft.instance_cleaning_result_id)).fetchone()
            if existing is None:
                frozen = connection.execute(
                    "SELECT COUNT(*) AS count FROM page_cleaning_inventory_items "
                    "WHERE project_id = ? AND page_cleaning_run_id = ? "
                    "AND cleaning_inventory_item_id IN ({})".format(
                        ",".join("?" for _ in inventory_item_ids)
                    ),
                    (self._project_id, draft.page_cleaning_run_id, *inventory_item_ids),
                ).fetchone()
                if frozen["count"] != len(inventory_item_ids):
                    raise ValueError("Instance result attribution must target this run's frozen inventory.")
                mismatched_instance = connection.execute(
                    "SELECT 1 FROM page_cleaning_inventory_items "
                    "WHERE project_id = ? AND page_cleaning_run_id = ? "
                    "AND cleaning_inventory_item_id IN ({}) "
                    "AND bubble_instance_revision_id != ?".format(
                        ",".join("?" for _ in inventory_item_ids)
                    ),
                    (
                        self._project_id,
                        draft.page_cleaning_run_id,
                        *inventory_item_ids,
                        draft.bubble_instance_revision_id,
                    ),
                ).fetchone()
                if mismatched_instance is not None:
                    raise ValueError("Instance result may only cover its BubbleInstance revision.")
                conflict = connection.execute("SELECT cleaning_inventory_item_id FROM instance_result_inventory_targets WHERE project_id = ? AND page_cleaning_run_id = ? AND cleaning_inventory_item_id IN ({})".format(",".join("?" for _ in inventory_item_ids)), (self._project_id, draft.page_cleaning_run_id, *inventory_item_ids)).fetchone()
                if conflict is not None:
                    raise ValueError("Inventory item already has a current instance result.")
                connection.execute(
                    """
                    INSERT INTO instance_cleaning_results (
                        instance_cleaning_result_id, project_id, page_cleaning_run_id,
                        bubble_instance_id, bubble_instance_revision_id,
                        source_artifact_id, source_hash, dependency_fingerprint,
                        workflow_attempt_id, provider_name, profile_snapshot_id, config_hash,
                        provider_candidate_artifact_id, official_candidate_artifact_id,
                        actual_changed_artifact_id, required_support_artifact_id,
                        safe_edit_artifact_id, protected_artifact_id,
                        uncertainty_artifact_id, visible_support_artifact_id,
                        residue_artifact_id, boundary_damage_artifact_id,
                        background_difference_artifact_id, validator_evidence_artifact_id,
                        actual_changed_pixel_count, unsafe_required_pixel_count,
                        residue_pixel_count, validator_summary, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        draft.instance_cleaning_result_id, self._project_id,
                        draft.page_cleaning_run_id, draft.bubble_instance_id,
                        draft.bubble_instance_revision_id, draft.source_artifact_id,
                        draft.source_hash, draft.dependency_fingerprint,
                        draft.workflow_attempt_id, draft.provider_name,
                        draft.profile_snapshot_id, draft.config_hash,
                        draft.provider_candidate_artifact_id,
                        draft.official_candidate_artifact_id,
                        draft.actual_changed_artifact_id,
                        draft.required_support_artifact_id,
                        draft.safe_edit_artifact_id, draft.protected_artifact_id,
                        draft.uncertainty_artifact_id,
                        draft.visible_support_artifact_id, draft.residue_artifact_id,
                        draft.boundary_damage_artifact_id,
                        draft.background_difference_artifact_id,
                        draft.validator_evidence_artifact_id,
                        draft.actual_changed_pixel_count,
                        draft.unsafe_required_pixel_count, draft.residue_pixel_count,
                        draft.validator_summary, draft.state, utc_now(),
                    ),
                )
                for item_id in inventory_item_ids:
                    connection.execute("INSERT INTO instance_result_inventory_targets (instance_cleaning_result_id, cleaning_inventory_item_id, project_id, page_cleaning_run_id, created_at) VALUES (?, ?, ?, ?, ?)", (draft.instance_cleaning_result_id, item_id, self._project_id, draft.page_cleaning_run_id, utc_now()))
            else:
                _verify_same_instance_result(existing, draft, inventory_item_ids, connection)
            rows = connection.execute("SELECT cleaning_inventory_item_id FROM instance_result_inventory_targets WHERE instance_cleaning_result_id = ? ORDER BY cleaning_inventory_item_id", (draft.instance_cleaning_result_id,)).fetchall()
            result_row = connection.execute(
                "SELECT * FROM instance_cleaning_results WHERE project_id = ? "
                "AND instance_cleaning_result_id = ?",
                (self._project_id, draft.instance_cleaning_result_id),
            ).fetchone()
        return _result_snapshot(
            result_row,
            {draft.instance_cleaning_result_id: tuple(row["cleaning_inventory_item_id"] for row in rows)},
        )

    def mark_unaccepted_cleaning_run_stale(self, *, page_cleaning_run_id: str, dependency_fingerprint: str) -> str:
        with connect_existing(self._project_db_path) as connection:
            run = connection.execute("SELECT page_id, status FROM page_cleaning_runs WHERE project_id = ? AND page_cleaning_run_id = ?", (self._project_id, page_cleaning_run_id)).fetchone()
            if run is None:
                raise ValueError("Unknown PageCleaningRun.")
            page = connection.execute("SELECT active_cleaned_artifact_id FROM pages WHERE project_id = ? AND page_id = ?", (self._project_id, run["page_id"])).fetchone()
            if page is None:
                raise ValueError("PageCleaningRun page is missing.")
            if page["active_cleaned_artifact_id"] is not None:
                return "ACTIVE_POINTER_STALE_REPAIR_REQUIRES_SLICE_2"
            if run["status"] == "accepted":
                raise ValueError("Accepted run stale repair requires Slice 2.")
            connection.execute("UPDATE page_cleaning_runs SET status = 'stale', stale_by_dependency_fingerprint = ? WHERE project_id = ? AND page_cleaning_run_id = ?", (dependency_fingerprint, self._project_id, page_cleaning_run_id))
            connection.execute(
                "UPDATE instance_cleaning_results SET status = 'stale', "
                "stale_by_dependency_fingerprint = ? WHERE project_id = ? "
                "AND page_cleaning_run_id = ?",
                (dependency_fingerprint, self._project_id, page_cleaning_run_id),
            )
            connection.execute(
                "UPDATE segment_cleaning_dispositions SET "
                "stale_by_dependency_fingerprint = ? WHERE project_id = ? "
                "AND cleaning_inventory_item_id IN "
                "(SELECT cleaning_inventory_item_id FROM page_cleaning_inventory_items "
                "WHERE project_id = ? AND page_cleaning_run_id = ?)",
                (dependency_fingerprint, self._project_id, self._project_id, page_cleaning_run_id),
            )
            connection.execute(
                "UPDATE cleaning_correction_chains SET status = 'stale', "
                "stale_by_dependency_fingerprint = ? WHERE project_id = ? "
                "AND page_cleaning_run_id = ?",
                (dependency_fingerprint, self._project_id, page_cleaning_run_id),
            )
            connection.execute(
                "UPDATE cleaning_correction_reservations SET status = 'stale' "
                "WHERE project_id = ? AND correction_chain_id IN "
                "(SELECT correction_chain_id FROM cleaning_correction_chains "
                "WHERE project_id = ? AND page_cleaning_run_id = ?)",
                (self._project_id, self._project_id, page_cleaning_run_id),
            )
        return "STALE_MARKED"

    def load_recovery_ledger(self, *, page_cleaning_run_id: str) -> CleaningRecoveryLedger:
        with connect_existing(self._project_db_path) as connection:
            run = connection.execute(
                "SELECT * FROM page_cleaning_runs WHERE project_id = ? "
                "AND page_cleaning_run_id = ?",
                (self._project_id, page_cleaning_run_id),
            ).fetchone()
            if run is None:
                raise ValueError("Unknown PageCleaningRun.")
            inventory_rows = connection.execute(
                "SELECT * FROM page_cleaning_inventory_items WHERE project_id = ? "
                "AND page_cleaning_run_id = ? ORDER BY inventory_ordinal",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
            result_rows = connection.execute(
                "SELECT * FROM instance_cleaning_results WHERE project_id = ? "
                "AND page_cleaning_run_id = ? ORDER BY instance_cleaning_result_id",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
            result_ids = tuple(row["instance_cleaning_result_id"] for row in result_rows)
            targets = _targets_by_result(connection, result_ids)
            disposition_rows = connection.execute(
                "SELECT d.* FROM segment_cleaning_dispositions d "
                "JOIN page_cleaning_inventory_items i ON "
                "i.cleaning_inventory_item_id = d.cleaning_inventory_item_id "
                "WHERE d.project_id = ? AND i.page_cleaning_run_id = ? "
                "AND d.superseded_by_disposition_id IS NULL "
                "ORDER BY d.cleaning_inventory_item_id",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
            chain_rows = connection.execute(
                "SELECT * FROM cleaning_correction_chains WHERE project_id = ? "
                "AND page_cleaning_run_id = ? ORDER BY correction_chain_id",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
            reservations = connection.execute(
                "SELECT r.* FROM cleaning_correction_reservations r "
                "JOIN cleaning_correction_chains c ON "
                "c.correction_chain_id = r.correction_chain_id "
                "WHERE r.project_id = ? AND c.page_cleaning_run_id = ? "
                "ORDER BY r.correction_reservation_id",
                (self._project_id, page_cleaning_run_id),
            ).fetchall()
        return CleaningRecoveryLedger(
            run=_run_snapshot(run),
            inventory=tuple(_inventory_draft(row) for row in inventory_rows),
            instance_results=tuple(_result_snapshot(row, targets) for row in result_rows),
            current_dispositions=tuple(_disposition_snapshot(row) for row in disposition_rows),
            correction_chains=tuple(_chain_snapshot(row) for row in chain_rows),
            correction_reservations=tuple(_reservation_snapshot(row) for row in reservations),
        )

    def load_page_cleaning_recovery_ledger(
        self, *, page_cleaning_run_id: str
    ) -> CleaningRecoveryLedger:
        return self.load_recovery_ledger(page_cleaning_run_id=page_cleaning_run_id)


def initialize_full_page_cleaning_ledger_schema(connection: sqlite3.Connection) -> None:
    """Create additive v3 ledger tables without interpreting legacy evidence."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS page_cleaning_runs (
            page_cleaning_run_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            visual_contract_revision_id TEXT NOT NULL,
            source_artifact_id TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            profile_snapshot_id TEXT,
            config_hash TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            inventory_fingerprint TEXT,
            status TEXT NOT NULL,
            supersedes_run_id TEXT,
            stale_by_dependency_fingerprint TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(project_id, idempotency_key)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS page_cleaning_inventory_items (
            cleaning_inventory_item_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_cleaning_run_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            text_segment_id TEXT NOT NULL,
            text_segment_revision_id TEXT NOT NULL,
            bubble_instance_id TEXT,
            bubble_instance_revision_id TEXT,
            assignment_id TEXT,
            target_class TEXT NOT NULL,
            eligibility TEXT NOT NULL,
            support_policy TEXT NOT NULL,
            dependency_fingerprint TEXT NOT NULL,
            evidence_artifact_id TEXT,
            inventory_ordinal INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, page_cleaning_run_id, text_segment_revision_id),
            UNIQUE(project_id, page_cleaning_run_id, inventory_ordinal)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS instance_cleaning_results (
            instance_cleaning_result_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_cleaning_run_id TEXT NOT NULL,
            bubble_instance_id TEXT NOT NULL,
            bubble_instance_revision_id TEXT NOT NULL,
            source_artifact_id TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            dependency_fingerprint TEXT NOT NULL,
            workflow_attempt_id TEXT,
            provider_name TEXT,
            profile_snapshot_id TEXT,
            config_hash TEXT NOT NULL,
            provider_candidate_artifact_id TEXT,
            official_candidate_artifact_id TEXT,
            actual_changed_artifact_id TEXT,
            required_support_artifact_id TEXT,
            safe_edit_artifact_id TEXT,
            protected_artifact_id TEXT,
            uncertainty_artifact_id TEXT,
            visible_support_artifact_id TEXT,
            residue_artifact_id TEXT,
            boundary_damage_artifact_id TEXT,
            background_difference_artifact_id TEXT,
            validator_evidence_artifact_id TEXT,
            actual_changed_pixel_count INTEGER NOT NULL,
            unsafe_required_pixel_count INTEGER NOT NULL,
            residue_pixel_count INTEGER NOT NULL,
            validator_summary TEXT NOT NULL,
            status TEXT NOT NULL,
            supersedes_result_id TEXT,
            stale_by_dependency_fingerprint TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, page_cleaning_run_id, bubble_instance_revision_id, dependency_fingerprint)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS instance_result_inventory_targets (
            instance_cleaning_result_id TEXT NOT NULL,
            cleaning_inventory_item_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            page_cleaning_run_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(instance_cleaning_result_id, cleaning_inventory_item_id),
            UNIQUE(project_id, page_cleaning_run_id, cleaning_inventory_item_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS segment_cleaning_dispositions (
            segment_cleaning_disposition_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            cleaning_inventory_item_id TEXT NOT NULL,
            disposition_code TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            root_stage TEXT NOT NULL,
            is_blocking INTEGER NOT NULL,
            policy_snapshot TEXT NOT NULL,
            dependency_fingerprint TEXT NOT NULL,
            evidence_artifact_id TEXT,
            instance_cleaning_result_id TEXT,
            quality_issue_id TEXT,
            workflow_decision_id TEXT,
            supersedes_disposition_id TEXT,
            superseded_by_disposition_id TEXT,
            stale_by_dependency_fingerprint TEXT,
            created_at TEXT NOT NULL,
            CHECK(disposition_code NOT IN ('CLEANED_PASS', 'OUT_OF_SLICE')),
            CHECK(is_blocking IN (0, 1))
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_current_segment_cleaning_disposition
        ON segment_cleaning_dispositions(cleaning_inventory_item_id)
        WHERE superseded_by_disposition_id IS NULL
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cleaning_correction_chains (
            correction_chain_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_cleaning_run_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            affected_target_scope_hash TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL,
            target_fingerprint TEXT NOT NULL,
            policy_config_identity TEXT NOT NULL,
            max_automatic_corrections INTEGER NOT NULL,
            status TEXT NOT NULL,
            supersedes_chain_id TEXT,
            stale_by_dependency_fingerprint TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(
                project_id,
                page_cleaning_run_id,
                affected_target_scope_hash,
                source_fingerprint,
                target_fingerprint,
                policy_config_identity
            )
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cleaning_correction_reservations (
            correction_reservation_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            correction_chain_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            idempotency_key TEXT NOT NULL,
            reserved_attempt_id TEXT,
            workflow_decision_id TEXT,
            status TEXT NOT NULL,
            budget_before INTEGER NOT NULL,
            budget_after INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(project_id, idempotency_key),
            UNIQUE(correction_chain_id, ordinal),
            CHECK(ordinal = 1),
            CHECK(budget_after = 0)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_page_cleaning_runs_page_status "
        "ON page_cleaning_runs(project_id, page_id, status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_inventory_run_segment "
        "ON page_cleaning_inventory_items(project_id, page_cleaning_run_id, text_segment_revision_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_instance_results_run_revision "
        "ON instance_cleaning_results(project_id, page_cleaning_run_id, bubble_instance_revision_id)"
    )


def initialize_full_page_cleaning_acceptance_schema(
    connection: sqlite3.Connection,
) -> None:
    """Create Slice 2 completion facts in its own immutable migration."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS combined_cleaning_candidates (
            combined_cleaning_candidate_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_cleaning_run_id TEXT NOT NULL,
            source_artifact_id TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            combined_artifact_id TEXT NOT NULL,
            combined_hash TEXT NOT NULL,
            combined_delta_artifact_id TEXT NOT NULL,
            combined_delta_hash TEXT NOT NULL,
            composition_config_hash TEXT NOT NULL,
            member_set_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL,
            accepted_validation_record_id TEXT,
            supersedes_candidate_id TEXT,
            stale_by_dependency_fingerprint TEXT,
            created_at TEXT NOT NULL,
            accepted_at TEXT,
            UNIQUE(project_id, page_cleaning_run_id, member_set_fingerprint),
            CHECK(status IN ('official_unselected', 'validated', 'accepted', 'stale')),
            FOREIGN KEY(page_cleaning_run_id)
                REFERENCES page_cleaning_runs(page_cleaning_run_id),
            FOREIGN KEY(supersedes_candidate_id)
                REFERENCES combined_cleaning_candidates(combined_cleaning_candidate_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS combined_cleaning_candidate_members (
            combined_cleaning_candidate_id TEXT NOT NULL,
            instance_cleaning_result_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            page_cleaning_run_id TEXT NOT NULL,
            bubble_instance_revision_id TEXT NOT NULL,
            composition_key TEXT NOT NULL,
            actual_changed_artifact_id TEXT NOT NULL,
            actual_changed_hash TEXT NOT NULL,
            selection_status TEXT NOT NULL,
            accepted_at TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY(combined_cleaning_candidate_id, instance_cleaning_result_id),
            UNIQUE(combined_cleaning_candidate_id, bubble_instance_revision_id),
            UNIQUE(combined_cleaning_candidate_id, composition_key),
            CHECK(selection_status IN ('proposed', 'accepted', 'stale')),
            FOREIGN KEY(combined_cleaning_candidate_id)
                REFERENCES combined_cleaning_candidates(combined_cleaning_candidate_id),
            FOREIGN KEY(instance_cleaning_result_id)
                REFERENCES instance_cleaning_results(instance_cleaning_result_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS page_cleaning_validation_records (
            page_cleaning_validation_record_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_cleaning_run_id TEXT NOT NULL,
            combined_cleaning_candidate_id TEXT NOT NULL,
            validation_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL,
            selection_status TEXT NOT NULL,
            inventory_complete INTEGER NOT NULL,
            dispositions_unique INTEGER NOT NULL,
            missing_attribution_count INTEGER NOT NULL,
            duplicate_attribution_count INTEGER NOT NULL,
            pairwise_overlap_pixel_count INTEGER NOT NULL,
            wrong_instance_write_pixel_count INTEGER NOT NULL,
            outside_safe_pixel_count INTEGER NOT NULL,
            protected_pixel_count INTEGER NOT NULL,
            uncertainty_pixel_count INTEGER NOT NULL,
            boundary_damage_pixel_count INTEGER NOT NULL,
            residue_pixel_count INTEGER NOT NULL,
            combined_delta_matches_member_union INTEGER NOT NULL,
            source_integrity_valid INTEGER NOT NULL,
            combined_integrity_valid INTEGER NOT NULL,
            dependencies_fresh INTEGER NOT NULL,
            evidence_artifact_id TEXT,
            overlap_evidence_artifact_id TEXT,
            wrong_instance_evidence_artifact_id TEXT,
            validator_summary TEXT NOT NULL,
            stale_by_dependency_fingerprint TEXT,
            created_at TEXT NOT NULL,
            accepted_at TEXT,
            UNIQUE(project_id, combined_cleaning_candidate_id, validation_fingerprint),
            CHECK(status IN ('pass', 'fail', 'stale')),
            CHECK(selection_status IN ('recorded', 'accepted', 'stale')),
            CHECK(inventory_complete IN (0, 1)),
            CHECK(dispositions_unique IN (0, 1)),
            CHECK(combined_delta_matches_member_union IN (0, 1)),
            CHECK(source_integrity_valid IN (0, 1)),
            CHECK(combined_integrity_valid IN (0, 1)),
            CHECK(dependencies_fresh IN (0, 1)),
            FOREIGN KEY(page_cleaning_run_id)
                REFERENCES page_cleaning_runs(page_cleaning_run_id),
            FOREIGN KEY(combined_cleaning_candidate_id)
                REFERENCES combined_cleaning_candidates(combined_cleaning_candidate_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cleaning_quality_issue_relations (
            cleaning_quality_issue_relation_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            issue_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            page_cleaning_run_id TEXT,
            cleaning_inventory_item_id TEXT,
            instance_cleaning_result_id TEXT,
            combined_cleaning_candidate_id TEXT,
            page_cleaning_validation_record_id TEXT,
            correction_reservation_id TEXT,
            workflow_decision_id TEXT,
            created_at TEXT NOT NULL,
            CHECK(
                (page_cleaning_run_id IS NOT NULL) +
                (cleaning_inventory_item_id IS NOT NULL) +
                (instance_cleaning_result_id IS NOT NULL) +
                (combined_cleaning_candidate_id IS NOT NULL) +
                (page_cleaning_validation_record_id IS NOT NULL) +
                (correction_reservation_id IS NOT NULL) +
                (workflow_decision_id IS NOT NULL) = 1
            ),
            FOREIGN KEY(issue_id) REFERENCES quality_issues(issue_id),
            FOREIGN KEY(page_cleaning_run_id)
                REFERENCES page_cleaning_runs(page_cleaning_run_id),
            FOREIGN KEY(cleaning_inventory_item_id)
                REFERENCES page_cleaning_inventory_items(cleaning_inventory_item_id),
            FOREIGN KEY(instance_cleaning_result_id)
                REFERENCES instance_cleaning_results(instance_cleaning_result_id),
            FOREIGN KEY(combined_cleaning_candidate_id)
                REFERENCES combined_cleaning_candidates(combined_cleaning_candidate_id),
            FOREIGN KEY(page_cleaning_validation_record_id)
                REFERENCES page_cleaning_validation_records(page_cleaning_validation_record_id),
            FOREIGN KEY(correction_reservation_id)
                REFERENCES cleaning_correction_reservations(correction_reservation_id),
            FOREIGN KEY(workflow_decision_id)
                REFERENCES workflow_decisions(decision_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS accepted_segment_cleaning_dispositions (
            accepted_segment_cleaning_disposition_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_cleaning_run_id TEXT NOT NULL,
            cleaning_inventory_item_id TEXT NOT NULL,
            instance_cleaning_result_id TEXT NOT NULL,
            combined_cleaning_candidate_id TEXT NOT NULL,
            page_cleaning_validation_record_id TEXT NOT NULL,
            disposition_code TEXT NOT NULL,
            dependency_fingerprint TEXT NOT NULL,
            stale_by_dependency_fingerprint TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, cleaning_inventory_item_id),
            CHECK(disposition_code = 'CLEANED_PASS'),
            FOREIGN KEY(page_cleaning_run_id)
                REFERENCES page_cleaning_runs(page_cleaning_run_id),
            FOREIGN KEY(cleaning_inventory_item_id)
                REFERENCES page_cleaning_inventory_items(cleaning_inventory_item_id),
            FOREIGN KEY(instance_cleaning_result_id)
                REFERENCES instance_cleaning_results(instance_cleaning_result_id),
            FOREIGN KEY(combined_cleaning_candidate_id)
                REFERENCES combined_cleaning_candidates(combined_cleaning_candidate_id),
            FOREIGN KEY(page_cleaning_validation_record_id)
                REFERENCES page_cleaning_validation_records(page_cleaning_validation_record_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS page_cleaning_acceptances (
            page_cleaning_acceptance_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_cleaning_run_id TEXT NOT NULL,
            combined_cleaning_candidate_id TEXT NOT NULL,
            page_cleaning_validation_record_id TEXT NOT NULL,
            cleaned_artifact_id TEXT NOT NULL,
            workflow_decision_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL,
            accepted_at TEXT NOT NULL,
            stale_at TEXT,
            UNIQUE(project_id, page_cleaning_run_id),
            UNIQUE(project_id, idempotency_key),
            CHECK(status IN ('accepted', 'stale')),
            FOREIGN KEY(page_cleaning_run_id)
                REFERENCES page_cleaning_runs(page_cleaning_run_id),
            FOREIGN KEY(combined_cleaning_candidate_id)
                REFERENCES combined_cleaning_candidates(combined_cleaning_candidate_id),
            FOREIGN KEY(page_cleaning_validation_record_id)
                REFERENCES page_cleaning_validation_records(page_cleaning_validation_record_id),
            FOREIGN KEY(workflow_decision_id)
                REFERENCES workflow_decisions(decision_id),
            FOREIGN KEY(task_id) REFERENCES processing_tasks(task_id)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_accepted_combined_candidate_per_run
        ON combined_cleaning_candidates(project_id, page_cleaning_run_id)
        WHERE status = 'accepted'
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_accepted_validation_per_candidate
        ON page_cleaning_validation_records(combined_cleaning_candidate_id)
        WHERE selection_status = 'accepted'
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_combined_candidate_run_status "
        "ON combined_cleaning_candidates(project_id, page_cleaning_run_id, status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_validation_candidate_status "
        "ON page_cleaning_validation_records(project_id, combined_cleaning_candidate_id, status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_cleaning_issue_relation_issue_run "
        "ON cleaning_quality_issue_relations(project_id, issue_id, page_cleaning_run_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_accepted_cleaning_disposition_run "
        "ON accepted_segment_cleaning_dispositions(project_id, page_cleaning_run_id)"
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_cleaned_pass_requires_accepted_member
        BEFORE INSERT ON accepted_segment_cleaning_dispositions
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1
                FROM combined_cleaning_candidates c
                JOIN combined_cleaning_candidate_members m
                  ON m.combined_cleaning_candidate_id = c.combined_cleaning_candidate_id
                JOIN page_cleaning_validation_records v
                  ON v.page_cleaning_validation_record_id = NEW.page_cleaning_validation_record_id
                WHERE c.combined_cleaning_candidate_id = NEW.combined_cleaning_candidate_id
                  AND c.status = 'accepted'
                  AND c.accepted_validation_record_id = NEW.page_cleaning_validation_record_id
                  AND m.instance_cleaning_result_id = NEW.instance_cleaning_result_id
                  AND m.selection_status = 'accepted'
                  AND v.combined_cleaning_candidate_id = c.combined_cleaning_candidate_id
                  AND v.status = 'pass'
                  AND v.selection_status = 'accepted'
            ) THEN RAISE(ABORT, 'CLEANED_PASS requires accepted combined member') END;
        END
        """
    )


__all__ = [
    "FullPageCleaningLedgerRepository",
    "CleaningInventoryItemDraft",
    "CorrectionChainDraft",
    "CorrectionChainSnapshot",
    "CorrectionReservationSnapshot",
    "SegmentCleaningDispositionDraft",
    "SegmentCleaningDispositionSnapshot",
    "InstanceCleaningResultDraft",
    "InstanceCleaningResultSnapshot",
    "CleaningRecoveryLedger",
    "PageCleaningRunDraft",
    "PageCleaningRunSnapshot",
    "initialize_full_page_cleaning_ledger_schema",
    "initialize_full_page_cleaning_acceptance_schema",
]


def _run_snapshot(row) -> PageCleaningRunSnapshot:
    return PageCleaningRunSnapshot(
        page_cleaning_run_id=row["page_cleaning_run_id"],
        batch_id=row["batch_id"],
        page_id=row["page_id"],
        visual_contract_revision_id=row["visual_contract_revision_id"],
        source_artifact_id=row["source_artifact_id"],
        source_hash=row["source_hash"],
        profile_snapshot_id=row["profile_snapshot_id"],
        config_hash=row["config_hash"],
        idempotency_key=row["idempotency_key"],
        status=row["status"],
        supersedes_run_id=row["supersedes_run_id"],
    )


def _inventory_draft(row) -> CleaningInventoryItemDraft:
    return CleaningInventoryItemDraft(
        cleaning_inventory_item_id=row["cleaning_inventory_item_id"],
        text_segment_id=row["text_segment_id"],
        text_segment_revision_id=row["text_segment_revision_id"],
        bubble_instance_id=row["bubble_instance_id"],
        bubble_instance_revision_id=row["bubble_instance_revision_id"],
        assignment_id=row["assignment_id"],
        target_class=row["target_class"],
        eligibility=row["eligibility"],
        support_policy=row["support_policy"],
        dependency_fingerprint=row["dependency_fingerprint"],
        evidence_artifact_id=row["evidence_artifact_id"],
        inventory_ordinal=row["inventory_ordinal"],
    )


def _reservation_snapshot(row) -> CorrectionReservationSnapshot:
    return CorrectionReservationSnapshot(row["correction_reservation_id"], row["correction_chain_id"], row["ordinal"], row["idempotency_key"], row["status"], row["budget_before"], row["budget_after"])


def _chain_snapshot(row) -> CorrectionChainSnapshot:
    return CorrectionChainSnapshot(
        correction_chain_id=row["correction_chain_id"],
        page_cleaning_run_id=row["page_cleaning_run_id"],
        affected_target_scope_hash=row["affected_target_scope_hash"],
        source_fingerprint=row["source_fingerprint"],
        target_fingerprint=row["target_fingerprint"],
        policy_config_identity=row["policy_config_identity"],
        status=row["status"],
        max_automatic_corrections=row["max_automatic_corrections"],
    )


def _targets_by_result(connection: sqlite3.Connection, result_ids: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    if not result_ids:
        return {}
    rows = connection.execute(
        "SELECT instance_cleaning_result_id, cleaning_inventory_item_id "
        "FROM instance_result_inventory_targets WHERE instance_cleaning_result_id IN ({}) "
        "ORDER BY instance_cleaning_result_id, cleaning_inventory_item_id".format(
            ",".join("?" for _ in result_ids)
        ),
        result_ids,
    ).fetchall()
    targets: dict[str, list[str]] = {result_id: [] for result_id in result_ids}
    for row in rows:
        targets[row["instance_cleaning_result_id"]].append(row["cleaning_inventory_item_id"])
    return {result_id: tuple(item_ids) for result_id, item_ids in targets.items()}


def _result_snapshot(row, targets: dict[str, tuple[str, ...]]) -> InstanceCleaningResultSnapshot:
    return InstanceCleaningResultSnapshot(
        instance_cleaning_result_id=row["instance_cleaning_result_id"],
        page_cleaning_run_id=row["page_cleaning_run_id"],
        bubble_instance_id=row["bubble_instance_id"],
        bubble_instance_revision_id=row["bubble_instance_revision_id"],
        source_artifact_id=row["source_artifact_id"],
        source_hash=row["source_hash"],
        dependency_fingerprint=row["dependency_fingerprint"],
        config_hash=row["config_hash"],
        state=row["status"],
        workflow_attempt_id=row["workflow_attempt_id"],
        provider_name=row["provider_name"],
        profile_snapshot_id=row["profile_snapshot_id"],
        provider_candidate_artifact_id=row["provider_candidate_artifact_id"],
        official_candidate_artifact_id=row["official_candidate_artifact_id"],
        actual_changed_artifact_id=row["actual_changed_artifact_id"],
        required_support_artifact_id=row["required_support_artifact_id"],
        safe_edit_artifact_id=row["safe_edit_artifact_id"],
        protected_artifact_id=row["protected_artifact_id"],
        uncertainty_artifact_id=row["uncertainty_artifact_id"],
        visible_support_artifact_id=row["visible_support_artifact_id"],
        residue_artifact_id=row["residue_artifact_id"],
        boundary_damage_artifact_id=row["boundary_damage_artifact_id"],
        background_difference_artifact_id=row["background_difference_artifact_id"],
        validator_evidence_artifact_id=row["validator_evidence_artifact_id"],
        actual_changed_pixel_count=row["actual_changed_pixel_count"],
        unsafe_required_pixel_count=row["unsafe_required_pixel_count"],
        residue_pixel_count=row["residue_pixel_count"],
        inventory_item_ids=targets.get(row["instance_cleaning_result_id"], ()),
    )


def _disposition_snapshot(row) -> SegmentCleaningDispositionSnapshot:
    return SegmentCleaningDispositionSnapshot(
        segment_cleaning_disposition_id=row["segment_cleaning_disposition_id"],
        cleaning_inventory_item_id=row["cleaning_inventory_item_id"],
        disposition_code=row["disposition_code"],
        reason_code=row["reason_code"],
        root_stage=row["root_stage"],
        is_blocking=bool(row["is_blocking"]),
        policy_snapshot=row["policy_snapshot"],
        dependency_fingerprint=row["dependency_fingerprint"],
        evidence_artifact_id=row["evidence_artifact_id"],
        instance_cleaning_result_id=row["instance_cleaning_result_id"],
        stale_by_dependency_fingerprint=row["stale_by_dependency_fingerprint"],
        supersedes_disposition_id=row["supersedes_disposition_id"],
    )


def _verify_same_instance_result(
    existing,
    draft: InstanceCleaningResultDraft,
    inventory_item_ids: tuple[str, ...],
    connection: sqlite3.Connection,
) -> None:
    actual_targets = tuple(
        row["cleaning_inventory_item_id"]
        for row in connection.execute(
            "SELECT cleaning_inventory_item_id FROM instance_result_inventory_targets "
            "WHERE instance_cleaning_result_id = ? ORDER BY cleaning_inventory_item_id",
            (draft.instance_cleaning_result_id,),
        ).fetchall()
    )
    expected = (
        draft.page_cleaning_run_id,
        draft.bubble_instance_id,
        draft.bubble_instance_revision_id,
        draft.source_artifact_id,
        draft.source_hash,
        draft.dependency_fingerprint,
        draft.workflow_attempt_id,
        draft.provider_name,
        draft.profile_snapshot_id,
        draft.config_hash,
        draft.provider_candidate_artifact_id,
        draft.official_candidate_artifact_id,
        draft.actual_changed_artifact_id,
        draft.required_support_artifact_id,
        draft.safe_edit_artifact_id,
        draft.protected_artifact_id,
        draft.uncertainty_artifact_id,
        draft.visible_support_artifact_id,
        draft.residue_artifact_id,
        draft.boundary_damage_artifact_id,
        draft.background_difference_artifact_id,
        draft.validator_evidence_artifact_id,
        draft.actual_changed_pixel_count,
        draft.unsafe_required_pixel_count,
        draft.residue_pixel_count,
        draft.validator_summary,
        draft.state,
        tuple(sorted(inventory_item_ids)),
    )
    durable = (
        existing["page_cleaning_run_id"],
        existing["bubble_instance_id"],
        existing["bubble_instance_revision_id"],
        existing["source_artifact_id"],
        existing["source_hash"],
        existing["dependency_fingerprint"],
        existing["workflow_attempt_id"],
        existing["provider_name"],
        existing["profile_snapshot_id"],
        existing["config_hash"],
        existing["provider_candidate_artifact_id"],
        existing["official_candidate_artifact_id"],
        existing["actual_changed_artifact_id"],
        existing["required_support_artifact_id"],
        existing["safe_edit_artifact_id"],
        existing["protected_artifact_id"],
        existing["uncertainty_artifact_id"],
        existing["visible_support_artifact_id"],
        existing["residue_artifact_id"],
        existing["boundary_damage_artifact_id"],
        existing["background_difference_artifact_id"],
        existing["validator_evidence_artifact_id"],
        existing["actual_changed_pixel_count"],
        existing["unsafe_required_pixel_count"],
        existing["residue_pixel_count"],
        existing["validator_summary"],
        existing["status"],
        actual_targets,
    )
    if durable != expected:
        raise ValueError("Conflicting replay for InstanceCleaningResult.")


def _verify_same_correction_chain(row, draft: CorrectionChainDraft) -> None:
    durable = (
        row["page_cleaning_run_id"],
        row["page_id"],
        row["affected_target_scope_hash"],
        row["source_fingerprint"],
        row["target_fingerprint"],
        row["policy_config_identity"],
    )
    requested = (
        draft.page_cleaning_run_id,
        draft.page_id,
        draft.affected_target_scope_hash,
        draft.source_fingerprint,
        draft.target_fingerprint,
        draft.policy_config_identity,
    )
    if durable != requested:
        raise ValueError("Conflicting replay for CorrectionChain.")


def _verify_same_run(snapshot: PageCleaningRunSnapshot, draft: PageCleaningRunDraft) -> None:
    if (
        snapshot.page_cleaning_run_id,
        snapshot.batch_id,
        snapshot.page_id,
        snapshot.visual_contract_revision_id,
        snapshot.source_artifact_id,
        snapshot.source_hash,
        snapshot.profile_snapshot_id,
        snapshot.config_hash,
        snapshot.idempotency_key,
        snapshot.status,
        snapshot.supersedes_run_id,
    ) != (
        draft.page_cleaning_run_id,
        draft.batch_id,
        draft.page_id,
        draft.visual_contract_revision_id,
        draft.source_artifact_id,
        draft.source_hash,
        draft.profile_snapshot_id,
        draft.config_hash,
        draft.idempotency_key,
        draft.status,
        draft.supersedes_run_id,
    ):
        raise ValueError("Conflicting replay for PageCleaningRun idempotency key.")
