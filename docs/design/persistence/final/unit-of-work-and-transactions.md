# Unit of Work and Transactions v0.1

## 1. Purpose

This document defines the minimal Unit of Work and transaction rules for MVP-0 persistence readiness.

The Unit of Work is a repository-owned transaction boundary. It is not a generic framework exposed to business logic.

Hard rule:

```text
No SQLite write transaction may span an external provider call, long local tool call, or long file-producing operation.
```

## 2. Unit of Work Types

| Unit of Work | DB | Purpose |
| --- | --- | --- |
| App lifecycle UoW | app.db | Initialize/migrate app.db; create/update Project registry rows. |
| Project lifecycle UoW | project.db | Initialize/migrate project.db; write/verify ProjectMetadata. |
| Import UoW | project.db | Create Batch/Page import state and select original artifact pointer. |
| Attempt reservation UoW | project.db | Claim stage work and create/mark WorkflowAttempt running. |
| Tool evidence UoW | project.db | Persist sanitized ToolRunLog and narrow attempt evidence. |
| Artifact metadata UoW | project.db | Register/update ProcessingArtifact metadata through ArtifactService. |
| Acceptance UoW | project.db | Select accepted outputs, issues, decisions, retry budget, and statuses together. |
| User edit UoW | project.db | Create user result version, update active pointer, propagate stale state. |
| Recovery repair UoW | project.db | Mark stale tasks/attempts and persist recovery decisions/repairs. |

No cross-database Unit of Work is required for MVP-0.

## 3. Project Creation Sequence

Project creation touches filesystem, app.db, and project.db. It is not one distributed transaction.

Sequence:

1. Generate Project identity.
2. Create Project workspace directory.
3. Initialize project.db.
4. Apply baseline project migrations.
5. Write ProjectMetadata.
6. Verify ProjectMetadata.
7. Register or finalize Project row in app.db with project path and project.db path.

Failure handling:

- project directory without app registry row: unregistered orphan, hidden from normal Project list.
- app registry row pointing to missing/mismatched project.db: repair-only state, workflow blocked.
- migration checksum mismatch: block further mutation until repair.
- no silent replacement of missing project.db with a new database for the same Project identity.

## 4. Project Open Sequence

1. app.db is initialized and migrated.
2. Project registry row is loaded.
3. project.db path is resolved.
4. ProjectMetadata is verified.
5. project schema migrations are verified/applied if compatible.
6. Project readiness result is returned.
7. Only `ready` Projects expose project repositories.

No workflow recovery, artifact cleanup, export readiness, or StageExecutor work may run before this gate passes.

## 5. Import Transaction

MVP-0 import is an ApplicationService/import use case, not a WorkflowLoopEngine stage.

Sequence:

1. Validate file type, path boundary, and Project readiness.
2. ArtifactService writes/registers the original artifact.
3. Import UoW creates or updates Batch/Page import rows and sets `Page.original_artifact_id`.
4. Commit sets Page aggregate state to `uploaded` or equivalent import-complete state.

Invariant:

- A Page must not be treated as imported if it lacks an official original artifact pointer.
- Original image bytes stay on the filesystem and are never overwritten.

The canonical workflow vocabulary still includes `import` for future task-based import.

## 6. Stage Execution Sequence

Canonical sequence:

1. Reserve attempt.
2. Call provider/tool outside a write transaction.
3. Persist tool outcome.
4. Register official artifacts as unselected evidence.
5. Run quality check.
6. Accept or decide next action.

### 6.1 Reserve Attempt

Short write transaction:

- verify Project is open and task is runnable;
- verify target is not deleted;
- verify pause/cancel requests;
- verify locked translation rules when relevant;
- create or mark WorkflowAttempt `running`;
- set current stage or stage status `running` when useful;
- update heartbeat/current stage.

Use expected task status/current stage guards to avoid duplicate runner claims.

### 6.2 Provider Call

No SQLite write transaction.

Provider Adapter may:

- read supplied input refs;
- use an attempt temp root;
- return ProviderResult success, partial_success, failure, refusal, or invalid_output;
- return temp refs.

Provider Adapter must not:

- access SQLite;
- register official artifacts;
- create QualityIssues;
- decide retry/fallback/skip/warning/block.

### 6.3 Persist Tool Outcome

Short write transaction through `StageEvidenceWriter`:

- persist sanitized ToolRunLog outcome;
- record provider/tool/model identity;
- record standardized error/refusal flags;
- attach retained raw request/response artifact ids after registration, if available;
- update narrow attempt evidence fields.

If the process crashes during provider call before outcome persistence, recovery uses the running attempt and heartbeat evidence.

### 6.4 Register Artifacts

ArtifactService may use one or more short transactions to:

- promote temp output to official project-relative path;
- compute hash and metadata;
- persist ProcessingArtifact with `storage_state = present`;
- mark failed/debug/sensitive flags.

Registration does not update active pointers or stage completion.

### 6.5 Quality Check

No required write transaction.

QualityCheckService returns a report. It does not persist issues or advance state.

### 6.6 Acceptance

One short write transaction. See section 7.

## 7. Acceptance Transaction

Acceptance is the only boundary that makes output current or export-effective candidate state.

Atomic writes:

- WorkflowAttempt terminal status when appropriate;
- WorkflowDecision;
- WorkflowDecisionIssue rows when decision links QualityIssues;
- QualityIssue creation/update/stale/supersede/resolve operations;
- accepted OCRResult or TranslationResult rows;
- active pointer updates;
- Page active cleaned/typeset artifact pointer updates;
- TextBlock stage statuses;
- Page aggregate status and stale flags;
- retry budget after;
- task progress/current stage/terminal status when applicable.

Expected-state guards:

- task id, task status, current stage, and last known attempt where relevant;
- expected active OCR/translation pointer ids;
- expected Page active artifact ids;
- expected locked translation pointer;
- source OCR/result hashes;
- context/glossary hashes;
- geometry/mask/base image hashes;
- cleaned artifact hash;
- active translation ids/text hashes;
- layout/font/config hashes;
- expected stage statuses.

If a guard fails:

- rollback acceptance;
- reload the relevant evidence bundle;
- WorkflowLoopEngine decides reuse, retry, pause, or block.

## 8. Stage-Specific Acceptance

OCR acceptance commits:

- OCRResult row;
- `TextBlock.active_ocr_result_id`;
- `ocr_status = done` or review/block status;
- downstream translation, translation_check, and typesetting stale when needed;
- issue lifecycle, decision, retry budget, task progress.

Translation acceptance commits:

- TranslationResult rows for valid blocks;
- active translation pointers for accepted results;
- missing/invalid output issues;
- translation and translation_check statuses;
- downstream typesetting stale where needed;
- issue lifecycle, decision, retry budget, task progress.

Cleaning acceptance commits:

- selected cleaned artifact pointer or skipped cleaning state;
- cleaning status;
- warning/blocking issues;
- decision, retry budget, task progress.

Typesetting acceptance commits:

- selected typeset artifact pointer or preview/warning/block state;
- typesetting status;
- typeset overflow issues if any;
- decision, retry budget, task progress.

Export readiness acceptance commits:

- Page status `ready_for_export`, `ready_for_export_with_warnings`, or `blocked`;
- task terminal status `succeeded`, `succeeded_with_warnings`, or `blocked`;
- decision and issue links.

It does not create actual export output artifacts in MVP-0.

## 9. Provider Failure and Refusal

Failure/refusal sequence:

1. Attempt reservation commits.
2. Provider returns failure/refusal outside transaction.
3. ToolRunLog records sanitized outcome.
4. Failed/refusal evidence artifacts may be registered.
5. QualityCheckService classifies issue draft.
6. Acceptance commits refused/failed attempt outcome, QualityIssue, WorkflowDecision, decision-issue link, retry budget after, and task/stage status.

Provider refusal is not a crash. It is a first-class workflow path. The final decision may be `fallback_provider`, `pause_for_user`, `skip_target`, `mark_warning`, or `block`.

No same-provider prompt evasion or policy bypass data may be introduced.

## 10. Cache Reuse Transaction

Reuse is a workflow decision, not an implicit repository side effect.

Sequence:

1. Check current active output freshness.
2. If needed, find historical compatible result/artifact.
3. Validate artifact presence/hash through ArtifactService for image outputs.
4. Acceptance transaction records `reuse_cached_result` and/or `reused_cached`, reconciles active pointers/statuses, and advances workflow.

Reuse must not:

- create duplicate active result rows;
- replace locked translation without explicit user override;
- treat failed/refused attempts as cache hits.

## 11. User Edit Transactions

OCR edit commits:

- new OCRResult with `source_type = user_edit`;
- parent link to previous active OCR when available;
- `TextBlock.active_ocr_result_id`;
- `ocr_status = done`, `needs_review`, or `blocked`;
- `translation_status = stale`;
- `translation_check_status = stale`;
- `typesetting_status = stale`;
- `review_status = needs_review`;
- Page `translation_context_stale = true`;
- Page `has_stale_blocks = true`;
- downstream issue stale/supersede changes.

Translation edit commits:

- new TranslationResult with current source OCR id/hash;
- parent link to previous active translation when available;
- `TextBlock.active_translation_result_id`;
- `translation_status = done` or review/block status;
- `translation_check_status = stale`;
- `typesetting_status = stale`;
- `review_status = needs_review`;
- Page `has_stale_blocks = true`;
- old typeset output remains preview/history, not export-effective;
- relevant issue stale/supersede changes.

## 12. Recovery Transactions

Recovery uses short transactions:

- claim stale task with expected status/heartbeat;
- mark task `interrupted`, then `recovering`;
- mark running attempts `interrupted`, `refused`, `failed`, or `abandoned_after_crash` after evidence review;
- persist recovery decision or repair evidence;
- repair Page aggregate status from durable facts.

Recovery must not:

- hold write transactions while scanning files or temp directories;
- call providers in recovery transaction;
- parse raw provider output into accepted results for MVP-0 unless normal validation and acceptance replay is explicitly implemented;
- select official unselected artifacts by timestamp.

## 13. Crash Point Outcomes

| Crash point | Recovery outcome |
| --- | --- |
| Before attempt reservation commit | Previous durable state remains authoritative. |
| After reservation before provider call | Running attempt is interrupted or abandoned under crash policy. |
| During provider call | No DB write lock exists; running attempt and heartbeat explain recovery. |
| After temp file before artifact registration | Temp/orphan file is not official. |
| After ToolRunLog outcome before artifact registration | Tool evidence exists; output remains unselected. |
| After artifact registration before acceptance | Official artifact is unselected evidence/reuse candidate. |
| During acceptance | SQLite commits all acceptance writes or none. |
| After acceptance | Active pointers, issues, decision, retry budget, and statuses agree. |
| Missing active artifact later | ArtifactService marks missing; WorkflowLoopEngine decides rebuild/warn/pause/block. |

## 14. Deferred Transaction Details

Deferred:

- exact isolation mode and lock timeout;
- exact optimistic concurrency implementation details;
- exact savepoint usage;
- exact Unit of Work class names;
- exact retry of aborted acceptance;
- cleanup policy for official unselected artifacts.
