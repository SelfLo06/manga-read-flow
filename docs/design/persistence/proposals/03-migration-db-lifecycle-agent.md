## 1. Scope

This proposal covers the minimal database lifecycle and migration strategy needed before MVP-0 FakeProvider single-Page backend work:

- `app.db` bootstrap and migration.
- Per-Project `project.db` bootstrap and migration.
- Project open identity verification.
- Independent app/project migration ledgers.
- Workspace and Project identity rules.
- Migration safety, resumability, backup/restore, and Project isolation.

It does not define SQL DDL, ORM models, migration files, API routes, frontend behavior, provider integrations, prompt templates, or a full production migration framework.

## 2. Role Bias

As the Migration and Database Lifecycle agent, I bias toward:

- explicit startup and Project-open gates before workflow execution;
- one global database lifecycle plus one isolated lifecycle per Project;
- short, restartable migrations over clever online migration machinery;
- backup/restore friendliness through project-relative artifact paths and self-identifying `project.db`;
- refusing ambiguous Project opens instead of guessing when identity or schema evidence conflicts.

## 3. Assumptions

- `docs/HLD.md` is the HLD source used for this proposal. `docs/HLD-v0.2.md` was not needed because the prompt allows either HLD path and `AGENTS.md` names `docs/HLD.md`.
- Older SRS/HLD examples that show direct file path fields or active flags are superseded by the final data-model documents: artifact metadata lives in `ProcessingArtifact`, and active selection uses owner pointers.
- `app.db` stores the Project registry, global non-secret settings, provider config metadata, processing profile templates, and its own migration ledger.
- Each `project.db` stores one Project's content, workflow state, artifacts metadata, quality issues, result versions, profile snapshots, export records, `ProjectMetadata`, and its own migration ledger.
- No cross-database foreign keys are required or expected.
- API keys and raw secrets are never stored in `project.db`, migration ledgers, logs, or debug artifacts.

## 4. Minimal Proposal

Initialize `app.db` at application startup before any Project is listed or opened.

- If `app.db` does not exist, create it in the configured workspace and apply the app baseline migration set.
- If it exists, verify the app migration ledger and apply pending compatible app migrations before exposing normal application use cases.
- If the ledger checksum for an already-applied migration does not match the expected migration manifest, block startup for repair instead of applying further migrations.
- `app.db` migration state is authoritative only for `app.db`; it does not mark any `project.db` migration as applied.

Initialize `project.db` during Project creation.

- Generate the Project identity before creating Project-owned storage.
- Create the Project workspace directory and initialize a new `project.db` under that Project directory.
- Apply the project baseline migration set to that `project.db`.
- Write `ProjectMetadata` with the Project identity, schema compatibility marker, workspace identity, and creation/open timestamps.
- Register the Project in `app.db` only after the `project.db` exists, has a project migration ledger, and contains matching `ProjectMetadata`.

Verify Project identity every time a Project is opened.

- Read the Project registry row from `app.db`.
- Resolve the stored project database path under the expected workspace/project root.
- Open `project.db` only long enough to read `ProjectMetadata` and its migration ledger.
- Require `ProjectMetadata.project_id` to match the `app.db` Project row.
- Require the Project path/workspace identity evidence to be compatible with the registry entry, allowing an explicit restore/relink path later but blocking silent mismatch.
- If identity verification fails, do not expose the Project for workflow, artifact cleanup, export, or migration.

Track migrations independently.

- `app.db` has its own `schema_migrations` ledger.
- Every `project.db` has its own `schema_migrations` ledger.
- A Project registry row may cache the last known project schema compatibility, but that cache is not the source of truth; the Project database ledger is.
- App migrations may update global registry/profile/provider structures. Project migrations may update only the opened Project database.
- Project migrations run per Project at Project-open time or at explicit Project-maintenance time, not as a single hidden operation over every Project.

Use the smallest MVP-0 migration strategy.

- Start with one baseline migration stream for `app.db` and one baseline migration stream for `project.db`.
- Before MVP-0, support creation and forward-only compatible upgrade of empty or already-MVP databases.
- Do not implement legacy imports, downgrades, cross-version semantic backfills, or large online migrations before real legacy data exists.
- Keep enum-like values as stable strings so later additions do not require rewriting historical attempts, decisions, issues, artifacts, or result rows.
- Require JSON payloads that may evolve, such as profile snapshots, to carry schema/version markers.

Support backup, restore, and isolation.

- A Project backup is the Project directory containing `project.db` plus project-relative artifact files.
- `app.db` backup preserves the global registry and templates, but Project-owned data remains restorable from its own Project directory.
- Restoring a Project into a new workspace should be possible by verifying `ProjectMetadata`, checking for Project identity collision, and registering or relinking the Project in `app.db`.
- Because artifact paths are project-relative, workspace moves do not require rewriting historical artifact metadata.
- Because migrations run per Project, a failed or blocked Project migration does not corrupt other Projects.

## 5. Repository / Transaction / Migration Implications

- Repository / DAO remains the only SQLite access boundary for lifecycle operations.
- Application startup may call a database lifecycle component through repository boundaries to initialize and migrate `app.db`.
- Project creation uses short, explicit steps: prepare workspace storage, initialize `project.db`, verify `ProjectMetadata`, then register the Project in `app.db`.
- No distributed transaction is required between filesystem, `app.db`, and `project.db`; instead, each step leaves recoverable evidence.
- A partially created Project directory without an `app.db` registry row is an unregistered orphan and must not appear in normal Project lists.
- An `app.db` Project row pointing to a missing or mismatched `project.db` is a blocked/open-repair condition, not a cue to create a replacement database with the same Project identity.
- Migration application should be one migration at a time with a ledger update committed only with that migration's effects.
- Provider Adapters, WorkflowLoopEngine, QualityCheckService, ArtifactService callers, API handlers, and UI code must not see migration tables, ORM sessions, or raw SQL details.

## 6. Software Engineering Principle Checks

- Single Responsibility: database lifecycle code owns initialization, open verification, and migration state; repositories own SQLite access; workflow services own workflow behavior.
- Information Hiding: callers learn only whether app/project storage is ready, blocked, missing, incompatible, or migrated; they do not inspect migration tables directly.
- High Cohesion / Low Coupling: app lifecycle concerns remain in `app.db`; Project lifecycle concerns remain in the selected `project.db`.
- Dependency Inversion: WorkflowLoopEngine, ArtifactService, and QualityCheckService depend on repository contracts after the Project store is opened, not concrete migration or ORM details.
- Testability: temporary SQLite tests can create `app.db`, create one Project, close/reopen, verify identity, and apply independent app/project migration ledgers.
- Recoverability: startup and Project-open gates happen before workflow recovery so stale task/attempt queries run only against a verified schema.
- Traceability: migration ledgers record which schema changes were applied without rewriting workflow audit rows.
- Scope Control: this avoids a generic persistence framework, distributed transactions, event sourcing, CQRS, or plugin persistence.

## 7. Recovery / Idempotency Impact

- Crash during `app.db` initialization leaves either no usable app database or an app database whose ledger explains the last committed migration.
- Crash during Project creation can leave an unregistered Project directory or an app row that fails Project-open verification; neither state is silently treated as a valid Project.
- Crash during a project migration is handled by rerunning pending migrations from that Project's own ledger after verification.
- Workflow crash recovery runs only after the Project database identity and schema are verified.
- Recovery queries must still use `ProcessingTask`, `WorkflowAttempt`, `WorkflowDecision`, active pointers, artifacts, `ToolRunLog`, and `QualityIssue`; database lifecycle must not encourage recovery from `Page.status` alone.
- Idempotent rerun depends on stable hashes, provider/model/config identity, active pointers, and artifact metadata; migrations must preserve those fields and avoid rewriting result text.
- Registered but unselected artifacts remain non-export-effective after restore or migration because active pointers, not timestamps, select current outputs.

## 8. FakeProvider Slice Impact

- MVP-0 FakeProvider work should begin only after both app and Project stores pass lifecycle readiness checks.
- The FakeProvider slice needs app initialization for Project registry and processing profile template lookup.
- It needs project initialization for the single-Page content/workflow/artifact/result tables and the project migration ledger.
- FakeProvider tests should cover create app store, create Project store, close/reopen, verify identity, run a no-op pending-migration check, then execute the single-Page workflow.
- FakeProvider mode/config evidence belongs in task/profile snapshot or sanitized attempt/tool metadata, not in migration state.
- No real provider, prompt, frontend, or export UI behavior is required to validate this lifecycle proposal.

## 9. HARNESS Scenario Coverage

| Scenario | Coverage |
| --- | --- |
| P01 Create Project and project database | Covered: final state has an `app.db` Project registry row, initialized `project.db`, matching `ProjectMetadata`, and no cross-db foreign keys. |
| M01 Initialize app.db | Covered: app startup creates/verifies `app.db` and records app migrations independently. |
| M02 Initialize project.db | Covered: Project creation/open creates/verifies `project.db`, records project migrations independently, and checks Project identity. |
| M03 Add enum value later | Covered: stable string values allow additive enum evolution without rewriting historical audit rows. |
| R01 Crash after OCR result committed | Supported indirectly: lifecycle verification precedes recovery; recovery still uses result/pointer/attempt evidence. |
| R02 Crash after provider temp file before artifact registration | Supported indirectly: temp/orphan handling remains ArtifactService/recovery work, not migration work. |
| R03 Crash after artifact registration before active pointer update | Supported indirectly: migration/open does not infer active artifacts by timestamp. |
| R04 Missing active artifact | Supported indirectly: Project-open verifies database identity; ArtifactService verifies file presence/hash after open. |
| I01/I02/I03 Idempotent rerun | Supported indirectly: migrations preserve cache keys, active pointers, artifact metadata, and stable audit rows. |

## 10. Rejected Alternatives

- Single global SQLite database for all Projects. Rejected because it weakens Project isolation, backup/restore, and corruption blast-radius control.
- One app-level migration ledger that records all Project migrations. Rejected because Projects may be offline, moved, restored, or opened independently.
- Migrating every Project automatically at application startup. Rejected for MVP because it turns startup into a hidden batch maintenance job and risks blocking unrelated Projects.
- Creating an `app.db` Project row and later silently replacing a missing/mismatched `project.db`. Rejected because it can destroy recovery evidence and violate Project identity.
- Deriving Project identity from filesystem path alone. Rejected because workspace moves and restore need stable Project metadata.
- Cross-database foreign keys. Rejected because SQLite cannot enforce the required app/project split cleanly and the design already uses explicit Project-open verification.
- Downgrade migrations before MVP-0. Rejected as unnecessary until there is a release/rollback policy and real user data compatibility burden.
- Full legacy backfill machinery before MVP-0. Rejected because no legacy production schema exists yet.

## 11. Risks

- Project creation is not a true distributed transaction across filesystem, `app.db`, and `project.db`; mitigation is ordered creation, verification, and recoverable orphan/block states.
- Workspace restore semantics can become ambiguous if the same Project identity appears in multiple paths; mitigation is to block silent relink and require an explicit restore decision later.
- Migration checksum mismatch can block startup or Project open; mitigation is clear repair guidance and no further mutation after mismatch detection.
- Long future migrations could make Project open slow; mitigation is to defer heavy backfills and run Project migrations per Project.
- App/profile/provider template changes could drift from old Project snapshots; mitigation is immutable `ProcessingProfileSnapshot` in `project.db`.
- File backup can omit artifacts even when `project.db` is intact; mitigation is project-relative artifact metadata plus post-restore ArtifactService missing/hash validation.

## 12. Open Questions

- Exact migration tool layout is deferred: one Alembic environment with separate app/project streams, two environments, or a lightweight custom runner.
- Exact locking policy for Project open and migration is deferred, including multi-process protection for the later desktop wrapper.
- Exact workspace identity format is deferred.
- Exact Project restore/relink user flow and collision policy are deferred.
- Exact compatibility policy for opening a Project created by a newer app version is deferred.
- Exact backup manifest format is deferred.
- Exact handling of partially initialized orphan Project directories is deferred beyond "do not expose as normal Projects."
- Exact migration test matrix is deferred, but MVP-0 should include temporary SQLite coverage for app init, project init, identity mismatch, and independent migration ledgers.
