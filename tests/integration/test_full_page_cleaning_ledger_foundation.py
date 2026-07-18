from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import manga_read_flow.persistence.project_store as project_store_module
from manga_read_flow.persistence.full_page_cleaning_ledger_repository import (
    CleaningInventoryItemDraft,
    CorrectionChainDraft,
    InstanceCleaningResultDraft,
    PageCleaningRunDraft,
    SegmentCleaningDispositionDraft,
)
from manga_read_flow.persistence.project_store import (
    AppStore,
    PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,
    PROJECT_VISUAL_CONTRACT_VERSION,
    ProjectOpenStatus,
)


def test_new_project_creates_v3_ledger_schema_and_exposes_named_repository(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Ledger Foundation",
        source_language="ja",
        target_language="zh-Hans",
    )

    opened = store.open_project(project.project_id)

    assert opened.status is ProjectOpenStatus.READY
    assert opened.metadata is not None
    assert opened.metadata.project_schema_version == "project_full_page_cleaning_ledger_v3"
    assert "project_full_page_cleaning_ledger_v3" in {
        migration.version for migration in opened.project_migrations
    }
    assert type(opened.repositories().full_page_cleaning_ledger).__name__ == (
        "FullPageCleaningLedgerRepository"
    )
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("page_cleaning_runs",),
        ).fetchone() is not None


def test_explicit_v3_migration_reopens_a_v2_project_without_legacy_backfill(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="V2 upgrade", source_language="ja", target_language="zh-Hans"
    )
    connection = sqlite3.connect(project.project_db_path)
    try:
        connection.execute(
            """
            INSERT INTO cleaning_result_records (
                cleaning_result_id, project_id, page_id, visual_contract_revision_id,
                workflow_attempt_id, cleaned_artifact_id, evidence_artifact_id,
                input_hash, config_hash, decision, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-cleaning-result", project.project_id, "legacy-page",
                "legacy-visual", "legacy-attempt", "legacy-cleaned",
                "legacy-evidence", "legacy-input", "legacy-config", "pass", "now",
            ),
        )
        connection.execute("DROP INDEX uq_current_segment_cleaning_disposition")
        for table in (
            "cleaning_correction_reservations",
            "cleaning_correction_chains",
            "segment_cleaning_dispositions",
            "instance_result_inventory_targets",
            "instance_cleaning_results",
            "page_cleaning_inventory_items",
            "page_cleaning_runs",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            (PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,),
        )
        connection.execute(
            "UPDATE project_metadata SET project_schema_version = ?",
            (PROJECT_VISUAL_CONTRACT_VERSION,),
        )
        connection.commit()
    finally:
        connection.close()

    assert store.open_project(project.project_id).status is ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED
    migrated = store.migrate_project(project.project_id)

    assert migrated.status is ProjectOpenStatus.READY
    assert migrated.project_record == project
    assert migrated.metadata is not None
    assert migrated.metadata.project_id == project.project_id
    replayed_migration = store.migrate_project(project.project_id)
    assert replayed_migration.status is ProjectOpenStatus.READY
    assert replayed_migration.project_migrations == migrated.project_migrations
    with sqlite3.connect(project.project_db_path) as verification:
        assert verification.execute(
            "SELECT COUNT(*) FROM cleaning_result_records"
        ).fetchone() == (1,)
        assert verification.execute(
            "SELECT COUNT(*) FROM page_cleaning_runs"
        ).fetchone() == (0,)
        assert verification.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'page_cleaning_runs'"
        ).fetchone() == (1,)


def test_v3_checksum_mismatch_blocks_explicit_migration_and_repository_access(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="V3 checksum", source_language="ja", target_language="zh-Hans"
    )
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = ?",
            ("tampered", PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION),
        )

    opened = store.open_project(project.project_id)

    assert opened.status is ProjectOpenStatus.CHECKSUM_MISMATCH
    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.CHECKSUM_MISMATCH
    with pytest.raises(RuntimeError):
        opened.repositories()


def test_future_project_metadata_version_blocks_open_and_migration_without_downgrade(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Future schema", source_language="ja", target_language="zh-Hans"
    )
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "UPDATE project_metadata SET project_schema_version = 'project_future_v99'"
        )

    assert store.open_project(project.project_id).status is ProjectOpenStatus.NEWER_INCOMPATIBLE_SCHEMA
    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.NEWER_INCOMPATIBLE_SCHEMA
    with sqlite3.connect(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT project_schema_version FROM project_metadata"
        ).fetchone() == ("project_future_v99",)


def test_failed_v3_migration_rolls_back_ddl_and_does_not_write_its_marker(tmp_path, monkeypatch):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="V3 rollback", source_language="ja", target_language="zh-Hans"
    )
    with sqlite3.connect(project.project_db_path) as connection:
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            (PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,),
        )

    def fail_after_ddl(connection):
        connection.execute("CREATE TABLE migration_rollback_probe (id TEXT PRIMARY KEY)")
        raise sqlite3.OperationalError("injected migration failure")

    monkeypatch.setattr(
        project_store_module, "initialize_repository_core_schema", fail_after_ddl
    )

    assert store.migrate_project(project.project_id).status is ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    with sqlite3.connect(project.project_db_path) as verification:
        assert verification.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,),
        ).fetchone() is None
        assert verification.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'migration_rollback_probe'"
        ).fetchone() is None


def test_page_cleaning_run_replays_the_same_idempotency_key(tmp_path):
    repositories = _ready_repositories(tmp_path)
    repositories.content_state.create_page(
        page_id="page-ledger",
        batch_id="batch-ledger",
        original_artifact_id="original-ledger",
        status="uploaded",
    )
    draft = PageCleaningRunDraft(
        page_cleaning_run_id="run-ledger-1",
        batch_id="batch-ledger",
        page_id="page-ledger",
        visual_contract_revision_id="visual-ledger-1",
        source_artifact_id="original-ledger",
        source_hash="source-hash-1",
        profile_snapshot_id=None,
        config_hash="config-hash-1",
        idempotency_key="run-key-1",
    )

    first = repositories.full_page_cleaning_ledger.create_or_replay_page_cleaning_run(
        draft
    )
    replay = repositories.full_page_cleaning_ledger.create_or_replay_page_cleaning_run(
        draft
    )

    assert first.page_cleaning_run_id == "run-ledger-1"
    assert first.status == "planned"
    assert replay == first


def test_recovery_selects_the_requested_run_without_page_status_or_timestamp_heuristics(tmp_path):
    repositories = _ready_repositories(tmp_path)
    repositories.content_state.create_page(
        page_id="page-recovery", batch_id="batch-recovery", original_artifact_id="original", status="uploaded"
    )
    ledger = repositories.full_page_cleaning_ledger
    first = ledger.create_or_replay_page_cleaning_run(
        PageCleaningRunDraft("run-first", "batch-recovery", "page-recovery", "visual-1", "original", "hash-1", None, "config", "key-first")
    )
    second = ledger.create_or_replay_page_cleaning_run(
        PageCleaningRunDraft("run-second", "batch-recovery", "page-recovery", "visual-2", "original", "hash-2", None, "config", "key-second")
    )
    for run, item_id in ((first, "item-first"), (second, "item-second")):
        ledger.freeze_cleaning_inventory(
            page_cleaning_run_id=run.page_cleaning_run_id,
            inventory_fingerprint=f"inventory-{run.page_cleaning_run_id}",
            items=(CleaningInventoryItemDraft(item_id, "segment", f"segment-{run.page_cleaning_run_id}", None, None, None, "ordinary_dialogue", "E1", "required", "fingerprint", None, 1),),
        )
    with sqlite3.connect(repositories.identity._project_db_path) as connection:
        connection.execute("UPDATE pages SET status = 'unexpected' WHERE page_id = 'page-recovery'")

    recovery = ledger.load_page_cleaning_recovery_ledger(
        page_cleaning_run_id=first.page_cleaning_run_id
    )

    assert recovery.run.page_cleaning_run_id == "run-first"
    assert recovery.run.source_hash == "hash-1"
    assert recovery.inventory[0].cleaning_inventory_item_id == "item-first"


def test_named_uow_exposes_slice1_ledger_without_acceptance_api(tmp_path):
    repositories = _ready_repositories(tmp_path)
    repositories.content_state.create_page(
        page_id="page-uow", batch_id="batch-uow", original_artifact_id="original", status="uploaded"
    )

    run = repositories.uow.create_or_replay_page_cleaning_run(
        PageCleaningRunDraft("run-uow", "batch-uow", "page-uow", "visual", "original", "hash", None, "config", "uow-key")
    )

    assert run.page_cleaning_run_id == "run-uow"
    assert not hasattr(repositories.uow, "accept_full_page_cleaning")


def test_inventory_freeze_is_immutable_and_replayable(tmp_path):
    repositories = _ready_repositories(tmp_path)
    repositories.content_state.create_page(
        page_id="page-inventory", batch_id="batch-inventory", original_artifact_id="original", status="uploaded"
    )
    run = repositories.full_page_cleaning_ledger.create_or_replay_page_cleaning_run(
        PageCleaningRunDraft("run-inventory", "batch-inventory", "page-inventory", "visual-1", "original", "hash", None, "config", "run-inventory-key")
    )
    items = (
        CleaningInventoryItemDraft("item-1", "segment-1", "segment-revision-1", "instance-1", "instance-revision-1", "assignment-1", "ordinary_dialogue", "E1", "required", "fingerprint-1", "evidence-1", 1),
        CleaningInventoryItemDraft("item-2", "segment-2", "segment-revision-2", None, None, "assignment-2", "ordinary_dialogue", "REVIEW", "required", "fingerprint-2", "evidence-2", 2),
    )

    assert repositories.full_page_cleaning_ledger.freeze_cleaning_inventory(
        page_cleaning_run_id=run.page_cleaning_run_id,
        inventory_fingerprint="inventory-hash",
        items=items,
    ) == items
    assert repositories.uow.load_page_cleaning_inventory(
        page_cleaning_run_id=run.page_cleaning_run_id
    ) == items
    with pytest.raises(ValueError, match="Frozen inventory replay conflicts"):
        repositories.full_page_cleaning_ledger.freeze_cleaning_inventory(
            page_cleaning_run_id=run.page_cleaning_run_id,
            inventory_fingerprint="different-inventory-hash",
            items=items,
        )
    assert repositories.full_page_cleaning_ledger.freeze_cleaning_inventory(
        page_cleaning_run_id=run.page_cleaning_run_id,
        inventory_fingerprint="inventory-hash",
        items=items,
    ) == items


def test_slice1_run_lifecycle_allows_execution_but_rejects_slice2_and_invalid_transitions(tmp_path):
    repositories, run, _ = _frozen_run(tmp_path, page_id="page-lifecycle")

    executing = repositories.uow.transition_page_cleaning_run(
        page_cleaning_run_id=run.page_cleaning_run_id,
        target_status="executing",
    )
    blocked = repositories.uow.transition_page_cleaning_run(
        page_cleaning_run_id=run.page_cleaning_run_id,
        target_status="blocked",
    )

    assert executing.status == "executing"
    assert blocked.status == "blocked"
    with pytest.raises(ValueError, match="Invalid Slice 1"):
        repositories.uow.transition_page_cleaning_run(
            page_cleaning_run_id=run.page_cleaning_run_id,
            target_status="executing",
        )
    with pytest.raises(ValueError, match="belongs to Slice 2"):
        repositories.uow.transition_page_cleaning_run(
            page_cleaning_run_id=run.page_cleaning_run_id,
            target_status="accepted",
        )
def test_cleaned_pass_without_slice2_acceptance_is_rejected(tmp_path):
    repositories = _ready_repositories(tmp_path)
    repositories.content_state.create_page(page_id="page-disposition", batch_id="batch-disposition", original_artifact_id="original", status="uploaded")
    run = repositories.full_page_cleaning_ledger.create_or_replay_page_cleaning_run(PageCleaningRunDraft("run-disposition", "batch-disposition", "page-disposition", "visual", "original", "hash", None, "config", "run-key"))
    repositories.full_page_cleaning_ledger.freeze_cleaning_inventory(page_cleaning_run_id=run.page_cleaning_run_id, inventory_fingerprint="inventory", items=(CleaningInventoryItemDraft("item", "segment", "segment-revision", None, None, None, "ordinary_dialogue", "E1", "required", "fingerprint", "evidence", 1),))

    with pytest.raises(ValueError, match="CLEANED_PASS requires Slice 2"):
        repositories.full_page_cleaning_ledger.record_or_supersede_segment_disposition(SegmentCleaningDispositionDraft("disposition", "item", "CLEANED_PASS", "candidate", "cleaning", True, "policy", "fingerprint", "evidence"))

    with sqlite3.connect(repositories.identity._project_db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="CLEANED_PASS"):
            connection.execute(
                """
                INSERT INTO segment_cleaning_dispositions (
                    segment_cleaning_disposition_id, project_id, cleaning_inventory_item_id,
                    disposition_code, reason_code, root_stage, is_blocking, policy_snapshot,
                    dependency_fingerprint, created_at
                ) VALUES (?, ?, ?, 'CLEANED_PASS', ?, ?, ?, ?, ?, ?)
                """,
                ("direct-cleaned-pass", repositories.identity.get_metadata().project_id, "item", "candidate", "cleaning", 1, "policy", "fingerprint", "now"),
            )


def test_validated_instance_result_persists_artifact_evidence_and_unique_attribution(tmp_path):
    repositories, run, items = _frozen_run(tmp_path, page_id="page-result")
    result = InstanceCleaningResultDraft(
        instance_cleaning_result_id="result-1",
        page_cleaning_run_id=run.page_cleaning_run_id,
        bubble_instance_id="instance-1",
        bubble_instance_revision_id="instance-revision-1",
        source_artifact_id="original",
        source_hash="hash",
        dependency_fingerprint="result-fingerprint",
        config_hash="config",
        state="validated",
        official_candidate_artifact_id="candidate-artifact",
        actual_changed_artifact_id="changed-mask",
        validator_evidence_artifact_id="validator-evidence",
        actual_changed_pixel_count=7863,
        unsafe_required_pixel_count=0,
        residue_pixel_count=0,
        validator_summary="pass",
        workflow_attempt_id="attempt-1",
        provider_name="test-provider",
        profile_snapshot_id="profile-snapshot",
        provider_candidate_artifact_id="provider-candidate",
        required_support_artifact_id="required-support",
        safe_edit_artifact_id="safe-edit",
        protected_artifact_id="protected-mask",
        uncertainty_artifact_id="uncertainty-mask",
        visible_support_artifact_id="visible-support",
        residue_artifact_id="residue-mask",
        boundary_damage_artifact_id="boundary-damage",
        background_difference_artifact_id="background-difference",
    )

    snapshot = repositories.full_page_cleaning_ledger.append_instance_cleaning_result(
        result,
        inventory_item_ids=(items[0].cleaning_inventory_item_id,),
    )

    assert snapshot.state == "validated"
    assert snapshot.actual_changed_pixel_count == 7863
    assert snapshot.inventory_item_ids == (items[0].cleaning_inventory_item_id,)
    assert snapshot.official_candidate_artifact_id == "candidate-artifact"
    assert snapshot.actual_changed_artifact_id == "changed-mask"

    recovery = repositories.full_page_cleaning_ledger.load_recovery_ledger(
        page_cleaning_run_id=run.page_cleaning_run_id
    )
    recovered = recovery.instance_results[0]
    assert recovered.source_hash == "hash"
    assert recovered.dependency_fingerprint == "result-fingerprint"
    assert recovered.profile_snapshot_id == "profile-snapshot"
    assert recovered.required_support_artifact_id == "required-support"
    assert recovered.background_difference_artifact_id == "background-difference"
    assert recovered.validator_evidence_artifact_id == "validator-evidence"
    assert recovered.inventory_item_ids == (items[0].cleaning_inventory_item_id,)

    assert repositories.full_page_cleaning_ledger.append_instance_cleaning_result(
        result,
        inventory_item_ids=(items[0].cleaning_inventory_item_id,),
    ) == snapshot

    with pytest.raises(ValueError, match="already has a current instance result"):
        repositories.full_page_cleaning_ledger.append_instance_cleaning_result(
            InstanceCleaningResultDraft(
                **{**result.__dict__, "instance_cleaning_result_id": "result-2", "dependency_fingerprint": "new-fingerprint"}
            ),
            inventory_item_ids=(items[0].cleaning_inventory_item_id,),
        )
    with pytest.raises(ValueError, match="BubbleInstance revision"):
        repositories.full_page_cleaning_ledger.append_instance_cleaning_result(
            _instance_result(
                "wrong-instance", run.page_cleaning_run_id,
                instance="wrong-instance", revision="wrong-instance-revision",
            ),
            inventory_item_ids=(items[0].cleaning_inventory_item_id,),
        )


def test_disposition_is_superseded_without_losing_its_history(tmp_path):
    repositories, run, items = _frozen_run(tmp_path, page_id="page-disposition-history")
    ledger = repositories.full_page_cleaning_ledger
    ledger.record_or_supersede_segment_disposition(
        SegmentCleaningDispositionDraft(
            "missing-evidence", items[0].cleaning_inventory_item_id,
            "MISSING_REQUIRED_EVIDENCE", "missing_instance_evidence", "cleaning",
            True, "policy", "fingerprint-1", "evidence-1",
        )
    )
    ledger.record_or_supersede_segment_disposition(
        SegmentCleaningDispositionDraft(
            "unsafe-block", items[0].cleaning_inventory_item_id,
            "BLOCKED_UNSAFE_EDIT", "unsafe_required_pixels", "validation",
            True, "policy", "fingerprint-2", "evidence-2",
        )
    )

    recovery = ledger.load_recovery_ledger(page_cleaning_run_id=run.page_cleaning_run_id)

    assert [(item.segment_cleaning_disposition_id, item.disposition_code) for item in recovery.current_dispositions] == [
        ("unsafe-block", "BLOCKED_UNSAFE_EDIT")
    ]
    with sqlite3.connect(repositories.identity._project_db_path) as connection:
        previous = connection.execute(
            "SELECT superseded_by_disposition_id FROM segment_cleaning_dispositions "
            "WHERE segment_cleaning_disposition_id = 'missing-evidence'"
        ).fetchone()
    assert previous == ("unsafe-block",)
    assert repositories.uow.list_current_segment_cleaning_dispositions(
        page_cleaning_run_id=run.page_cleaning_run_id
    ) == recovery.current_dispositions


def test_one_correction_reservation_replays_and_rejects_a_second_attempt(tmp_path):
    repositories, run, _ = _frozen_run(tmp_path, page_id="page-correction")
    ledger = repositories.full_page_cleaning_ledger
    chain = CorrectionChainDraft(
        "chain-1", run.page_cleaning_run_id, "page-correction", "scope",
        "source", "target", "policy",
    )

    first = ledger.reserve_or_replay_correction(
        chain=chain, correction_reservation_id="reservation-1",
        idempotency_key="correction-key-1", reserved_attempt_id="attempt-1",
    )
    replay = ledger.reserve_or_replay_correction(
        chain=chain, correction_reservation_id="reservation-1",
        idempotency_key="correction-key-1", reserved_attempt_id="attempt-1",
    )

    assert first == replay
    assert (first.ordinal, first.budget_before, first.budget_after) == (1, 1, 0)
    with pytest.raises(ValueError, match="Second automatic correction"):
        ledger.reserve_or_replay_correction(
            chain=chain, correction_reservation_id="reservation-2",
            idempotency_key="correction-key-2", reserved_attempt_id="attempt-2",
        )
    with pytest.raises(ValueError, match="Second automatic correction"):
        repositories.uow.reject_second_automatic_cleaning_correction(
            correction_chain_id=chain.correction_chain_id
        )


def test_correction_reservation_records_recovery_lifecycle_without_new_budget(tmp_path):
    repositories, run, _ = _frozen_run(tmp_path, page_id="page-correction-lifecycle")
    ledger = repositories.full_page_cleaning_ledger
    reservation = ledger.reserve_or_replay_correction(
        chain=CorrectionChainDraft("chain-lifecycle", run.page_cleaning_run_id, "page-correction-lifecycle", "scope", "source", "target", "policy"),
        correction_reservation_id="reservation-lifecycle", idempotency_key="lifecycle-key",
        reserved_attempt_id="attempt-lifecycle",
    )

    executing = repositories.uow.mark_cleaning_correction_executing(
        correction_reservation_id=reservation.correction_reservation_id
    )
    abandoned = repositories.uow.abandon_cleaning_correction_after_crash(
        correction_reservation_id=reservation.correction_reservation_id
    )

    assert executing.status == "executing"
    assert abandoned.status == "abandoned_after_crash"
    assert (abandoned.ordinal, abandoned.budget_after) == (1, 0)
    with pytest.raises(ValueError, match="cannot transition"):
        repositories.uow.complete_cleaning_correction(
            correction_reservation_id=reservation.correction_reservation_id
        )


def test_stale_unaccepted_run_preserves_ledger_and_never_repairs_pointer(tmp_path):
    repositories, run, items = _frozen_run(tmp_path, page_id="page-stale")
    ledger = repositories.full_page_cleaning_ledger
    ledger.append_instance_cleaning_result(
        _instance_result("result-stale", run.page_cleaning_run_id),
        inventory_item_ids=(items[0].cleaning_inventory_item_id,),
    )
    ledger.reserve_or_replay_correction(
        chain=CorrectionChainDraft("chain-stale", run.page_cleaning_run_id, "page-stale", "scope", "source", "target", "policy"),
        correction_reservation_id="reservation-stale", idempotency_key="stale-key",
        reserved_attempt_id="attempt-stale",
    )
    ledger.record_or_supersede_segment_disposition(
        SegmentCleaningDispositionDraft(
            "stale-disposition", items[0].cleaning_inventory_item_id,
            "MISSING_REQUIRED_EVIDENCE", "missing_evidence", "cleaning", True,
            "policy", "fingerprint", "evidence",
        )
    )

    assert ledger.mark_unaccepted_cleaning_run_stale(
        page_cleaning_run_id=run.page_cleaning_run_id,
        dependency_fingerprint="new-source",
    ) == "STALE_MARKED"

    recovery = ledger.load_recovery_ledger(page_cleaning_run_id=run.page_cleaning_run_id)
    assert repositories.uow.load_page_cleaning_recovery_ledger(
        page_cleaning_run_id=run.page_cleaning_run_id
    ) == recovery
    assert recovery.run.status == "stale"
    assert recovery.instance_results[0].state == "stale"
    assert recovery.current_dispositions[0].stale_by_dependency_fingerprint == "new-source"
    assert recovery.correction_chains[0].status == "stale"
    assert recovery.correction_chains[0].max_automatic_corrections == 1
    assert recovery.correction_reservations[0].status == "stale"
    with sqlite3.connect(repositories.identity._project_db_path) as connection:
        pointer = connection.execute(
            "SELECT active_cleaned_artifact_id FROM pages WHERE page_id = 'page-stale'"
        ).fetchone()
    assert pointer == (None,)
    with pytest.raises(ValueError, match="non-active run"):
        ledger.append_instance_cleaning_result(
            _instance_result("result-after-stale", run.page_cleaning_run_id),
            inventory_item_ids=(items[0].cleaning_inventory_item_id,),
        )
    with pytest.raises(ValueError, match="non-active run"):
        ledger.reserve_or_replay_correction(
            chain=CorrectionChainDraft("chain-after-stale", run.page_cleaning_run_id, "page-stale", "scope-2", "source", "target", "policy"),
            correction_reservation_id="reservation-after-stale",
            idempotency_key="stale-key-2", reserved_attempt_id="attempt-after-stale",
        )


def test_active_pointer_stale_repair_is_explicitly_deferred_to_slice2(tmp_path):
    repositories, run, _ = _frozen_run(tmp_path, page_id="page-pointer")
    with sqlite3.connect(repositories.identity._project_db_path) as connection:
        connection.execute(
            "UPDATE pages SET active_cleaned_artifact_id = 'accepted-cleaned' "
            "WHERE page_id = 'page-pointer'"
        )

    outcome = repositories.full_page_cleaning_ledger.mark_unaccepted_cleaning_run_stale(
        page_cleaning_run_id=run.page_cleaning_run_id,
        dependency_fingerprint="new-source",
    )

    assert outcome == "ACTIVE_POINTER_STALE_REPAIR_REQUIRES_SLICE_2"
    assert repositories.full_page_cleaning_ledger.load_recovery_ledger(
        page_cleaning_run_id=run.page_cleaning_run_id
    ).run.status == "inventory_frozen"
    with sqlite3.connect(repositories.identity._project_db_path) as connection:
        assert connection.execute(
            "SELECT active_cleaned_artifact_id FROM pages WHERE page_id = 'page-pointer'"
        ).fetchone() == ("accepted-cleaned",)


@pytest.mark.parametrize("case_id", ("case-71", "case-72"))
def test_case71_and_case72_inventory_fixture_uses_results_and_explicit_blockers_only(tmp_path, case_id):
    repositories = _ready_repositories(tmp_path)
    repositories.content_state.create_page(
        page_id=case_id, batch_id=f"batch-{case_id}", original_artifact_id="original", status="uploaded"
    )
    run = repositories.full_page_cleaning_ledger.create_or_replay_page_cleaning_run(
        PageCleaningRunDraft(f"run-{case_id}", f"batch-{case_id}", case_id, "visual", "original", "hash", None, "config", f"key-{case_id}")
    )
    segment_ids = (
        ("g002/s01", "g002/s02", "g003", "g004", "g005", "g007/s01")
        if case_id == "case-71"
        else ("g002", "g004", "g003", "g005", "g007/s01", "g007/s02")
    )
    items = tuple(
        CleaningInventoryItemDraft(
            f"{case_id}-item-{index}", segment_id, f"{segment_id}-revision",
            f"instance-{index}" if index < 3 else None,
            f"instance-revision-{index}" if index < 3 else None,
            f"assignment-{index}", "ordinary_dialogue", "E1", "required",
            f"fingerprint-{index}", None, index,
        )
        for index, segment_id in enumerate(segment_ids, start=1)
    )
    ledger = repositories.full_page_cleaning_ledger
    ledger.freeze_cleaning_inventory(page_cleaning_run_id=run.page_cleaning_run_id, inventory_fingerprint="case-inventory", items=items)
    if case_id == "case-71":
        ledger.append_instance_cleaning_result(_instance_result("g002-s01", run.page_cleaning_run_id), inventory_item_ids=(items[0].cleaning_inventory_item_id,))
        ledger.append_instance_cleaning_result(_instance_result("g002-s02", run.page_cleaning_run_id, instance="instance-2", revision="instance-revision-2"), inventory_item_ids=(items[1].cleaning_inventory_item_id,))
        for index, item in enumerate(items[2:], start=3):
            ledger.record_or_supersede_segment_disposition(
                SegmentCleaningDispositionDraft(
                    f"missing-{index}", item.cleaning_inventory_item_id,
                    "MISSING_REQUIRED_EVIDENCE", "no_instance_result", "cleaning", True,
                    "policy", f"fingerprint-{index}", None,
                )
            )
    else:
        g002 = ledger.append_instance_cleaning_result(
            _instance_result("case72-g002", run.page_cleaning_run_id, unsafe_required_pixel_count=710),
            inventory_item_ids=(items[0].cleaning_inventory_item_id,),
        )
        g004 = ledger.append_instance_cleaning_result(
            _instance_result("case72-g004", run.page_cleaning_run_id, instance="instance-2", revision="instance-revision-2", unsafe_required_pixel_count=70),
            inventory_item_ids=(items[1].cleaning_inventory_item_id,),
        )
        for result, item, count in ((g002, items[0], 710), (g004, items[1], 70)):
            ledger.record_or_supersede_segment_disposition(
                SegmentCleaningDispositionDraft(
                    f"unsafe-{count}", item.cleaning_inventory_item_id,
                    "BLOCKED_UNSAFE_REQUIRED", "unsafe_required_pixels", "validation",
                    True, "policy", f"fingerprint-{count}", "validator-evidence",
                    result.instance_cleaning_result_id,
                )
            )
        ledger.record_or_supersede_segment_disposition(
            SegmentCleaningDispositionDraft(
                "incomplete-g003", items[2].cleaning_inventory_item_id,
                "INCOMPLETE_REVIEW", "review_required", "cleaning", True,
                "policy", "fingerprint-g003", None,
            )
        )
        for item in items[3:]:
            ledger.record_or_supersede_segment_disposition(
                SegmentCleaningDispositionDraft(
                    f"missing-{item.cleaning_inventory_item_id}", item.cleaning_inventory_item_id,
                    "MISSING_REQUIRED_EVIDENCE", "no_instance_result", "cleaning", True,
                    "policy", f"fingerprint-{item.cleaning_inventory_item_id}", None,
                )
            )

    recovery = ledger.load_recovery_ledger(page_cleaning_run_id=run.page_cleaning_run_id)
    assert len(recovery.inventory) == 6
    assert {result.state for result in recovery.instance_results} == {"validated"}
    if case_id == "case-71":
        assert {item.disposition_code for item in recovery.current_dispositions} == {"MISSING_REQUIRED_EVIDENCE"}
        assert {item.cleaning_inventory_item_id for item in recovery.current_dispositions}.isdisjoint(
            {items[0].cleaning_inventory_item_id, items[1].cleaning_inventory_item_id}
        )
    else:
        assert {
            item.disposition_code for item in recovery.current_dispositions
        } == {"BLOCKED_UNSAFE_REQUIRED", "INCOMPLETE_REVIEW", "MISSING_REQUIRED_EVIDENCE"}
        assert {
            result.unsafe_required_pixel_count for result in recovery.instance_results
        } == {70, 710}


def test_slice1_foundation_initializer_and_repository_keep_their_original_boundary(tmp_path):
    source = Path(
        "src/manga_read_flow/persistence/full_page_cleaning_ledger_repository.py"
    ).read_text(encoding="utf-8")
    foundation_source = source.split(
        "def initialize_full_page_cleaning_acceptance_schema", 1
    )[0].split("def initialize_full_page_cleaning_ledger_schema", 1)[1]
    repository_source = source.split(
        "def initialize_full_page_cleaning_ledger_schema", 1
    )[0]
    repositories = _ready_repositories(tmp_path)
    with sqlite3.connect(repositories.identity._project_db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert "combined_cleaning_candidates" in tables
    assert "page_cleaning_validation_records" in tables
    assert "combined_cleaning_candidates" not in foundation_source
    assert "page_cleaning_validation_records" not in foundation_source
    assert "UPDATE pages SET active_cleaned_artifact_id" not in repository_source
    assert "accept_stage(" not in repository_source
    assert "manga_read_flow.providers" not in repository_source
    assert "ArtifactService" not in repository_source
    source_root = Path("src/manga_read_flow")
    non_persistence_sqlite_users = [
        path
        for path in source_root.rglob("*.py")
        if "persistence" not in path.parts
        and any(token in path.read_text(encoding="utf-8") for token in ("import sqlite3", "sqlite3.connect", "connect_existing("))
    ]
    assert non_persistence_sqlite_users == []
    ledger_tables = {
        "page_cleaning_runs",
        "page_cleaning_inventory_items",
        "instance_cleaning_results",
        "instance_result_inventory_targets",
        "segment_cleaning_dispositions",
        "cleaning_correction_chains",
        "cleaning_correction_reservations",
    }
    with sqlite3.connect(repositories.identity._project_db_path) as connection:
        column_types = {
            column[2].upper()
            for table in ledger_tables
            for column in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
    assert "BLOB" not in column_types


def _instance_result(
    result_id,
    run_id,
    *,
    instance="instance-1",
    revision="instance-revision-1",
    unsafe_required_pixel_count=0,
):
    return InstanceCleaningResultDraft(
        instance_cleaning_result_id=result_id, page_cleaning_run_id=run_id,
        bubble_instance_id=instance, bubble_instance_revision_id=revision,
        source_artifact_id="original", source_hash="hash",
        dependency_fingerprint=f"fingerprint-{result_id}", config_hash="config",
        state="validated", official_candidate_artifact_id="candidate",
        actual_changed_artifact_id="changed", validator_evidence_artifact_id="validator",
        actual_changed_pixel_count=1, unsafe_required_pixel_count=unsafe_required_pixel_count,
        residue_pixel_count=0, validator_summary="pass",
    )


def _ready_repositories(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Ledger Test",
        source_language="ja",
        target_language="zh-Hans",
    )
    opened = store.open_project(project.project_id)
    assert opened.status is ProjectOpenStatus.READY
    return opened.repositories()


def _frozen_run(tmp_path, *, page_id):
    repositories = _ready_repositories(tmp_path)
    repositories.content_state.create_page(page_id=page_id, batch_id=f"batch-{page_id}", original_artifact_id="original", status="uploaded")
    run = repositories.full_page_cleaning_ledger.create_or_replay_page_cleaning_run(PageCleaningRunDraft(f"run-{page_id}", f"batch-{page_id}", page_id, "visual", "original", "hash", None, "config", f"key-{page_id}"))
    items = (CleaningInventoryItemDraft(f"item-{page_id}", "segment", "segment-revision", "instance-1", "instance-revision-1", "assignment", "ordinary_dialogue", "E1", "required", "fingerprint", "evidence", 1),)
    repositories.full_page_cleaning_ledger.freeze_cleaning_inventory(page_cleaning_run_id=run.page_cleaning_run_id, inventory_fingerprint="inventory", items=items)
    return repositories, run, items
