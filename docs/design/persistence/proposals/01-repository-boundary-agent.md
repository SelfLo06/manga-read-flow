## 1. Scope

This proposal covers the Repository / DAO boundary for Goal 3 persistence readiness.

It answers:

- which repository groups are needed for MVP-0;
- which modules may call which repository contracts;
- which modules must never depend on SQLite, SQL, ORM/session, cursor, connection, or row details;
- how the boundary preserves single responsibility, information hiding, dependency inversion, recovery, and idempotency;
- which repository complexity should be deferred.

Out of scope:

- SQL DDL, ORM model code, migration files, API route design, frontend behavior, real Provider integration, prompt templates, event sourcing, CQRS, distributed transactions, plugin persistence, and data-model redesign.

Source tension noted: older SRS/HLD examples mention direct image path fields and result-level active markers. The later data-model, workflow-state, and execution-contract final documents resolve this by using `ProcessingArtifact` metadata plus active owner pointers. This proposal follows the later final documents.

## 2. Role Bias

As the Repository Boundary and Module Responsibility Agent, I bias toward:

- narrow repository contracts grouped by application need, not one generic table gateway;
- Repository / DAO as the only SQLite access entry;
- domain/evidence DTOs crossing module boundaries instead of SQL rows or ORM objects;
- Unit of Work as a transaction boundary abstraction, not a leaked session handle;
- keeping WorkflowLoopEngine decisive while repositories stay persistence-only;
- keeping ArtifactService, QualityCheckService, StageExecutor, API handlers, and Provider Adapters out of persistence internals.

## 3. Assumptions

- `docs/HLD.md` is the HLD source for this workspace.
- `app.db` stores global registry/config/template data; each Project has its own `project.db`.
- No cross-database foreign keys are required.
- MVP-0 is the FakeProvider single-Page backend vertical slice: create Project, create/import one Batch/Page, run fake workflow, persist evidence, reach readiness or blocked/warning state.
- Active OCR, translation, cleaned image, and typeset image selection is by active pointer only.
- Provider Adapters never call repositories.
- QualityCheckService returns issue drafts/classifications for MVP-0; WorkflowLoopEngine persists issue lifecycle changes with decisions unless the final synthesis chooses a narrower direct issue writer.
- Exact method names, ORM mappings, and table constraints remain deferred to implementation design.

## 4. Minimal Proposal

### Repository boundary decision

All SQLite access must pass through Repository / DAO implementations behind repository contracts. Callers receive domain DTOs, command DTOs, evidence snapshots, and IDs. They must not receive ORM/session objects, query builders, cursors, SQL strings, transaction handles, lazy ORM relationships, or database row dictionaries.

Repository contracts are made available through either an `AppUnitOfWork` or `ProjectUnitOfWork` abstraction. The Unit of Work owns commit/rollback mechanics; repositories own persistence operations; application modules own business decisions.

### MVP-0 repository groups

| Repository group | DB | Minimal responsibility | Primary allowed callers |
| --- | --- | --- | --- |
| ProjectCatalogRepository | `app.db` | Project registry, project workspace path, project.db path, lifecycle metadata, last-opened metadata. | ApplicationService, project open/lifecycle service. |
| AppConfigRepository | `app.db` | ProviderConfig metadata, ProcessingProfile templates, non-secret global settings. Returns secret references only. | ConfigService, ApplicationService, WorkflowService snapshot creation. |
| ProjectIdentityRepository | `project.db` | ProjectMetadata verification, project identity mirror, schema/version metadata visible after migration. | Project open/lifecycle service, migration runner, ApplicationService after open. |
| ContentStateRepository | `project.db` | Batch, Page, TextBlock, ordering, stage statuses, active page artifact pointers, active TextBlock result pointers, stale propagation state. | ApplicationService, WorkflowService, WorkflowLoopEngine, StageExecutor read context, review/edit use cases. |
| ResultVersionRepository | `project.db` | OCRResult and TranslationResult immutable histories, version creation, parent links, reuse lookups, dependency hashes. | WorkflowLoopEngine acceptance, ApplicationService edit/review use cases, StageExecutor read context. |
| GlossaryRepository | `project.db` | GlossaryTerm and GlossaryVersion reads/writes, current version identity, initial empty glossary version. | ApplicationService, WorkflowLoopEngine, StageExecutor translation context builder. |
| WorkflowExecutionRepository | `project.db` | ProcessingTask, ProcessingProfileSnapshot, WorkflowAttempt, WorkflowDecision, WorkflowDecisionIssue, ToolRunLog, task heartbeat/control evidence. | WorkflowService, WorkflowLoopEngine, StageExecutor tool-evidence writer through a narrow contract, TaskRunner only through WorkflowService or task-control facade. |
| QualityIssueRepository | `project.db` | QualityIssue persistence, lifecycle changes, stale/supersede updates, open blocking issue queries, decision issue links. | WorkflowLoopEngine, ApplicationService review/resolve use cases, Export/export-check use case. QualityCheckService should return drafts in MVP-0. |
| ArtifactMetadataRepository | `project.db` | ProcessingArtifact metadata, storage state, retention metadata, provenance refs, missing/metadata-only state. | ArtifactService for mutation; WorkflowLoopEngine or recovery reads only through ArtifactService/evidence snapshots. |
| ExportRepository | `project.db` | Minimal ExportRecord or readiness/export precheck evidence, blocker/warning counts and snapshot refs when export is attempted. | ApplicationService/export use case, WorkflowLoopEngine `export_check` if readiness is persisted as workflow evidence. |

### Module dependency rules

| Module | Allowed repository dependency | Must not do |
| --- | --- | --- |
| API handlers | None directly; call ApplicationService. | No SQLite, no repository, no long workflow execution, no file lifecycle decisions. |
| ApplicationService | Use app/project repository contracts for user use cases and command orchestration. | No SQL/ORM/session access, no Provider calls, no direct official artifact writes. |
| WorkflowService | WorkflowExecutionRepository, ContentStateRepository, profile snapshot reads/writes through Unit of Work. | No Provider calls directly, no SQL/ORM/session access. |
| WorkflowLoopEngine | WorkflowExecution, ContentState, ResultVersion, QualityIssue, Glossary read contracts, and artifact evidence via ArtifactService/read snapshots. | No SQL/ORM/session access, no artifact path/hash ownership, no quality detection rules, no Provider calls. |
| StageExecutor | Stage input read contracts, ArtifactService, Provider Adapter, and narrow ToolRunLog/evidence writer. | No workflow decisions, no active pointer acceptance, no repository transaction ownership across Provider calls, no SQL/ORM/session access. |
| ArtifactService | ArtifactMetadataRepository plus project-relative path/workspace resolver. | No retry/fallback/skip/block decisions, no QualityIssue ownership, no Provider calls. |
| QualityCheckService | Prefer no repository dependency for MVP-0; return issue drafts and lifecycle suggestions. If needed later, only narrow QualityIssue read/dedupe contracts. | No workflow state advancement, no active pointer updates, no SQL/ORM/session access. |
| Provider Adapter | None. | No SQLite, no repository, no official artifact registration, no QualityIssue creation, no retry/fallback/skip/block decisions. |
| TaskRunner | WorkflowService or narrow task-control facade. | No direct stage/result/artifact SQL, no workflow policy decisions. |
| ConfigService | AppConfigRepository for non-secret settings and secret references. | No raw secret persistence in project.db, no workflow decisions. |
| Repository / DAO implementations | SQLite/ORM/session internals. | No business policy, no Provider calls, no file bytes as image BLOBs. |
| Migration runner | Migration ledger and schema update mechanics. | No workflow/business decisions. |

## 5. Repository / Transaction / Migration Implications

- Use separate app-level and project-level Unit of Work boundaries. Do not require a cross-database transaction for MVP-0.
- Project creation/open should be recoverable if app.db registration and project.db initialization are interrupted; exact sequence belongs to the Unit of Work / migration agent.
- Provider calls must happen outside write transactions. Repositories provide short write operations for attempt start, tool evidence, artifact metadata, and acceptance.
- Acceptance should be exposed as a cohesive project transaction boundary that can persist decision, issue lifecycle, result versions, active pointers, retry budget after, and stage statuses without leaking the session to WorkflowLoopEngine.
- Artifact registration may be its own short transaction, but official artifact metadata mutation remains behind ArtifactService plus ArtifactMetadataRepository.
- Repositories should assume migrations have already made the opened database compatible; migration ledger reads/writes belong to migration infrastructure, not normal workflow repositories.
- Repository contracts should validate project scope and owner consistency at the boundary, especially active pointer updates, artifact owner references, and target scope IDs.

## 6. Software Engineering Principle Checks

- Single Responsibility: repositories persist and query data only; they do not classify quality, choose retry/fallback, generate files, or call Providers.
- Information Hiding: callers work with domain/evidence contracts and do not know table layout, join strategy, SQL, ORM session lifetime, or migration internals.
- High Cohesion / Low Coupling: repository groups follow workflow needs: content state, result versions, workflow evidence, quality issues, artifact metadata, glossary, app registry/config.
- Dependency Inversion: WorkflowLoopEngine, ArtifactService, QualityCheckService, StageExecutor, ApplicationService, and API layer depend on contracts, not concrete SQLite/ORM classes.
- Interface Segregation: Provider Adapter has no persistence interface; ArtifactService receives only artifact metadata operations; QualityCheckService receives at most quality issue reads if future dedupe needs prove it.
- Recoverability: repositories expose recovery evidence from tasks, attempts, decisions, active pointers, result hashes, artifact states, tool logs, and issues; they do not make Page.status the recovery truth.
- Traceability: attempts, decisions, issues, artifacts, tool logs, active pointer changes, result versions, and export checks remain persisted as auditable evidence.
- Scope Control: no generic enterprise repository framework, event store, CQRS layer, plugin persistence layer, or distributed transaction layer is needed for MVP-0.

## 7. Recovery / Idempotency Impact

Repository contracts must support recovery without exposing SQL:

- find stale `ProcessingTask` records by status and heartbeat;
- find running/incomplete `WorkflowAttempt` records by task, stage, target, and status;
- load a recovery snapshot for a Page/TextBlock scope containing active pointers, result dependency hashes, stage statuses, artifact storage states, recent attempts, decisions, ToolRunLogs, and open issues;
- mark attempts `interrupted` or `abandoned_after_crash` through WorkflowExecutionRepository;
- repair aggregate Page/TextBlock status only after evidence reconciliation.

Repository contracts must support idempotency without giving cache ownership to Provider Adapters:

- ResultVersionRepository finds reusable OCRResult by TextBlock/input/config/provider/model/tool/geometry key.
- ResultVersionRepository finds reusable TranslationResult by source OCR/source text/context/glossary/provider/model/prompt/config key.
- ArtifactMetadataRepository and ArtifactService verify cleaned/typeset artifact provenance, hash, and storage state before reuse.
- WorkflowExecutionRepository records `reused_cached` attempts or `reuse_cached_result` decisions so reuse remains auditable.
- ContentStateRepository updates active pointers/statuses only through expected-state operations that prevent pointer/status drift.

## 8. FakeProvider Slice Impact

For the FakeProvider single-Page slice, the repository boundary should be sufficient to support:

- creating an app.db Project registry entry and a matching project.db ProjectMetadata row;
- importing one original image through ArtifactService and storing only artifact metadata in project.db;
- creating one Batch, one Page, and deterministic TextBlocks;
- creating fake OCRResult and TranslationResult versions without overwriting prior versions;
- registering fake cleaned/typeset artifacts through ArtifactService;
- recording fake ToolRunLog, WorkflowAttempt, WorkflowDecision, QualityIssue, and active pointer/status changes;
- blocking or warning readiness from QualityIssue state;
- rerunning the slice and proving reuse through repository lookups and persisted reuse decisions.

FakeProvider itself receives structured inputs and returns structured outputs/errors/refusals only. It must not call any repository, register official artifacts, or decide workflow outcomes.

## 9. HARNESS Scenario Coverage

| Scenario group | Proposal coverage |
| --- | --- |
| P01 Create Project and project database | ProjectCatalogRepository and ProjectIdentityRepository preserve app.db/project.db split and no cross-db FK requirement. Exact lifecycle sequence is deferred to migration/UoW proposal. |
| P02 Import one Page | ArtifactService plus ArtifactMetadataRepository owns official original artifact metadata; ContentStateRepository stores Page pointer; file bytes stay outside SQLite. |
| P03 Happy-path single Page workflow | ContentState, ResultVersion, WorkflowExecution, QualityIssue, ArtifactMetadata, Glossary, and Export repositories provide the required persistence groups. |
| P04 Acceptance transaction | Boundary requires a cohesive project transaction for result rows, active pointers, issues, decision, retry budget, and statuses; exact sequence deferred to transaction agent. |
| R01 Crash after OCR result committed | Recovery snapshot loads active OCR pointer, OCRResult, task/attempt state, and downstream statuses without rerunning OCR by default. |
| R02 Crash after provider temp file before artifact registration | Temp files are not official artifacts; ArtifactService and recovery decide registration/cleanup path without Provider DB access. |
| R03 Crash after artifact registration before active pointer update | Registered artifact remains official but unselected; active pointer is not derived by timestamp. |
| R04 Missing active artifact | ArtifactService validates storage state and uses ArtifactMetadataRepository to mark missing; WorkflowLoopEngine decides rebuild/warn/block. |
| I01/I02 Result rerun reuse | ResultVersionRepository owns OCR/translation reuse lookups; WorkflowExecutionRepository records reuse decisions. |
| I03 Cleaned/typeset artifact reuse | ArtifactMetadataRepository plus ArtifactService verify provenance, hash, and presence before reuse. |
| Q01 Provider refusal | ToolRunLog, WorkflowAttempt, QualityIssue, and WorkflowDecision persist refusal evidence; Provider Adapter remains DB-free. |
| Q02 Blocking issue prevents readiness/export | QualityIssueRepository provides open blocking issue queries by scope; ExportRepository records export/precheck evidence when used. |
| Q03 Cleaning skip warning | QualityIssueRepository and ContentStateRepository preserve warning/skipped state; WorkflowLoopEngine owns readiness decision. |
| S01/S02 User edits | ResultVersionRepository creates new versions; ContentStateRepository updates active pointers and stale statuses atomically with issue lifecycle updates. |
| M01/M02/M03 Migration | Repository boundary assumes separate ledgers and stable string values; detailed migration lifecycle is deferred to the migration agent. |
| Boundary failure checks | Explicitly forbids Provider DB access, API/repository bypass, SQL/ORM leakage, Page.status-only recovery, timestamp-derived active selection, and image BLOB storage. |

## 10. Rejected Alternatives

| Alternative | Reason rejected |
| --- | --- |
| One repository per table exposed to services | Encourages table-shaped business logic and leaks persistence structure into workflow modules. |
| A generic `Repository<T>` / query-builder API for all modules | Leaks storage concerns, weakens information hiding, and invites ad hoc queries from WorkflowLoopEngine or services. |
| Passing ORM sessions into WorkflowLoopEngine or StageExecutor | Violates dependency inversion and makes transaction safety implicit. |
| Provider Adapter writes database rows | Violates architecture constraints and makes refusals/retries/artifacts untraceable to workflow decisions. |
| ArtifactService decides retry/rebuild/block | Mixes file lifecycle with workflow policy. |
| QualityCheckService advances workflow state | Splits decision ownership and makes recovery harder to explain. |
| Active result by latest timestamp | Conflicts with active pointer design, locked translations, and manual selection. |
| Single global SQLite database for all Project data | Weakens project isolation and backup/restore boundaries. |
| Event sourcing, CQRS, distributed transactions, or plugin persistence | Too much machinery for MVP-0 and explicitly outside scope. |

## 11. Risks

- Repository contracts may become too broad if they mirror whole tables instead of use-case snapshots.
- Splitting ContentStateRepository and ResultVersionRepository can cause pointer/result drift unless acceptance uses one Unit of Work boundary.
- StageExecutor may accumulate write authority if tool evidence, artifact registration, and acceptance are not separated.
- QualityIssue dedupe may tempt QualityCheckService to query persistence directly; keep this read-only or return drafts for MVP-0.
- Artifact recovery may require coordination between filesystem inspection and metadata updates; keep file decisions in ArtifactService and workflow decisions in WorkflowLoopEngine.
- Separate app.db/project.db lifecycle can leave partial project creation states; migration/UoW design must make open/init recovery explicit.

## 12. Open Questions

- Should QualityCheckService remain entirely repository-free for MVP-0, or may it use a narrow QualityIssue read/dedupe contract?
- Should StageExecutor write ToolRunLog directly through a narrow evidence repository, or should it return evidence for WorkflowLoopEngine/WorkflowService to persist?
- Should `WorkflowDecisionIssue` be mandatory in the first FakeProvider slice, or can issue links be temporarily represented through decision/issue refs while preserving the final model?
- Should active pointer updates live in ContentStateRepository only, or should ResultVersionRepository expose combined create-and-select commands for OCR/translation edits?
- What exact repository method names and DTO shapes should implementation use once transaction boundaries are finalized?
