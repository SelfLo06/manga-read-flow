from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3

from manga_read_flow.persistence.acceptance_repository import (
    IssueLifecycleChange,
    apply_issue_lifecycle_change,
)
from manga_read_flow.persistence.sqlite_repository_helpers import (
    connect_existing,
    utc_now,
)
from manga_read_flow.quality.grouping_check import (
    GROUPING_CHECK_RESULT_ID_PREFIX,
    GROUPING_ROOT_STAGE,
    GroupingCheckMetrics,
    GroupingCheckResult,
)


@dataclass(frozen=True)
class GroupingCheckExecutionDraft:
    execution_id: str
    check_result_id: str
    snapshot_id: str
    page_id: str
    input_fingerprint: str


@dataclass(frozen=True)
class GroupingCheckExecutionSnapshot:
    execution_id: str
    check_result_id: str
    snapshot_id: str
    page_id: str
    input_fingerprint: str
    outcome: str
    completed_at: str


@dataclass(frozen=True)
class GroupingCheckCommitOutcome:
    check_result: GroupingCheckResult
    issue_ids: tuple[str, ...]
    execution: GroupingCheckExecutionSnapshot
    created: bool


class GroupingCheckRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def get(self, check_result_id: str) -> GroupingCheckResult:
        with connect_existing(self._project_db_path) as connection:
            return _load_and_validate_result(connection, self._project_id, check_result_id)

    def get_optional_by_input_fingerprint(
        self,
        input_fingerprint: str,
    ) -> GroupingCheckResult | None:
        with connect_existing(self._project_db_path) as connection:
            row = connection.execute(
                """
                SELECT check_result_id FROM grouping_check_results
                WHERE project_id = ? AND input_fingerprint = ?
                """,
                (self._project_id, input_fingerprint),
            ).fetchone()
            if row is None:
                return None
            return _load_and_validate_result(
                connection, self._project_id, row["check_result_id"]
            )

    def issue_ids_for_result(self, check_result_id: str) -> tuple[str, ...]:
        with connect_existing(self._project_db_path) as connection:
            _load_and_validate_result(connection, self._project_id, check_result_id)
            return _load_issue_ids(connection, self._project_id, check_result_id)

    def list_executions(
        self, check_result_id: str
    ) -> tuple[GroupingCheckExecutionSnapshot, ...]:
        with connect_existing(self._project_db_path) as connection:
            _load_and_validate_result(connection, self._project_id, check_result_id)
            return _load_executions(connection, self._project_id, check_result_id)

    def commit_evaluation(
        self,
        *,
        check_result: GroupingCheckResult,
        issue_changes: tuple[IssueLifecycleChange, ...],
        execution: GroupingCheckExecutionDraft,
    ) -> GroupingCheckCommitOutcome:
        with connect_existing(self._project_db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            _validate_result_draft(connection, self._project_id, check_result)
            existing = connection.execute(
                """
                SELECT check_result_id FROM grouping_check_results
                WHERE project_id = ? AND input_fingerprint = ?
                """,
                (self._project_id, check_result.input_fingerprint),
            ).fetchone()
            created = existing is None
            if created:
                _insert_result(connection, self._project_id, check_result)
                persisted_result = check_result
            else:
                persisted_result = _load_and_validate_result(
                    connection, self._project_id, existing["check_result_id"]
                )
                _require_equivalent_result(persisted_result, check_result)

            issue_ids = _persist_issues(
                connection,
                self._project_id,
                persisted_result,
                issue_changes,
            )
            execution_snapshot = _insert_execution(
                connection,
                self._project_id,
                execution,
                outcome="MATERIALIZED" if created else "REUSED",
            )
            exact = _load_and_validate_result(
                connection, self._project_id, persisted_result.check_result_id
            )
            if _load_issue_ids(connection, self._project_id, exact.check_result_id) != issue_ids:
                raise ValueError("Grouping CheckResult issue relation set is inconsistent.")
        return GroupingCheckCommitOutcome(
            check_result=exact,
            issue_ids=issue_ids,
            execution=execution_snapshot,
            created=created,
        )


def initialize_grouping_check_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS grouping_check_results (
            check_result_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            check_name TEXT NOT NULL,
            check_version TEXT NOT NULL,
            input_fingerprint TEXT NOT NULL,
            candidate_manifest_sha256 TEXT NOT NULL,
            candidate_dependency_fingerprint TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            finding_codes_json TEXT NOT NULL,
            evidence_artifact_id TEXT,
            evidence_artifact_sha256 TEXT,
            completed_at TEXT NOT NULL,
            CHECK(check_result_id = 'grouping-check-result-v1:' || input_fingerprint),
            CHECK(
                (evidence_artifact_id IS NULL AND evidence_artifact_sha256 IS NULL)
                OR
                (evidence_artifact_id IS NOT NULL AND evidence_artifact_sha256 IS NOT NULL)
            ),
            UNIQUE(project_id, snapshot_id, check_name, check_version, input_fingerprint),
            FOREIGN KEY(page_id) REFERENCES pages(page_id),
            FOREIGN KEY(snapshot_id)
                REFERENCES frozen_grouping_evidence_snapshots(snapshot_id),
            FOREIGN KEY(evidence_artifact_id)
                REFERENCES processing_artifacts(artifact_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS grouping_check_result_issues (
            relation_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            check_result_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            issue_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, check_result_id, issue_id),
            FOREIGN KEY(check_result_id) REFERENCES grouping_check_results(check_result_id),
            FOREIGN KEY(snapshot_id)
                REFERENCES frozen_grouping_evidence_snapshots(snapshot_id),
            FOREIGN KEY(issue_id) REFERENCES quality_issues(issue_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS grouping_check_executions (
            execution_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            check_result_id TEXT NOT NULL,
            input_fingerprint TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome IN ('MATERIALIZED', 'REUSED')),
            completed_at TEXT NOT NULL,
            FOREIGN KEY(page_id) REFERENCES pages(page_id),
            FOREIGN KEY(snapshot_id)
                REFERENCES frozen_grouping_evidence_snapshots(snapshot_id),
            FOREIGN KEY(check_result_id) REFERENCES grouping_check_results(check_result_id)
        )
        """
    )
    for table in (
        "grouping_check_results",
        "grouping_check_result_issues",
        "grouping_check_executions",
    ):
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


def _validate_result_draft(
    connection: sqlite3.Connection,
    project_id: str,
    result: GroupingCheckResult,
) -> None:
    if result.project_id != project_id:
        raise ValueError("Grouping CheckResult Project binding is invalid.")
    if result.check_result_id != (
        f"{GROUPING_CHECK_RESULT_ID_PREFIX}{result.input_fingerprint}"
    ):
        raise ValueError("Grouping CheckResult identity is invalid.")
    for name, value in (
        ("page_id", result.page_id),
        ("snapshot_id", result.snapshot_id),
        ("check_name", result.check_name),
        ("check_version", result.check_version),
        ("completed_at", result.completed_at),
    ):
        if not value:
            raise ValueError(f"Grouping CheckResult {name} is required.")
    for name, value in (
        ("input_fingerprint", result.input_fingerprint),
        ("candidate_manifest_sha256", result.candidate_manifest_sha256),
        ("candidate_dependency_fingerprint", result.candidate_dependency_fingerprint),
    ):
        if not _is_sha256(value):
            raise ValueError(f"Grouping CheckResult {name} is invalid.")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in asdict(result.metrics).values()
    ):
        raise ValueError("Grouping CheckResult metrics are invalid.")
    if tuple(sorted(set(result.finding_codes), key=_utf8_key)) != result.finding_codes:
        raise ValueError("Grouping CheckResult finding codes must be canonical.")
    snapshot = connection.execute(
        """
        SELECT page_id, manifest_artifact_sha256, dependency_fingerprint
        FROM frozen_grouping_evidence_snapshots
        WHERE project_id = ? AND snapshot_id = ?
        """,
        (project_id, result.snapshot_id),
    ).fetchone()
    if (
        snapshot is None
        or snapshot["page_id"] != result.page_id
        or snapshot["manifest_artifact_sha256"]
        != result.candidate_manifest_sha256
        or snapshot["dependency_fingerprint"]
        != result.candidate_dependency_fingerprint
    ):
        raise ValueError("Grouping CheckResult candidate binding is invalid.")
    if (result.evidence_artifact_id is None) != (
        result.evidence_artifact_sha256 is None
    ):
        raise ValueError("Grouping CheckResult evidence binding is incomplete.")
    if result.evidence_artifact_id is not None:
        artifact = connection.execute(
            """
            SELECT page_id, owner_type, owner_id, artifact_type, source_stage,
                   file_hash, mime_type, storage_state, dependency_hash
            FROM processing_artifacts
            WHERE project_id = ? AND artifact_id = ?
            """,
            (project_id, result.evidence_artifact_id),
        ).fetchone()
        if (
            artifact is None
            or artifact["page_id"] != result.page_id
            or artifact["owner_type"] != "grouping_check_result"
            or artifact["owner_id"] != result.check_result_id
            or artifact["artifact_type"] != "grouping_check_evidence"
            or artifact["source_stage"] != "grouping_check"
            or artifact["file_hash"] != result.evidence_artifact_sha256
            or artifact["mime_type"] != "application/json"
            or artifact["storage_state"] != "present"
            or artifact["dependency_hash"] != result.input_fingerprint
        ):
            raise ValueError("Grouping CheckResult evidence artifact binding is invalid.")


def _insert_result(
    connection: sqlite3.Connection,
    project_id: str,
    result: GroupingCheckResult,
) -> None:
    connection.execute(
        """
        INSERT INTO grouping_check_results (
            check_result_id, project_id, page_id, snapshot_id, check_name,
            check_version, input_fingerprint, candidate_manifest_sha256,
            candidate_dependency_fingerprint, metrics_json, finding_codes_json,
            evidence_artifact_id, evidence_artifact_sha256, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.check_result_id,
            project_id,
            result.page_id,
            result.snapshot_id,
            result.check_name,
            result.check_version,
            result.input_fingerprint,
            result.candidate_manifest_sha256,
            result.candidate_dependency_fingerprint,
            _canonical_json(asdict(result.metrics)),
            _canonical_json(list(result.finding_codes)),
            result.evidence_artifact_id,
            result.evidence_artifact_sha256,
            result.completed_at,
        ),
    )


def _persist_issues(
    connection: sqlite3.Connection,
    project_id: str,
    result: GroupingCheckResult,
    issue_changes: tuple[IssueLifecycleChange, ...],
) -> tuple[str, ...]:
    issue_ids: list[str] = []
    dedupe_keys: set[str] = set()
    for change in issue_changes:
        if (
            change.action != "create"
            or change.page_id != result.page_id
            or change.discovered_stage != GROUPING_ROOT_STAGE
            or change.root_stage != GROUPING_ROOT_STAGE
            or change.applies_to_result_id != result.check_result_id
            or change.input_hash != result.input_fingerprint
            or not change.dedupe_key
            or change.dedupe_key in dedupe_keys
        ):
            raise ValueError("Grouping QualityIssue lifecycle binding is invalid.")
        dedupe_keys.add(change.dedupe_key)
        rows = connection.execute(
            """
            SELECT * FROM quality_issues
            WHERE project_id = ? AND dedupe_key = ?
            ORDER BY issue_id
            """,
            (project_id, change.dedupe_key),
        ).fetchall()
        if len(rows) > 1:
            raise ValueError("Grouping QualityIssue dedupe identity is ambiguous.")
        if rows:
            issue_id = rows[0]["issue_id"]
            _require_equivalent_issue(rows[0], change)
        else:
            apply_issue_lifecycle_change(connection, project_id, change)
            issue_id = change.issue_id
        relation_id = f"grouping-check-issue:{result.check_result_id}:{issue_id}"
        connection.execute(
            """
            INSERT OR IGNORE INTO grouping_check_result_issues (
                relation_id, project_id, check_result_id, snapshot_id, issue_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                relation_id,
                project_id,
                result.check_result_id,
                result.snapshot_id,
                issue_id,
                utc_now(),
            ),
        )
        issue_ids.append(issue_id)
    expected = tuple(sorted(issue_ids, key=_utf8_key))
    existing = _load_issue_ids(connection, project_id, result.check_result_id)
    if existing != expected:
        raise ValueError("Grouping CheckResult issue set conflicts with immutable facts.")
    return expected


def _insert_execution(
    connection: sqlite3.Connection,
    project_id: str,
    draft: GroupingCheckExecutionDraft,
    *,
    outcome: str,
) -> GroupingCheckExecutionSnapshot:
    if (
        not draft.execution_id
        or not draft.page_id
        or draft.check_result_id
        != f"{GROUPING_CHECK_RESULT_ID_PREFIX}{draft.input_fingerprint}"
    ):
        raise ValueError("Grouping check execution identity is invalid.")
    result = connection.execute(
        """
        SELECT page_id, snapshot_id, input_fingerprint
        FROM grouping_check_results
        WHERE project_id = ? AND check_result_id = ?
        """,
        (project_id, draft.check_result_id),
    ).fetchone()
    if (
        result is None
        or result["page_id"] != draft.page_id
        or result["snapshot_id"] != draft.snapshot_id
        or result["input_fingerprint"] != draft.input_fingerprint
    ):
        raise ValueError("Grouping check execution result binding is invalid.")
    existing = connection.execute(
        "SELECT * FROM grouping_check_executions WHERE execution_id = ?",
        (draft.execution_id,),
    ).fetchone()
    if existing is None:
        connection.execute(
            """
            INSERT INTO grouping_check_executions (
                execution_id, project_id, page_id, snapshot_id, check_result_id,
                input_fingerprint, outcome, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft.execution_id,
                project_id,
                draft.page_id,
                draft.snapshot_id,
                draft.check_result_id,
                draft.input_fingerprint,
                outcome,
                utc_now(),
            ),
        )
    else:
        expected = (
            project_id,
            draft.page_id,
            draft.snapshot_id,
            draft.check_result_id,
            draft.input_fingerprint,
        )
        actual = tuple(
            existing[name]
            for name in (
                "project_id",
                "page_id",
                "snapshot_id",
                "check_result_id",
                "input_fingerprint",
            )
        )
        if actual != expected:
            raise ValueError("Grouping check execution identity conflicts.")
    row = connection.execute(
        "SELECT * FROM grouping_check_executions WHERE execution_id = ?",
        (draft.execution_id,),
    ).fetchone()
    return _execution_snapshot(row)


def _load_and_validate_result(
    connection: sqlite3.Connection,
    project_id: str,
    check_result_id: str,
) -> GroupingCheckResult:
    row = connection.execute(
        """
        SELECT * FROM grouping_check_results
        WHERE project_id = ? AND check_result_id = ?
        """,
        (project_id, check_result_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"GroupingCheckResult not found: {check_result_id}")
    try:
        metrics_data = json.loads(row["metrics_json"])
        finding_codes_data = json.loads(row["finding_codes_json"])
        metrics = GroupingCheckMetrics(**metrics_data)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Grouping CheckResult structured metadata is malformed.") from exc
    if not isinstance(finding_codes_data, list) or not all(
        isinstance(item, str) for item in finding_codes_data
    ):
        raise ValueError("Grouping CheckResult finding codes are malformed.")
    result = GroupingCheckResult(
        check_result_id=row["check_result_id"],
        project_id=row["project_id"],
        page_id=row["page_id"],
        snapshot_id=row["snapshot_id"],
        check_name=row["check_name"],
        check_version=row["check_version"],
        input_fingerprint=row["input_fingerprint"],
        candidate_manifest_sha256=row["candidate_manifest_sha256"],
        candidate_dependency_fingerprint=row["candidate_dependency_fingerprint"],
        metrics=metrics,
        finding_codes=tuple(finding_codes_data),
        evidence_artifact_id=row["evidence_artifact_id"],
        evidence_artifact_sha256=row["evidence_artifact_sha256"],
        completed_at=row["completed_at"],
    )
    _validate_result_draft(connection, project_id, result)
    issue_ids = _load_issue_ids(connection, project_id, result.check_result_id)
    for issue_id in issue_ids:
        issue = connection.execute(
            """
            SELECT page_id, root_stage, applies_to_result_id, input_hash
            FROM quality_issues WHERE project_id = ? AND issue_id = ?
            """,
            (project_id, issue_id),
        ).fetchone()
        if (
            issue is None
            or issue["page_id"] != result.page_id
            or issue["root_stage"] != GROUPING_ROOT_STAGE
            or issue["applies_to_result_id"] != result.check_result_id
            or issue["input_hash"] != result.input_fingerprint
        ):
            raise ValueError("Grouping CheckResult QualityIssue binding is invalid.")
    return result


def _load_issue_ids(
    connection: sqlite3.Connection,
    project_id: str,
    check_result_id: str,
) -> tuple[str, ...]:
    rows = connection.execute(
        """
        SELECT issue_id FROM grouping_check_result_issues
        WHERE project_id = ? AND check_result_id = ?
        ORDER BY issue_id
        """,
        (project_id, check_result_id),
    ).fetchall()
    return tuple(row["issue_id"] for row in rows)


def _load_executions(
    connection: sqlite3.Connection,
    project_id: str,
    check_result_id: str,
) -> tuple[GroupingCheckExecutionSnapshot, ...]:
    return tuple(
        _execution_snapshot(row)
        for row in connection.execute(
            """
            SELECT * FROM grouping_check_executions
            WHERE project_id = ? AND check_result_id = ?
            ORDER BY completed_at, execution_id
            """,
            (project_id, check_result_id),
        ).fetchall()
    )


def _execution_snapshot(row: sqlite3.Row) -> GroupingCheckExecutionSnapshot:
    return GroupingCheckExecutionSnapshot(
        execution_id=row["execution_id"],
        check_result_id=row["check_result_id"],
        snapshot_id=row["snapshot_id"],
        page_id=row["page_id"],
        input_fingerprint=row["input_fingerprint"],
        outcome=row["outcome"],
        completed_at=row["completed_at"],
    )


def _require_equivalent_result(
    current: GroupingCheckResult,
    proposed: GroupingCheckResult,
) -> None:
    current_values = asdict(current)
    proposed_values = asdict(proposed)
    current_values.pop("completed_at")
    proposed_values.pop("completed_at")
    if current_values != proposed_values:
        raise ValueError("Grouping CheckResult identity conflicts with immutable facts.")


def _require_equivalent_issue(
    current: sqlite3.Row,
    proposed: IssueLifecycleChange,
) -> None:
    expected = {
        "target_type": proposed.target_type,
        "target_id": proposed.target_id,
        "page_id": proposed.page_id,
        "discovered_stage": proposed.discovered_stage,
        "root_stage": proposed.root_stage,
        "issue_type": proposed.issue_type,
        "error_code": proposed.error_code,
        "severity": proposed.severity,
        "message_key": proposed.message_key,
        "message_params_json": proposed.message_params_json,
        "suggested_action_key": proposed.suggested_action_key,
        "related_artifact_id": proposed.related_artifact_id,
        "applies_to_result_id": proposed.applies_to_result_id,
        "input_hash": proposed.input_hash,
        "config_hash": proposed.config_hash,
        "dedupe_key": proposed.dedupe_key,
    }
    if any(current[name] != value for name, value in expected.items()):
        raise ValueError("Grouping QualityIssue dedupe identity conflicts.")


def _canonical_json(value: object) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(payload.encode("utf-8")) > 256 * 1024:
        raise ValueError("Grouping CheckResult metadata exceeds the size limit.")
    return payload


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _utf8_key(value: str) -> bytes:
    return value.encode("utf-8")
