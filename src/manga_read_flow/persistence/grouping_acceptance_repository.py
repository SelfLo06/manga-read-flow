from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from manga_read_flow.persistence.detection_evidence_repository import (
    _load_and_validate_evidence_set,
)
from manga_read_flow.persistence.grouping_snapshot_repository import (
    FrozenGroupingEvidenceSnapshot,
    _load_and_validate_snapshot,
)
from manga_read_flow.persistence.sqlite_repository_helpers import (
    connect_existing,
    utc_now,
)
from manga_read_flow.persistence.grouping_stale_repository import (
    GroupingSnapshotStaleFactDraft,
    persist_grouping_stale_fact,
    snapshot_has_stale_fact,
)


GROUPING_ACCEPTANCE_ID_PREFIX = "grouping-acceptance-v1:"


@dataclass(frozen=True)
class ExpectedGroupingIssue:
    issue_id: str
    status: str
    is_blocking: bool
    updated_at: str


@dataclass(frozen=True)
class ExpectedGroupingOcrDependency:
    text_block_id: str
    ocr_result_id: str
    version_number: int
    text_hash: str
    geometry_hash: str
    input_hash: str


@dataclass(frozen=True)
class _GroupingCheckBinding:
    check_result_id: str
    page_id: str
    snapshot_id: str
    input_fingerprint: str
    candidate_manifest_sha256: str
    candidate_dependency_fingerprint: str


@dataclass(frozen=True)
class GroupingDecisionContextDraft:
    page_id: str
    snapshot_id: str
    check_result_id: str
    check_execution_id: str
    decision_execution_id: str
    current_detection_dependency_id: str
    current_detection_dependency_hash: str
    current_profile_snapshot_id: str
    current_profile_settings_hash: str
    current_source_artifact_id: str
    current_source_sha256: str
    current_ocr_dependencies: tuple[ExpectedGroupingOcrDependency, ...]
    current_check_input_fingerprint: str
    expected_producer_name: str
    expected_producer_version: str
    expected_producer_implementation_hash: str
    expected_operation_semantics_version: str
    expected_active_grouping_snapshot_id: str | None
    expected_page_grouping_state_version: int | None
    expected_issues: tuple[ExpectedGroupingIssue, ...]
    acceptance_id: str | None = None


@dataclass(frozen=True)
class GroupingAcceptanceSnapshot:
    acceptance_id: str
    project_id: str
    page_id: str
    snapshot_id: str
    check_result_id: str
    workflow_decision_id: str
    workflow_attempt_id: str | None
    acceptance_execution_id: str
    accepted_manifest_sha256: str
    accepted_dependency_fingerprint: str
    accepted_at: str


@dataclass(frozen=True)
class PageGroupingStateSnapshot:
    project_id: str
    page_id: str
    active_grouping_snapshot_id: str | None
    version: int
    updated_at: str


@dataclass(frozen=True)
class CurrentGroupingSnapshot:
    page_state: PageGroupingStateSnapshot
    acceptance: GroupingAcceptanceSnapshot
    snapshot: FrozenGroupingEvidenceSnapshot


@dataclass(frozen=True)
class GroupingCommitPlan:
    context: GroupingDecisionContextDraft
    snapshot: FrozenGroupingEvidenceSnapshot
    existing_acceptance: GroupingAcceptanceSnapshot | None
    replaced_acceptance: GroupingAcceptanceSnapshot | None
    replay: bool


@dataclass(frozen=True)
class GroupingCommitResult:
    acceptance_id: str | None
    active_grouping_snapshot_id: str | None
    page_grouping_state_version: int | None
    replayed: bool
    stale_fact_ids: tuple[str, ...] = ()


class NoCurrentGroupingError(LookupError):
    pass


class GroupingStaleError(ValueError):
    pass


class GroupingDependencyMismatchError(ValueError):
    pass


class GroupingBlockedError(ValueError):
    pass


@dataclass(frozen=True)
class GroupingRepairOutcome:
    status: str
    stale_fact_id: str | None
    page_grouping_state_version: int | None


class GroupingAcceptanceRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def get_acceptance(self, acceptance_id: str) -> GroupingAcceptanceSnapshot:
        with connect_existing(self._project_db_path) as connection:
            return _load_acceptance(connection, self._project_id, acceptance_id)

    def get_page_state(self, page_id: str) -> PageGroupingStateSnapshot | None:
        with connect_existing(self._project_db_path) as connection:
            return _load_page_state(connection, self._project_id, page_id)

    def get_current(self, page_id: str) -> CurrentGroupingSnapshot:
        with connect_existing(self._project_db_path) as connection:
            state = _load_page_state(connection, self._project_id, page_id)
            if state is None or state.active_grouping_snapshot_id is None:
                raise NoCurrentGroupingError(f"Current Grouping snapshot not found: {page_id}")
            rows = connection.execute(
                """
                SELECT acceptance_id
                FROM grouping_snapshot_acceptances
                WHERE project_id = ? AND page_id = ? AND snapshot_id = ?
                ORDER BY accepted_at, acceptance_id
                """,
                (self._project_id, page_id, state.active_grouping_snapshot_id),
            ).fetchall()
            if len(rows) != 1:
                raise ValueError("Current Grouping pointer does not select one acceptance.")
            acceptance = _load_acceptance(
                connection, self._project_id, rows[0]["acceptance_id"]
            )
            snapshot = _load_and_validate_snapshot(
                connection, self._project_id, state.active_grouping_snapshot_id
            )
            if snapshot_has_stale_fact(connection, self._project_id, snapshot.snapshot_id):
                raise GroupingStaleError("Current Grouping snapshot has a stale fact.")
            if (
                acceptance.page_id != snapshot.page_id
                or acceptance.accepted_manifest_sha256
                != snapshot.manifest_artifact_sha256
                or acceptance.accepted_dependency_fingerprint
                != snapshot.dependency_fingerprint
            ):
                raise ValueError("Current Grouping acceptance binding is inconsistent.")
            if not _snapshot_dependencies_current(
                connection, self._project_id, snapshot
            ):
                raise GroupingDependencyMismatchError(
                    "Current Grouping snapshot dependencies are stale."
                )
            blocker = connection.execute(
                """
                SELECT 1
                FROM grouping_check_result_issues relation
                JOIN quality_issues issue
                  ON issue.project_id = relation.project_id
                 AND issue.issue_id = relation.issue_id
                WHERE relation.project_id = ?
                  AND relation.check_result_id = ?
                  AND issue.is_blocking = 1
                  AND issue.status = 'open'
                LIMIT 1
                """,
                (self._project_id, acceptance.check_result_id),
            ).fetchone()
            if blocker is not None:
                raise GroupingBlockedError(
                    "Current Grouping acceptance has an unresolved blocker."
                )
            return CurrentGroupingSnapshot(
                page_state=state,
                acceptance=acceptance,
                snapshot=snapshot,
            )

    def repair_dependency_mismatch(
        self,
        *,
        page_id: str,
        expected_active_grouping_snapshot_id: str,
        expected_page_grouping_state_version: int,
        triggering_operation_id: str,
    ) -> GroupingRepairOutcome:
        with connect_existing(self._project_db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            state = _load_page_state(connection, self._project_id, page_id)
            if state is None or state.active_grouping_snapshot_id is None:
                return GroupingRepairOutcome("ALREADY_CLEAR", None, state.version if state else None)
            if (
                state.active_grouping_snapshot_id != expected_active_grouping_snapshot_id
                or state.version != expected_page_grouping_state_version
            ):
                return GroupingRepairOutcome("CONFLICT_RELOAD", None, state.version)
            acceptance = _load_acceptance_for_snapshot(
                connection, self._project_id, page_id, state.active_grouping_snapshot_id
            )
            if acceptance is None:
                raise ValueError("Active Grouping pointer has no acceptance.")
            snapshot = _load_and_validate_snapshot(
                connection, self._project_id, state.active_grouping_snapshot_id
            )
            if (
                not snapshot_has_stale_fact(connection, self._project_id, snapshot.snapshot_id)
                and _snapshot_dependencies_current(connection, self._project_id, snapshot)
            ):
                return GroupingRepairOutcome("NOT_REQUIRED", None, state.version)
            draft = GroupingSnapshotStaleFactDraft(
                project_id=self._project_id, page_id=page_id,
                snapshot_id=snapshot.snapshot_id, acceptance_id=acceptance.acceptance_id,
                reason_type="DEPENDENCY_MISMATCH_REPAIR",
                previous_dependency_type="GROUPING_DEPENDENCY_FINGERPRINT",
                previous_dependency_id=snapshot.snapshot_id,
                previous_dependency_hash=snapshot.dependency_fingerprint,
                replacement_dependency_id=None, replacement_dependency_hash=None,
                triggering_operation_type="RECOVERY_REPAIR",
                triggering_operation_id=triggering_operation_id,
            )
            stale_id = persist_grouping_stale_fact(connection, draft)
            version = state.version + 1
            updated = connection.execute(
                """UPDATE page_grouping_state
                   SET active_grouping_snapshot_id = NULL, version = ?, updated_at = ?
                   WHERE project_id = ? AND page_id = ?
                     AND active_grouping_snapshot_id = ? AND version = ?""",
                (version, utc_now(), self._project_id, page_id,
                 state.active_grouping_snapshot_id, state.version),
            )
            if updated.rowcount != 1:
                raise sqlite3.IntegrityError("Grouping repair pointer CAS failed.")
        return GroupingRepairOutcome("REPAIRED", stale_id, version)


def grouping_acceptance_id(*, snapshot_id: str, check_result_id: str) -> str:
    payload = json.dumps(
        {"check_result_id": check_result_id, "snapshot_id": snapshot_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{GROUPING_ACCEPTANCE_ID_PREFIX}{sha256(payload).hexdigest()}"


def initialize_grouping_acceptance_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS grouping_snapshot_acceptances (
            acceptance_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            check_result_id TEXT NOT NULL,
            workflow_decision_id TEXT NOT NULL,
            workflow_attempt_id TEXT,
            acceptance_execution_id TEXT NOT NULL,
            accepted_manifest_sha256 TEXT NOT NULL,
            accepted_dependency_fingerprint TEXT NOT NULL,
            accepted_at TEXT NOT NULL,
            CHECK(acceptance_id LIKE 'grouping-acceptance-v1:%'),
            UNIQUE(project_id, page_id, snapshot_id),
            FOREIGN KEY(page_id) REFERENCES pages(page_id),
            FOREIGN KEY(snapshot_id)
                REFERENCES frozen_grouping_evidence_snapshots(snapshot_id),
            FOREIGN KEY(check_result_id) REFERENCES grouping_check_results(check_result_id),
            FOREIGN KEY(workflow_decision_id) REFERENCES workflow_decisions(decision_id),
            FOREIGN KEY(workflow_attempt_id) REFERENCES workflow_attempts(attempt_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS grouping_acceptance_executions (
            execution_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            check_result_id TEXT NOT NULL,
            acceptance_id TEXT NOT NULL,
            workflow_decision_id TEXT NOT NULL,
            workflow_attempt_id TEXT,
            outcome TEXT NOT NULL CHECK(outcome IN ('ACCEPTED', 'REPLAYED')),
            completed_at TEXT NOT NULL,
            FOREIGN KEY(page_id) REFERENCES pages(page_id),
            FOREIGN KEY(snapshot_id)
                REFERENCES frozen_grouping_evidence_snapshots(snapshot_id),
            FOREIGN KEY(check_result_id) REFERENCES grouping_check_results(check_result_id),
            FOREIGN KEY(acceptance_id)
                REFERENCES grouping_snapshot_acceptances(acceptance_id),
            FOREIGN KEY(workflow_decision_id) REFERENCES workflow_decisions(decision_id),
            FOREIGN KEY(workflow_attempt_id) REFERENCES workflow_attempts(attempt_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS page_grouping_state (
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            active_grouping_snapshot_id TEXT,
            version INTEGER NOT NULL CHECK(version >= 1),
            updated_at TEXT NOT NULL,
            PRIMARY KEY(project_id, page_id),
            UNIQUE(page_id),
            FOREIGN KEY(page_id) REFERENCES pages(page_id),
            FOREIGN KEY(active_grouping_snapshot_id)
                REFERENCES frozen_grouping_evidence_snapshots(snapshot_id)
        )
        """
    )
    for table in ("grouping_snapshot_acceptances", "grouping_acceptance_executions"):
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_immutable_update
            BEFORE UPDATE ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{table} is immutable');
            END
            """
        )
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_immutable_delete
            BEFORE DELETE ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{table} is immutable');
            END
            """
        )
    for action in ("INSERT", "UPDATE OF active_grouping_snapshot_id"):
        suffix = "insert" if action == "INSERT" else "update"
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_page_grouping_state_acceptance_{suffix}
            BEFORE {action} ON page_grouping_state
            WHEN NEW.active_grouping_snapshot_id IS NOT NULL
            BEGIN
                SELECT CASE WHEN NOT EXISTS (
                    SELECT 1 FROM grouping_snapshot_acceptances acceptance
                    WHERE acceptance.project_id = NEW.project_id
                      AND acceptance.page_id = NEW.page_id
                      AND acceptance.snapshot_id = NEW.active_grouping_snapshot_id
                ) THEN RAISE(ABORT, 'Grouping pointer requires an acceptance') END;
            END
            """
        )


def validate_grouping_commit(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    task_id: str,
    decision,
    context: GroupingDecisionContextDraft,
) -> tuple[GroupingCommitPlan | None, tuple[str, ...]]:
    conflicts: list[str] = []
    if decision.stage != "grouping":
        raise ValueError("Grouping decision must use the grouping stage.")
    if decision.decision_type not in {"accept", "retry", "fallback", "skip", "block"}:
        raise ValueError("Unsupported Grouping Workflow decision.")

    snapshot = _load_and_validate_snapshot(connection, project_id, context.snapshot_id)
    check_result = _load_check_binding(connection, project_id, context.check_result_id)
    if snapshot.page_id != context.page_id:
        conflicts.append("grouping_page_id")
    if (
        check_result.snapshot_id != snapshot.snapshot_id
        or check_result.page_id != context.page_id
        or check_result.candidate_manifest_sha256
        != snapshot.manifest_artifact_sha256
        or check_result.candidate_dependency_fingerprint
        != snapshot.dependency_fingerprint
    ):
        conflicts.append("grouping_check_result_binding")

    execution = connection.execute(
        """
        SELECT snapshot_id, check_result_id, input_fingerprint
        FROM grouping_check_executions
        WHERE project_id = ? AND execution_id = ?
        """,
        (project_id, context.check_execution_id),
    ).fetchone()
    if (
        execution is None
        or execution["snapshot_id"] != snapshot.snapshot_id
        or execution["check_result_id"] != check_result.check_result_id
        or execution["input_fingerprint"] != check_result.input_fingerprint
    ):
        conflicts.append("grouping_check_execution_binding")

    issue_rows = connection.execute(
        """
        SELECT issue.issue_id, issue.status, issue.is_blocking, issue.updated_at,
               issue.applies_to_result_id, issue.root_stage, relation.snapshot_id
        FROM grouping_check_result_issues relation
        JOIN quality_issues issue
          ON issue.project_id = relation.project_id
         AND issue.issue_id = relation.issue_id
        WHERE relation.project_id = ? AND relation.check_result_id = ?
        ORDER BY issue.issue_id
        """,
        (project_id, check_result.check_result_id),
    ).fetchall()
    actual_issues = tuple(
        ExpectedGroupingIssue(
            issue_id=row["issue_id"],
            status=row["status"],
            is_blocking=bool(row["is_blocking"]),
            updated_at=row["updated_at"],
        )
        for row in issue_rows
    )
    expected_issues = tuple(
        sorted(context.expected_issues, key=lambda item: item.issue_id.encode("utf-8"))
    )
    if actual_issues != expected_issues:
        conflicts.append("grouping_quality_issue_lifecycle")
    if any(
        row["applies_to_result_id"] != check_result.check_result_id
        or row["root_stage"] != "grouping"
        or row["snapshot_id"] != snapshot.snapshot_id
        for row in issue_rows
    ):
        conflicts.append("grouping_quality_issue_binding")
    actual_issue_ids = tuple(issue.issue_id for issue in actual_issues)
    if tuple(sorted(decision.linked_issue_ids)) != actual_issue_ids:
        conflicts.append("grouping_workflow_issue_binding")

    task = connection.execute(
        """
        SELECT target_type, target_id, profile_snapshot_id
        FROM processing_tasks WHERE project_id = ? AND task_id = ?
        """,
        (project_id, task_id),
    ).fetchone()
    if (
        task is None
        or task["target_type"] != "page"
        or task["target_id"] != context.page_id
        or task["profile_snapshot_id"] != context.current_profile_snapshot_id
    ):
        conflicts.append("grouping_task_binding")

    page = connection.execute(
        """
        SELECT original_artifact_id FROM pages
        WHERE project_id = ? AND page_id = ?
        """,
        (project_id, context.page_id),
    ).fetchone()
    source = connection.execute(
        """
        SELECT file_hash, storage_state FROM processing_artifacts
        WHERE project_id = ? AND artifact_id = ?
        """,
        (project_id, context.current_source_artifact_id),
    ).fetchone()
    source_context_conflict = (
        page is None
        or page["original_artifact_id"] != context.current_source_artifact_id
        or source is None
        or source["storage_state"] != "present"
        or source["file_hash"] != context.current_source_sha256
    )
    if source_context_conflict:
        conflicts.append("grouping_source_dependency")

    try:
        detection = _load_and_validate_evidence_set(
            connection, project_id, context.current_detection_dependency_id
        )
    except (LookupError, ValueError):
        detection = None
    detection_matches_context = not (
        detection is None
        or detection.page_id != context.page_id
        or detection.canonical_manifest_sha256
        != context.current_detection_dependency_hash
    )
    if not detection_matches_context:
        conflicts.append("grouping_detection_dependency")

    profile = connection.execute(
        """
        SELECT settings_json, settings_hash FROM processing_profile_snapshots
        WHERE project_id = ? AND profile_snapshot_id = ?
        """,
        (project_id, context.current_profile_snapshot_id),
    ).fetchone()
    profile_matches_context = not (
        profile is None
        or sha256(profile["settings_json"].encode("utf-8")).hexdigest()
        != profile["settings_hash"]
        or profile["settings_hash"] != context.current_profile_settings_hash
    )
    if not profile_matches_context:
        conflicts.append("grouping_profile_dependency")

    producer_matches_candidate = not (
        snapshot.producer_name != context.expected_producer_name
        or snapshot.producer_version != context.expected_producer_version
        or snapshot.producer_implementation_hash
        != context.expected_producer_implementation_hash
        or snapshot.operation_semantics_version
        != context.expected_operation_semantics_version
    )
    actual_ocr = _load_current_ocr(connection, project_id, snapshot)
    expected_ocr = tuple(
        sorted(
            context.current_ocr_dependencies,
            key=lambda item: item.text_block_id.encode("utf-8"),
        )
    )
    if actual_ocr != expected_ocr:
        conflicts.append("grouping_ocr_dependency_state")

    state = _load_page_state(connection, project_id, context.page_id)
    actual_active = state.active_grouping_snapshot_id if state is not None else None
    actual_version = state.version if state is not None else None
    if actual_active != context.expected_active_grouping_snapshot_id:
        conflicts.append("active_grouping_snapshot_id")
    if actual_version != context.expected_page_grouping_state_version:
        conflicts.append("page_grouping_state_version")

    existing = _load_acceptance_for_snapshot(
        connection, project_id, context.page_id, snapshot.snapshot_id
    )
    if decision.decision_type == "accept":
        if context.current_check_input_fingerprint != check_result.input_fingerprint:
            conflicts.append("grouping_check_input_fingerprint")
        if (
            snapshot.source_artifact_id != context.current_source_artifact_id
            or snapshot.source_sha256 != context.current_source_sha256
        ):
            conflicts.append("grouping_source_dependency")
        if (
            snapshot.detection_dependency_id
            != context.current_detection_dependency_id
            or snapshot.detection_dependency_hash
            != context.current_detection_dependency_hash
        ):
            conflicts.append("grouping_detection_dependency")
        if (
            snapshot.profile_snapshot_id != context.current_profile_snapshot_id
            or snapshot.profile_settings_hash != context.current_profile_settings_hash
        ):
            conflicts.append("grouping_profile_dependency")
        if not producer_matches_candidate:
            conflicts.append("grouping_producer_operation_binding")
        if not _ocr_matches_snapshot(expected_ocr, snapshot):
            conflicts.append("grouping_ocr_dependency")
        if snapshot.candidate_disposition != "PRODUCED":
            conflicts.append("grouping_candidate_disposition")
        if any(issue.is_blocking and issue.status == "open" for issue in actual_issues):
            conflicts.append("grouping_unresolved_blocker")
        expected_acceptance_id = grouping_acceptance_id(
            snapshot_id=snapshot.snapshot_id,
            check_result_id=check_result.check_result_id,
        )
        if context.acceptance_id != expected_acceptance_id:
            conflicts.append("grouping_acceptance_id")
        if existing is not None and (
            existing.acceptance_id != expected_acceptance_id
            or existing.check_result_id != check_result.check_result_id
            or existing.accepted_manifest_sha256 != snapshot.manifest_artifact_sha256
            or existing.accepted_dependency_fingerprint != snapshot.dependency_fingerprint
        ):
            conflicts.append("grouping_existing_acceptance")
        if existing is not None and snapshot_has_stale_fact(
            connection, project_id, snapshot.snapshot_id
        ):
            conflicts.append("grouping_stale_snapshot_reactivation")
        replaced = None
        if existing is None and actual_active not in {None, snapshot.snapshot_id}:
            replaced = _load_acceptance_for_snapshot(
                connection, project_id, context.page_id, actual_active
            )
            if replaced is None or snapshot_has_stale_fact(
                connection, project_id, actual_active
            ):
                conflicts.append("grouping_replacement_source_not_current")
        replay = existing is not None and actual_active == snapshot.snapshot_id
    else:
        if context.acceptance_id is not None:
            conflicts.append("grouping_non_accept_has_acceptance")
        replay = False
        replaced = None

    if conflicts:
        return None, tuple(dict.fromkeys(conflicts))
    return (
        GroupingCommitPlan(
            context=context,
            snapshot=snapshot,
            existing_acceptance=existing,
            replaced_acceptance=replaced,
            replay=replay,
        ),
        (),
    )


def persist_grouping_commit(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    decision,
    plan: GroupingCommitPlan,
) -> GroupingCommitResult:
    if decision.decision_type != "accept":
        return GroupingCommitResult(None, None, None, False)
    now = utc_now()
    context = plan.context
    acceptance_id = context.acceptance_id
    assert acceptance_id is not None
    if not plan.replay:
        connection.execute(
            """
            INSERT INTO grouping_snapshot_acceptances (
                acceptance_id, project_id, page_id, snapshot_id, check_result_id,
                workflow_decision_id, workflow_attempt_id,
                acceptance_execution_id, accepted_manifest_sha256,
                accepted_dependency_fingerprint, accepted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                acceptance_id,
                project_id,
                context.page_id,
                context.snapshot_id,
                context.check_result_id,
                decision.decision_id,
                decision.attempt_id,
                context.decision_execution_id,
                plan.snapshot.manifest_artifact_sha256,
                plan.snapshot.dependency_fingerprint,
                now,
            ),
        )
        state = _load_page_state(connection, project_id, context.page_id)
        stale_fact_ids: tuple[str, ...] = ()
        if state is None:
            connection.execute(
                """
                INSERT INTO page_grouping_state (
                    project_id, page_id, active_grouping_snapshot_id, version, updated_at
                ) VALUES (?, ?, ?, 1, ?)
                """,
                (project_id, context.page_id, context.snapshot_id, now),
            )
            version = 1
        elif plan.replaced_acceptance is not None:
            old = plan.replaced_acceptance
            stale_id = persist_grouping_stale_fact(
                connection,
                GroupingSnapshotStaleFactDraft(
                    project_id=project_id, page_id=context.page_id,
                    snapshot_id=old.snapshot_id, acceptance_id=old.acceptance_id,
                    reason_type="GROUPING_REVISION_SUPERSEDED",
                    previous_dependency_type="GROUPING_SNAPSHOT",
                    previous_dependency_id=old.snapshot_id,
                    previous_dependency_hash=old.accepted_dependency_fingerprint,
                    replacement_dependency_id=context.snapshot_id,
                    replacement_dependency_hash=plan.snapshot.dependency_fingerprint,
                    triggering_operation_type="GROUPING_ACCEPTANCE",
                    triggering_operation_id=decision.decision_id,
                ),
            )
            version = state.version + 1
            updated = connection.execute(
                """UPDATE page_grouping_state
                   SET active_grouping_snapshot_id = ?, version = ?, updated_at = ?
                   WHERE project_id = ? AND page_id = ?
                     AND active_grouping_snapshot_id = ? AND version = ?""",
                (context.snapshot_id, version, now, project_id, context.page_id,
                 old.snapshot_id, state.version),
            )
            if updated.rowcount != 1:
                raise sqlite3.IntegrityError("Grouping replacement pointer CAS failed.")
            stale_fact_ids = (stale_id,)
        else:
            version = state.version + 1
            updated = connection.execute(
                """
                UPDATE page_grouping_state
                SET active_grouping_snapshot_id = ?, version = ?, updated_at = ?
                WHERE project_id = ? AND page_id = ?
                  AND active_grouping_snapshot_id IS NULL AND version = ?
                """,
                (
                    context.snapshot_id,
                    version,
                    now,
                    project_id,
                    context.page_id,
                    state.version,
                ),
            )
            if updated.rowcount != 1:
                raise sqlite3.IntegrityError("Grouping pointer CAS failed during commit.")
        execution_outcome = "ACCEPTED"
    else:
        state = _load_page_state(connection, project_id, context.page_id)
        assert state is not None
        version = state.version
        execution_outcome = "REPLAYED"
        stale_fact_ids = ()
    connection.execute(
        """
        INSERT INTO grouping_acceptance_executions (
            execution_id, project_id, page_id, snapshot_id, check_result_id,
            acceptance_id, workflow_decision_id, workflow_attempt_id, outcome,
            completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            context.decision_execution_id,
            project_id,
            context.page_id,
            context.snapshot_id,
            context.check_result_id,
            acceptance_id,
            decision.decision_id,
            decision.attempt_id,
            execution_outcome,
            now,
        ),
    )
    return GroupingCommitResult(
        acceptance_id=acceptance_id,
        active_grouping_snapshot_id=context.snapshot_id,
        page_grouping_state_version=version,
        replayed=plan.replay,
        stale_fact_ids=stale_fact_ids,
    )


def plan_upstream_grouping_stale(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    page_id: str,
    reason_type: str,
    previous_dependency_type: str,
    replacement_dependency_id: str,
    replacement_dependency_hash: str,
    triggering_operation_type: str,
    triggering_operation_id: str,
    text_block_id: str | None = None,
) -> tuple[PageGroupingStateSnapshot, GroupingSnapshotStaleFactDraft] | None:
    state = _load_page_state(connection, project_id, page_id)
    if state is None or state.active_grouping_snapshot_id is None:
        return None
    acceptance = _load_acceptance_for_snapshot(
        connection, project_id, page_id, state.active_grouping_snapshot_id
    )
    if acceptance is None:
        raise ValueError("Active Grouping pointer has no acceptance.")
    snapshot = _load_and_validate_snapshot(
        connection, project_id, state.active_grouping_snapshot_id
    )
    if snapshot_has_stale_fact(connection, project_id, snapshot.snapshot_id):
        raise ValueError("Active Grouping pointer already selects stale evidence.")
    if reason_type == "DETECTION_DEPENDENCY_CHANGED":
        previous_id = snapshot.detection_dependency_id
        previous_hash = snapshot.detection_dependency_hash
    elif reason_type == "OCR_DEPENDENCY_CHANGED":
        dependency = next(
            (item for item in snapshot.ocr_dependencies if item.text_block_id == text_block_id),
            None,
        )
        if dependency is None:
            return None
        previous_id = dependency.ocr_result_id
        previous_hash = _ocr_dependency_hash(
            dependency.ocr_result_id, dependency.ocr_version_number,
            dependency.ocr_text_hash, dependency.ocr_geometry_hash,
            dependency.ocr_input_hash,
        )
    else:
        raise ValueError("Unsupported upstream Grouping stale trigger.")
    if previous_id == replacement_dependency_id and previous_hash == replacement_dependency_hash:
        return None
    return state, GroupingSnapshotStaleFactDraft(
        project_id=project_id, page_id=page_id, snapshot_id=snapshot.snapshot_id,
        acceptance_id=acceptance.acceptance_id, reason_type=reason_type,
        previous_dependency_type=previous_dependency_type,
        previous_dependency_id=previous_id, previous_dependency_hash=previous_hash,
        replacement_dependency_id=replacement_dependency_id,
        replacement_dependency_hash=replacement_dependency_hash,
        triggering_operation_type=triggering_operation_type,
        triggering_operation_id=triggering_operation_id,
    )


def persist_stale_plans_and_clear_pointer(
    connection: sqlite3.Connection,
    *,
    plans: tuple[tuple[PageGroupingStateSnapshot, GroupingSnapshotStaleFactDraft], ...],
) -> tuple[tuple[str, ...], int | None]:
    if not plans:
        return (), None
    expected = plans[0][0]
    if any(plan[0] != expected or plan[1].snapshot_id != plans[0][1].snapshot_id for plan in plans):
        raise ValueError("Grouping stale plans must target one exact current snapshot.")
    ids = tuple(persist_grouping_stale_fact(connection, plan[1]) for plan in plans)
    version = expected.version + 1
    updated = connection.execute(
        """UPDATE page_grouping_state
           SET active_grouping_snapshot_id = NULL, version = ?, updated_at = ?
           WHERE project_id = ? AND page_id = ?
             AND active_grouping_snapshot_id = ? AND version = ?""",
        (version, utc_now(), expected.project_id, expected.page_id,
         expected.active_grouping_snapshot_id, expected.version),
    )
    if updated.rowcount != 1:
        raise sqlite3.IntegrityError("Grouping stale pointer CAS failed.")
    return ids, version


def _ocr_dependency_hash(
    result_id: str, version: int, text_hash: str, geometry_hash: str, input_hash: str
) -> str:
    return sha256(json.dumps(
        [result_id, version, text_hash, geometry_hash, input_hash],
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _load_current_ocr(
    connection: sqlite3.Connection,
    project_id: str,
    snapshot: FrozenGroupingEvidenceSnapshot,
) -> tuple[ExpectedGroupingOcrDependency, ...]:
    current: list[ExpectedGroupingOcrDependency] = []
    for dependency in snapshot.ocr_dependencies:
        row = connection.execute(
            """
            SELECT tb.page_id, tb.ocr_status, tb.active_ocr_result_id,
                   tb.geometry_hash AS text_block_geometry_hash,
                   ocr.ocr_result_id, ocr.version_number, ocr.source_text,
                   ocr.source_text_hash, ocr.geometry_hash, ocr.input_hash
            FROM text_blocks tb
            LEFT JOIN ocr_results ocr
              ON ocr.project_id = tb.project_id
             AND ocr.text_block_id = tb.text_block_id
             AND ocr.ocr_result_id = tb.active_ocr_result_id
            WHERE tb.project_id = ? AND tb.text_block_id = ?
            """,
            (project_id, dependency.text_block_id),
        ).fetchone()
        if (
            row is None
            or row["page_id"] != snapshot.page_id
            or row["ocr_status"] != "done"
            or row["active_ocr_result_id"] is None
            or row["ocr_result_id"] != row["active_ocr_result_id"]
            or row["version_number"] is None
            or row["version_number"] < 1
            or row["source_text_hash"] is None
            or row["geometry_hash"] is None
            or row["input_hash"] is None
            or row["text_block_geometry_hash"] != row["geometry_hash"]
            or row["source_text"] is None
            or sha256(row["source_text"].encode("utf-8")).hexdigest()
            != row["source_text_hash"]
        ):
            continue
        current.append(
            ExpectedGroupingOcrDependency(
                text_block_id=dependency.text_block_id,
                ocr_result_id=row["ocr_result_id"],
                version_number=row["version_number"],
                text_hash=row["source_text_hash"],
                geometry_hash=row["geometry_hash"],
                input_hash=row["input_hash"],
            )
        )
    return tuple(sorted(current, key=lambda item: item.text_block_id.encode("utf-8")))


def _ocr_matches_snapshot(
    current: tuple[ExpectedGroupingOcrDependency, ...],
    snapshot: FrozenGroupingEvidenceSnapshot,
) -> bool:
    stored = tuple(
        ExpectedGroupingOcrDependency(
            text_block_id=item.text_block_id,
            ocr_result_id=item.ocr_result_id,
            version_number=item.ocr_version_number,
            text_hash=item.ocr_text_hash,
            geometry_hash=item.ocr_geometry_hash,
            input_hash=item.ocr_input_hash,
        )
        for item in snapshot.ocr_dependencies
    )
    return current == stored


def _load_check_binding(
    connection: sqlite3.Connection,
    project_id: str,
    check_result_id: str,
) -> _GroupingCheckBinding:
    row = connection.execute(
        """
        SELECT check_result_id, page_id, snapshot_id, input_fingerprint,
               candidate_manifest_sha256, candidate_dependency_fingerprint,
               evidence_artifact_id, evidence_artifact_sha256
        FROM grouping_check_results
        WHERE project_id = ? AND check_result_id = ?
        """,
        (project_id, check_result_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"Grouping CheckResult not found: {check_result_id}")
    if row["check_result_id"] != f"grouping-check-result-v1:{row['input_fingerprint']}":
        raise ValueError("Grouping CheckResult identity is inconsistent.")
    if row["evidence_artifact_id"] is not None:
        artifact = connection.execute(
            """
            SELECT page_id, owner_type, owner_id, artifact_type, source_stage,
                   file_hash, storage_state, dependency_hash
            FROM processing_artifacts
            WHERE project_id = ? AND artifact_id = ?
            """,
            (project_id, row["evidence_artifact_id"]),
        ).fetchone()
        if (
            artifact is None
            or artifact["page_id"] != row["page_id"]
            or artifact["owner_type"] != "grouping_check_result"
            or artifact["owner_id"] != row["check_result_id"]
            or artifact["artifact_type"] != "grouping_check_evidence"
            or artifact["source_stage"] != "grouping_check"
            or artifact["file_hash"] != row["evidence_artifact_sha256"]
            or artifact["storage_state"] != "present"
            or artifact["dependency_hash"] != row["input_fingerprint"]
        ):
            raise ValueError("Grouping CheckResult evidence binding is inconsistent.")
    return _GroupingCheckBinding(
        check_result_id=row["check_result_id"],
        page_id=row["page_id"],
        snapshot_id=row["snapshot_id"],
        input_fingerprint=row["input_fingerprint"],
        candidate_manifest_sha256=row["candidate_manifest_sha256"],
        candidate_dependency_fingerprint=row["candidate_dependency_fingerprint"],
    )


def _snapshot_dependencies_current(
    connection: sqlite3.Connection,
    project_id: str,
    snapshot: FrozenGroupingEvidenceSnapshot,
) -> bool:
    page = connection.execute(
        """
        SELECT original_artifact_id FROM pages
        WHERE project_id = ? AND page_id = ?
        """,
        (project_id, snapshot.page_id),
    ).fetchone()
    source = connection.execute(
        """
        SELECT file_hash, storage_state FROM processing_artifacts
        WHERE project_id = ? AND artifact_id = ?
        """,
        (project_id, snapshot.source_artifact_id),
    ).fetchone()
    manifest = connection.execute(
        """
        SELECT file_hash, storage_state, dependency_hash
        FROM processing_artifacts
        WHERE project_id = ? AND artifact_id = ?
        """,
        (project_id, snapshot.manifest_artifact_id),
    ).fetchone()
    profile = connection.execute(
        """
        SELECT settings_json, settings_hash FROM processing_profile_snapshots
        WHERE project_id = ? AND profile_snapshot_id = ?
        """,
        (project_id, snapshot.profile_snapshot_id),
    ).fetchone()
    try:
        detection = _load_and_validate_evidence_set(
            connection, project_id, snapshot.detection_dependency_id
        )
    except (LookupError, ValueError):
        return False
    return bool(
        page is not None
        and page["original_artifact_id"] == snapshot.source_artifact_id
        and source is not None
        and source["file_hash"] == snapshot.source_sha256
        and source["storage_state"] == "present"
        and manifest is not None
        and manifest["file_hash"] == snapshot.manifest_artifact_sha256
        and manifest["storage_state"] == "present"
        and manifest["dependency_hash"] == snapshot.dependency_fingerprint
        and profile is not None
        and profile["settings_hash"] == snapshot.profile_settings_hash
        and sha256(profile["settings_json"].encode("utf-8")).hexdigest()
        == profile["settings_hash"]
        and detection.page_id == snapshot.page_id
        and detection.canonical_manifest_sha256
        == snapshot.detection_dependency_hash
        and _ocr_matches_snapshot(
            _load_current_ocr(connection, project_id, snapshot), snapshot
        )
    )


def _load_acceptance(
    connection: sqlite3.Connection,
    project_id: str,
    acceptance_id: str,
) -> GroupingAcceptanceSnapshot:
    row = connection.execute(
        """
        SELECT * FROM grouping_snapshot_acceptances
        WHERE project_id = ? AND acceptance_id = ?
        """,
        (project_id, acceptance_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"Grouping acceptance not found: {acceptance_id}")
    return GroupingAcceptanceSnapshot(
        acceptance_id=row["acceptance_id"],
        project_id=row["project_id"],
        page_id=row["page_id"],
        snapshot_id=row["snapshot_id"],
        check_result_id=row["check_result_id"],
        workflow_decision_id=row["workflow_decision_id"],
        workflow_attempt_id=row["workflow_attempt_id"],
        acceptance_execution_id=row["acceptance_execution_id"],
        accepted_manifest_sha256=row["accepted_manifest_sha256"],
        accepted_dependency_fingerprint=row["accepted_dependency_fingerprint"],
        accepted_at=row["accepted_at"],
    )


def _load_acceptance_for_snapshot(
    connection: sqlite3.Connection,
    project_id: str,
    page_id: str,
    snapshot_id: str,
) -> GroupingAcceptanceSnapshot | None:
    row = connection.execute(
        """
        SELECT acceptance_id FROM grouping_snapshot_acceptances
        WHERE project_id = ? AND page_id = ? AND snapshot_id = ?
        """,
        (project_id, page_id, snapshot_id),
    ).fetchone()
    if row is None:
        return None
    return _load_acceptance(connection, project_id, row["acceptance_id"])


def _load_page_state(
    connection: sqlite3.Connection,
    project_id: str,
    page_id: str,
) -> PageGroupingStateSnapshot | None:
    row = connection.execute(
        """
        SELECT * FROM page_grouping_state WHERE project_id = ? AND page_id = ?
        """,
        (project_id, page_id),
    ).fetchone()
    if row is None:
        return None
    return PageGroupingStateSnapshot(
        project_id=row["project_id"],
        page_id=row["page_id"],
        active_grouping_snapshot_id=row["active_grouping_snapshot_id"],
        version=row["version"],
        updated_at=row["updated_at"],
    )
