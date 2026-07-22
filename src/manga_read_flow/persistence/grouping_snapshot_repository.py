from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from manga_read_flow.domain.grouping import (
    GROUPING_DISPOSITION_INCOMPLETE,
    GROUPING_DISPOSITION_PRODUCED,
    GROUPING_OUTCOME_ABSTAINED,
    GROUPING_OUTCOME_FAILED,
    GROUPING_OUTCOME_SUCCEEDED,
    GROUPING_SNAPSHOT_ID_PREFIX,
    GroupingDependencyFingerprintInput,
    GroupingFingerprintOcrDependency,
    GroupingProducerIdentity,
    grouping_dependency_fingerprint_from_bindings,
)
from manga_read_flow.persistence.detection_evidence_repository import (
    _load_and_validate_evidence_set,
)
from manga_read_flow.persistence.sqlite_repository_helpers import (
    connect_existing,
    utc_now,
)


@dataclass(frozen=True)
class GroupingSnapshotOcrDependencyDraft:
    text_block_id: str
    ocr_result_id: str
    ocr_version_number: int
    ocr_text_hash: str
    ocr_geometry_hash: str
    ocr_input_hash: str


@dataclass(frozen=True)
class FrozenGroupingEvidenceSnapshotDraft:
    snapshot_id: str
    project_id: str
    page_id: str
    source_artifact_id: str
    source_sha256: str
    coordinate_space_json: str
    detection_dependency_id: str
    detection_dependency_hash: str
    manifest_artifact_id: str
    manifest_artifact_sha256: str
    manifest_schema_version: str
    profile_snapshot_id: str
    profile_settings_hash: str
    producer_name: str
    producer_version: str
    producer_implementation_hash: str
    operation_semantics_version: str
    dependency_fingerprint: str
    candidate_disposition: str
    ocr_dependency_count: int


@dataclass(frozen=True)
class GroupingGenerationRunDraft:
    generation_run_id: str
    page_id: str
    detection_dependency_id: str
    profile_snapshot_id: str
    producer_name: str
    producer_version: str
    producer_implementation_hash: str
    operation_semantics_version: str
    outcome: str
    materialization_status: str
    reason_codes: tuple[str, ...] = ()
    error_code: str | None = None
    snapshot_id: str | None = None


@dataclass(frozen=True)
class GroupingSnapshotOcrDependencySnapshot:
    text_block_id: str
    ocr_result_id: str
    ocr_version_number: int
    ocr_text_hash: str
    ocr_geometry_hash: str
    ocr_input_hash: str
    canonical_ordinal: int


@dataclass(frozen=True)
class GroupingGenerationRunSnapshot:
    generation_run_id: str
    outcome: str
    materialization_status: str
    reason_codes: tuple[str, ...]
    error_code: str | None
    snapshot_id: str | None
    created_at: str


@dataclass(frozen=True)
class FrozenGroupingEvidenceSnapshot:
    snapshot_id: str
    project_id: str
    page_id: str
    source_artifact_id: str
    source_sha256: str
    coordinate_space_json: str
    detection_dependency_id: str
    detection_dependency_hash: str
    manifest_artifact_id: str
    manifest_artifact_sha256: str
    manifest_schema_version: str
    profile_snapshot_id: str
    profile_settings_hash: str
    producer_name: str
    producer_version: str
    producer_implementation_hash: str
    operation_semantics_version: str
    dependency_fingerprint: str
    candidate_disposition: str
    ocr_dependency_count: int
    created_at: str
    ocr_dependencies: tuple[GroupingSnapshotOcrDependencySnapshot, ...]
    generation_runs: tuple[GroupingGenerationRunSnapshot, ...]


@dataclass(frozen=True)
class GroupingCandidateMaterializationOutcome:
    snapshot: FrozenGroupingEvidenceSnapshot
    created: bool


class GroupingSnapshotRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def get(self, snapshot_id: str) -> FrozenGroupingEvidenceSnapshot:
        with connect_existing(self._project_db_path) as connection:
            return _load_and_validate_snapshot(connection, self._project_id, snapshot_id)

    def get_optional(self, snapshot_id: str) -> FrozenGroupingEvidenceSnapshot | None:
        with connect_existing(self._project_db_path) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM frozen_grouping_evidence_snapshots
                WHERE project_id = ? AND snapshot_id = ?
                """,
                (self._project_id, snapshot_id),
            ).fetchone()
            if row is None:
                return None
            return _load_and_validate_snapshot(connection, self._project_id, snapshot_id)

    def materialize_candidate(
        self,
        *,
        snapshot: FrozenGroupingEvidenceSnapshotDraft,
        ocr_dependencies: tuple[GroupingSnapshotOcrDependencyDraft, ...],
        generation_run: GroupingGenerationRunDraft,
    ) -> GroupingCandidateMaterializationOutcome:
        with connect_existing(self._project_db_path) as connection:
            _validate_snapshot_draft(
                connection,
                self._project_id,
                snapshot,
                ocr_dependencies,
            )
            existing = connection.execute(
                """
                SELECT manifest_artifact_id
                FROM frozen_grouping_evidence_snapshots
                WHERE project_id = ? AND snapshot_id = ?
                """,
                (self._project_id, snapshot.snapshot_id),
            ).fetchone()
            created = existing is None
            if created:
                _insert_snapshot(connection, self._project_id, snapshot, ocr_dependencies)
            else:
                current = _load_and_validate_snapshot(
                    connection,
                    self._project_id,
                    snapshot.snapshot_id,
                )
                _require_equivalent_snapshot(current, snapshot, ocr_dependencies)
            _insert_generation_run(
                connection,
                self._project_id,
                replace(
                    generation_run,
                    materialization_status=("MATERIALIZED" if created else "REUSED"),
                ),
                expected_snapshot_id=snapshot.snapshot_id,
                expected_materialization_status=(
                    "MATERIALIZED" if created else "REUSED"
                ),
            )
            loaded = _load_and_validate_snapshot(
                connection,
                self._project_id,
                snapshot.snapshot_id,
            )
        return GroupingCandidateMaterializationOutcome(snapshot=loaded, created=created)

    def record_generation_outcome(self, run: GroupingGenerationRunDraft) -> None:
        with connect_existing(self._project_db_path) as connection:
            _validate_run_context(connection, self._project_id, run)
            _insert_generation_run(
                connection,
                self._project_id,
                run,
                expected_snapshot_id=None,
                expected_materialization_status="NO_CANDIDATE",
            )


def initialize_grouping_snapshot_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS frozen_grouping_evidence_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            source_artifact_id TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            coordinate_space_json TEXT NOT NULL,
            detection_dependency_id TEXT NOT NULL,
            detection_dependency_hash TEXT NOT NULL,
            manifest_artifact_id TEXT NOT NULL,
            manifest_artifact_sha256 TEXT NOT NULL,
            manifest_schema_version TEXT NOT NULL,
            profile_snapshot_id TEXT NOT NULL,
            profile_settings_hash TEXT NOT NULL,
            producer_name TEXT NOT NULL,
            producer_version TEXT NOT NULL,
            producer_implementation_hash TEXT NOT NULL,
            operation_semantics_version TEXT NOT NULL,
            dependency_fingerprint TEXT NOT NULL UNIQUE,
            candidate_disposition TEXT NOT NULL
                CHECK(candidate_disposition IN ('PRODUCED', 'INCOMPLETE')),
            ocr_dependency_count INTEGER NOT NULL CHECK(ocr_dependency_count >= 0),
            created_at TEXT NOT NULL,
            CHECK(snapshot_id = 'grouping-snapshot-v1:' || dependency_fingerprint),
            FOREIGN KEY(page_id) REFERENCES pages(page_id),
            FOREIGN KEY(source_artifact_id) REFERENCES processing_artifacts(artifact_id),
            FOREIGN KEY(detection_dependency_id)
                REFERENCES accepted_detection_evidence_sets(detection_dependency_id),
            FOREIGN KEY(manifest_artifact_id)
                REFERENCES processing_artifacts(artifact_id),
            FOREIGN KEY(profile_snapshot_id)
                REFERENCES processing_profile_snapshots(profile_snapshot_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS grouping_snapshot_ocr_dependencies (
            snapshot_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            text_block_id TEXT NOT NULL,
            ocr_result_id TEXT NOT NULL,
            ocr_version_number INTEGER NOT NULL CHECK(ocr_version_number >= 1),
            ocr_text_hash TEXT NOT NULL,
            ocr_geometry_hash TEXT NOT NULL,
            ocr_input_hash TEXT NOT NULL,
            canonical_ordinal INTEGER NOT NULL CHECK(canonical_ordinal >= 0),
            PRIMARY KEY(snapshot_id, text_block_id),
            UNIQUE(snapshot_id, ocr_result_id),
            UNIQUE(snapshot_id, canonical_ordinal),
            FOREIGN KEY(snapshot_id)
                REFERENCES frozen_grouping_evidence_snapshots(snapshot_id),
            FOREIGN KEY(text_block_id) REFERENCES text_blocks(text_block_id),
            FOREIGN KEY(ocr_result_id) REFERENCES ocr_results(ocr_result_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS grouping_generation_runs (
            generation_run_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            detection_dependency_id TEXT NOT NULL,
            profile_snapshot_id TEXT NOT NULL,
            producer_name TEXT NOT NULL,
            producer_version TEXT NOT NULL,
            producer_implementation_hash TEXT NOT NULL,
            operation_semantics_version TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome IN ('SUCCEEDED', 'ABSTAINED', 'FAILED')),
            materialization_status TEXT NOT NULL
                CHECK(materialization_status IN ('MATERIALIZED', 'REUSED', 'NO_CANDIDATE')),
            reason_codes_json TEXT NOT NULL,
            error_code TEXT,
            snapshot_id TEXT,
            created_at TEXT NOT NULL,
            CHECK(
                (outcome = 'SUCCEEDED'
                    AND materialization_status IN ('MATERIALIZED', 'REUSED')
                    AND snapshot_id IS NOT NULL)
                OR
                (outcome IN ('ABSTAINED', 'FAILED')
                    AND materialization_status = 'NO_CANDIDATE'
                    AND snapshot_id IS NULL)
            ),
            FOREIGN KEY(detection_dependency_id)
                REFERENCES accepted_detection_evidence_sets(detection_dependency_id),
            FOREIGN KEY(profile_snapshot_id)
                REFERENCES processing_profile_snapshots(profile_snapshot_id),
            FOREIGN KEY(snapshot_id)
                REFERENCES frozen_grouping_evidence_snapshots(snapshot_id)
        )
        """
    )
    for table in (
        "frozen_grouping_evidence_snapshots",
        "grouping_snapshot_ocr_dependencies",
        "grouping_generation_runs",
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


def _validate_snapshot_draft(
    connection: sqlite3.Connection,
    project_id: str,
    draft: FrozenGroupingEvidenceSnapshotDraft,
    ocr_dependencies: tuple[GroupingSnapshotOcrDependencyDraft, ...],
) -> None:
    if draft.project_id != project_id:
        raise ValueError("Grouping snapshot Project binding is invalid.")
    if draft.candidate_disposition not in {
        GROUPING_DISPOSITION_PRODUCED,
        GROUPING_DISPOSITION_INCOMPLETE,
    }:
        raise ValueError("Grouping snapshot candidate disposition is invalid.")
    if draft.manifest_schema_version != "frozen-grouping-evidence-manifest.v1":
        raise ValueError("Grouping snapshot manifest schema version is invalid.")
    if draft.snapshot_id != f"{GROUPING_SNAPSHOT_ID_PREFIX}{draft.dependency_fingerprint}":
        raise ValueError("Grouping snapshot identity is invalid.")
    if draft.ocr_dependency_count != len(ocr_dependencies):
        raise ValueError("Grouping snapshot OCR dependency count is inconsistent.")
    if len({item.text_block_id for item in ocr_dependencies}) != len(ocr_dependencies):
        raise ValueError("Grouping snapshot contains duplicate TextBlock dependencies.")
    if len({item.ocr_result_id for item in ocr_dependencies}) != len(ocr_dependencies):
        raise ValueError("Grouping snapshot contains duplicate OCR dependencies.")

    detection = _load_and_validate_evidence_set(
        connection,
        project_id,
        draft.detection_dependency_id,
    )
    if (
        detection.project_id != project_id
        or detection.page_id != draft.page_id
        or detection.source_artifact_id != draft.source_artifact_id
        or detection.source_sha256 != draft.source_sha256
        or detection.coordinate_space_json != draft.coordinate_space_json
        or detection.canonical_manifest_sha256 != draft.detection_dependency_hash
    ):
        raise ValueError("Grouping snapshot Detection dependency binding is invalid.")
    dependency_ids = tuple(
        sorted(item.text_block_id for item in ocr_dependencies)
    )
    detection_ids = tuple(member.text_block_id for member in detection.members)
    if dependency_ids != detection_ids:
        raise ValueError("Grouping snapshot OCR dependencies must match Detection members.")

    _validate_source_profile_and_manifest(connection, project_id, draft)
    for dependency in ocr_dependencies:
        _validate_ocr_dependency(
            connection,
            project_id,
            draft.page_id,
            dependency,
        )
    expected_fingerprint = _fingerprint_from_draft(draft, ocr_dependencies)
    if expected_fingerprint != draft.dependency_fingerprint:
        raise ValueError("Grouping snapshot dependency fingerprint is inconsistent.")


def _validate_source_profile_and_manifest(
    connection: sqlite3.Connection,
    project_id: str,
    draft: FrozenGroupingEvidenceSnapshotDraft,
) -> None:
    page = connection.execute(
        """
        SELECT original_artifact_id FROM pages
        WHERE project_id = ? AND page_id = ?
        """,
        (project_id, draft.page_id),
    ).fetchone()
    source = connection.execute(
        """
        SELECT artifact_type, file_hash, storage_state
        FROM processing_artifacts
        WHERE project_id = ? AND artifact_id = ?
        """,
        (project_id, draft.source_artifact_id),
    ).fetchone()
    profile = connection.execute(
        """
        SELECT settings_json, settings_hash
        FROM processing_profile_snapshots
        WHERE project_id = ? AND profile_snapshot_id = ?
        """,
        (project_id, draft.profile_snapshot_id),
    ).fetchone()
    manifest = connection.execute(
        """
        SELECT page_id, owner_type, owner_id, artifact_type, source_stage,
               file_hash, mime_type, storage_state, dependency_hash
        FROM processing_artifacts
        WHERE project_id = ? AND artifact_id = ?
        """,
        (project_id, draft.manifest_artifact_id),
    ).fetchone()
    if (
        page is None
        or page["original_artifact_id"] != draft.source_artifact_id
        or source is None
        or source["artifact_type"] != "original_image"
        or source["file_hash"] != draft.source_sha256
        or source["storage_state"] != "present"
    ):
        raise ValueError("Grouping snapshot source binding is invalid.")
    if (
        profile is None
        or profile["settings_hash"] != draft.profile_settings_hash
        or sha256(profile["settings_json"].encode("utf-8")).hexdigest()
        != draft.profile_settings_hash
    ):
        raise ValueError("Grouping snapshot profile binding is invalid.")
    try:
        json.loads(profile["settings_json"])
    except json.JSONDecodeError as exc:
        raise ValueError("Grouping snapshot profile settings are malformed.") from exc
    if (
        manifest is None
        or manifest["page_id"] != draft.page_id
        or manifest["owner_type"] != "frozen_grouping_evidence_snapshot"
        or manifest["owner_id"] != draft.snapshot_id
        or manifest["artifact_type"] != "frozen_grouping_evidence_manifest"
        or manifest["source_stage"] != "grouping"
        or manifest["file_hash"] != draft.manifest_artifact_sha256
        or manifest["mime_type"] != "application/json"
        or manifest["storage_state"] != "present"
        or manifest["dependency_hash"] != draft.dependency_fingerprint
    ):
        raise ValueError("Grouping snapshot manifest artifact binding is invalid.")


def _validate_ocr_dependency(
    connection: sqlite3.Connection,
    project_id: str,
    page_id: str,
    dependency: GroupingSnapshotOcrDependencyDraft,
) -> None:
    row = connection.execute(
        """
        SELECT tb.page_id, tb.ocr_status, tb.active_ocr_result_id,
               ocr.version_number, ocr.source_text_hash, ocr.geometry_hash, ocr.input_hash
        FROM text_blocks tb
        LEFT JOIN ocr_results ocr
            ON ocr.project_id = tb.project_id
            AND ocr.text_block_id = tb.text_block_id
            AND ocr.ocr_result_id = ?
        WHERE tb.project_id = ? AND tb.text_block_id = ?
        """,
        (dependency.ocr_result_id, project_id, dependency.text_block_id),
    ).fetchone()
    if (
        row is None
        or row["page_id"] != page_id
        or row["ocr_status"] != "done"
        or row["active_ocr_result_id"] != dependency.ocr_result_id
        or row["version_number"] != dependency.ocr_version_number
        or row["source_text_hash"] != dependency.ocr_text_hash
        or row["geometry_hash"] != dependency.ocr_geometry_hash
        or row["input_hash"] != dependency.ocr_input_hash
    ):
        raise ValueError("Grouping snapshot exact OCR dependency is invalid.")


def _fingerprint_from_draft(
    draft: FrozenGroupingEvidenceSnapshotDraft | FrozenGroupingEvidenceSnapshot,
    dependencies,
) -> str:
    return grouping_dependency_fingerprint_from_bindings(
        input_data=GroupingDependencyFingerprintInput(
            source_artifact_id=draft.source_artifact_id,
            source_sha256=draft.source_sha256,
            coordinate_space_json=draft.coordinate_space_json,
            detection_dependency_id=draft.detection_dependency_id,
            detection_dependency_hash=draft.detection_dependency_hash,
            profile_snapshot_id=draft.profile_snapshot_id,
            profile_settings_hash=draft.profile_settings_hash,
            producer=GroupingProducerIdentity(
                producer_name=draft.producer_name,
                producer_version=draft.producer_version,
                implementation_hash=draft.producer_implementation_hash,
            ),
            operation_semantics_version=draft.operation_semantics_version,
            ocr_dependencies=tuple(
                GroupingFingerprintOcrDependency(
                    text_block_id=item.text_block_id,
                    ocr_result_id=item.ocr_result_id,
                    version_number=item.ocr_version_number,
                    text_hash=item.ocr_text_hash,
                    geometry_hash=item.ocr_geometry_hash,
                    input_hash=item.ocr_input_hash,
                )
                for item in dependencies
            ),
        ),
        canonical_manifest_sha256=draft.manifest_artifact_sha256,
    )


def _insert_snapshot(
    connection: sqlite3.Connection,
    project_id: str,
    draft: FrozenGroupingEvidenceSnapshotDraft,
    dependencies: tuple[GroupingSnapshotOcrDependencyDraft, ...],
) -> None:
    connection.execute(
        """
        INSERT INTO frozen_grouping_evidence_snapshots (
            snapshot_id, project_id, page_id, source_artifact_id, source_sha256,
            coordinate_space_json, detection_dependency_id, detection_dependency_hash,
            manifest_artifact_id, manifest_artifact_sha256, manifest_schema_version,
            profile_snapshot_id, profile_settings_hash, producer_name, producer_version,
            producer_implementation_hash, operation_semantics_version,
            dependency_fingerprint, candidate_disposition, ocr_dependency_count, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft.snapshot_id, project_id, draft.page_id, draft.source_artifact_id,
            draft.source_sha256, draft.coordinate_space_json,
            draft.detection_dependency_id, draft.detection_dependency_hash,
            draft.manifest_artifact_id, draft.manifest_artifact_sha256,
            draft.manifest_schema_version, draft.profile_snapshot_id,
            draft.profile_settings_hash, draft.producer_name, draft.producer_version,
            draft.producer_implementation_hash, draft.operation_semantics_version,
            draft.dependency_fingerprint, draft.candidate_disposition,
            draft.ocr_dependency_count, utc_now(),
        ),
    )
    for ordinal, dependency in enumerate(
        sorted(dependencies, key=lambda item: item.text_block_id.encode("utf-8"))
    ):
        connection.execute(
            """
            INSERT INTO grouping_snapshot_ocr_dependencies (
                snapshot_id, project_id, page_id, text_block_id, ocr_result_id,
                ocr_version_number, ocr_text_hash, ocr_geometry_hash,
                ocr_input_hash, canonical_ordinal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft.snapshot_id, project_id, draft.page_id,
                dependency.text_block_id, dependency.ocr_result_id,
                dependency.ocr_version_number, dependency.ocr_text_hash,
                dependency.ocr_geometry_hash, dependency.ocr_input_hash, ordinal,
            ),
        )


def _validate_run_context(
    connection: sqlite3.Connection,
    project_id: str,
    run: GroupingGenerationRunDraft,
) -> None:
    if (
        not run.generation_run_id
        or not run.page_id
        or not run.profile_snapshot_id
        or not run.producer_name
        or not run.producer_version
        or not run.operation_semantics_version
        or len(run.producer_implementation_hash) != 64
        or any(
            character not in "0123456789abcdef"
            for character in run.producer_implementation_hash
        )
    ):
        raise ValueError("Grouping generation run identity is invalid.")
    detection = _load_and_validate_evidence_set(
        connection, project_id, run.detection_dependency_id
    )
    profile = connection.execute(
        """
        SELECT 1 FROM processing_profile_snapshots
        WHERE project_id = ? AND profile_snapshot_id = ?
        """,
        (project_id, run.profile_snapshot_id),
    ).fetchone()
    if detection.page_id != run.page_id or profile is None:
        raise ValueError("Grouping generation run input binding is invalid.")


def _insert_generation_run(
    connection: sqlite3.Connection,
    project_id: str,
    run: GroupingGenerationRunDraft,
    *,
    expected_snapshot_id: str | None,
    expected_materialization_status: str,
) -> None:
    _validate_run_context(connection, project_id, run)
    if run.snapshot_id != expected_snapshot_id:
        raise ValueError("Grouping generation run snapshot binding is invalid.")
    if run.materialization_status != expected_materialization_status:
        raise ValueError("Grouping generation run materialization status is invalid.")
    if expected_snapshot_id is None:
        if run.outcome not in {GROUPING_OUTCOME_ABSTAINED, GROUPING_OUTCOME_FAILED}:
            raise ValueError("Grouping run without a candidate must abstain or fail.")
        if not run.reason_codes:
            raise ValueError("Grouping run without a candidate requires reason codes.")
    elif run.outcome != GROUPING_OUTCOME_SUCCEEDED:
        raise ValueError("Materialized Grouping candidate must have SUCCEEDED outcome.")
    reason_codes_json = json.dumps(
        sorted(set(run.reason_codes), key=lambda value: value.encode("utf-8")),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    expected = (
        project_id, run.page_id, run.detection_dependency_id, run.profile_snapshot_id,
        run.producer_name, run.producer_version, run.producer_implementation_hash,
        run.operation_semantics_version, run.outcome, run.materialization_status,
        reason_codes_json, run.error_code, run.snapshot_id,
    )
    existing = connection.execute(
        """
        SELECT project_id, page_id, detection_dependency_id, profile_snapshot_id,
               producer_name, producer_version, producer_implementation_hash,
               operation_semantics_version, outcome, materialization_status,
               reason_codes_json, error_code, snapshot_id
        FROM grouping_generation_runs WHERE generation_run_id = ?
        """,
        (run.generation_run_id,),
    ).fetchone()
    if existing is not None:
        if tuple(existing) != expected:
            raise ValueError("Grouping generation run identity conflicts.")
        return
    connection.execute(
        """
        INSERT INTO grouping_generation_runs (
            generation_run_id, project_id, page_id, detection_dependency_id,
            profile_snapshot_id, producer_name, producer_version,
            producer_implementation_hash, operation_semantics_version,
            outcome, materialization_status, reason_codes_json, error_code,
            snapshot_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run.generation_run_id, *expected, utc_now()),
    )


def _load_and_validate_snapshot(
    connection: sqlite3.Connection,
    project_id: str,
    snapshot_id: str,
) -> FrozenGroupingEvidenceSnapshot:
    row = connection.execute(
        """
        SELECT * FROM frozen_grouping_evidence_snapshots
        WHERE project_id = ? AND snapshot_id = ?
        """,
        (project_id, snapshot_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"FrozenGroupingEvidenceSnapshot not found: {snapshot_id}")
    dependency_rows = connection.execute(
        """
        SELECT * FROM grouping_snapshot_ocr_dependencies
        WHERE project_id = ? AND snapshot_id = ?
        ORDER BY canonical_ordinal
        """,
        (project_id, snapshot_id),
    ).fetchall()
    if any(item["page_id"] != row["page_id"] for item in dependency_rows):
        raise ValueError("Grouping snapshot OCR dependency Page binding is inconsistent.")
    dependencies = tuple(
        GroupingSnapshotOcrDependencySnapshot(
            text_block_id=item["text_block_id"],
            ocr_result_id=item["ocr_result_id"],
            ocr_version_number=item["ocr_version_number"],
            ocr_text_hash=item["ocr_text_hash"],
            ocr_geometry_hash=item["ocr_geometry_hash"],
            ocr_input_hash=item["ocr_input_hash"],
            canonical_ordinal=item["canonical_ordinal"],
        )
        for item in dependency_rows
    )
    if len(dependencies) != row["ocr_dependency_count"] or tuple(
        item.canonical_ordinal for item in dependencies
    ) != tuple(range(len(dependencies))):
        raise ValueError("Grouping snapshot OCR dependency membership is inconsistent.")
    runs = tuple(
        GroupingGenerationRunSnapshot(
            generation_run_id=item["generation_run_id"],
            outcome=item["outcome"],
            materialization_status=item["materialization_status"],
            reason_codes=tuple(json.loads(item["reason_codes_json"])),
            error_code=item["error_code"],
            snapshot_id=item["snapshot_id"],
            created_at=item["created_at"],
        )
        for item in connection.execute(
            """
            SELECT generation_run_id, outcome, materialization_status,
                   reason_codes_json, error_code, snapshot_id, created_at
            FROM grouping_generation_runs
            WHERE project_id = ? AND snapshot_id = ?
            ORDER BY created_at, generation_run_id
            """,
            (project_id, snapshot_id),
        ).fetchall()
    )
    snapshot = FrozenGroupingEvidenceSnapshot(
        snapshot_id=row["snapshot_id"], project_id=row["project_id"],
        page_id=row["page_id"], source_artifact_id=row["source_artifact_id"],
        source_sha256=row["source_sha256"],
        coordinate_space_json=row["coordinate_space_json"],
        detection_dependency_id=row["detection_dependency_id"],
        detection_dependency_hash=row["detection_dependency_hash"],
        manifest_artifact_id=row["manifest_artifact_id"],
        manifest_artifact_sha256=row["manifest_artifact_sha256"],
        manifest_schema_version=row["manifest_schema_version"],
        profile_snapshot_id=row["profile_snapshot_id"],
        profile_settings_hash=row["profile_settings_hash"],
        producer_name=row["producer_name"], producer_version=row["producer_version"],
        producer_implementation_hash=row["producer_implementation_hash"],
        operation_semantics_version=row["operation_semantics_version"],
        dependency_fingerprint=row["dependency_fingerprint"],
        candidate_disposition=row["candidate_disposition"],
        ocr_dependency_count=row["ocr_dependency_count"], created_at=row["created_at"],
        ocr_dependencies=dependencies, generation_runs=runs,
    )
    _validate_loaded_snapshot(connection, project_id, snapshot)
    return snapshot


def _validate_loaded_snapshot(
    connection: sqlite3.Connection,
    project_id: str,
    snapshot: FrozenGroupingEvidenceSnapshot,
) -> None:
    # Historical reads validate only the immutable record itself. Whether these
    # bindings are still current is a separate GroupingCheck responsibility.
    if snapshot.project_id != project_id:
        raise ValueError("Grouping snapshot Project binding is inconsistent.")
    for name, value in (
        ("snapshot_id", snapshot.snapshot_id),
        ("page_id", snapshot.page_id),
        ("source_artifact_id", snapshot.source_artifact_id),
        ("detection_dependency_id", snapshot.detection_dependency_id),
        ("manifest_artifact_id", snapshot.manifest_artifact_id),
        ("manifest_schema_version", snapshot.manifest_schema_version),
        ("profile_snapshot_id", snapshot.profile_snapshot_id),
        ("producer_name", snapshot.producer_name),
        ("producer_version", snapshot.producer_version),
        ("operation_semantics_version", snapshot.operation_semantics_version),
        ("candidate_disposition", snapshot.candidate_disposition),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"Historical Grouping snapshot {name} is invalid.")
    for name, value in (
        ("source_sha256", snapshot.source_sha256),
        ("detection_dependency_hash", snapshot.detection_dependency_hash),
        ("manifest_artifact_sha256", snapshot.manifest_artifact_sha256),
        ("profile_settings_hash", snapshot.profile_settings_hash),
        ("producer_implementation_hash", snapshot.producer_implementation_hash),
        ("dependency_fingerprint", snapshot.dependency_fingerprint),
    ):
        if not _is_sha256(value):
            raise ValueError(f"Historical Grouping snapshot {name} is invalid.")
    try:
        coordinate_space = json.loads(snapshot.coordinate_space_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Historical Grouping coordinate space is malformed.") from exc
    if not isinstance(coordinate_space, dict) or not coordinate_space:
        raise ValueError("Historical Grouping coordinate space is invalid.")
    for dependency in snapshot.ocr_dependencies:
        if (
            not dependency.text_block_id
            or not dependency.ocr_result_id
            or dependency.ocr_version_number < 1
            or not _is_sha256(dependency.ocr_text_hash)
            or not _is_sha256(dependency.ocr_geometry_hash)
            or not _is_sha256(dependency.ocr_input_hash)
        ):
            raise ValueError("Historical Grouping OCR binding is invalid.")


def _require_equivalent_snapshot(
    current: FrozenGroupingEvidenceSnapshot,
    draft: FrozenGroupingEvidenceSnapshotDraft,
    dependencies: tuple[GroupingSnapshotOcrDependencyDraft, ...],
) -> None:
    comparable_current = (
        current.project_id, current.page_id, current.source_artifact_id,
        current.source_sha256, current.coordinate_space_json,
        current.detection_dependency_id, current.detection_dependency_hash,
        current.manifest_artifact_sha256, current.manifest_schema_version,
        current.profile_snapshot_id, current.profile_settings_hash,
        current.producer_name, current.producer_version,
        current.producer_implementation_hash, current.operation_semantics_version,
        current.dependency_fingerprint, current.candidate_disposition,
        current.ocr_dependency_count,
    )
    comparable_draft = (
        draft.project_id, draft.page_id, draft.source_artifact_id,
        draft.source_sha256, draft.coordinate_space_json,
        draft.detection_dependency_id, draft.detection_dependency_hash,
        draft.manifest_artifact_sha256, draft.manifest_schema_version,
        draft.profile_snapshot_id, draft.profile_settings_hash,
        draft.producer_name, draft.producer_version,
        draft.producer_implementation_hash, draft.operation_semantics_version,
        draft.dependency_fingerprint, draft.candidate_disposition,
        draft.ocr_dependency_count,
    )
    current_dependencies = tuple(
        (
            item.text_block_id, item.ocr_result_id, item.ocr_version_number,
            item.ocr_text_hash, item.ocr_geometry_hash, item.ocr_input_hash,
        )
        for item in current.ocr_dependencies
    )
    draft_dependencies = tuple(
        (
            item.text_block_id, item.ocr_result_id, item.ocr_version_number,
            item.ocr_text_hash, item.ocr_geometry_hash, item.ocr_input_hash,
        )
        for item in sorted(
            dependencies, key=lambda item: item.text_block_id.encode("utf-8")
        )
    )
    if comparable_current != comparable_draft or current_dependencies != draft_dependencies:
        raise ValueError("Grouping snapshot identity conflicts with immutable semantics.")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
