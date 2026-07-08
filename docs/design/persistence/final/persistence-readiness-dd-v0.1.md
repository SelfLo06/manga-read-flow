# Persistence Readiness Detailed Design v0.1

## 1. Design Goals

This design defines the minimal persistence readiness needed before implementing the FakeProvider single-Page backend vertical slice.

The goal is not to redesign the data model. The goal is to make the existing data-model, workflow-state, and execution-contract baselines implementable through repository contracts, Unit of Work boundaries, transaction rules, and database lifecycle rules.

Primary goals:

- Preserve `app.db + project.db` Project isolation.
- Keep Repository / DAO as the only SQLite access boundary.
- Make active pointer updates, result versions, attempts, decisions, issues, tool evidence, and artifact metadata recoverable and auditable.
- Keep provider calls outside SQLite write transactions.
- Make crash recovery and idempotent rerun queryable without relying on `Page.status`.
- Support temporary SQLite integration tests for the FakeProvider slice.
- Stop MVP-0 persistence readiness at `ready_for_export`; actual `ExportRecord` and output export are follow-up unless explicitly added later.

Non-goals:

- SQL DDL, ORM mappings, Alembic files, repository method signatures, API routes, frontend behavior, real provider integration, prompt templates, complete export design, or P1/P2 features.

## 2. Source Documents

Read and synthesized:

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/HLD-v0.2.md`
- `docs/PROJECT-PLAN.md`
- `docs/design/persistence/GOAL.md`
- `docs/design/persistence/HARNESS.md`
- `docs/design/persistence/PLAN.md`
- `docs/design/persistence/reviews/00-preflight.md`
- `docs/design/persistence/proposals/01-repository-boundary-agent.md`
- `docs/design/persistence/proposals/02-unit-of-work-transaction-agent.md`
- `docs/design/persistence/proposals/03-migration-db-lifecycle-agent.md`
- `docs/design/persistence/proposals/04-recovery-idempotency-agent.md`
- `docs/design/persistence/proposals/05-fakeprovider-slice-readiness-agent.md`
- `docs/design/persistence/reviews/01-cross-review.md`
- `docs/design/persistence/reviews/02-no-blocking-revision-needed.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/workflow-state/final/state-vocabulary.md`
- `docs/design/workflow-state/final/recovery-rules.md`
- `docs/design/workflow-state/final/stale-propagation-rules.md`
- `docs/design/workflow-state/final/decision-matrix.md`
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`

Baseline decision:

- Use `docs/HLD-v0.2.md` plus the data-model, workflow-state, and execution-contract final documents as the current baseline.
- `docs/HLD.md` remains the older HLD reference.
- The execution-contract final noted that `HLD-v0.2.md` was absent at its synthesis time. It is present now, and this persistence design follows `HLD-v0.2.md` where it reconciles active pointers, artifact ownership, export gate, provider refusal, and recovery.

## 3. Software Engineering Principle Application

| Principle | Persistence application |
| --- | --- |
| Single Responsibility | Repositories persist/query SQLite only. WorkflowLoopEngine decides. QualityCheckService classifies issues. ArtifactService owns official files. Provider Adapters call tools only. |
| Information Hiding | Callers receive domain/evidence DTOs and named persistence operations, not SQL, ORM sessions, cursors, row dictionaries, or table-shaped APIs. |
| High Cohesion / Low Coupling | Repository groups follow workflow needs: catalog, identity, content state, results, workflow evidence, quality, artifact metadata, glossary, readiness. |
| Dependency Inversion | WorkflowLoopEngine, ArtifactService, StageExecutor, ConfigService, and ApplicationService depend on repository contracts, not concrete SQLite or ORM details. |
| Interface Segregation | StageExecutor may use only a narrow `StageEvidenceWriter`; QualityCheckService is repository-free for MVP-0; Provider Adapters get no persistence interface. |
| Recoverability | Recovery queries use tasks, attempts, decisions, tool logs, active pointers, dependency hashes, artifacts, issues, and TextBlock statuses. `Page.status` is repairable summary only. |
| Traceability | Attempts, decisions, decision-issue links, issue lifecycle, tool logs, artifacts, active pointer changes, and result versions remain auditable. |
| Scope Control | No generic persistence framework, event sourcing, CQRS, distributed transactions, cross-project cache, or plugin persistence layer for MVP-0. |
| Testability | The first slice must run against temporary real SQLite `app.db` and `project.db` files plus temporary workspace artifacts. |

## 4. Key Decisions

1. `app.db` stores global Project registry, non-secret app settings, app-level provider/profile templates or skeletons, and app schema migrations.
2. Each Project has one `project.db` for Project-owned content, workflow, quality, result versions, artifact metadata, profile snapshots, and project schema migrations.
3. Project repositories are exposed only after Project identity and migration readiness are verified.
4. Import is an ApplicationService/import use case for MVP-0, not a WorkflowLoopEngine stage. The `import` stage remains canonical vocabulary for later task-based import.
5. MVP-0 stops at `ready_for_export`. Actual `ExportRecord`, export output artifact, ZIP, and manifest are follow-up unless a later implementation milestone explicitly adds them.
6. QualityCheckService is repository-free for MVP-0. It returns issue drafts, lifecycle suggestions, attribution, severity, and suggested actions. WorkflowLoopEngine persists them in acceptance.
7. StageExecutor may use only a narrow `StageEvidenceWriter` for ToolRunLog and attempt tool evidence. It must not receive generic repositories, active pointer writers, issue lifecycle writers, or decision writers.
8. Acceptance transaction is the semantic commit point. It must atomically persist accepted result rows or active artifact pointer changes, active pointers, issue lifecycle changes, `WorkflowDecision`, `WorkflowDecisionIssue` rows when issues are linked, retry budget after, task progress, and stage statuses.
9. Acceptance must guard expected active pointer ids, relevant dependency hashes, and stage statuses. Timestamp-only guards are insufficient.
10. Registered official artifacts that are not selected by active pointers are evidence/reuse candidates only. They are never selected by timestamp.
11. `workflow_decision_issues` is minimal required infrastructure when a persisted `WorkflowDecision` links persisted `QualityIssue` rows. The happy path may create no rows.
12. app-level `projects` and `schema_migrations` are immediate. app-level `provider_configs` and `processing_profiles` may be skeletal if a deterministic project-local `ProcessingProfileSnapshot` exists for FakeProvider.

## 5. app.db / project.db Boundary

`app.db` owns:

- `projects`
- `schema_migrations`
- optional/skeletal `provider_configs`
- optional/skeletal `processing_profiles`
- optional `global_settings`

`project.db` owns:

- `project_metadata`
- `schema_migrations`
- `batches`
- `pages`
- `text_blocks`
- `ocr_results`
- `translation_results`
- `glossary_versions`
- optional/skeletal `glossary_terms`
- `processing_profile_snapshots`
- `processing_tasks`
- `workflow_attempts`
- `workflow_decisions`
- `workflow_decision_issues`
- `quality_issues`
- `processing_artifacts`
- `tool_run_logs`
- optional/follow-up `export_records`

Rules:

- No cross-database foreign keys.
- No cross-database transaction is required for MVP-0.
- `project_id` remains on project-owned rows as an isolation guard.
- Project open verifies `app.db.projects.project_id` against `project.db.project_metadata.project_id`.
- Artifact paths are project-relative.
- API keys, tokens, and raw secrets are not stored in `project.db`, workflow logs, artifacts, or snapshots.

## 6. Minimal FakeProvider Persistence Scope

MVP-0 must prove:

```text
create project
-> initialize project.db
-> import one page
-> run deterministic FakeProvider workflow
-> persist evidence and active pointers
-> reach ready_for_export or a documented warning/block path
```

Required immediately:

- real temporary `app.db` and `project.db`;
- Project registry and ProjectMetadata identity;
- one Batch, one Page, one or more TextBlocks;
- original, cleaned, and typeset artifacts as official metadata with filesystem bytes outside SQLite;
- immutable OCRResult and TranslationResult rows;
- active OCR, translation, cleaned, and typeset pointers;
- empty/current GlossaryVersion for translation provenance;
- ProcessingProfileSnapshot;
- ProcessingTask, WorkflowAttempt, WorkflowDecision, ToolRunLog;
- QualityIssue support and open blocking issue query;
- `workflow_decision_issues` when decisions link persisted issues.

Skeleton or follow-up for the first slice:

- `provider_configs` and `processing_profiles`: skeletal app rows or deferred behind deterministic snapshot bootstrap;
- `glossary_terms`: can exist empty;
- `export_records`: follow-up unless actual export is explicitly in scope;
- mask/crop/raw OCR/raw translation/quality report artifacts: optional modes unless needed by a failure test.

## 7. Required Entity/Table Priority

| Priority | Entity/table | Reason |
| --- | --- | --- |
| Immediate app | `projects`, `schema_migrations` | Project registry and app lifecycle. |
| Immediate project identity | `project_metadata`, `schema_migrations` | Project open verification and independent migrations. |
| Immediate content | `batches`, `pages`, `text_blocks` | Ownership spine, stage statuses, active pointers. |
| Immediate results | `ocr_results`, `translation_results`, `glossary_versions` | Versioning, provenance, idempotent reuse. |
| Immediate workflow | `processing_profile_snapshots`, `processing_tasks`, `workflow_attempts`, `workflow_decisions`, `workflow_decision_issues` | Durable execution, decisions, retry/recovery evidence. |
| Immediate evidence | `processing_artifacts`, `tool_run_logs`, `quality_issues` | Artifact metadata, sanitized tool trace, warning/block/export gate source. |
| Skeleton | `provider_configs`, `processing_profiles`, `glossary_terms`, `global_settings` | Preserve future shape without requiring full UI/config/profile behavior. |
| Follow-up | `export_records`, export issue snapshots, manifest artifacts | Actual export/output design is after readiness. |
| Deferred P1/P2 | GeometryRevision, ContextPack, TermCandidate, TaskSummaryIndex, full ArtifactRetentionPolicy | Not required for FakeProvider MVP-0. |

## 8. Repository Groups and Module Dependency Rules

Detailed contracts are in `repository-contract-minimal.md`.

Repository groups:

- ProjectCatalogRepository
- AppConfigRepository
- ProjectIdentityRepository
- ContentStateRepository
- ResultVersionRepository
- GlossaryRepository
- WorkflowExecutionRepository
- QualityIssueRepository
- ArtifactMetadataRepository
- ReadinessQueryRepository

Dependency rules:

- API handlers call ApplicationService, not repositories.
- Provider Adapters receive no repositories.
- QualityCheckService receives no repositories in MVP-0.
- ArtifactService may mutate `ProcessingArtifact` metadata only through ArtifactMetadataRepository.
- WorkflowLoopEngine uses repository contracts and ArtifactService evidence, not SQL or ORM sessions.
- StageExecutor uses Provider Adapters, ArtifactService, read-only stage context, and narrow `StageEvidenceWriter` only.
- ConfigService may read app-level non-secret config and secret references; raw secrets must not enter Project persistence.

## 9. Unit of Work Boundary

Detailed sequences are in `unit-of-work-and-transactions.md`.

Use named Unit of Work operations, not a generic framework exposed to business logic:

- app database lifecycle Unit of Work;
- project database lifecycle Unit of Work;
- import Unit of Work;
- stage attempt reservation Unit of Work;
- tool evidence Unit of Work;
- artifact metadata Unit of Work through ArtifactService;
- workflow acceptance Unit of Work;
- user edit Unit of Work;
- recovery repair Unit of Work.

No Unit of Work may hold a write transaction during a provider call, long file-producing operation, temp directory scan, or external model/tool invocation.

## 10. Transaction Sequences

Canonical stage execution sequence:

1. Reserve attempt in a short transaction.
2. Call Provider Adapter outside any SQLite write transaction.
3. Persist sanitized tool outcome through `StageEvidenceWriter`.
4. Register official artifacts through ArtifactService. These artifacts are official but unselected.
5. Run QualityCheckService. It returns drafts and suggestions, not database writes.
6. Run acceptance transaction. Only this step selects active results/artifacts and advances workflow state.

Import sequence:

1. ApplicationService validates user-supplied local image and target Project.
2. ArtifactService stores/registers original artifact metadata.
3. Import transaction creates/updates Batch/Page and sets `Page.original_artifact_id`.
4. Page is not treated as imported unless original artifact metadata and pointer commit together.

Recovery sequence:

1. Project open verifies identity and migrations.
2. Find stale running tasks by status/heartbeat.
3. Claim recovery with expected status/heartbeat checks.
4. Load task/page recovery bundle.
5. ArtifactService validates missing/hash state when needed.
6. WorkflowLoopEngine decides reuse, retry, pause, warning, or block.
7. Persist repair decision and state in short transactions.

## 11. Acceptance Transaction

Acceptance is the semantic commit point for current state.

It must commit together:

- accepted OCRResult or TranslationResult rows, when created;
- `TextBlock.active_ocr_result_id` or `TextBlock.active_translation_result_id`;
- `Page.active_cleaned_artifact_id` or `Page.active_typeset_artifact_id`, when accepting image artifacts;
- TextBlock stage statuses and Page aggregate status changes;
- downstream stale propagation when accepting user edits or upstream-changing results;
- QualityIssue creation/lifecycle updates from QualityCheck issue drafts;
- WorkflowDecision;
- WorkflowDecisionIssue rows for linked persisted issues;
- retry budget after and task progress/current stage;
- expected-state guard results.

Expected-state guards:

- expected active pointer ids for affected TextBlocks/Page;
- expected dependency hashes, such as source OCR hash, context hash, glossary hash, geometry hash, mask hash, cleaned artifact hash, translation text hashes, layout config hash;
- expected stage statuses, such as `running`, `pending`, `stale`, or `needs_review`;
- expected task status/current stage;
- expected locked translation pointer when relevant.

If a guard fails, acceptance aborts, reloads evidence, and WorkflowLoopEngine decides again.

## 12. Recovery Query Requirements

Recovery repositories must support:

- find stale `ProcessingTask` rows in running-like states by Project, status, and heartbeat;
- claim stale task recovery with expected status/heartbeat guard;
- load running/incomplete attempts for task/stage/target;
- load latest decisions, tool logs, issues, artifacts, active pointers, result rows, stage statuses, and profile snapshot;
- mark attempts `interrupted`, `refused`, `failed`, or `abandoned_after_crash` after WorkflowLoopEngine reconciliation;
- query open blocking and warning issues by Page/Batch/TextBlock scope;
- persist recovery decisions or repair evidence when attempts are abandoned or state is repaired.

Recovery must not:

- derive success from `Page.status`;
- select latest result or artifact by timestamp;
- turn temp/orphan files into official artifacts without ArtifactService and normal validation;
- make official unselected artifacts export-effective without acceptance.

## 13. Idempotency Query Requirements

Idempotent rerun must distinguish:

- task duplicate suppression key: request-level idempotency key for creating/running tasks;
- stage reuse key: evidence-level key for OCR, translation, cleaned, and typeset outputs.

Required reuse lookups:

- OCR: TextBlock, geometry/input hash, OCR config hash, provider, model, tool version, source language.
- Translation: source OCR result id, source text hash, context hash, glossary version or terms hash, provider, model, prompt template version, generation config hash, target language.
- Cleaning: base image hash, mask hash or mask set hash, geometry hashes, skip set, cleaning provider/mode/tool version, config hash.
- Typesetting: active cleaned artifact id/hash, active TranslationResult ids and text hashes in reading order, geometry hashes, font/layout config hash, typesetter version, target language/direction policy.

Reuse must record `reused_cached` attempt and/or `reuse_cached_result` decision. Reuse cannot replace locked translation without explicit user override.

## 14. Minimal Migration Strategy

Detailed lifecycle is in `migration-strategy-minimal.md`.

Required:

- independent `schema_migrations` in app.db and every project.db;
- app startup migrates/verifies app.db before Project listing/open;
- Project creation initializes project.db, applies baseline project migrations, writes ProjectMetadata, then registers or finalizes Project in app.db;
- Project open verifies identity and migration readiness before repositories are exposed;
- checksum mismatch, identity mismatch, missing project.db, incompatible newer schema, or failed migration blocks workflow mutation;
- stable string values for stages, statuses, decisions, issues, artifact states, and error codes.

Deferred:

- exact migration tool topology;
- restore/relink UX;
- backup manifest;
- downgrade strategy;
- legacy data backfills;
- multi-process desktop locking beyond "no workflow while migrating".

## 15. Minimal Correctness Constraints and Indexes

This section is design guidance, not SQL DDL.

Correctness constraints:

- unique Project identity in app.db;
- unique active Project workspace path in app.db;
- one ProjectMetadata identity per project.db;
- unique active Page order within Batch;
- unique active TextBlock reading order within Page when assigned;
- OCRResult and TranslationResult version numbers unique per TextBlock;
- active OCR/translation pointers must reference results for the same TextBlock;
- Page active artifact pointers must reference artifacts in the same Project/Page scope;
- workflow attempts unique by task/stage/target/attempt number;
- decision-issue links unique by decision/issue/relation;
- artifact relative paths unique while storage state is `present` or `moved_to_trash`;
- stable strings are additive; historical audit rows are not rewritten to rename old values.

Minimal index categories:

- Project listing and open: project status/path/id.
- Task recovery: project, task status, heartbeat.
- Attempt recovery: task/stage/status and target/stage/status.
- TextBlock recovery: page plus each stage status.
- Result histories and reuse keys for OCR and translation.
- Artifact lookup by owner/type, page/type, file hash/type, retention/storage state.
- QualityIssue blocker/warning queries by project, batch, page, text block, blocking flag, and status.
- ToolRunLog by attempt and project/stage/status/time.
- WorkflowDecision by task/time, attempt, target/stage.

## 16. Testability Plan with Temporary SQLite

The first implementation should test with temporary workspace directories and real SQLite files:

- initialize app.db and verify app migration ledger;
- create Project, initialize project.db, verify ProjectMetadata identity;
- import one Page and assert original image bytes are filesystem-only;
- run happy path to `ready_for_export`;
- verify active OCR, translation, cleaned, and typeset pointers;
- verify attempts, decisions, tool logs, artifacts, issues, and profile snapshot;
- rerun unchanged workflow and verify auditable reuse;
- simulate crash after OCR acceptance and resume from translation;
- simulate crash after artifact registration before acceptance and verify artifact is not selected;
- simulate provider refusal or invalid translation and verify ToolRunLog, WorkflowAttempt, QualityIssue, WorkflowDecision, and decision-issue links;
- mark an active artifact missing and verify ArtifactService marks metadata while WorkflowLoopEngine owns rebuild/warn/block decision;
- verify open blocking QualityIssue prevents pure readiness;
- verify app and project migrations are tracked independently.

## 17. Scenario Replay Against HARNESS

| Scenario | Result | Summary |
| --- | --- | --- |
| P01 Create Project and project database | PASS | app.db registers Project; project.db owns Project data; ProjectMetadata identity is verified; no cross-db FK required. |
| P02 Import one Page | PASS | original artifact metadata is registered; Page points to original artifact id; bytes remain on filesystem; original is never overwritten. |
| P03 Happy-path single Page workflow | PASS | required content, result, artifact, attempt, decision, tool, and issue data can persist; active pointers select accepted outputs; Page can reach `ready_for_export`. |
| P04 Acceptance transaction | PASS | result rows, active pointers, issue lifecycle, decision, retry budget, task progress, and stage statuses commit together; provider call is outside write transaction. |
| R01 Crash after OCR result committed | PASS | stale task/running attempt can be found; active OCR pointer/result are reusable; recovery resumes at translation. |
| R02 Crash after provider temp file before artifact registration | PASS | temp/orphan file is not official; recovery marks attempt abandoned/interrupted or retries under policy. |
| R03 Crash after artifact registration before active pointer update | PASS | official artifact remains unselected evidence/reuse candidate only; no timestamp promotion. |
| R04 Missing active artifact | PASS | artifact metadata can be loaded; ArtifactService marks `missing`; WorkflowLoopEngine decides rebuild, warning, pause, or block. |
| I01 Rerun unchanged OCR | PASS | OCR reuse query uses full key; reuse is auditable and avoids duplicate provider call. |
| I02 Rerun unchanged translation | PASS | translation reuse query uses source OCR/source/context/glossary/provider/model/prompt/config; locks are respected. |
| I03 Rerun unchanged cleaned/typeset artifacts | PASS | artifact provenance, presence, and hash validation are required before reuse. |
| Q01 Provider refusal persistence | PASS | refusal persists as ToolRunLog, refused attempt, QualityIssue, WorkflowDecision, and decision-issue link when applicable; no bypass data. |
| Q02 Blocking issue prevents readiness/export | PASS | open blocking issue query by scope blocks normal readiness/export; warning remains profile-controlled. |
| Q03 Cleaning skip warning state | PASS | skip stage/status and warning issue persist; pure `ready_for_export` is not allowed with unresolved skip/warning. |
| S01 OCR edit | PASS | new OCRResult plus active pointer, downstream stale statuses, page stale flags, and issue lifecycle changes are atomic. |
| S02 Translation edit | PASS | new TranslationResult plus active pointer, translation_check/typesetting stale, and old typeset non-effectiveness are atomic. |
| M01 Initialize app.db | PASS | app migration ledger is immediate and independent. |
| M02 Initialize project.db | PASS | project migration ledger and ProjectMetadata identity are immediate and independent. |
| M03 Add enum value later | PASS | stable string values are additive and do not require rewriting historical audit rows. |
| Boundary failure checks | PASS | final design forbids provider DB access, artifact workflow decisions, QualityCheck state advancement, SQL leakage, Page.status-only recovery, timestamp active selection, image BLOBs, and P1/P2 requirements. |

## 18. Rejected Alternatives

| Alternative | Reason rejected |
| --- | --- |
| Single global SQLite database | Weakens Project isolation, backup/restore, corruption blast radius, and delete boundary. |
| Cross-database transaction for app/project writes | Unneeded for MVP-0 and brittle with filesystem operations. Ordered recoverable lifecycle is enough. |
| Long write transaction around provider call | Causes SQLite lock and crash recovery problems. |
| Provider Adapter writes database rows or artifact metadata | Violates provider boundary and hides workflow decisions. |
| Artifact registration selects active pointers | Bypasses quality checks and acceptance. |
| QualityCheckService persists issue lifecycle or workflow state | Splits ownership; acceptance must keep decisions/issues/statuses consistent. |
| Generic repository framework or `Repository<T>` | Leaks table shape and invites ad hoc persistence from workflow modules. |
| Page.status as recovery source of truth | Cannot explain active pointer drift, missing artifacts, abandoned attempts, stale state, or partial acceptance. |
| Latest timestamp selects current result/artifact | Conflicts with active pointers, locked translations, manual edits, and official unselected artifacts. |
| Full export implementation before readiness | Scope creep; workflow-state already distinguishes `export_check` readiness from export records. |
| In-memory fake persistence for FakeProvider | Would not validate recovery, migration, idempotency, or repository boundaries. |

## 19. Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Active pointer/status drift | Acceptance transaction with expected active pointer ids, dependency hashes, and stage status guards. |
| Artifact DB/filesystem drift | ArtifactService hash validation and `storage_state` updates; WorkflowLoopEngine owns rebuild/warn/block. |
| Official unselected artifact confusion | Unselected artifacts are evidence/reuse candidates only; never timestamp-selected. |
| Repository contracts become table-shaped | Use use-case snapshots and named operations; no generic query API to workflow modules. |
| StageExecutor write authority expands | Limit to `StageEvidenceWriter`; no active pointer, issue lifecycle, decision, or generic repository writes. |
| QualityCheck persistence ownership drift | Repository-free issue drafts for MVP-0; WorkflowLoopEngine persists in acceptance. |
| Migration/open ambiguity | Project open returns explicit readiness or blocked states before repositories are exposed. |
| False idempotent reuse | Require full dependency keys and artifact validation before reuse. |
| Under-tested recovery | Include crash-after-OCR and registered-but-unselected artifact tests in temporary SQLite suite. |
| Skeleton app config becomes permanent weak design | Mark provider/profile skeletons as MVP-0 only and require follow-up design before real providers. |

## 20. ADR List

- `docs/design/persistence/adr/0001-repository-unit-of-work-boundary.md`
- `docs/design/persistence/adr/0002-acceptance-transaction-semantic-commit.md`
- `docs/design/persistence/adr/0003-independent-app-project-migrations.md`
- `docs/design/persistence/adr/0004-recovery-from-committed-evidence.md`
- `docs/design/persistence/adr/0005-fakeprovider-mvp0-readiness-scope.md`

## 21. Open Questions and Deferred Decisions

See `open-questions.md`.

None block the FakeProvider single-Page persistence readiness design. Deferred areas include exact DDL/ORM/migration files, method names, DTO shapes, migration tool topology, heartbeat values, restore/relink UX, export implementation, full provider/profile config, cleanup TTLs, and P1/P2 features.
