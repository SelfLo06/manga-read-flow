from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Self
from urllib.parse import quote
from uuid import uuid4

from manga_read_flow.persistence.artifact_metadata_repository import (
    ArtifactMetadataRepository,
)
from manga_read_flow.persistence.repository_uow_core import (
    ContentStateRepository,
    GlossaryRepository,
    ProjectUnitOfWork,
    QualityIssueRepository,
    ReadinessQueryRepository,
    ResultVersionRepository,
    StageEvidenceWriter,
    WorkflowExecutionRepository,
    initialize_repository_core_schema,
)
from manga_read_flow.persistence.visual_contract_repository import (
    VisualContractRepository,
)
from manga_read_flow.persistence.full_page_cleaning_ledger_repository import (
    FullPageCleaningLedgerRepository,
    initialize_full_page_cleaning_acceptance_schema,
)
from manga_read_flow.persistence.full_page_cleaning_acceptance_repository import (
    FullPageCleaningAcceptanceRepository,
)


APP_BASELINE_VERSION = "app_baseline_v1"
PROJECT_BASELINE_VERSION = "project_baseline_v1"
PROJECT_VISUAL_CONTRACT_VERSION = "project_visual_contract_v2"
PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION = "project_full_page_cleaning_ledger_v3"
PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION = "project_full_page_cleaning_acceptance_v3"
APP_BASELINE_CHECKSUM = sha256(
    b"app_baseline_v1:projects:schema_migrations"
).hexdigest()
PROJECT_BASELINE_CHECKSUM = sha256(
    b"project_baseline_v1:project_metadata:schema_migrations:repository_uow_core:artifactservice_import:slice06_quality_issues_readiness"
).hexdigest()
PROJECT_VISUAL_CONTRACT_CHECKSUM = sha256(
    b"project_visual_contract_v2:page_current_revision:instance_segment_eligibility:cleaning_result_history"
).hexdigest()
PROJECT_FULL_PAGE_CLEANING_LEDGER_CHECKSUM = sha256(
    b"project_full_page_cleaning_ledger_v3:run:inventory:disposition:instance_result:correction"
).hexdigest()
PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_CHECKSUM = sha256(
    b"project_full_page_cleaning_acceptance_v3:combined_candidate:normalized_membership:page_validation:quality_issue_relations:atomic_acceptance"
).hexdigest()

PROJECT_FULL_PAGE_CLEANING_REQUIRED_MIGRATIONS = (
    (PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION, PROJECT_FULL_PAGE_CLEANING_LEDGER_CHECKSUM),
    (
        PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,
        PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_CHECKSUM,
    ),
)

PROJECT_FULL_PAGE_CLEANING_REQUIRED_SCHEMA_OBJECTS = (
    ("table", "page_cleaning_runs"),
    ("table", "page_cleaning_inventory_items"),
    ("table", "instance_cleaning_results"),
    ("table", "instance_result_inventory_targets"),
    ("table", "segment_cleaning_dispositions"),
    ("table", "cleaning_correction_chains"),
    ("table", "cleaning_correction_reservations"),
    ("table", "combined_cleaning_candidates"),
    ("table", "combined_cleaning_candidate_members"),
    ("table", "page_cleaning_validation_records"),
    ("table", "cleaning_quality_issue_relations"),
    ("table", "accepted_segment_cleaning_dispositions"),
    ("table", "page_cleaning_acceptances"),
    ("index", "uq_accepted_combined_candidate_per_run"),
    ("index", "uq_accepted_validation_per_candidate"),
    ("trigger", "trg_cleaned_pass_requires_accepted_member"),
)

PROJECT_FULL_PAGE_CLEANING_REQUIRED_TABLE_COLUMNS = {
    "combined_cleaning_candidates": {
        "combined_cleaning_candidate_id",
        "page_cleaning_run_id",
        "combined_artifact_id",
        "combined_hash",
        "member_set_fingerprint",
        "status",
        "accepted_validation_record_id",
    },
    "combined_cleaning_candidate_members": {
        "combined_cleaning_candidate_id",
        "instance_cleaning_result_id",
        "bubble_instance_revision_id",
        "composition_key",
        "actual_changed_artifact_id",
        "actual_changed_hash",
        "selection_status",
    },
    "page_cleaning_validation_records": {
        "page_cleaning_validation_record_id",
        "combined_cleaning_candidate_id",
        "status",
        "selection_status",
        "missing_attribution_count",
        "duplicate_attribution_count",
        "pairwise_overlap_pixel_count",
        "wrong_instance_write_pixel_count",
        "combined_delta_matches_member_union",
        "dependencies_fresh",
    },
    "cleaning_quality_issue_relations": {
        "cleaning_quality_issue_relation_id",
        "issue_id",
        "page_cleaning_run_id",
        "cleaning_inventory_item_id",
        "instance_cleaning_result_id",
        "combined_cleaning_candidate_id",
        "page_cleaning_validation_record_id",
        "correction_reservation_id",
        "workflow_decision_id",
    },
    "accepted_segment_cleaning_dispositions": {
        "accepted_segment_cleaning_disposition_id",
        "cleaning_inventory_item_id",
        "instance_cleaning_result_id",
        "combined_cleaning_candidate_id",
        "page_cleaning_validation_record_id",
        "disposition_code",
    },
    "page_cleaning_acceptances": {
        "page_cleaning_acceptance_id",
        "page_cleaning_run_id",
        "combined_cleaning_candidate_id",
        "page_cleaning_validation_record_id",
        "cleaned_artifact_id",
        "idempotency_key",
        "status",
    },
}

PROJECT_FULL_PAGE_CLEANING_REQUIRED_SQL_FRAGMENTS = {
    "combined_cleaning_candidates": (
        "unique(project_id,page_cleaning_run_id,member_set_fingerprint)",
        "check(statusin('official_unselected','validated','accepted','stale'))",
    ),
    "combined_cleaning_candidate_members": (
        "unique(combined_cleaning_candidate_id,bubble_instance_revision_id)",
        "unique(combined_cleaning_candidate_id,composition_key)",
    ),
    "page_cleaning_validation_records": (
        "unique(project_id,combined_cleaning_candidate_id,validation_fingerprint)",
        "check(statusin('pass','fail','stale'))",
    ),
    "accepted_segment_cleaning_dispositions": (
        "check(disposition_code='cleaned_pass')",
        "unique(project_id,cleaning_inventory_item_id)",
    ),
    "page_cleaning_acceptances": (
        "unique(project_id,page_cleaning_run_id)",
        "unique(project_id,idempotency_key)",
    ),
}


class ProjectOpenStatus(str, Enum):
    READY = "ready"
    APP_MIGRATION_REQUIRED = "app_migration_required"
    APP_MIGRATION_FAILED = "app_migration_failed"
    PROJECT_MIGRATION_REQUIRED = "project_migration_required"
    PROJECT_MIGRATION_FAILED = "project_migration_failed"
    IDENTITY_MISMATCH = "identity_mismatch"
    DATABASE_MISSING = "database_missing"
    DATABASE_UNREADABLE = "database_unreadable"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    NEWER_INCOMPATIBLE_SCHEMA = "newer_incompatible_schema"
    REPAIR_REQUIRED = "repair_required"


class ProjectStoreNotReadyError(RuntimeError):
    """Raised when Project repositories are requested before readiness."""


class AppStoreNotReadyError(RuntimeError):
    """Raised when app-level Project operations are requested before readiness."""


@dataclass(frozen=True)
class MigrationRecord:
    version: str
    checksum: str
    applied_at: str


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    name: str
    workspace_path: Path
    project_db_path: Path
    source_language: str
    target_language: str


@dataclass(frozen=True)
class ProjectMetadata:
    project_id: str
    project_schema_version: str
    workspace_identity: str
    created_at: str
    last_opened_at: str | None


@dataclass(frozen=True)
class ProjectOpenResult:
    status: ProjectOpenStatus
    project_id: str
    project_record: ProjectRecord | None = None
    metadata: ProjectMetadata | None = None
    project_migrations: tuple[MigrationRecord, ...] = ()

    def repositories(self) -> ProjectRepositories:
        if self.status is not ProjectOpenStatus.READY or self.project_record is None:
            raise ProjectStoreNotReadyError(
                f"Project repositories are unavailable while open status is "
                f"{self.status.value}."
            )
        return ProjectRepositories(
            project_db_path=self.project_record.project_db_path,
            project_id=self.project_id,
        )


class AppStore:
    def __init__(self, workspace_root: Path, app_db_path: Path, is_ready: bool) -> None:
        self.workspace_root = workspace_root
        self.app_db_path = app_db_path
        self.is_ready = is_ready

    @classmethod
    def initialize(cls, workspace_root: Path | str) -> Self:
        root = Path(workspace_root)
        root.mkdir(parents=True, exist_ok=True)
        app_db_path = root / "app.db"

        with _connect(app_db_path) as connection:
            _initialize_app_schema(connection)
            _ensure_migration(
                connection,
                version=APP_BASELINE_VERSION,
                checksum=APP_BASELINE_CHECKSUM,
            )
            _require_ready_migration(
                connection,
                version=APP_BASELINE_VERSION,
                checksum=APP_BASELINE_CHECKSUM,
                missing_status=ProjectOpenStatus.APP_MIGRATION_REQUIRED,
                error_cls=AppStoreNotReadyError,
            )

        return cls(workspace_root=root, app_db_path=app_db_path, is_ready=True)

    def app_migrations(self) -> tuple[MigrationRecord, ...]:
        self._require_ready()
        with _connect(self.app_db_path) as connection:
            return _load_migrations(connection)

    def create_project(
        self,
        *,
        name: str,
        source_language: str,
        target_language: str,
    ) -> ProjectRecord:
        self._require_ready()

        project_id = str(uuid4())
        project_workspace = self.workspace_root / "projects" / project_id
        project_db_path = project_workspace / "project.db"
        project_workspace.mkdir(parents=True, exist_ok=False)

        workspace_identity = _workspace_identity(project_id, project_workspace)
        _initialize_project_database(
            project_db_path=project_db_path,
            project_id=project_id,
            workspace_identity=workspace_identity,
        )

        now = _utc_now()
        with _connect(self.app_db_path) as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    project_id,
                    name,
                    workspace_project_path,
                    project_db_path,
                    default_source_language,
                    default_target_language,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    name,
                    str(project_workspace),
                    str(project_db_path),
                    source_language,
                    target_language,
                    "active",
                    now,
                    now,
                ),
            )

        return ProjectRecord(
            project_id=project_id,
            name=name,
            workspace_path=project_workspace,
            project_db_path=project_db_path,
            source_language=source_language,
            target_language=target_language,
        )

    def open_project(self, project_id: str) -> ProjectOpenResult:
        app_status = self._app_status()
        if app_status is not ProjectOpenStatus.READY:
            return ProjectOpenResult(
                status=app_status,
                project_id=project_id,
            )

        project_record = self._load_project_record(project_id)
        if project_record is None:
            return ProjectOpenResult(
                status=ProjectOpenStatus.REPAIR_REQUIRED,
                project_id=project_id,
            )

        if not self._project_paths_are_valid(project_record):
            return ProjectOpenResult(
                status=ProjectOpenStatus.REPAIR_REQUIRED,
                project_id=project_id,
                project_record=project_record,
            )

        if not project_record.project_db_path.is_file():
            return ProjectOpenResult(
                status=ProjectOpenStatus.DATABASE_MISSING,
                project_id=project_id,
                project_record=project_record,
            )

        try:
            with _connect_existing(project_record.project_db_path) as connection:
                metadata = _load_project_metadata(connection)
                if metadata is None:
                    return ProjectOpenResult(
                        status=ProjectOpenStatus.REPAIR_REQUIRED,
                        project_id=project_id,
                        project_record=project_record,
                    )

                if metadata.project_id != project_id:
                    return ProjectOpenResult(
                        status=ProjectOpenStatus.IDENTITY_MISMATCH,
                        project_id=project_id,
                        project_record=project_record,
                        metadata=metadata,
                        project_migrations=_load_migrations(connection),
                    )

                if metadata.workspace_identity != _workspace_identity(
                    project_id,
                    project_record.workspace_path,
                ):
                    return ProjectOpenResult(
                        status=ProjectOpenStatus.IDENTITY_MISMATCH,
                        project_id=project_id,
                        project_record=project_record,
                        metadata=metadata,
                        project_migrations=_load_migrations(connection),
                    )

                metadata_version_status = _project_metadata_version_status(
                    metadata.project_schema_version
                )
                if metadata_version_status is not ProjectOpenStatus.READY:
                    return ProjectOpenResult(
                        status=metadata_version_status,
                        project_id=project_id,
                        project_record=project_record,
                        metadata=metadata,
                        project_migrations=_load_migrations(connection),
                    )

                migration_status = _project_migration_status(connection)
                if migration_status is not ProjectOpenStatus.READY:
                    return ProjectOpenResult(
                        status=migration_status,
                        project_id=project_id,
                        project_record=project_record,
                        metadata=metadata,
                        project_migrations=_load_migrations(connection),
                    )
                if metadata.project_schema_version != PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION:
                    return ProjectOpenResult(
                        status=ProjectOpenStatus.REPAIR_REQUIRED,
                        project_id=project_id,
                        project_record=project_record,
                        metadata=metadata,
                        project_migrations=_load_migrations(connection),
                    )

                opened_at = _utc_now()
                connection.execute(
                    "UPDATE project_metadata SET last_opened_at = ? WHERE project_id = ?",
                    (opened_at, project_id),
                )
                metadata = _load_project_metadata(connection)

                return ProjectOpenResult(
                    status=ProjectOpenStatus.READY,
                    project_id=project_id,
                    project_record=project_record,
                    metadata=metadata,
                    project_migrations=_load_migrations(connection),
                )
        except sqlite3.DatabaseError:
            return ProjectOpenResult(
                status=ProjectOpenStatus.DATABASE_UNREADABLE,
                project_id=project_id,
                project_record=project_record,
            )

    def migrate_project(self, project_id: str) -> ProjectOpenResult:
        """Apply explicit additive project migrations through the ledger v3 schema."""
        self._require_ready()
        project_record = self._load_project_record(project_id)
        if project_record is None or not self._project_paths_are_valid(project_record):
            return ProjectOpenResult(status=ProjectOpenStatus.REPAIR_REQUIRED, project_id=project_id)
        try:
            with _connect_existing(project_record.project_db_path) as connection:
                metadata = _load_project_metadata(connection)
                if metadata is None:
                    return ProjectOpenResult(status=ProjectOpenStatus.REPAIR_REQUIRED, project_id=project_id, project_record=project_record)
                metadata_version_status = _project_metadata_version_status(
                    metadata.project_schema_version
                )
                if metadata_version_status is not ProjectOpenStatus.READY:
                    return ProjectOpenResult(status=metadata_version_status, project_id=project_id, project_record=project_record, metadata=metadata)
                base = _verify_migration(
                    connection,
                    version=PROJECT_BASELINE_VERSION,
                    checksum=PROJECT_BASELINE_CHECKSUM,
                    missing_status=ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
                )
                if base is not ProjectOpenStatus.READY:
                    return ProjectOpenResult(status=base, project_id=project_id, project_record=project_record)
                visual = _verify_migration(
                    connection,
                    version=PROJECT_VISUAL_CONTRACT_VERSION,
                    checksum=PROJECT_VISUAL_CONTRACT_CHECKSUM,
                    missing_status=ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
                )
                if visual not in {
                    ProjectOpenStatus.READY,
                    ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
                }:
                    return ProjectOpenResult(status=visual, project_id=project_id, project_record=project_record)
                ledger = _verify_migration(
                    connection,
                    version=PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,
                    checksum=PROJECT_FULL_PAGE_CLEANING_LEDGER_CHECKSUM,
                    missing_status=ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
                )
                if ledger not in {
                    ProjectOpenStatus.READY,
                    ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
                }:
                    return ProjectOpenResult(status=ledger, project_id=project_id, project_record=project_record)
                completion = _verify_migration(
                    connection,
                    version=PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,
                    checksum=PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_CHECKSUM,
                    missing_status=ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
                )
                if completion not in {
                    ProjectOpenStatus.READY,
                    ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
                }:
                    return ProjectOpenResult(status=completion, project_id=project_id, project_record=project_record)

                if visual is ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED or ledger is ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED:
                    connection.execute("BEGIN IMMEDIATE")
                    initialize_repository_core_schema(connection)
                    _ensure_migration(
                        connection,
                        version=PROJECT_VISUAL_CONTRACT_VERSION,
                        checksum=PROJECT_VISUAL_CONTRACT_CHECKSUM,
                    )
                    _ensure_migration(
                        connection,
                        version=PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,
                        checksum=PROJECT_FULL_PAGE_CLEANING_LEDGER_CHECKSUM,
                    )
                    connection.execute(
                        "UPDATE project_metadata SET project_schema_version = ?",
                        (PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,),
                    )
                    connection.commit()

                if completion is ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED:
                    connection.execute("BEGIN IMMEDIATE")
                    initialize_full_page_cleaning_acceptance_schema(connection)
                    _require_project_schema_shape(connection)
                    _ensure_migration(
                        connection,
                        version=PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,
                        checksum=PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_CHECKSUM,
                    )
                    connection.commit()
        except sqlite3.DatabaseError:
            return ProjectOpenResult(status=ProjectOpenStatus.PROJECT_MIGRATION_FAILED, project_id=project_id, project_record=project_record)
        return self.open_project(project_id)

    def _load_project_record(self, project_id: str) -> ProjectRecord | None:
        with _connect(self.app_db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    project_id,
                    name,
                    workspace_project_path,
                    project_db_path,
                    default_source_language,
                    default_target_language
                FROM projects
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()

        if row is None:
            return None

        return ProjectRecord(
            project_id=row["project_id"],
            name=row["name"],
            workspace_path=Path(row["workspace_project_path"]),
            project_db_path=Path(row["project_db_path"]),
            source_language=row["default_source_language"],
            target_language=row["default_target_language"],
        )

    def _require_ready(self) -> None:
        status = self._app_status()
        if status is not ProjectOpenStatus.READY:
            raise AppStoreNotReadyError(f"AppStore is not ready: {status.value}.")

    def _app_status(self) -> ProjectOpenStatus:
        if not self.is_ready or not self.app_db_path.is_file():
            return ProjectOpenStatus.APP_MIGRATION_FAILED

        try:
            with _connect_existing(self.app_db_path) as connection:
                return _app_migration_status(connection)
        except sqlite3.DatabaseError:
            return ProjectOpenStatus.APP_MIGRATION_FAILED

    def _project_paths_are_valid(self, project_record: ProjectRecord) -> bool:
        expected_workspace = self.workspace_root / "projects" / project_record.project_id
        expected_project_db_path = expected_workspace / "project.db"

        return (
            _same_path(project_record.workspace_path, expected_workspace)
            and _same_path(project_record.project_db_path, expected_project_db_path)
            and _is_relative_to(project_record.workspace_path, self.workspace_root)
            and _is_relative_to(project_record.project_db_path, project_record.workspace_path)
        )


class ProjectRepositories:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self.identity = ProjectIdentityRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.content_state = ContentStateRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.result_versions = ResultVersionRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.glossary = GlossaryRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.workflow_execution = WorkflowExecutionRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.quality_issues = QualityIssueRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.artifact_metadata = ArtifactMetadataRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.visual_contract = VisualContractRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.full_page_cleaning_ledger = FullPageCleaningLedgerRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.full_page_cleaning_acceptance = FullPageCleaningAcceptanceRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.readiness = ReadinessQueryRepository(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.uow = ProjectUnitOfWork(
            project_db_path=project_db_path,
            project_id=project_id,
        )
        self.stage_evidence_writer = StageEvidenceWriter(
            project_db_path=project_db_path,
            project_id=project_id,
        )


class ProjectIdentityRepository:
    def __init__(self, *, project_db_path: Path, project_id: str) -> None:
        self._project_db_path = project_db_path
        self._project_id = project_id

    def get_metadata(self) -> ProjectMetadata:
        try:
            with _connect_existing(self._project_db_path) as connection:
                metadata = _load_project_metadata(connection)
        except sqlite3.DatabaseError as exc:
            raise ProjectStoreNotReadyError(
                "Project identity is no longer readable for repository access."
            ) from exc

        if metadata is None or metadata.project_id != self._project_id:
            raise ProjectStoreNotReadyError(
                "Project identity is no longer ready for repository access."
            )

        return metadata


def _initialize_app_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            workspace_project_path TEXT NOT NULL UNIQUE,
            project_db_path TEXT NOT NULL UNIQUE,
            default_source_language TEXT NOT NULL,
            default_target_language TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            trash_path TEXT
        )
        """
    )


def _initialize_project_database(
    *,
    project_db_path: Path,
    project_id: str,
    workspace_identity: str,
) -> None:
    with _connect(project_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS project_metadata (
                project_id TEXT PRIMARY KEY,
                project_schema_version TEXT NOT NULL,
                workspace_identity TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_opened_at TEXT
            )
            """
        )
        initialize_repository_core_schema(connection)
        _ensure_migration(
            connection,
            version=PROJECT_BASELINE_VERSION,
            checksum=PROJECT_BASELINE_CHECKSUM,
        )
        _ensure_migration(
            connection,
            version=PROJECT_VISUAL_CONTRACT_VERSION,
            checksum=PROJECT_VISUAL_CONTRACT_CHECKSUM,
        )
        _ensure_migration(
            connection,
            version=PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,
            checksum=PROJECT_FULL_PAGE_CLEANING_LEDGER_CHECKSUM,
        )
        _require_ready_migration(
            connection,
            version=PROJECT_BASELINE_VERSION,
            checksum=PROJECT_BASELINE_CHECKSUM,
            missing_status=ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
            error_cls=ProjectStoreNotReadyError,
        )

        now = _utc_now()
        connection.execute(
            """
            INSERT INTO project_metadata (
                project_id,
                project_schema_version,
                workspace_identity,
                created_at,
                last_opened_at
            )
            VALUES (?, ?, ?, ?, NULL)
            """,
            (project_id, PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION, workspace_identity, now),
        )
        connection.commit()

        connection.execute("BEGIN IMMEDIATE")
        initialize_full_page_cleaning_acceptance_schema(connection)
        _require_project_schema_shape(connection)
        _ensure_migration(
            connection,
            version=PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,
            checksum=PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_CHECKSUM,
        )


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _connect_existing(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise sqlite3.OperationalError(f"Database does not exist: {path}")

    connection = sqlite3.connect(_sqlite_readwrite_uri(path), uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _sqlite_readwrite_uri(path: Path) -> str:
    return f"file:{quote(str(path), safe='/')}?mode=rw"


def _ensure_migration(
    connection: sqlite3.Connection,
    *,
    version: str,
    checksum: str,
) -> None:
    existing = connection.execute(
        "SELECT checksum FROM schema_migrations WHERE version = ?",
        (version,),
    ).fetchone()

    if existing is not None:
        return

    connection.execute(
        """
        INSERT INTO schema_migrations (version, checksum, applied_at)
        VALUES (?, ?, ?)
        """,
        (version, checksum, _utc_now()),
    )


def _verify_migration(
    connection: sqlite3.Connection,
    *,
    version: str,
    checksum: str,
    missing_status: ProjectOpenStatus,
) -> ProjectOpenStatus:
    row = connection.execute(
        "SELECT checksum FROM schema_migrations WHERE version = ?",
        (version,),
    ).fetchone()

    if row is None:
        return missing_status
    if row["checksum"] != checksum:
        return ProjectOpenStatus.CHECKSUM_MISMATCH
    return ProjectOpenStatus.READY


def _require_ready_migration(
    connection: sqlite3.Connection,
    *,
    version: str,
    checksum: str,
    missing_status: ProjectOpenStatus,
    error_cls: type[RuntimeError],
) -> None:
    status = _verify_migration(
        connection,
        version=version,
        checksum=checksum,
        missing_status=missing_status,
    )
    if status is not ProjectOpenStatus.READY:
        raise error_cls(f"Migration {version} is not ready: {status.value}.")


def _app_migration_status(connection: sqlite3.Connection) -> ProjectOpenStatus:
    return _verify_migration(
        connection,
        version=APP_BASELINE_VERSION,
        checksum=APP_BASELINE_CHECKSUM,
        missing_status=ProjectOpenStatus.APP_MIGRATION_REQUIRED,
    )


def _project_migration_status(connection: sqlite3.Connection) -> ProjectOpenStatus:
    base_status = _verify_migration(
        connection,
        version=PROJECT_BASELINE_VERSION,
        checksum=PROJECT_BASELINE_CHECKSUM,
        missing_status=ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
    )
    if base_status is not ProjectOpenStatus.READY:
        return base_status
    visual_status = _verify_migration(
        connection,
        version=PROJECT_VISUAL_CONTRACT_VERSION,
        checksum=PROJECT_VISUAL_CONTRACT_CHECKSUM,
        missing_status=ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
    )
    if visual_status is not ProjectOpenStatus.READY:
        return visual_status
    ledger_status = _verify_migration(
        connection,
        version=PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,
        checksum=PROJECT_FULL_PAGE_CLEANING_LEDGER_CHECKSUM,
        missing_status=ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
    )
    if ledger_status is not ProjectOpenStatus.READY:
        return ledger_status
    completion_status = _verify_migration(
        connection,
        version=PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_VERSION,
        checksum=PROJECT_FULL_PAGE_CLEANING_ACCEPTANCE_CHECKSUM,
        missing_status=ProjectOpenStatus.PROJECT_MIGRATION_REQUIRED,
    )
    if completion_status is not ProjectOpenStatus.READY:
        return completion_status
    return _project_schema_shape_status(connection)


def _project_schema_shape_status(connection: sqlite3.Connection) -> ProjectOpenStatus:
    for object_type, name in PROJECT_FULL_PAGE_CLEANING_REQUIRED_SCHEMA_OBJECTS:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
            (object_type, name),
        ).fetchone()
        if row is None:
            return ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    for table, required_columns in PROJECT_FULL_PAGE_CLEANING_REQUIRED_TABLE_COLUMNS.items():
        actual_columns = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if not required_columns.issubset(actual_columns):
            return ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    for table, fragments in PROJECT_FULL_PAGE_CLEANING_REQUIRED_SQL_FRAGMENTS.items():
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        normalized_sql = "".join(row["sql"].lower().split()) if row and row["sql"] else ""
        if any(fragment not in normalized_sql for fragment in fragments):
            return ProjectOpenStatus.PROJECT_MIGRATION_FAILED
    return ProjectOpenStatus.READY


def _require_project_schema_shape(connection: sqlite3.Connection) -> None:
    if _project_schema_shape_status(connection) is not ProjectOpenStatus.READY:
        raise sqlite3.OperationalError("Full-page Cleaning v3 schema shape is invalid.")


def _project_metadata_version_status(version: str) -> ProjectOpenStatus:
    if version not in {
        PROJECT_BASELINE_VERSION,
        PROJECT_VISUAL_CONTRACT_VERSION,
        PROJECT_FULL_PAGE_CLEANING_LEDGER_VERSION,
    }:
        return ProjectOpenStatus.NEWER_INCOMPATIBLE_SCHEMA
    return ProjectOpenStatus.READY


def _load_migrations(connection: sqlite3.Connection) -> tuple[MigrationRecord, ...]:
    rows = connection.execute(
        """
        SELECT version, checksum, applied_at
        FROM schema_migrations
        ORDER BY applied_at, version
        """
    ).fetchall()

    return tuple(
        MigrationRecord(
            version=row["version"],
            checksum=row["checksum"],
            applied_at=row["applied_at"],
        )
        for row in rows
    )


def _load_project_metadata(connection: sqlite3.Connection) -> ProjectMetadata | None:
    row = connection.execute(
        """
        SELECT
            project_id,
            project_schema_version,
            workspace_identity,
            created_at,
            last_opened_at
        FROM project_metadata
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return None

    return ProjectMetadata(
        project_id=row["project_id"],
        project_schema_version=row["project_schema_version"],
        workspace_identity=row["workspace_identity"],
        created_at=row["created_at"],
        last_opened_at=row["last_opened_at"],
    )


def _workspace_identity(project_id: str, workspace_path: Path) -> str:
    material = f"{project_id}:{workspace_path}".encode("utf-8")
    return sha256(material).hexdigest()


def _same_path(left: Path, right: Path) -> bool:
    return left.resolve(strict=False) == right.resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
