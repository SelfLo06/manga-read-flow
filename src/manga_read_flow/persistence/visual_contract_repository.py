from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from manga_read_flow.persistence.sqlite_repository_helpers import connect_existing, utc_now


@dataclass(frozen=True)
class VisualContractRevisionDraft:
    visual_contract_revision_id: str
    page_id: str
    source_artifact_id: str
    input_hash: str
    status: str = "frozen"


@dataclass(frozen=True)
class BubbleInstanceRevisionDraft:
    bubble_instance_revision_id: str
    bubble_instance_id: str
    page_id: str
    visual_contract_revision_id: str
    region_hash: str
    instance_mask_artifact_id: str
    required_support_artifact_id: str | None
    safe_edit_artifact_id: str | None
    protected_artifact_id: str | None
    uncertainty_artifact_id: str | None


@dataclass(frozen=True)
class TextSegmentRevisionDraft:
    text_segment_revision_id: str
    text_segment_id: str
    page_id: str
    visual_contract_revision_id: str
    source_text_block_id: str
    segment_order: int


@dataclass(frozen=True)
class SegmentInstanceAssignmentDraft:
    assignment_id: str
    visual_contract_revision_id: str
    text_segment_revision_id: str
    bubble_instance_revision_id: str | None
    disposition: str
    reason_code: str
    evidence_artifact_id: str


@dataclass(frozen=True)
class CleaningEligibilityDraft:
    cleaning_eligibility_id: str
    bubble_instance_revision_id: str
    eligibility: str
    required_safe_completeness: str
    reason_code: str
    evidence_artifact_id: str


@dataclass(frozen=True)
class CleaningResultDraft:
    cleaning_result_id: str
    page_id: str
    visual_contract_revision_id: str
    workflow_attempt_id: str
    cleaned_artifact_id: str
    evidence_artifact_id: str
    input_hash: str
    config_hash: str
    decision: str


@dataclass(frozen=True)
class CleaningResultSnapshot:
    cleaning_result_id: str
    page_id: str
    visual_contract_revision_id: str
    workflow_attempt_id: str
    cleaned_artifact_id: str
    evidence_artifact_id: str
    input_hash: str
    config_hash: str
    decision: str


class VisualContractRepository:
    def __init__(self, *, project_db_path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def prepare_contract(
        self,
        *,
        revision: VisualContractRevisionDraft,
        instances: tuple[BubbleInstanceRevisionDraft, ...],
        segments: tuple[TextSegmentRevisionDraft, ...],
        assignments: tuple[SegmentInstanceAssignmentDraft, ...],
        eligibility: tuple[CleaningEligibilityDraft, ...],
    ) -> None:
        """Persist one coherent visual revision or verify an identical retry."""
        instance_revision_ids = {
            instance.bubble_instance_revision_id for instance in instances
        }
        segment_revision_ids = {
            segment.text_segment_revision_id for segment in segments
        }
        if len(instance_revision_ids) != len(instances):
            raise ValueError("BubbleInstance revision ids must be unique.")
        if len(segment_revision_ids) != len(segments):
            raise ValueError("TextSegment revision ids must be unique.")
        if len({segment.source_text_block_id for segment in segments}) != len(segments):
            raise ValueError("Source TextBlocks must map to at most one TextSegment revision.")
        if any(
            item.page_id != revision.page_id
            or item.visual_contract_revision_id != revision.visual_contract_revision_id
            for item in (*instances, *segments)
        ):
            raise ValueError("Visual contract rows must share one Page and revision.")
        if {assignment.text_segment_revision_id for assignment in assignments} != segment_revision_ids:
            raise ValueError("Every TextSegment revision requires exactly one assignment.")
        if len(assignments) != len(segment_revision_ids):
            raise ValueError("TextSegment assignments must be one-to-one.")
        for assignment in assignments:
            if assignment.visual_contract_revision_id != revision.visual_contract_revision_id:
                raise ValueError("Assignment references the wrong visual revision.")
            if (assignment.disposition == "assigned") != (
                assignment.bubble_instance_revision_id is not None
            ):
                raise ValueError("Assignment disposition and instance reference disagree.")
            if (
                assignment.bubble_instance_revision_id is not None
                and assignment.bubble_instance_revision_id not in instance_revision_ids
            ):
                raise ValueError("Assignment references an unknown BubbleInstance revision.")
        if {item.bubble_instance_revision_id for item in eligibility} != instance_revision_ids:
            raise ValueError("Every BubbleInstance revision requires one eligibility record.")
        if len(eligibility) != len(instance_revision_ids):
            raise ValueError("Cleaning eligibility records must be one-to-one.")

        now = utc_now()
        with connect_existing(self._project_db_path) as connection:
            prior_revision = connection.execute(
                """
                SELECT visual_contract_revision_id
                FROM visual_contract_revisions
                WHERE project_id = ? AND visual_contract_revision_id = ?
                """,
                (self._project_id, revision.visual_contract_revision_id),
            ).fetchone()
            _insert_or_verify(
                connection,
                "visual_contract_revisions",
                "visual_contract_revision_id",
                revision.visual_contract_revision_id,
                {
                    "visual_contract_revision_id": revision.visual_contract_revision_id,
                    "project_id": self._project_id,
                    "page_id": revision.page_id,
                    "source_artifact_id": revision.source_artifact_id,
                    "input_hash": revision.input_hash,
                    "status": revision.status,
                    "created_at": now,
                },
                ignore_columns={"created_at"},
            )
            for item in instances:
                _insert_or_verify(
                    connection,
                    "bubble_instance_revisions",
                    "bubble_instance_revision_id",
                    item.bubble_instance_revision_id,
                    {
                        "bubble_instance_revision_id": item.bubble_instance_revision_id,
                        "bubble_instance_id": item.bubble_instance_id,
                        "project_id": self._project_id,
                        "page_id": item.page_id,
                        "visual_contract_revision_id": item.visual_contract_revision_id,
                        "region_hash": item.region_hash,
                        "instance_mask_artifact_id": item.instance_mask_artifact_id,
                        "required_support_artifact_id": item.required_support_artifact_id,
                        "safe_edit_artifact_id": item.safe_edit_artifact_id,
                        "protected_artifact_id": item.protected_artifact_id,
                        "uncertainty_artifact_id": item.uncertainty_artifact_id,
                        "created_at": now,
                    },
                    ignore_columns={"created_at"},
                )
            for item in segments:
                _insert_or_verify(
                    connection,
                    "text_segment_revisions",
                    "text_segment_revision_id",
                    item.text_segment_revision_id,
                    {
                        "text_segment_revision_id": item.text_segment_revision_id,
                        "text_segment_id": item.text_segment_id,
                        "project_id": self._project_id,
                        "page_id": item.page_id,
                        "visual_contract_revision_id": item.visual_contract_revision_id,
                        "source_text_block_id": item.source_text_block_id,
                        "segment_order": item.segment_order,
                        "created_at": now,
                    },
                    ignore_columns={"created_at"},
                )
            for item in assignments:
                _insert_or_verify(
                    connection,
                    "segment_instance_assignments",
                    "assignment_id",
                    item.assignment_id,
                    {
                        "assignment_id": item.assignment_id,
                        "project_id": self._project_id,
                        "visual_contract_revision_id": item.visual_contract_revision_id,
                        "text_segment_revision_id": item.text_segment_revision_id,
                        "bubble_instance_revision_id": item.bubble_instance_revision_id,
                        "disposition": item.disposition,
                        "reason_code": item.reason_code,
                        "evidence_artifact_id": item.evidence_artifact_id,
                        "created_at": now,
                    },
                    ignore_columns={"created_at"},
                )
            for item in eligibility:
                _insert_or_verify(
                    connection,
                    "cleaning_eligibility_records",
                    "cleaning_eligibility_id",
                    item.cleaning_eligibility_id,
                    {
                        "cleaning_eligibility_id": item.cleaning_eligibility_id,
                        "project_id": self._project_id,
                        "bubble_instance_revision_id": item.bubble_instance_revision_id,
                        "eligibility": item.eligibility,
                        "required_safe_completeness": item.required_safe_completeness,
                        "reason_code": item.reason_code,
                        "evidence_artifact_id": item.evidence_artifact_id,
                        "created_at": now,
                    },
                    ignore_columns={"created_at"},
                )
            current = connection.execute(
                """
                SELECT active_visual_contract_revision_id
                FROM page_visual_contract_state
                WHERE project_id = ? AND page_id = ?
                """,
                (self._project_id, revision.page_id),
            ).fetchone()
            if (
                prior_revision is not None
                and current is not None
                and current["active_visual_contract_revision_id"]
                != revision.visual_contract_revision_id
            ):
                raise ValueError("Cannot reactivate a stale visual contract revision.")
            connection.execute(
                """
                INSERT INTO page_visual_contract_state (
                    project_id,
                    page_id,
                    active_visual_contract_revision_id,
                    input_hash,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, page_id) DO UPDATE SET
                    active_visual_contract_revision_id = excluded.active_visual_contract_revision_id,
                    input_hash = excluded.input_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    self._project_id,
                    revision.page_id,
                    revision.visual_contract_revision_id,
                    revision.input_hash,
                    now,
                ),
            )

    def current_revision_id(self, *, page_id: str) -> str | None:
        with connect_existing(self._project_db_path) as connection:
            row = connection.execute(
                """
                SELECT active_visual_contract_revision_id
                FROM page_visual_contract_state
                WHERE project_id = ? AND page_id = ?
                """,
                (self._project_id, page_id),
            ).fetchone()
        return row["active_visual_contract_revision_id"] if row is not None else None

    def has_revision(self, *, visual_contract_revision_id: str) -> bool:
        with connect_existing(self._project_db_path) as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM visual_contract_revisions
                WHERE project_id = ? AND visual_contract_revision_id = ?
                """,
                (self._project_id, visual_contract_revision_id),
            ).fetchone()
        return row is not None

    def find_reusable_pass(
        self,
        *,
        visual_contract_revision_id: str,
        input_hash: str,
        config_hash: str,
    ) -> CleaningResultSnapshot | None:
        with connect_existing(self._project_db_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM cleaning_result_records
                WHERE project_id = ?
                  AND visual_contract_revision_id = ?
                  AND input_hash = ?
                  AND config_hash = ?
                  AND decision = 'pass'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    self._project_id,
                    visual_contract_revision_id,
                    input_hash,
                    config_hash,
                ),
            ).fetchone()
        return _cleaning_result_snapshot(row) if row is not None else None

    def list_results(self, *, page_id: str) -> tuple[CleaningResultSnapshot, ...]:
        with connect_existing(self._project_db_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM cleaning_result_records
                WHERE project_id = ? AND page_id = ?
                ORDER BY created_at, cleaning_result_id
                """,
                (self._project_id, page_id),
            ).fetchall()
        return tuple(_cleaning_result_snapshot(row) for row in rows)


def insert_cleaning_result(
    connection: sqlite3.Connection,
    project_id: str,
    result: CleaningResultDraft,
) -> None:
    connection.execute(
        """
        INSERT INTO cleaning_result_records (
            cleaning_result_id,
            project_id,
            page_id,
            visual_contract_revision_id,
            workflow_attempt_id,
            cleaned_artifact_id,
            evidence_artifact_id,
            input_hash,
            config_hash,
            decision,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.cleaning_result_id,
            project_id,
            result.page_id,
            result.visual_contract_revision_id,
            result.workflow_attempt_id,
            result.cleaned_artifact_id,
            result.evidence_artifact_id,
            result.input_hash,
            result.config_hash,
            result.decision,
            utc_now(),
        ),
    )


def initialize_visual_contract_schema(connection: sqlite3.Connection) -> None:
    """Create the minimum durable facts required by the MVP-1 visual slice."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS visual_contract_revisions (
            visual_contract_revision_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            source_artifact_id TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS page_visual_contract_state (
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            active_visual_contract_revision_id TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(project_id, page_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS bubble_instance_revisions (
            bubble_instance_revision_id TEXT PRIMARY KEY,
            bubble_instance_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            visual_contract_revision_id TEXT NOT NULL,
            region_hash TEXT NOT NULL,
            instance_mask_artifact_id TEXT NOT NULL,
            required_support_artifact_id TEXT,
            safe_edit_artifact_id TEXT,
            protected_artifact_id TEXT,
            uncertainty_artifact_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, bubble_instance_id, visual_contract_revision_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS text_segment_revisions (
            text_segment_revision_id TEXT PRIMARY KEY,
            text_segment_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            visual_contract_revision_id TEXT NOT NULL,
            source_text_block_id TEXT NOT NULL,
            segment_order INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, text_segment_id, visual_contract_revision_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS segment_instance_assignments (
            assignment_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            visual_contract_revision_id TEXT NOT NULL,
            text_segment_revision_id TEXT NOT NULL,
            bubble_instance_revision_id TEXT,
            disposition TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            evidence_artifact_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, text_segment_revision_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cleaning_eligibility_records (
            cleaning_eligibility_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            bubble_instance_revision_id TEXT NOT NULL,
            eligibility TEXT NOT NULL,
            required_safe_completeness TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            evidence_artifact_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(project_id, bubble_instance_revision_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cleaning_result_records (
            cleaning_result_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            visual_contract_revision_id TEXT NOT NULL,
            workflow_attempt_id TEXT NOT NULL,
            cleaned_artifact_id TEXT NOT NULL,
            evidence_artifact_id TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            config_hash TEXT NOT NULL,
            decision TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def _insert_or_verify(
    connection: sqlite3.Connection,
    table: str,
    id_column: str,
    identity: str,
    values: dict[str, object],
    *,
    ignore_columns: set[str],
) -> None:
    allowed_tables = {
        "visual_contract_revisions",
        "bubble_instance_revisions",
        "text_segment_revisions",
        "segment_instance_assignments",
        "cleaning_eligibility_records",
    }
    if table not in allowed_tables or id_column not in values:
        raise ValueError("Unsupported visual-contract persistence target.")
    columns = tuple(values)
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(values[column] for column in columns),
    )
    row = connection.execute(
        f"SELECT * FROM {table} WHERE project_id = ? AND {id_column} = ?",
        (values["project_id"], identity),
    ).fetchone()
    if row is None:
        raise sqlite3.IntegrityError(f"Unable to persist {table} record.")
    for column, expected in values.items():
        if column not in ignore_columns and row[column] != expected:
            raise ValueError(f"Conflicting retry for {table}.{column}.")


def _cleaning_result_snapshot(row) -> CleaningResultSnapshot:
    return CleaningResultSnapshot(
        cleaning_result_id=row["cleaning_result_id"],
        page_id=row["page_id"],
        visual_contract_revision_id=row["visual_contract_revision_id"],
        workflow_attempt_id=row["workflow_attempt_id"],
        cleaned_artifact_id=row["cleaned_artifact_id"],
        evidence_artifact_id=row["evidence_artifact_id"],
        input_hash=row["input_hash"],
        config_hash=row["config_hash"],
        decision=row["decision"],
    )


__all__ = [
    "BubbleInstanceRevisionDraft",
    "CleaningEligibilityDraft",
    "CleaningResultDraft",
    "CleaningResultSnapshot",
    "SegmentInstanceAssignmentDraft",
    "TextSegmentRevisionDraft",
    "VisualContractRepository",
    "VisualContractRevisionDraft",
    "initialize_visual_contract_schema",
    "insert_cleaning_result",
]
