# Minimal Repository Contract v0.1

## 1. Purpose

This document defines the minimal repository boundary for MVP-0 persistence readiness. It is contract guidance, not concrete method names, DDL, ORM mappings, or package layout.

Repository / DAO is the only SQLite access entry. Callers must not depend on SQL strings, ORM sessions, query builders, cursors, lazy ORM relationships, or table-shaped row dictionaries.

## 2. Contract Style

Repositories expose:

- named use-case operations;
- domain/evidence snapshots;
- command DTOs;
- created/updated ids;
- conflict/blocked outcomes.

Repositories do not expose:

- generic query builders;
- `Repository<T>` table gateways;
- ORM session or connection handles;
- SQL fragments;
- active pointer writes outside expected-state operations;
- business decisions such as retry, fallback, skip, warning, block, or readiness.

## 3. Repository Groups

| Repository group | DB | Minimal responsibility |
| --- | --- | --- |
| ProjectCatalogRepository | app.db | Project registry, workspace/project.db path, lifecycle fields, last opened/processed metadata. |
| AppConfigRepository | app.db | Non-secret settings, provider/profile templates or skeletons, secret references only. |
| ProjectIdentityRepository | project.db | ProjectMetadata, schema compatibility, open verification evidence. |
| ContentStateRepository | project.db | Batch, Page, TextBlock, active pointers, stage statuses, stale flags, skip/manual state. |
| ResultVersionRepository | project.db | OCRResult and TranslationResult immutable versions, parent links, provenance, reuse lookups. |
| GlossaryRepository | project.db | GlossaryVersion and optional GlossaryTerm reads/writes; initial empty glossary version. |
| WorkflowExecutionRepository | project.db | ProcessingTask, ProcessingProfileSnapshot, WorkflowAttempt, WorkflowDecision, WorkflowDecisionIssue, heartbeat/control fields. |
| QualityIssueRepository | project.db | Persist issue drafts during acceptance, lifecycle updates, blocker/warning queries, stale/supersede/resolve operations. |
| ArtifactMetadataRepository | project.db | ProcessingArtifact metadata, storage state, retention/provenance fields. Mutation is reached through ArtifactService. |
| ReadinessQueryRepository | project.db | Export-readiness queries for active outputs, blocker/warning counts, freshness evidence. Actual ExportRepository is follow-up. |

## 4. Module Dependency Rules

| Module | Allowed persistence dependency | Forbidden |
| --- | --- | --- |
| API handlers | None directly; call ApplicationService. | SQL, repositories, provider calls, artifact lifecycle. |
| ApplicationService | Project catalog, project lifecycle, import/content/edit use-case repositories. | Provider calls, official artifact writes outside ArtifactService, workflow decisions. |
| Project open/lifecycle service | app/project migration and identity repositories. | Exposing project repositories before identity and migrations are ready. |
| WorkflowService | Workflow execution and content state contracts. | Provider calls and SQL/ORM/session access. |
| WorkflowLoopEngine | Content, result, workflow, issue, glossary, readiness contracts plus ArtifactService evidence. | SQL/ORM/session access, direct filesystem ownership, provider calls. |
| StageExecutor | Stage input read snapshots, ArtifactService, Provider Adapters, and `StageEvidenceWriter`. | Active pointer updates, QualityIssue lifecycle, WorkflowDecision writes, generic repository use. |
| StageEvidenceWriter | Narrow write boundary for ToolRunLog and attempt tool evidence. | Result creation, active pointer selection, issue lifecycle, decisions, retry/fallback/skip/block. |
| ArtifactService | ArtifactMetadataRepository and workspace resolver. | Workflow decisions, QualityIssue creation, Provider calls. |
| QualityCheckService | No repository for MVP-0. | SQLite access, issue persistence, active pointer/status updates, WorkflowDecision creation. |
| Provider Adapter | None. | SQLite, repositories, official artifact registration, QualityIssue creation, cache decisions, workflow decisions. |
| ConfigService | AppConfigRepository and external secret lookup by secret_ref. | Persisting raw secrets in project.db, logs, snapshots, or artifacts. |
| TaskRunner | WorkflowService or narrow task-control facade. | Direct result/artifact/issue SQL or policy decisions. |

## 5. Project Store Gate

Project-scoped repositories are available only through a verified Project persistence context.

Open sequence:

1. Load app Project registry row.
2. Resolve project.db path under the expected workspace/project root.
3. Verify project.db exists and can be opened.
4. Verify `project_metadata.project_id` matches app registry.
5. Verify app/project migration ledgers and compatibility.
6. Acquire any required project-open/migration lock.
7. Expose project repository contracts.

If identity, schema, checksum, or path validation fails, the Project is repair-only and workflow repositories are not exposed.

## 6. StageEvidenceWriter

StageExecutor may persist only tool evidence needed around provider execution:

- create or update ToolRunLog start/outcome;
- attach sanitized provider/tool status, error code, refusal flag, timing, usage estimates, and artifact ids;
- attach attempt-level provider metadata that is known before acceptance.

StageEvidenceWriter must not:

- create OCRResult or TranslationResult rows;
- update active pointers;
- mutate QualityIssue lifecycle;
- create WorkflowDecision;
- update retry budget;
- update Page/TextBlock completion statuses;
- expose a generic repository or Unit of Work.

Rationale:

- Tool timing/outcome evidence may be useful even if the process crashes before WorkflowLoopEngine acceptance.
- Keeping the writer narrow prevents StageExecutor from becoming a hidden WorkflowLoopEngine.

## 7. QualityCheckService Boundary

For MVP-0, QualityCheckService is repository-free.

It returns:

- issue drafts;
- lifecycle suggestions, such as stale, supersede, resolve, or keep open;
- discovered stage and root stage attribution;
- severity and blocking flag suggestions;
- message keys and suggested action keys;
- dependency hashes used to decide applicability.

WorkflowLoopEngine consumes this report and persists QualityIssues and lifecycle changes in the acceptance transaction.

## 8. Artifact Metadata Boundary

ArtifactService is the only official artifact lifecycle entry.

ArtifactService uses ArtifactMetadataRepository to:

- register official artifacts;
- update `storage_state`, such as `present`, `metadata_only_cleaned`, `moved_to_trash`, `missing`, or `deleted`;
- store path, hash, byte size, media type, provenance, retention, and safety flags.

WorkflowLoopEngine and StageExecutor may read artifact evidence snapshots, but they must not update artifact metadata directly.

## 9. Recovery Contract Requirements

Repositories must provide recovery snapshots that include:

- task status, heartbeat, current stage, profile snapshot id, last attempt/decision ids;
- running/incomplete attempts;
- latest decisions and decision-issue links;
- ToolRunLogs, including refusal evidence;
- active Page/TextBlock pointers;
- active OCR/translation result rows and dependency hashes;
- original/cleaned/typeset/mask artifact metadata and storage states;
- open blocking and warning QualityIssues;
- TextBlock stage statuses and Page stale flags.

The recovery snapshot is evidence. WorkflowLoopEngine decides repair, reuse, retry, fallback, warning, pause, or block.

## 10. Idempotency Contract Requirements

Repositories must support:

- task duplicate suppression by idempotency key when creating/running tasks;
- OCR reuse lookup by TextBlock/input/config/provider/model/tool/geometry/source-language key;
- translation reuse lookup by source OCR/source text/context/glossary/provider/model/prompt/config/target-language key;
- cleaned artifact reuse lookup by base image/mask/geometry/skip-set/provider/mode/config key;
- typeset artifact reuse lookup by cleaned artifact/active translations/geometry/layout/font/typesetter key;
- auditable reuse decisions and/or attempts.

Failed attempts and provider refusals may affect retry/fallback policy, but they are not successful cache hits.

## 11. Open Scope for Implementation

Deferred:

- concrete method names;
- DTO field shapes;
- ORM session lifetime mechanics;
- exact package layout;
- SQL constraints and indexes;
- exact read model shape for UI pages.

Not deferred:

- repository-only SQLite access;
- project-open gate before repository exposure;
- no provider repository access;
- narrow StageEvidenceWriter only;
- QualityCheckService repository-free for MVP-0;
- active pointer selection only through guarded acceptance.
