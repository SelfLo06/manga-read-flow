from __future__ import annotations

import sqlite3
import pytest

from manga_read_flow.application.process_page import ProcessPageCommand, ProcessPageService
from manga_read_flow.application.repair_grouping_current import (
    RepairGroupingCurrentApplicationService,
    RepairGroupingCurrentCommand,
)
from manga_read_flow.application.select_physical_boundary_grouping_input import (
    SelectPhysicalBoundaryGroupingInputApplicationService,
    SelectPhysicalBoundaryGroupingInputCommand,
)
from tests.integration.test_grouping_acceptance_application import (
    _accept_command,
    _accept_service,
    _checked_candidate,
)
from tests.integration.test_grouping_candidate_application import _accept_ocr_v2
from manga_read_flow.providers.fake import FakeProvider


def _selection_command(context):
    candidate = context["candidate"]
    return SelectPhysicalBoundaryGroupingInputCommand(
        page_id=context["page_id"],
        current_detection_dependency_id=context["dependency_id"],
        current_profile_snapshot_id=candidate.profile_snapshot_id,
        expected_grouping_producer_name=candidate.producer_name,
        expected_grouping_producer_version=candidate.producer_version,
        expected_grouping_producer_implementation_hash=candidate.producer_implementation_hash,
        expected_grouping_operation_semantics_version=candidate.operation_semantics_version,
    )


def test_physical_boundary_selector_returns_exact_current_binding_without_producer(tmp_path):
    context = _checked_candidate(tmp_path)
    accepted = _accept_service(context).accept(
        _accept_command(context, task_suffix="physical-boundary-selector")
    )

    result = SelectPhysicalBoundaryGroupingInputApplicationService(
        project_id=context["project"].project_id,
        repositories=context["repositories"],
        artifact_service=context["artifacts"],
    ).select(_selection_command(context))

    assert result.status == "SELECTED"
    assert result.binding.grouping_acceptance_id == accepted.acceptance.acceptance_id
    assert result.binding.grouping_snapshot_id == context["candidate"].snapshot_id
    assert result.binding.grouping_manifest_sha256 == context["candidate"].manifest_artifact_sha256
    assert tuple(item.ocr_result_id for item in result.binding.ocr_dependencies) == tuple(
        item.ocr_result_id for item in context["candidate"].ocr_dependencies
    )


def test_physical_boundary_selector_rejects_after_atomic_ocr_stale(tmp_path):
    context = _checked_candidate(tmp_path)
    _accept_service(context).accept(_accept_command(context, task_suffix="selector-stale"))
    _accept_ocr_v2(context["repositories"], context["candidate"])

    result = SelectPhysicalBoundaryGroupingInputApplicationService(
        project_id=context["project"].project_id,
        repositories=context["repositories"],
        artifact_service=context["artifacts"],
    ).select(_selection_command(context))

    assert result.status == "REJECTED"
    assert result.error_code == "NO_CURRENT_GROUPING"


def test_formal_detection_acceptance_atomically_stales_current_grouping(tmp_path):
    context = _checked_candidate(tmp_path)
    _accept_service(context).accept(_accept_command(context, task_suffix="detection-stale"))

    with pytest.raises(ValueError, match="detection_success/ocr"):
        ProcessPageService(
            project_id=context["project"].project_id,
            repositories=context["repositories"],
            artifact_service=context["artifacts"],
            provider=FakeProvider(fake_mode="detection_success"),
        ).process_page(ProcessPageCommand(page_id=context["page_id"]))

    state = context["repositories"].grouping_acceptance.get_page_state(context["page_id"])
    assert state.active_grouping_snapshot_id is None
    facts = context["repositories"].grouping_stale.list_for_snapshot(
        context["candidate"].snapshot_id
    )
    assert {fact.reason_type for fact in facts} == {"DETECTION_DEPENDENCY_CHANGED"}


def test_recovery_repairs_legacy_dependency_mismatch_with_cas_and_stale_fact(tmp_path):
    context = _checked_candidate(tmp_path)
    accepted = _accept_service(context).accept(
        _accept_command(context, task_suffix="repair-legacy")
    )
    dependency = context["candidate"].ocr_dependencies[0]
    with sqlite3.connect(context["project"].project_db_path) as connection:
        connection.execute(
            "UPDATE text_blocks SET active_ocr_result_id = NULL WHERE text_block_id = ?",
            (dependency.text_block_id,),
        )

    outcome = RepairGroupingCurrentApplicationService(
        repositories=context["repositories"]
    ).repair(RepairGroupingCurrentCommand(
        page_id=context["page_id"],
        expected_active_grouping_snapshot_id=accepted.current.snapshot.snapshot_id,
        expected_page_grouping_state_version=1,
        triggering_operation_id="recovery-test-1",
    ))

    assert outcome.status == "REPAIRED"
    state = context["repositories"].grouping_acceptance.get_page_state(context["page_id"])
    assert state.active_grouping_snapshot_id is None
    assert state.version == 2
    fact = context["repositories"].grouping_stale.list_for_snapshot(
        context["candidate"].snapshot_id
    )[0]
    assert fact.reason_type == "DEPENDENCY_MISMATCH_REPAIR"

    replay = RepairGroupingCurrentApplicationService(
        repositories=context["repositories"]
    ).repair(RepairGroupingCurrentCommand(
        page_id=context["page_id"],
        expected_active_grouping_snapshot_id=accepted.current.snapshot.snapshot_id,
        expected_page_grouping_state_version=1,
        triggering_operation_id="recovery-test-2",
    ))
    assert replay.status == "ALREADY_CLEAR"


def test_recovery_cas_conflict_does_not_change_current(tmp_path):
    context = _checked_candidate(tmp_path)
    accepted = _accept_service(context).accept(
        _accept_command(context, task_suffix="repair-conflict")
    )
    outcome = RepairGroupingCurrentApplicationService(
        repositories=context["repositories"]
    ).repair(RepairGroupingCurrentCommand(
        page_id=context["page_id"],
        expected_active_grouping_snapshot_id=accepted.current.snapshot.snapshot_id,
        expected_page_grouping_state_version=99,
        triggering_operation_id="recovery-conflict",
    ))
    assert outcome.status == "CONFLICT_RELOAD"
    assert context["repositories"].grouping_acceptance.get_current(
        context["page_id"]
    ).snapshot.snapshot_id == context["candidate"].snapshot_id


def test_recovery_database_failure_rolls_back_stale_fact_and_pointer(tmp_path):
    context = _checked_candidate(tmp_path)
    accepted = _accept_service(context).accept(
        _accept_command(context, task_suffix="repair-rollback")
    )
    dependency = context["candidate"].ocr_dependencies[0]
    with sqlite3.connect(context["project"].project_db_path) as connection:
        connection.execute(
            "UPDATE text_blocks SET active_ocr_result_id = NULL WHERE text_block_id = ?",
            (dependency.text_block_id,),
        )
        connection.execute(
            """CREATE TRIGGER fail_grouping_repair BEFORE UPDATE ON page_grouping_state
               BEGIN SELECT RAISE(ABORT, 'injected repair failure'); END"""
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected repair failure"):
        RepairGroupingCurrentApplicationService(
            repositories=context["repositories"]
        ).repair(RepairGroupingCurrentCommand(
            page_id=context["page_id"],
            expected_active_grouping_snapshot_id=accepted.current.snapshot.snapshot_id,
            expected_page_grouping_state_version=1,
            triggering_operation_id="recovery-rollback",
        ))

    assert context["repositories"].grouping_stale.list_for_snapshot(
        context["candidate"].snapshot_id
    ) == ()
    state = context["repositories"].grouping_acceptance.get_page_state(context["page_id"])
    assert state.active_grouping_snapshot_id == context["candidate"].snapshot_id


def test_stale_facts_are_immutable(tmp_path):
    context = _checked_candidate(tmp_path)
    _accept_service(context).accept(_accept_command(context, task_suffix="immutable-stale"))
    _accept_ocr_v2(context["repositories"], context["candidate"])
    with sqlite3.connect(context["project"].project_db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="is immutable"):
            connection.execute(
                "UPDATE grouping_snapshot_stale_facts SET reason_type = reason_type"
            )
        with pytest.raises(sqlite3.IntegrityError, match="is immutable"):
            connection.execute("DELETE FROM grouping_snapshot_stale_facts")
