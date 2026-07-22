from __future__ import annotations

import json
from hashlib import sha256
import sqlite3
import struct
import zlib

import pytest

from manga_read_flow.application.import_page import ImportPageCommand, ImportPageService
from manga_read_flow.application.check_grouping_candidate import (
    GROUPING_CHECK_APPLICATION_COMPLETED,
    GROUPING_CHECK_APPLICATION_REUSED,
    CheckGroupingCandidateApplicationService,
    CheckGroupingCandidateCommand,
    GroupingCheckCommitError,
)
from manga_read_flow.application.materialize_grouping_candidate import (
    GROUPING_APPLICATION_ABSTAINED,
    GROUPING_APPLICATION_FAILED,
    GROUPING_APPLICATION_MATERIALIZED,
    GROUPING_APPLICATION_REUSED,
    GroupingCandidateApplicationService,
    GroupingCandidateCommitError,
    MaterializeGroupingCandidateCommand,
)
from manga_read_flow.application.process_page import ProcessPageCommand, ProcessPageService
from manga_read_flow.artifacts.service import ArtifactService
from manga_read_flow.domain.grouping import (
    GROUPING_DISPOSITION_INCOMPLETE,
    GROUPING_DISPOSITION_PRODUCED,
    GROUPING_OUTCOME_ABSTAINED,
    GROUPING_OUTCOME_FAILED,
    GROUPING_OUTCOME_SUCCEEDED,
    GroupingCandidateDraft,
    GroupingCandidateFragmentDraft,
    GroupingProducerIdentity,
    GroupingProducerResult,
    GroupingTextGroupDraft,
    GroupingUnresolvedRelationDraft,
)
from manga_read_flow.persistence.project_store import AppStore, ProjectOpenStatus
from manga_read_flow.persistence.repository_uow_core import (
    AcceptanceCommand,
    AcceptedResult,
    ActivePointerUpdate,
    AttemptReservation,
    ExpectedState,
    StageStatusUpdate,
    TaskProgressUpdate,
    WorkflowDecisionDraft,
)
from manga_read_flow.providers.fake import FakeProvider
from manga_read_flow.quality.grouping_check import (
    GROUPING_MANIFEST_HASH_MISMATCH,
    GROUPING_MANIFEST_MISSING,
    GROUPING_OCR_DEPENDENCY_MISMATCH,
    GROUPING_UNRESOLVED_RELATION,
)


PRODUCER_HASH = "e" * 64
PROFILE_ID = "profile-snapshot-fakeprovider-default"


class _DeterministicGroupingProducer:
    identity = GroupingProducerIdentity(
        producer_name="deterministic-test-producer",
        producer_version="1",
        implementation_hash=PRODUCER_HASH,
    )

    def __init__(self, mode: str = "produced") -> None:
        self.mode = mode
        self.inputs = []

    def produce(self, input_data):
        self.inputs.append(input_data)
        if self.mode == "abstained":
            return GroupingProducerResult(
                outcome=GROUPING_OUTCOME_ABSTAINED,
                reason_codes=("capability_boundary",),
            )
        if self.mode == "failed":
            return GroupingProducerResult(
                outcome=GROUPING_OUTCOME_FAILED,
                reason_codes=("producer_failed",),
                error_code="TEST_PRODUCER_FAILED",
            )
        if self.mode == "raises":
            raise RuntimeError("test producer error")
        disposition = (
            GROUPING_DISPOSITION_INCOMPLETE
            if self.mode == "incomplete"
            else GROUPING_DISPOSITION_PRODUCED
        )
        fragments = tuple(
            GroupingCandidateFragmentDraft(
                fragment_id=item.fragment_id,
                membership_provenance_json='{"kind":"deterministic_test"}',
            )
            for item in input_data.fragments
        )
        if self.mode == "incomplete":
            first, second = input_data.fragments
            groups = (
                GroupingTextGroupDraft(
                    group_id="group-001",
                    ordered_fragment_ids=(first.fragment_id,),
                    group_order=0,
                    ordering_metadata_json='{"basis":"m1_order"}',
                    membership_provenance_json='{"kind":"deterministic_test"}',
                    unresolved_relation_ids=("relation-001",),
                ),
            )
            relations = (
                GroupingUnresolvedRelationDraft(
                    relation_id="relation-001",
                    affected_fragment_ids=(second.fragment_id,),
                    affected_group_ids=(),
                    reason_code="membership_uncertain",
                    supporting_evidence_json='{"kind":"test_evidence"}',
                ),
            )
        else:
            groups = (
                GroupingTextGroupDraft(
                    group_id="group-001",
                    ordered_fragment_ids=tuple(
                        item.fragment_id
                        for item in sorted(
                            input_data.fragments,
                            key=lambda item: item.reading_order,
                        )
                    ),
                    group_order=0,
                    ordering_metadata_json='{"basis":"m1_order"}',
                    membership_provenance_json='{"kind":"deterministic_test"}',
                    supporting_geometry_references_json=(
                        '{"physical_boundary":"forbidden"}'
                        if self.mode == "invalid_physical"
                        else "{}"
                    ),
                ),
            )
            relations = ()
        return GroupingProducerResult(
            outcome=GROUPING_OUTCOME_SUCCEEDED,
            candidate=GroupingCandidateDraft(
                candidate_disposition=disposition,
                fragments=fragments,
                text_groups=groups,
                unresolved_relations=relations,
            ),
        )


def test_formal_grouping_entry_materializes_and_exact_reads_candidate(tmp_path):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    repositories.content_state.create_text_block(
        text_block_id="auxiliary-page-row",
        page_id=page_id,
        reading_order=99,
        ocr_status="pending",
        translation_status="pending",
    )
    producer = _DeterministicGroupingProducer()

    result = _service(project, repositories, artifacts, producer).materialize(
        _command(page_id, dependency_id, run_id="grouping-run-formal")
    )

    assert result.status == GROUPING_APPLICATION_MATERIALIZED
    assert result.snapshot is not None
    snapshot = repositories.grouping_snapshots.get(result.snapshot.snapshot_id)
    manifest_artifact = repositories.artifact_metadata.get_artifact(
        snapshot.manifest_artifact_id
    )
    manifest = artifacts.read_json_artifact(
        manifest_artifact.artifact_id,
        expected_use="test_grouping_manifest",
    )
    assert tuple(item.text_block_id for item in snapshot.ocr_dependencies) == (
        "tb-page-grouping-001",
        "tb-page-grouping-002",
    )
    assert tuple(item.ocr_result_id for item in snapshot.ocr_dependencies) == tuple(
        fragment["ocr"]["ocr_result_id"] for fragment in manifest["fragments"]
    )
    assert snapshot.detection_dependency_id == dependency_id
    assert snapshot.candidate_disposition == GROUPING_DISPOSITION_PRODUCED
    assert snapshot.dependency_fingerprint == manifest_artifact.dependency_hash
    assert manifest["schema_version"] == "frozen-grouping-evidence-manifest.v1"
    assert manifest["text_groups"][0]["ordered_fragment_ids"] == [
        "tb-page-grouping-001",
        "tb-page-grouping-002",
    ]
    assert len(producer.inputs) == 1
    assert tuple(item.text_block_id for item in producer.inputs[0].fragments) == (
        "tb-page-grouping-001",
        "tb-page-grouping-002",
    )
    with _connection(project.project_db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "grouping_check_results" in tables
    assert repositories.grouping_acceptance.get_page_state(page_id) is None
    assert "grouping_stale_facts" not in tables


def test_incomplete_candidate_persists_unresolved_facts_without_acceptance(tmp_path):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)

    result = _service(
        project,
        repositories,
        artifacts,
        _DeterministicGroupingProducer("incomplete"),
    ).materialize(_command(page_id, dependency_id, run_id="grouping-run-incomplete"))

    assert result.status == GROUPING_APPLICATION_MATERIALIZED
    assert result.snapshot.candidate_disposition == GROUPING_DISPOSITION_INCOMPLETE
    manifest = artifacts.read_json_artifact(
        result.snapshot.manifest_artifact_id,
        expected_use="test_incomplete_grouping_manifest",
    )
    assert manifest["unresolved_relations"][0]["reason_code"] == "membership_uncertain"


@pytest.mark.parametrize(
    "mode,expected_error",
    [
        ("failed", "TEST_PRODUCER_FAILED"),
        ("raises", "GROUPING_PRODUCER_EXCEPTION"),
        ("invalid_physical", "GROUPING_PRODUCER_OUTPUT_INVALID"),
    ],
)
def test_failed_exception_and_invalid_output_create_no_candidate(
    tmp_path, mode, expected_error
):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)

    result = _service(
        project,
        repositories,
        artifacts,
        _DeterministicGroupingProducer(mode),
    ).materialize(_command(page_id, dependency_id, run_id=f"grouping-run-{mode}"))

    assert result.status == GROUPING_APPLICATION_FAILED
    assert result.snapshot is None
    assert result.error_code == expected_error
    with _connection(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM frozen_grouping_evidence_snapshots"
        ).fetchone()[0] == 0
        run = connection.execute(
            "SELECT outcome, materialization_status FROM grouping_generation_runs"
        ).fetchone()
    assert tuple(run) == ("FAILED", "NO_CANDIDATE")


def test_producer_abstention_and_missing_ocr_preserve_run_without_candidate(tmp_path):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    producer_abstained = _service(
        project,
        repositories,
        artifacts,
        _DeterministicGroupingProducer("abstained"),
    ).materialize(_command(page_id, dependency_id, run_id="grouping-run-abstained"))
    with _connection(project.project_db_path) as connection:
        connection.execute(
            """
            UPDATE text_blocks SET active_ocr_result_id = NULL, ocr_status = 'pending'
            WHERE page_id = ? AND reading_order = 1
            """,
            (page_id,),
        )
    missing_ocr = _service(
        project,
        repositories,
        artifacts,
        _DeterministicGroupingProducer(),
    ).materialize(_command(page_id, dependency_id, run_id="grouping-run-missing-ocr"))

    assert producer_abstained.status == GROUPING_APPLICATION_ABSTAINED
    assert producer_abstained.reason_codes == ("capability_boundary",)
    assert missing_ocr.status == GROUPING_APPLICATION_ABSTAINED
    assert missing_ocr.reason_codes == ("exact_ocr_dependencies_not_ready",)
    with _connection(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM frozen_grouping_evidence_snapshots"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM grouping_generation_runs WHERE outcome = 'ABSTAINED'"
        ).fetchone()[0] == 2


def test_replay_reuses_manifest_snapshot_and_adds_generation_run(tmp_path):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    service = _service(
        project, repositories, artifacts, _DeterministicGroupingProducer()
    )

    first = service.materialize(_command(page_id, dependency_id, run_id="grouping-run-1"))
    second = service.materialize(_command(page_id, dependency_id, run_id="grouping-run-2"))

    assert first.status == GROUPING_APPLICATION_MATERIALIZED
    assert second.status == GROUPING_APPLICATION_REUSED
    assert first.snapshot.snapshot_id == second.snapshot.snapshot_id
    with _connection(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM frozen_grouping_evidence_snapshots"
        ).fetchone()[0] == 1
        assert connection.execute(
            """
            SELECT count(*) FROM processing_artifacts
            WHERE artifact_type = 'frozen_grouping_evidence_manifest'
            """
        ).fetchone()[0] == 1
        statuses = {
            row[0]
            for row in connection.execute(
                "SELECT materialization_status FROM grouping_generation_runs"
            ).fetchall()
        }
    assert statuses == {"MATERIALIZED", "REUSED"}


def test_manifest_registration_failure_is_recorded_without_candidate(
    tmp_path, monkeypatch
):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)

    def fail_registration(**_kwargs):
        raise ValueError("injected manifest registration failure")

    monkeypatch.setattr(artifacts, "register_stage_json", fail_registration)

    result = _service(
        project, repositories, artifacts, _DeterministicGroupingProducer()
    ).materialize(_command(page_id, dependency_id, run_id="grouping-run-artifact-fail"))

    assert result.status == GROUPING_APPLICATION_FAILED
    assert result.error_code == "GROUPING_MANIFEST_REGISTRATION_FAILED"
    with _connection(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM frozen_grouping_evidence_snapshots"
        ).fetchone()[0] == 0
        run = connection.execute(
            """
            SELECT outcome, materialization_status FROM grouping_generation_runs
            WHERE generation_run_id = 'grouping-run-artifact-fail'
            """
        ).fetchone()
    assert tuple(run) == ("FAILED", "NO_CANDIDATE")


def test_database_failure_rolls_back_candidate_and_keeps_orphan_manifest(tmp_path):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    with _connection(project.project_db_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_grouping_candidate_insert
            BEFORE INSERT ON frozen_grouping_evidence_snapshots
            BEGIN
                SELECT RAISE(ABORT, 'injected grouping candidate failure');
            END
            """
        )

    with pytest.raises(GroupingCandidateCommitError) as error:
        _service(
            project,
            repositories,
            artifacts,
            _DeterministicGroupingProducer(),
        ).materialize(_command(page_id, dependency_id, run_id="grouping-run-db-fail"))

    assert error.value.manifest_artifact.storage_state == "present"
    with _connection(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM frozen_grouping_evidence_snapshots"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM grouping_snapshot_ocr_dependencies"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM grouping_generation_runs"
        ).fetchone()[0] == 0
        assert connection.execute(
            """
            SELECT count(*) FROM processing_artifacts
            WHERE artifact_type = 'frozen_grouping_evidence_manifest'
            """
        ).fetchone()[0] == 1


def test_historical_read_survives_current_ocr_and_manifest_metadata_drift(tmp_path):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    result = _service(
        project, repositories, artifacts, _DeterministicGroupingProducer()
    ).materialize(_command(page_id, dependency_id, run_id="grouping-run-tamper"))
    snapshot_id = result.snapshot.snapshot_id
    manifest_artifact_id = result.snapshot.manifest_artifact_id

    with _connection(project.project_db_path) as connection:
        connection.execute(
            """
            UPDATE text_blocks SET active_ocr_result_id = NULL
            WHERE page_id = ? AND reading_order = 1
            """,
            (page_id,),
        )
    historical = repositories.grouping_snapshots.get(snapshot_id)
    assert historical.snapshot_id == snapshot_id
    with _connection(project.project_db_path) as connection:
        dependency = connection.execute(
            """
            SELECT text_block_id, ocr_result_id
            FROM grouping_snapshot_ocr_dependencies
            WHERE snapshot_id = ? AND canonical_ordinal = 0
            """,
            (snapshot_id,),
        ).fetchone()
        connection.execute(
            "UPDATE text_blocks SET active_ocr_result_id = ? WHERE text_block_id = ?",
            (dependency["ocr_result_id"], dependency["text_block_id"]),
        )
        connection.execute(
            "UPDATE processing_artifacts SET file_hash = ? WHERE artifact_id = ?",
            ("f" * 64, manifest_artifact_id),
        )
    historical = repositories.grouping_snapshots.get(snapshot_id)
    assert historical.manifest_artifact_id == manifest_artifact_id


def test_snapshot_is_immutable_and_exact_read_is_project_isolated(tmp_path):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    result = _service(
        project, repositories, artifacts, _DeterministicGroupingProducer()
    ).materialize(_command(page_id, dependency_id, run_id="grouping-run-isolation"))

    with _connection(project.project_db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """
                UPDATE frozen_grouping_evidence_snapshots
                SET candidate_disposition = 'INCOMPLETE'
                WHERE snapshot_id = ?
                """,
                (result.snapshot.snapshot_id,),
            )

    other_store = AppStore.initialize(tmp_path / "other-workspace")
    other_project = other_store.create_project(
        name="Other project",
        source_language="ja",
        target_language="zh-Hans",
    )
    other_repository = other_store.open_project(
        other_project.project_id
    ).repositories().grouping_snapshots
    with pytest.raises(LookupError, match="not found"):
        other_repository.get(result.snapshot.snapshot_id)


def test_exact_read_rejects_member_count_and_detection_binding_tampering(tmp_path):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    result = _service(
        project, repositories, artifacts, _DeterministicGroupingProducer()
    ).materialize(_command(page_id, dependency_id, run_id="grouping-run-bindings"))
    snapshot_id = result.snapshot.snapshot_id
    with _connection(project.project_db_path) as connection:
        connection.execute(
            "DROP TRIGGER trg_frozen_grouping_evidence_snapshots_immutable_update"
        )
        connection.execute(
            """
            UPDATE frozen_grouping_evidence_snapshots
            SET ocr_dependency_count = ocr_dependency_count + 1
            WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        )
    with pytest.raises(ValueError, match="membership is inconsistent"):
        repositories.grouping_snapshots.get(snapshot_id)
    with _connection(project.project_db_path) as connection:
        connection.execute(
            """
            UPDATE frozen_grouping_evidence_snapshots
            SET ocr_dependency_count = ocr_dependency_count - 1,
                detection_dependency_hash = ?
            WHERE snapshot_id = ?
            """,
            ("f" * 64, snapshot_id),
        )
    historical = repositories.grouping_snapshots.get(snapshot_id)
    assert historical.detection_dependency_hash == "f" * 64


def test_formal_grouping_check_entry_persists_immutable_result_without_acceptance(
    tmp_path,
):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    producer = _DeterministicGroupingProducer()
    candidate = _service(project, repositories, artifacts, producer).materialize(
        _command(page_id, dependency_id, run_id="grouping-run-check-valid")
    ).snapshot
    with _connection(project.project_db_path) as connection:
        candidate_before = tuple(
            connection.execute(
                "SELECT * FROM frozen_grouping_evidence_snapshots WHERE snapshot_id = ?",
                (candidate.snapshot_id,),
            ).fetchone()
        )

    checked = _check_service(project, repositories, artifacts).check(
        _check_command(
            candidate,
            dependency_id,
            execution_id="grouping-check-execution-valid",
        )
    )

    assert checked.status == GROUPING_CHECK_APPLICATION_COMPLETED
    assert checked.quality_issues == ()
    assert checked.check_result.metrics.fragment_count == 2
    assert checked.check_result.metrics.group_count == 1
    assert checked.check_result.evidence_artifact_id
    assert checked.check_result.evidence_artifact_sha256
    assert checked.execution.outcome == "MATERIALIZED"
    assert len(producer.inputs) == 1
    evidence = artifacts.read_json_artifact(
        checked.check_result.evidence_artifact_id,
        expected_use="test_grouping_check_evidence",
    )
    assert evidence["schema_version"] == "grouping-check-evidence.v1"
    assert evidence["check_result_id"] == checked.check_result.check_result_id
    with _connection(project.project_db_path) as connection:
        candidate_after = tuple(
            connection.execute(
                "SELECT * FROM frozen_grouping_evidence_snapshots WHERE snapshot_id = ?",
                (candidate.snapshot_id,),
            ).fetchone()
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert connection.execute(
            "SELECT count(*) FROM grouping_check_results"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM grouping_check_executions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM workflow_decisions WHERE stage = 'grouping'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM grouping_snapshot_acceptances"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM page_grouping_state"
        ).fetchone()[0] == 0
    assert candidate_after == candidate_before
    assert "grouping_stale_facts" not in tables


def test_incomplete_grouping_check_persists_formal_review_issue_and_replays_idempotently(
    tmp_path,
):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    candidate = _service(
        project,
        repositories,
        artifacts,
        _DeterministicGroupingProducer("incomplete"),
    ).materialize(
        _command(page_id, dependency_id, run_id="grouping-run-check-incomplete")
    ).snapshot
    service = _check_service(project, repositories, artifacts)

    first = service.check(
        _check_command(
            candidate,
            dependency_id,
            execution_id="grouping-check-execution-incomplete-1",
        )
    )
    second = service.check(
        _check_command(
            candidate,
            dependency_id,
            execution_id="grouping-check-execution-incomplete-2",
        )
    )
    same_execution_replay = service.check(
        _check_command(
            candidate,
            dependency_id,
            execution_id="grouping-check-execution-incomplete-1",
        )
    )

    assert first.status == GROUPING_CHECK_APPLICATION_COMPLETED
    assert second.status == GROUPING_CHECK_APPLICATION_REUSED
    assert same_execution_replay.status == GROUPING_CHECK_APPLICATION_REUSED
    assert same_execution_replay.execution.execution_id == (
        "grouping-check-execution-incomplete-1"
    )
    assert first.check_result.check_result_id == second.check_result.check_result_id
    assert first.check_result.evidence_artifact_id == second.check_result.evidence_artifact_id
    assert len(first.quality_issues) == 1
    issue = first.quality_issues[0]
    assert issue.issue_type == GROUPING_UNRESOLVED_RELATION
    assert issue.severity == "warning"
    assert issue.is_blocking is True
    assert issue.root_stage == "grouping"
    assert issue.target_type == "grouping_unresolved_relation"
    assert issue.message_params == {"relation_id": "relation-001"}
    assert issue.suggested_action_key == "action.review_grouping_relation"
    assert second.quality_issues[0].issue_id == issue.issue_id
    with _connection(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM grouping_check_results"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM quality_issues WHERE root_stage = 'grouping'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM grouping_check_result_issues"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM grouping_check_executions"
        ).fetchone()[0] == 2
        assert connection.execute(
            """
            SELECT count(*) FROM processing_artifacts
            WHERE artifact_type = 'grouping_check_evidence'
            """
        ).fetchone()[0] == 1


def test_ocr_v2_drift_keeps_historical_candidate_readable_and_persists_blocker(
    tmp_path,
):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    candidate = _service(
        project, repositories, artifacts, _DeterministicGroupingProducer()
    ).materialize(
        _command(page_id, dependency_id, run_id="grouping-run-check-ocr-v1")
    ).snapshot
    before = repositories.grouping_snapshots.get(candidate.snapshot_id)

    _accept_ocr_v2(repositories, candidate)

    historical = repositories.grouping_snapshots.get(candidate.snapshot_id)
    checked = _check_service(project, repositories, artifacts).check(
        _check_command(
            candidate,
            dependency_id,
            execution_id="grouping-check-execution-ocr-v2",
        )
    )

    assert historical == before
    issues = {item.issue_type: item for item in checked.quality_issues}
    assert GROUPING_OCR_DEPENDENCY_MISMATCH in issues
    assert issues[GROUPING_OCR_DEPENDENCY_MISMATCH].is_blocking is True
    with _connection(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM frozen_grouping_evidence_snapshots"
        ).fetchone()[0] == 1
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert repositories.grouping_acceptance.get_page_state(page_id) is None
    assert "grouping_stale_facts" not in tables


def test_manifest_hash_tamper_becomes_formal_quality_issue(tmp_path):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    candidate = _service(
        project, repositories, artifacts, _DeterministicGroupingProducer()
    ).materialize(
        _command(page_id, dependency_id, run_id="grouping-run-check-tamper")
    ).snapshot
    artifact = repositories.artifact_metadata.get_artifact(candidate.manifest_artifact_id)
    manifest_path = project.workspace_path / artifact.relative_path
    manifest_path.write_bytes(b'{"tampered":true}')

    checked = _check_service(project, repositories, artifacts).check(
        _check_command(
            candidate,
            dependency_id,
            execution_id="grouping-check-execution-tamper",
        )
    )

    issues = {item.issue_type for item in checked.quality_issues}
    assert GROUPING_MANIFEST_HASH_MISMATCH in issues
    assert repositories.grouping_snapshots.get(candidate.snapshot_id).snapshot_id == (
        candidate.snapshot_id
    )


def test_missing_manifest_remains_historically_auditable_and_becomes_formal_issue(
    tmp_path,
):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    candidate = _service(
        project, repositories, artifacts, _DeterministicGroupingProducer()
    ).materialize(
        _command(page_id, dependency_id, run_id="grouping-run-check-missing-manifest")
    ).snapshot
    artifact = repositories.artifact_metadata.get_artifact(candidate.manifest_artifact_id)
    (project.workspace_path / artifact.relative_path).unlink()

    historical = repositories.grouping_snapshots.get(candidate.snapshot_id)
    checked = _check_service(project, repositories, artifacts).check(
        _check_command(
            candidate,
            dependency_id,
            execution_id="grouping-check-execution-missing-manifest",
        )
    )

    assert historical.snapshot_id == candidate.snapshot_id
    assert GROUPING_MANIFEST_MISSING in {
        item.issue_type for item in checked.quality_issues
    }


def test_grouping_check_database_failure_rolls_back_result_and_issues_but_keeps_orphan_evidence(
    tmp_path,
):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    candidate = _service(
        project,
        repositories,
        artifacts,
        _DeterministicGroupingProducer("incomplete"),
    ).materialize(
        _command(page_id, dependency_id, run_id="grouping-run-check-db-fail")
    ).snapshot
    with _connection(project.project_db_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_grouping_quality_issue_insert
            BEFORE INSERT ON quality_issues
            BEGIN
                SELECT RAISE(ABORT, 'injected grouping QualityIssue failure');
            END
            """
        )

    with pytest.raises(GroupingCheckCommitError) as error:
        _check_service(project, repositories, artifacts).check(
            _check_command(
                candidate,
                dependency_id,
                execution_id="grouping-check-execution-db-fail",
            )
        )

    assert error.value.evidence_artifact is not None
    assert error.value.evidence_artifact.storage_state == "present"
    with _connection(project.project_db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM grouping_check_results"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM grouping_check_result_issues"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM grouping_check_executions"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM quality_issues WHERE root_stage = 'grouping'"
        ).fetchone()[0] == 0
        assert connection.execute(
            """
            SELECT count(*) FROM processing_artifacts
            WHERE artifact_type = 'grouping_check_evidence'
            """
        ).fetchone()[0] == 1


def test_grouping_check_result_is_immutable_and_project_isolated(tmp_path):
    project, repositories, artifacts, page_id, dependency_id = _processed_page(tmp_path)
    candidate = _service(
        project, repositories, artifacts, _DeterministicGroupingProducer()
    ).materialize(
        _command(page_id, dependency_id, run_id="grouping-run-check-immutable")
    ).snapshot
    checked = _check_service(project, repositories, artifacts).check(
        _check_command(
            candidate,
            dependency_id,
            execution_id="grouping-check-execution-immutable",
        )
    )
    with _connection(project.project_db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """
                UPDATE grouping_check_results SET check_version = 'tampered'
                WHERE check_result_id = ?
                """,
                (checked.check_result.check_result_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM grouping_check_results WHERE check_result_id = ?",
                (checked.check_result.check_result_id,),
            )

    other_store = AppStore.initialize(tmp_path / "other-check-workspace")
    other_project = other_store.create_project(
        name="Other check project",
        source_language="ja",
        target_language="zh-Hans",
    )
    other_checks = other_store.open_project(
        other_project.project_id
    ).repositories().grouping_checks
    with pytest.raises(LookupError, match="not found"):
        other_checks.get(checked.check_result.check_result_id)


def _processed_page(tmp_path):
    store = AppStore.initialize(tmp_path / "workspace")
    project = store.create_project(
        name="Grouping candidate",
        source_language="ja",
        target_language="zh-Hans",
    )
    opened = store.open_project(project.project_id)
    assert opened.status is ProjectOpenStatus.READY
    repositories = opened.repositories()
    artifacts = ArtifactService(
        project_id=project.project_id,
        project_workspace_path=project.workspace_path,
        artifact_repository=repositories.artifact_metadata,
    )
    source = tmp_path / "incoming" / "page.png"
    source.parent.mkdir()
    source.write_bytes(_tiny_png(width=32, height=24))
    imported = ImportPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifacts,
    ).import_page(
        ImportPageCommand(
            source_path=source,
            batch_id="batch-grouping",
            batch_name="Grouping",
            page_id="page-grouping",
            page_index=1,
        )
    )
    result = ProcessPageService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifacts,
        provider=FakeProvider.happy_path(),
    ).process_page(ProcessPageCommand(page_id=imported.page.page_id))
    assert result.task_status == "succeeded"
    with _connection(project.project_db_path) as connection:
        dependency_id = connection.execute(
            "SELECT detection_dependency_id FROM accepted_detection_evidence_sets"
        ).fetchone()[0]
    return project, repositories, artifacts, imported.page.page_id, dependency_id


def _service(project, repositories, artifacts, producer):
    return GroupingCandidateApplicationService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifacts,
        producer=producer,
    )


def _command(page_id, dependency_id, *, run_id):
    return MaterializeGroupingCandidateCommand(
        page_id=page_id,
        detection_dependency_id=dependency_id,
        profile_snapshot_id=PROFILE_ID,
        operation_semantics_version="grouping-op.v1",
        generation_run_id=run_id,
    )


def _check_service(project, repositories, artifacts):
    return CheckGroupingCandidateApplicationService(
        project_id=project.project_id,
        repositories=repositories,
        artifact_service=artifacts,
    )


def _check_command(candidate, dependency_id, *, execution_id):
    return CheckGroupingCandidateCommand(
        page_id=candidate.page_id,
        snapshot_id=candidate.snapshot_id,
        current_detection_dependency_id=dependency_id,
        current_profile_snapshot_id=PROFILE_ID,
        expected_producer_name="deterministic-test-producer",
        expected_producer_version="1",
        expected_producer_implementation_hash=PRODUCER_HASH,
        expected_operation_semantics_version="grouping-op.v1",
        execution_id=execution_id,
    )


def _accept_ocr_v2(repositories, candidate):
    task_id = "task-ocr-v2"
    attempt_id = "attempt-ocr-v2"
    repositories.workflow_execution.create_task(
        task_id=task_id,
        target_type="page",
        target_id=candidate.page_id,
        task_type="manual_ocr_revision",
        status="queued",
        current_stage="ocr",
        profile_snapshot_id=PROFILE_ID,
    )
    reserved = repositories.uow.reserve_attempt(
        AttemptReservation(
            task_id=task_id,
            attempt_id=attempt_id,
            stage="ocr",
            target_type="page",
            target_id=candidate.page_id,
            expected_task_status="queued",
            expected_current_stage="ocr",
            runner_id="test-runner",
        )
    )
    assert reserved.committed
    accepted_results = []
    pointers = []
    stages = []
    expected_active = {}
    for index, dependency in enumerate(candidate.ocr_dependencies, start=1):
        text = f"formal_ocr_v2_{index}"
        result_id = f"ocr-v2-{dependency.text_block_id}"
        accepted_results.append(
            AcceptedResult(
                result_type="ocr",
                result_id=result_id,
                target_type="text_block",
                target_id=dependency.text_block_id,
                source_text=text,
                source_text_hash=sha256(text.encode("utf-8")).hexdigest(),
                provider_name="manual-test-provider",
                model_id="manual-v2",
                workflow_attempt_id=attempt_id,
                geometry_hash=dependency.ocr_geometry_hash,
                input_hash=sha256(f"input-v2-{index}".encode("utf-8")).hexdigest(),
                config_hash="b" * 64,
            )
        )
        pointers.append(
            ActivePointerUpdate(
                owner_type="text_block",
                owner_id=dependency.text_block_id,
                pointer_name="active_ocr_result_id",
                value_id=result_id,
            )
        )
        stages.append(
            StageStatusUpdate(
                target_type="text_block",
                target_id=dependency.text_block_id,
                stage="ocr",
                status="done",
            )
        )
        expected_active[dependency.text_block_id] = dependency.ocr_result_id
    outcome = repositories.uow.accept_stage(
        AcceptanceCommand(
            task_id=task_id,
            expected=ExpectedState(
                task_status="running",
                current_stage="ocr",
                active_ocr_result_ids=expected_active,
                attempt_id=attempt_id,
                attempt_status="running",
            ),
            accepted_results=tuple(accepted_results),
            active_pointers=tuple(pointers),
            issue_lifecycle=(),
            workflow_decision=WorkflowDecisionDraft(
                decision_id="decision-ocr-v2",
                attempt_id=attempt_id,
                stage="ocr",
                decision_type="accept",
                reason_code="manual_revision_accepted",
            ),
            retry_budget_after={"ocr": 0},
            task_progress=TaskProgressUpdate(
                status="succeeded",
                current_stage="ocr",
                progress_state="complete",
            ),
            stage_statuses=tuple(stages),
            attempt_terminal_status="succeeded",
        )
    )
    assert outcome.committed


def _connection(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _tiny_png(*, width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = b"".join(b"\x00" + (b"\xff\x00\x00" * width) for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
