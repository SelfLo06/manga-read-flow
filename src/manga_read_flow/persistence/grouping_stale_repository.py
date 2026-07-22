from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from manga_read_flow.persistence.sqlite_repository_helpers import connect_existing, utc_now


GROUPING_STALE_REASONS = (
    "DETECTION_DEPENDENCY_CHANGED",
    "OCR_DEPENDENCY_CHANGED",
    "PROFILE_DEPENDENCY_CHANGED",
    "SOURCE_BINDING_CHANGED",
    "GROUPING_REVISION_SUPERSEDED",
    "DEPENDENCY_MISMATCH_REPAIR",
)


@dataclass(frozen=True)
class GroupingSnapshotStaleFactDraft:
    project_id: str
    page_id: str
    snapshot_id: str
    acceptance_id: str
    reason_type: str
    previous_dependency_type: str
    previous_dependency_id: str
    previous_dependency_hash: str
    replacement_dependency_id: str | None
    replacement_dependency_hash: str | None
    triggering_operation_type: str
    triggering_operation_id: str


@dataclass(frozen=True)
class GroupingSnapshotStaleFact(GroupingSnapshotStaleFactDraft):
    stale_fact_id: str
    created_at: str


def grouping_stale_fact_id(draft: GroupingSnapshotStaleFactDraft) -> str:
    payload = json.dumps(
        {
            key: getattr(draft, key)
            for key in (
                "project_id", "page_id", "snapshot_id", "acceptance_id",
                "reason_type", "previous_dependency_type",
                "previous_dependency_id", "previous_dependency_hash",
                "replacement_dependency_id", "replacement_dependency_hash",
                "triggering_operation_type", "triggering_operation_id",
            )
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"grouping-stale-fact-v1:{sha256(payload).hexdigest()}"


class GroupingStaleRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def list_for_snapshot(self, snapshot_id: str) -> tuple[GroupingSnapshotStaleFact, ...]:
        with connect_existing(self._project_db_path) as connection:
            rows = connection.execute(
                """SELECT * FROM grouping_snapshot_stale_facts
                   WHERE project_id = ? AND snapshot_id = ?
                   ORDER BY created_at, stale_fact_id""",
                (self._project_id, snapshot_id),
            ).fetchall()
        return tuple(_fact_from_row(row) for row in rows)


def initialize_grouping_stale_schema(connection: sqlite3.Connection) -> None:
    reasons = ", ".join(f"'{reason}'" for reason in GROUPING_STALE_REASONS)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS grouping_snapshot_stale_facts (
            stale_fact_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            acceptance_id TEXT NOT NULL,
            reason_type TEXT NOT NULL CHECK(reason_type IN ({reasons})),
            previous_dependency_type TEXT NOT NULL,
            previous_dependency_id TEXT NOT NULL,
            previous_dependency_hash TEXT NOT NULL,
            replacement_dependency_id TEXT,
            replacement_dependency_hash TEXT,
            triggering_operation_type TEXT NOT NULL,
            triggering_operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK(stale_fact_id LIKE 'grouping-stale-fact-v1:%'),
            FOREIGN KEY(page_id) REFERENCES pages(page_id),
            FOREIGN KEY(snapshot_id) REFERENCES frozen_grouping_evidence_snapshots(snapshot_id),
            FOREIGN KEY(acceptance_id) REFERENCES grouping_snapshot_acceptances(acceptance_id)
        )
        """
    )
    for action in ("update", "delete"):
        connection.execute(
            f"""CREATE TRIGGER IF NOT EXISTS trg_grouping_snapshot_stale_facts_immutable_{action}
                BEFORE {action.upper()} ON grouping_snapshot_stale_facts
                BEGIN SELECT RAISE(ABORT, 'grouping_snapshot_stale_facts is immutable'); END"""
        )


def persist_grouping_stale_fact(
    connection: sqlite3.Connection,
    draft: GroupingSnapshotStaleFactDraft,
) -> str:
    if draft.reason_type not in GROUPING_STALE_REASONS:
        raise ValueError("Unsupported Grouping stale reason.")
    stale_id = grouping_stale_fact_id(draft)
    existing = connection.execute(
        "SELECT * FROM grouping_snapshot_stale_facts WHERE stale_fact_id = ?",
        (stale_id,),
    ).fetchone()
    if existing is not None:
        expected = draft
        actual = _fact_from_row(existing)
        if any(getattr(actual, field) != getattr(expected, field) for field in expected.__dataclass_fields__):
            raise ValueError("Grouping stale fact identity collision.")
        return stale_id
    connection.execute(
        """INSERT INTO grouping_snapshot_stale_facts (
               stale_fact_id, project_id, page_id, snapshot_id, acceptance_id,
               reason_type, previous_dependency_type, previous_dependency_id,
               previous_dependency_hash, replacement_dependency_id,
               replacement_dependency_hash, triggering_operation_type,
               triggering_operation_id, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (stale_id, draft.project_id, draft.page_id, draft.snapshot_id,
         draft.acceptance_id, draft.reason_type, draft.previous_dependency_type,
         draft.previous_dependency_id, draft.previous_dependency_hash,
         draft.replacement_dependency_id, draft.replacement_dependency_hash,
         draft.triggering_operation_type, draft.triggering_operation_id, utc_now()),
    )
    return stale_id


def snapshot_has_stale_fact(connection: sqlite3.Connection, project_id: str, snapshot_id: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM grouping_snapshot_stale_facts WHERE project_id = ? AND snapshot_id = ? LIMIT 1",
        (project_id, snapshot_id),
    ).fetchone() is not None


def _fact_from_row(row: sqlite3.Row) -> GroupingSnapshotStaleFact:
    return GroupingSnapshotStaleFact(
        stale_fact_id=row["stale_fact_id"], project_id=row["project_id"],
        page_id=row["page_id"], snapshot_id=row["snapshot_id"],
        acceptance_id=row["acceptance_id"], reason_type=row["reason_type"],
        previous_dependency_type=row["previous_dependency_type"],
        previous_dependency_id=row["previous_dependency_id"],
        previous_dependency_hash=row["previous_dependency_hash"],
        replacement_dependency_id=row["replacement_dependency_id"],
        replacement_dependency_hash=row["replacement_dependency_hash"],
        triggering_operation_type=row["triggering_operation_type"],
        triggering_operation_id=row["triggering_operation_id"], created_at=row["created_at"],
    )
