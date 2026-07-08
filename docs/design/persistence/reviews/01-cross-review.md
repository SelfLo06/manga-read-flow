# Persistence Readiness Cross-Review

Review role: Phase 2 Cross-Review agent for Goal 3 Persistence Readiness Design.

Inputs read: `AGENTS.md`, `docs/SRS-v1.0.md`, `docs/HLD.md`, `docs/PROJECT-PLAN.md`, persistence `GOAL.md`, `HARNESS.md`, `PLAN.md`, data-model final documents, workflow-state final design, execution-contract final design, all five persistence proposal files, and the persistence preflight for context.

Overall review result: no blocking issue requires a limited proposal revision round. The proposals are implementation-ready enough for synthesis, but the final design must make several explicit synthesis decisions so the first FakeProvider persistence slice is not left to guess.

## 1. Summary of each proposal.

### 1.1 Repository Boundary and Module Responsibility Agent

Proposal 01 defines a narrow Repository / DAO boundary and groups persistence contracts by workflow need rather than table shape. It keeps SQLite access behind app-level and project-level Unit of Work contracts, forbids SQL/ORM/session leakage to WorkflowLoopEngine, StageExecutor, ArtifactService, QualityCheckService, API handlers, and Provider Adapters, and recommends repository groups for project catalog, app config, project identity, content state, result versions, glossary, workflow execution, quality issues, artifact metadata, and export evidence.

Strengths:

- Strongly preserves repository-only SQLite access.
- Correctly rejects result active flags and timestamp-derived active selection.
- Clearly separates ArtifactService file lifecycle from repository metadata persistence.
- Defines useful recovery and idempotency repository bundles without exposing query internals.

Implementation-readiness weakness:

- Leaves the StageExecutor / ToolRunLog writer split unresolved.
- Leaves QualityCheckService repository access unresolved.
- Mentions `ExportRepository` before the slice has decided whether it stops at readiness or performs real export.

### 1.2 Unit of Work and Transaction Boundary Agent

Proposal 02 defines the best transaction spine of the set: reserve attempt, call provider outside write transactions, persist tool outcome, register artifacts as official but unselected, run quality checks, then perform one semantic acceptance transaction. The acceptance transaction is the point where results, active pointers, issue lifecycle changes, workflow decisions, retry budget, task progress, and stage statuses become current.

Strengths:

- Correctly avoids long SQLite write transactions across provider calls.
- Treats artifact registration as evidence, not selection.
- Covers crash points between reservation, provider call, artifact registration, and acceptance.
- Names user edit transactions as atomic result-version plus pointer plus stale-propagation updates.

Implementation-readiness weakness:

- Does not choose the optimistic-concurrency guard required for acceptance.
- Does not fully define the import original-image transaction boundary.
- Leaves recovery decision recording for `abandoned_after_crash` open.

### 1.3 Migration and Database Lifecycle Agent

Proposal 03 defines independent app/project database lifecycle. `app.db` initializes at startup, each `project.db` initializes during Project creation, Project open verifies `ProjectMetadata`, and both database types maintain independent migration ledgers. It correctly blocks silent replacement of missing or mismatched project databases and keeps migration concerns outside workflow modules.

Strengths:

- Preserves Project isolation and no cross-database foreign keys.
- Makes Project identity verification an explicit open gate before recovery or workflow execution.
- Supports backup/restore by project-relative paths and self-identifying `project.db`.
- Keeps enum-like audit values as stable strings.

Implementation-readiness weakness:

- Defers migration runner shape, workspace identity format, lock policy, newer-app compatibility, and orphan cleanup behavior.
- Does not define minimal lifecycle status values returned to callers, such as ready, blocked, missing, incompatible, or repair-required.

### 1.4 Recovery and Idempotency Repository Agent

Proposal 04 defines recovery and reuse repository support. It requires stale task scans by status/heartbeat, short recovery claiming, running attempt reconciliation from durable evidence, page recovery bundles that include active pointers/results/artifacts/issues/logs/decisions, and full-stage reuse keys for OCR, translation, cleaned artifacts, and typeset artifacts.

Strengths:

- Explicitly rejects `Page.status` as recovery truth.
- Treats official unselected artifacts as evidence/reuse candidates only.
- Correctly separates refusal/failure evidence from successful cache hits.
- Gives concrete index categories tied to recovery and reuse scenarios.

Implementation-readiness weakness:

- Leaves heartbeat thresholds, ToolRunLog crash outcome vocabulary, and official-unselected artifact default recovery behavior open.
- Needs final synthesis to decide whether `WorkflowDecisionIssue` is immediate or deferred.

### 1.5 FakeProvider Slice Persistence Readiness Agent

Proposal 05 ranks the minimal table/entity subset for the first FakeProvider backend vertical slice. It requires real durable rows for Project, ProjectMetadata, Batch, Page, TextBlock, OCRResult, TranslationResult, GlossaryVersion, ProcessingProfileSnapshot, ProcessingTask, WorkflowAttempt, WorkflowDecision, ProcessingArtifact, ToolRunLog, and QualityIssue, while allowing skeletal or deferred behavior for glossary terms, decision issue relation, export records, provider configs, processing profiles, and global settings.

Strengths:

- Keeps the first slice real enough to validate persistence, recovery, idempotency, artifact metadata, and active pointers.
- Correctly avoids in-memory stand-ins for persistence-critical state.
- Defines useful temporary SQLite integration tests.
- Keeps actual export, full provider/profile UI/config, and P1/P2 features out of the first slice.

Implementation-readiness weakness:

- Needs final synthesis to choose whether MVP-0 stops at `ready_for_export` or creates an actual `ExportRecord`.
- Leaves import-as-workflow-stage versus ApplicationService import operation unresolved.
- Leaves mandatory fake evidence artifacts beyond original/cleaned/typeset unresolved.

## 2. Agreements.

The proposals agree on the core persistence shape:

- Use `app.db` for global Project registry, non-secret app config, provider/profile templates, and app migration ledger.
- Use one `project.db` per Project for content, result versions, workflow evidence, quality issues, artifact metadata, profile snapshots, export evidence if used, and project migration ledger.
- Do not use cross-database foreign keys or cross-database transactions for MVP-0.
- Repository / DAO is the only SQLite access entry.
- Provider Adapter must not access SQLite, register official artifacts, create QualityIssues, decide retry/fallback/skip/warning/block, or own cache decisions.
- ArtifactService owns official artifact path, promotion, hash, registration, retention, cleanup, trash, and missing-state transitions, but not workflow outcomes.
- QualityCheckService owns issue classification and root-stage attribution, but not workflow advancement.
- WorkflowLoopEngine owns workflow decisions and active selection acceptance.
- Active pointers are the P0 source of truth; do not use result-row active flags or latest timestamp selection.
- Image bytes and large payloads stay on the filesystem; SQLite stores metadata, hashes, paths, and provenance.
- Provider calls must happen outside SQLite write transactions.
- Registered artifacts are official evidence but unselected until acceptance updates active pointers.
- Recovery must use tasks, attempts, decisions, tool logs, active pointers, result hashes, artifact states, QualityIssues, and TextBlock stage states, not `Page.status` alone.
- Idempotent reuse is a workflow decision that must be auditable.
- FakeProvider must exercise the same persistence boundaries as real providers.
- No P1/P2 feature is required for MVP-0.

## 3. Conflicts.

No conflict is severe enough to require proposal revision, but the following must be resolved in final synthesis:

- HLD source emphasis: proposals mostly cite `docs/HLD.md`; preflight and this review also read `docs/HLD.md`. Final synthesis should use the promoted `docs/HLD.md` baseline where it reconciles active pointers, export gate, Provider refusal, ArtifactService, and recovery.
- Quality issue persistence: proposal 01 leaves QualityCheckService repository access open; execution-contract final chooses issue drafts with WorkflowLoopEngine persisting lifecycle changes in acceptance. Final should adopt the execution-contract choice for MVP-0.
- ToolRunLog ownership: proposals allow either StageExecutor direct evidence writes or returning evidence for WorkflowLoopEngine to persist. Final must choose a narrow evidence writer model.
- `WorkflowDecisionIssue`: data-model recommends the relation; proposals debate immediate implementation. Final should decide whether it is required for first refusal/warning tests or only after happy path.
- Export readiness versus actual export: workflow-state uses `export_check` for readiness, while data-model includes `ExportRecord`. Proposal 05 recommends readiness-only unless actual export is in the milestone. Final must keep these distinct.
- Import modeling: proposal 05 asks whether import is a workflow stage or ApplicationService operation. Final must decide for MVP-0.
- App-level provider/profile rows: proposal 05 allows bootstrapping snapshots without full app-level provider/profile tables. Data-model lists provider configs and processing profiles as P0. Final must choose minimal skeleton versus direct snapshot bootstrap.
- Migration tooling: proposal 03 intentionally defers runner layout. Final can keep the tool choice deferred, but must still define the lifecycle contract.

## 4. Missing repository boundaries.

The proposals are strong on top-level boundaries, but final synthesis should close these boundary gaps:

- Define a ProjectStore or ProjectPersistenceContext obtained only after project identity and migrations pass. Workflow modules should not receive repository contracts before this gate.
- Define whether StageExecutor can call a narrow `StageEvidenceWriter` for ToolRunLog and attempt evidence. If allowed, it must not expose generic repositories, sessions, active pointer operations, QualityIssue mutations, or WorkflowDecision writes.
- Keep QualityCheckService repository-free for MVP-0. It should return issue drafts, lifecycle suggestions, and classification evidence; WorkflowLoopEngine persists those with the decision.
- Artifact metadata mutation should be reachable only through ArtifactService. WorkflowLoopEngine and StageExecutor may read artifact evidence snapshots but should not update storage state directly.
- Export readiness should use a QualityIssue query contract. Actual export history should remain in ExportRepository only if the first slice includes export execution.
- ConfigService may read app-level ProviderConfig / ProcessingProfile templates and secret references, but no project workflow module should receive raw secrets or secret-bearing config.
- Recovery repair operations need a repository boundary separate from ordinary stage acceptance so repair cannot become hidden workflow decision logic.

## 5. Missing Unit of Work / transaction boundaries.

Proposal 02 gives the right sequence, but final synthesis should add these precise boundaries:

- Project creation boundary: app.db registration and project.db initialization are not atomic together. Final must define ordered states and cleanup/repair behavior for orphan project directories and registry rows pointing to missing/mismatched project.db files.
- Import boundary: registering original artifact metadata and setting `Page.original_artifact_id` must commit with Page import completion, so no Page is treated as imported without an official original artifact.
- Attempt reservation boundary: stage status and running attempt creation should use expected task/status checks so duplicate runners do not reserve the same stage.
- Tool evidence boundary: if a ToolRunLog is created before the provider call, final must define how a crash leaves it and how recovery closes it. If only outcome logs are persisted after return, final must state that crash-during-call evidence comes from the running attempt plus heartbeat.
- Artifact registration boundary: official artifact registration may commit separately, but selection must not happen there.
- Acceptance boundary: accepted result rows, active pointer updates, stage statuses, task progress, retry budget after, WorkflowDecision, and QualityIssue lifecycle changes must commit together.
- Optimistic-concurrency boundary: acceptance should guard expected active pointer ids, dependency hashes, and stage statuses. Updated-at alone is too vague for active pointer correctness.
- User edit boundary: user-created OCR/TranslationResult, active pointer update, downstream stale statuses, page stale flags, and issue staleness/supersession must be atomic.
- Recovery boundary: marking stale tasks/attempts interrupted/recovering/abandoned should be short transactions and should not scan files or call providers inside the write transaction.

## 6. Migration lifecycle gaps.

The migration proposal is sound but leaves implementation-facing gaps that synthesis should classify:

- The exact migration tool can remain deferred, but final must define two streams: app migrations and project migrations.
- The Project-open lifecycle must return explicit outcomes: ready, app migration required/failed, project migration required/failed, identity mismatch, database missing, newer incompatible schema, or repair required.
- Workspace identity format can remain deferred, but the final design must require some identity evidence in `ProjectMetadata` and app registry path validation.
- Locking can remain minimal for MVP-0, but final should require no workflow processing while project migrations are running.
- Checksum mismatch should block further mutation until repair; proposal 03 states this for app startup and final should apply it to project migrations too.
- Opening a project from a newer app version needs an explicit block/read-only/unsupported outcome, even if exact UX is deferred.
- Orphan Project directories and app rows with missing/mismatched project.db should not appear as normal Projects. Final should mark them repair-only or hidden from normal workflow.
- Stable strings for statuses/decisions/issues should be final; exact enum validation mechanism can remain deferred.

## 7. Recovery and idempotency gaps.

The recovery proposal is close to implementation-ready. Final synthesis should resolve or explicitly defer:

- Heartbeat stale threshold and recovery timeout may be constants, but final must state they live in ProcessingProfileSnapshot, task policy, or app config. They cannot be hidden magic values in recovery code.
- ToolRunLog crash status vocabulary should be compatible with WorkflowAttempt statuses; otherwise recovery will be forced to invent ad hoc mappings.
- Official unselected artifacts after crash should default to evidence/reuse candidates only. MVP-0 should not parse raw provider output into accepted results unless normal validation and acceptance replay is explicitly performed.
- Recovery should record a decision or repair evidence when marking attempts `abandoned_after_crash`; otherwise retry budget and user-facing history can become hard to explain.
- Cache reuse should distinguish current active fresh output, historical compatible result, official compatible artifact, and failure/refusal evidence. Only the first three can become reuse candidates.
- Locked translation handling should be explicit: reuse cannot replace `locked_translation_result_id` without user override.
- Missing active artifact flow should be: ArtifactService validates and marks missing; WorkflowLoopEngine decides rebuild, warning, pause, or block; repository persists the decision and state.
- Idempotency keys for task duplicate suppression should not be confused with stage reuse keys. Final should name both concepts separately.

## 8. FakeProvider slice readiness gaps.

Proposal 05 is usable, but final synthesis should sharpen the first slice:

- Decide whether MVP-0 stops at `ready_for_export`. Recommendation: yes. Actual single-page export and `ExportRecord` can be a follow-up unless explicitly included in the implementation milestone.
- Require real `app.db` and `project.db` temporary SQLite tests from the first slice, not in-memory stand-ins.
- Require an empty/current `GlossaryVersion` for translation provenance.
- Require a minimal `ProcessingProfileSnapshot`, even if bootstrapped from a hardcoded FakeProvider profile.
- Require original, cleaned, and typeset artifacts as official metadata. Mask, crop, raw OCR output, raw translation payload, and quality report artifacts can be optional test modes unless a failure scenario depends on them.
- Require at least one failure-mode test early: provider refusal or invalid/partial translation should persist ToolRunLog, WorkflowAttempt, QualityIssue, and WorkflowDecision.
- Require crash-after-OCR-acceptance and registered-but-unselected-artifact tests before claiming recovery/idempotency readiness.
- Keep `ExportRecord`, app-level `provider_configs`, app-level `processing_profiles`, and `workflow_decision_issues` as skeleton-or-follow-up unless the final design requires them for a specific MVP-0 scenario.

## 9. Software engineering principle violations.

No proposal contains a hard architecture violation, but several edges could become violations if synthesis is vague:

- StageExecutor write authority could violate Single Responsibility if it grows beyond ToolRunLog/attempt evidence. It must not accept results, update active pointers, create WorkflowDecisions, or own QualityIssue lifecycle.
- QualityCheckService repository access could violate Information Hiding and decision ownership if it mutates issues or state directly. For MVP-0 it should return drafts.
- ExportRepository could become scope creep if readiness is confused with actual export. Export readiness should be a QualityIssue gate and active artifact check.
- A generic Unit of Work framework would violate Scope Control. The final design should describe named operations and transaction scopes, not an enterprise persistence abstraction.
- Repository contracts that mirror every table would weaken high cohesion/low coupling. The final design should prefer use-case snapshots and acceptance commands.
- Migration lifecycle must remain separate from workflow decisions. Migration repair should not infer workflow success from rows or files.

## 10. Scope creep.

Scope creep to exclude from final synthesis:

- SQL DDL, ORM mappings, Alembic files, and concrete repository method signatures.
- FastAPI route design, frontend behavior, real Provider integration, and prompt templates.
- Full export implementation, ZIP manifests, forced/incomplete export, and export UI.
- Full provider capability catalog and editable ProcessingProfile UI.
- Backup/restore UX, collision resolution screens, or desktop multi-process locking beyond lifecycle requirements.
- P1/P2 entities such as GeometryRevision, ContextPack, TermCandidate, TaskSummaryIndex, full ArtifactRetentionPolicy, and multi-page context.
- Cross-project caches, event sourcing, CQRS, distributed transactions, plugin persistence, or generic repository frameworks.
- Full cleanup scheduler behavior and retention TTLs.

## 11. Recommended final decisions.

The synthesizer should make these decisions:

- Proceed to final synthesis without a limited proposal revision round.
- Use `docs/HLD.md` plus the data-model, workflow-state, and execution-contract final documents as the current architecture baseline.
- Define app and project Unit of Work boundaries, but keep them as named persistence operations rather than a generic framework.
- Require Project open to verify identity and migration readiness before any workflow repository is exposed.
- Adopt the six-step stage sequence: reserve attempt, provider call outside write transaction, persist tool outcome, register artifacts unselected, quality check, acceptance transaction.
- Keep QualityCheckService repository-free for MVP-0; WorkflowLoopEngine persists issue drafts/lifecycle changes in acceptance.
- Allow StageExecutor only a narrow evidence writer for ToolRunLog/attempt tool evidence, or require it to return evidence for WorkflowLoopEngine to persist. Choose one in the final design. Recommended: use a narrow StageEvidenceWriter so provider timing/outcome can be persisted without exposing generic repositories.
- Require acceptance optimistic guards using expected active pointer ids, relevant dependency hashes, and stage statuses.
- Implement minimal `workflow_decision_issues` when a WorkflowDecision links to persisted QualityIssues; the happy path can naturally create no rows.
- Stop MVP-0 at `ready_for_export`; defer actual ExportRecord/output artifact unless explicitly added to the implementation milestone.
- Treat import as an ApplicationService/import use case for MVP-0, not a WorkflowLoopEngine stage, while leaving the `import` stage vocabulary available for later task-based import.
- Require app/project migration ledgers and stable string values from the first temporary SQLite tests.
- Require minimal app-level `projects` and `schema_migrations`; allow app-level provider/profile tables to be skeletons if a project-local ProcessingProfileSnapshot is created deterministically.
- Define recovery default for official unselected artifacts: do not select by timestamp; reuse only through normal validation and acceptance.
- Keep all P1/P2 and full export/profile/provider details deferred.

## 12. ADR candidates.

Recommended ADR candidates for the persistence final phase:

- Repository and Unit of Work boundary for SQLite access.
- Acceptance transaction as the semantic commit point for active pointers and workflow advancement.
- Independent app.db and per-project project.db migration lifecycle.
- Recovery source of truth: committed evidence and active pointers, not Page.status.
- FakeProvider MVP-0 persistence subset and readiness-only scope.

Optional ADR candidates if final synthesis makes a durable trade-off:

- StageEvidenceWriter versus WorkflowLoopEngine-only tool evidence persistence.
- `WorkflowDecisionIssue` immediate implementation versus post-happy-path deferral.
- Readiness-only `export_check` before full ExportRecord implementation.

## 13. Blocking issues.

No blocking issue requires one limited proposal revision round.

The proposals collectively contain enough material for final synthesis. The unresolved points are synthesis decisions, not proposal defects. A blocker would exist only if the final design leaves any of these unanswered:

- who persists ToolRunLog/tool evidence;
- whether QualityCheckService mutates repository state;
- what writes are in the acceptance transaction;
- whether MVP-0 includes actual export or only readiness;
- how Project identity/migration gates are enforced before workflow;
- how recovery treats official unselected artifacts.

## 14. Non-blocking issues.

Non-blocking issues to carry forward:

- Exact repository method names and DTO shapes.
- Exact migration runner layout.
- Exact workspace identity string format.
- Exact Project restore/relink and collision UX.
- Exact heartbeat timeout values and crash retry ceilings.
- Exact enum validation mechanism.
- Exact cleanup policy for official unselected artifacts and successful payloads.
- Exact fake artifact set beyond original, cleaned, and typeset.
- Whether temporary SQLite tests use one connection per Unit of Work or a shared test connection.
- Whether app-level provider/profile rows are skeletal or deferred behind deterministic snapshot bootstrap for the first happy path.

## 15. Open questions that block synthesis.

These questions block the final design only if left unanswered in synthesis; they do not require proposal revision:

- Does MVP-0 stop at `ready_for_export` or create actual export artifacts and `ExportRecord` rows?
- Does StageExecutor persist ToolRunLog through a narrow evidence writer, or does WorkflowLoopEngine persist all tool evidence?
- Is QualityCheckService repository-free for MVP-0?
- Is import modeled as an ApplicationService operation or a WorkflowLoopEngine stage for MVP-0?
- Are app-level `provider_configs` and `processing_profiles` required in the first schema, or can deterministic ProcessingProfileSnapshots stand in until the next slice?
- What optimistic-concurrency guard is required for acceptance transactions?
- What default recovery action applies to official unselected artifacts found after a crash?
- Is `WorkflowDecisionIssue` mandatory for the first QualityIssue-bearing scenario?

Recommended answers are given in section 11, so the synthesizer can proceed without another proposal round.

## 16. Open questions that do not block synthesis.

These can remain deferred after final synthesis if the final documents mark them explicitly:

- Exact SQL DDL, ORM models, Alembic migration files, partial index syntax, and constraint names.
- Exact repository method names, DTO fields, and package layout.
- Exact heartbeat stale threshold, recovery timeout, and crash retry ceiling values.
- Exact migration tool topology and migration file naming convention.
- Exact workspace identity format and restore/relink UX.
- Exact backup manifest format.
- Exact cleanup TTLs and retention scheduler behavior.
- Exact export manifest schema and ZIP behavior.
- Exact provider capability/license metadata schema.
- Exact ProcessingProfile defaults for fast/balanced/strict.
- Exact API key storage mechanism and OS secret-store integration.
- Exact UI/API behavior for displaying blocked Projects, migrations, warnings, and recovery.
- Exact P1/P2 user edit UX beyond ensuring result versioning and stale propagation are not blocked.
