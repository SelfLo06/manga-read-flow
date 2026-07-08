# FakeProvider Persistence Readiness v0.1

## 1. Purpose

This document defines the minimum persistence subset for the first FakeProvider single-Page backend vertical slice.

The slice proves persistence boundaries, recovery evidence, idempotent reuse, and readiness. It does not implement real providers, API routes, frontend UI, prompt templates, or actual export output.

## 2. MVP-0 Scope Decision

MVP-0 stops at:

```text
ready_for_export
```

Actual `ExportRecord`, output export image, ZIP output, manifest artifact, and export UI are follow-up unless explicitly added by a later implementation prompt.

The workflow-state `export_check` readiness stage remains in scope. It queries active output freshness and open blocking QualityIssues.

## 3. Immediate Tables

| DB | Table/entity | Required behavior |
| --- | --- | --- |
| app.db | `projects` | Project identity, name, workspace path, project.db path, defaults, lifecycle. |
| app.db | `schema_migrations` | App migration ledger. |
| project.db | `project_metadata` | Project identity and schema readiness marker. |
| project.db | `schema_migrations` | Project migration ledger. |
| project.db | `batches` | One Batch ownership scope. |
| project.db | `pages` | One Page, original/cleaned/typeset active artifact pointers, aggregate readiness. |
| project.db | `text_blocks` | Fake detection output, geometry, reading order, stage statuses, active result pointers. |
| project.db | `ocr_results` | Immutable fake OCR versions. |
| project.db | `translation_results` | Immutable fake translation versions tied to active OCR and glossary version. |
| project.db | `glossary_versions` | Initial empty/current glossary version. |
| project.db | `processing_profile_snapshots` | Deterministic FakeProvider policy snapshot. |
| project.db | `processing_tasks` | Durable workflow command, heartbeat, task status. |
| project.db | `workflow_attempts` | Attempt evidence for each stage. |
| project.db | `workflow_decisions` | WorkflowLoopEngine rationale. |
| project.db | `workflow_decision_issues` | Required when decisions link persisted issues; happy path may create no rows. |
| project.db | `processing_artifacts` | Official artifact metadata for original, cleaned, typeset, and optional evidence artifacts. |
| project.db | `tool_run_logs` | Sanitized fake provider/tool invocation trace. |
| project.db | `quality_issues` | Warning/block/refusal/readiness gate source. |

## 4. Skeleton or Deferred Tables

Skeleton acceptable:

- `provider_configs`: optional app-level skeleton if FakeProvider identity is carried by snapshot/attempt/log metadata.
- `processing_profiles`: optional app-level skeleton if deterministic snapshot bootstrap exists.
- `global_settings`: optional unless workspace settings are implemented.
- `glossary_terms`: may exist empty.

Follow-up:

- `export_records`;
- export issue snapshots;
- manifest artifacts;
- cost/token rollups;
- full provider capability catalog;
- full ProcessingProfile UI/config.

Deferred P1/P2:

- GeometryRevision;
- ContextPack;
- TermCandidate;
- TaskSummaryIndex;
- full ArtifactRetentionPolicy table;
- multi-page context.

## 5. Mandatory Artifacts

Required official artifacts:

- original image;
- cleaned image;
- typeset image.

Optional fake evidence artifacts:

- mask;
- crop;
- raw OCR output;
- raw translation request/response;
- detection visualization;
- quality report;
- failed/refusal payload artifact.

Optional artifacts may be required by specific failure tests, but not by the first happy path.

All artifact bytes remain on the filesystem. SQLite stores metadata only.

## 6. FakeProvider Stage Expectations

Detection:

- creates deterministic TextBlocks;
- may create optional mask artifacts;
- acceptance updates detection status and reading order.

OCR:

- uses deterministic provider/model/tool/config identity;
- creates OCRResult rows through acceptance;
- selects active OCR pointers atomically.

Translation:

- uses active OCR ids/hashes and current GlossaryVersion;
- creates TranslationResult rows through acceptance;
- selects active translation pointers atomically;
- partial/invalid output creates issues and decisions.

Cleaning:

- registers cleaned artifact through ArtifactService;
- selects active cleaned pointer only in acceptance;
- cleaning skip creates warning-bearing state.

Typesetting:

- registers typeset artifact through ArtifactService;
- selects active typeset pointer only in acceptance;
- overflow can create warning or block issue.

Export readiness:

- verifies active typeset artifact is present/hash-valid;
- checks freshness and dependency hashes;
- queries open blocking QualityIssues;
- sets `ready_for_export`, `ready_for_export_with_warnings`, or `blocked`;
- does not create export output in MVP-0.

## 7. Minimal ProcessingProfileSnapshot

The first slice needs a deterministic project-local snapshot with:

- snapshot schema version;
- source profile identity or `fakeprovider_default`;
- settings hash;
- per-stage retry budgets;
- crash recovery retry budget or ceiling;
- provider/fallback/refusal policy references;
- warning readiness/export policy;
- auto-skip allowlist;
- retention/debug hints.

The snapshot must not contain secrets.

## 8. Required Failure Modes

The first implementation should not stop with only the happy path. It should include at least one early QualityIssue-bearing mode.

Required before claiming persistence readiness:

- provider refusal or invalid/partial translation creates ToolRunLog, WorkflowAttempt, QualityIssue, WorkflowDecision, and WorkflowDecisionIssue link;
- crash after OCR acceptance resumes from translation without rerunning OCR;
- crash after artifact registration before acceptance leaves official unselected artifact that is not export-effective;
- missing active artifact is marked `missing` by ArtifactService, then WorkflowLoopEngine decides outcome;
- open blocking QualityIssue blocks pure readiness.

## 9. Temporary SQLite Integration Tests

Use real temporary SQLite files and temporary workspace files.

Test set:

1. app.db init and migration ledger.
2. project.db init, ProjectMetadata, and migration ledger.
3. Project open identity verification.
4. Import one Page and verify original bytes are not in SQLite.
5. Happy path reaches `ready_for_export`.
6. Active OCR, translation, cleaned, and typeset pointers are set.
7. Attempts, decisions, tool logs, artifacts, issues, and profile snapshot are persisted.
8. Rerun unchanged OCR/translation/cleaning/typesetting and verify auditable reuse.
9. Crash after OCR acceptance and resume at translation.
10. Registered-but-unselected artifact is not selected by timestamp.
11. Provider refusal or invalid translation persists issue/decision evidence.
12. Missing active artifact is marked missing and does not become ready.
13. Open blocking QualityIssue prevents pure readiness.
14. WorkflowDecisionIssue rows exist when a decision links persisted QualityIssues.

## 10. Overengineering to Avoid

Do not implement for MVP-0:

- full export output and ZIP;
- full provider config UI or secret storage integration;
- full ProcessingProfile editor;
- real OCR/LLM/cleaning/typesetting providers;
- generic repository framework;
- cross-project cache;
- event sourcing or CQRS;
- distributed transaction manager;
- P1/P2 geometry and context features;
- cleanup scheduler and TTL policy beyond minimal artifact states.

## 11. Readiness Exit Criteria

The persistence slice is ready for FakeProvider implementation when:

- the required tables/entities can be initialized in temporary app.db/project.db;
- Project open verifies identity and migrations before repositories are exposed;
- import can register an original artifact and Page pointer;
- the stage transaction sequence is implementable;
- acceptance can guard expected active pointers, dependency hashes, and stage statuses;
- recovery and reuse queries are supported;
- QualityCheckService can remain repository-free;
- StageExecutor uses only `StageEvidenceWriter`;
- no P1/P2 feature is needed to reach readiness.
