# Data Model Harness Validation

## Phase

Phase 5 validation of the synthesized data model design.

Validated files:

- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/erd.mmd`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/data-model/final/open-questions.md`
- `docs/design/data-model/adr/0001-app-db-project-db-split.md`
- `docs/design/data-model/adr/0002-active-result-pointers.md`
- `docs/design/data-model/adr/0003-artifact-metadata-lifecycle.md`
- `docs/design/data-model/adr/0004-page-translation-textblock-results.md`
- `docs/design/data-model/adr/0005-workflow-recovery-source-of-truth.md`
- `docs/design/data-model/adr/0006-processing-profile-snapshots.md`
- `docs/design/data-model/adr/0007-quality-issue-export-gate.md`
- `docs/design/data-model/adr/0008-provider-refusal-handling.md`
- `docs/design/data-model/adr/0009-soft-delete-trash.md`
- `docs/design/data-model/adr/0010-glossary-version-reproducibility.md`

Harness result: PASS.

The final design is acceptable for MVP backend skeleton design. No hard invariant failure was found. Remaining questions are non-blocking detailed-design or implementation questions already captured in `final/open-questions.md` and section 27 of the final design.

## Hard Invariant Checklist

| Invariant | Result | Evidence |
| --- | --- | --- |
| No image BLOBs in SQLite. | PASS | Final design stores image and large payload bytes on the filesystem only; SQLite stores `ProcessingArtifact` metadata. |
| Original image is immutable. | PASS | `Page.original_artifact_id` points to a `permanent_original` artifact; original images are never overwritten. |
| Project data is isolated. | PASS | `app.db` only registers Projects; each Project has its own `project.db` and project-relative artifacts. |
| Page belongs to Batch. | PASS | `Page.batch_id` and Batch/Page relationship are explicit in the final design, schema outline, and ERD. |
| Batch belongs to Project. | PASS | `Batch.project_id` is explicit and project.db is scoped to one Project. |
| TextBlock belongs to Page. | PASS | `TextBlock.page_id` is explicit and detection creates TextBlocks under a Page. |
| Detection creates TextBlock. | PASS | Detection stage creates `TextBlock` rows with geometry, reading order, and stage status. |
| OCRResult is versioned. | PASS | `OCRResult.version_number`, parent pointer, immutable text/hash, and unique per-TextBlock version are specified. |
| TranslationResult is versioned. | PASS | `TranslationResult.version_number`, parent pointer, immutable text/hash, and unique per-TextBlock version are specified. |
| User edits create new versions. | PASS | OCR and translation edit paths create new result rows and update active pointers. |
| Active OCR and active Translation are explicit. | PASS | `TextBlock.active_ocr_result_id` and `TextBlock.active_translation_result_id` are the P0 source of truth. |
| TranslationResult records glossary_version. | PASS | `glossary_version_id`, `glossary_version_number`, and `glossary_terms_hash` are required. |
| WorkflowAttempt metadata is always persisted. | PASS | WorkflowAttempt metadata persists even when payload artifacts are cleaned. |
| WorkflowDecision is persisted. | PASS | Workflow decisions are append-only and linked to attempts/issues. |
| QualityIssue supports discovered_stage and root_stage. | PASS | Required QualityIssue fields include both attribution fields. |
| ProcessingArtifact records file path, hash, type, and ownership. | PASS | `relative_path`, `file_hash`, `artifact_type`, `owner_type`, and `owner_id` are required field groups. |
| Failed attempt artifacts are persisted by default. | PASS | `failed_attempt_payload` retention class keeps failed raw payloads by default. |
| Successful raw payload retention is configurable. | PASS | `successful_payload` retention class and ProcessingProfile retention policy make cleanup configurable. |
| Provider adapters do not own persistence. | PASS | Provider Adapters cannot access DB, register artifacts, or create retry/fallback/quality decisions. |
| API keys are not stored in project.db. | PASS | ProviderConfig stores secret references only; snapshots/logs/artifacts must not copy secrets. |
| Export checks unresolved blocking issues. | PASS | Normal export queries open blocking QualityIssues in scope and creates blocked ExportRecords without output artifacts. |

## Required Scenario Replay

| Scenario | Result | Validation |
| --- | --- | --- |
| S1 Happy path: Project -> Batch -> Page -> TextBlocks -> OCR -> Page-level Translation -> Cleaning -> Typesetting -> Export. | PASS | Relationship spine, result rows, artifacts, workflow records, and export gate are all represented. |
| S2 Restart after OCR. | PASS | Active OCR results/artifacts remain; interrupted running attempts/tasks are reconciled and translation can continue without rerunning OCR. |
| S3 OCR edit. | PASS | New OCRResult becomes active; prior OCR remains; translation, checks, page context, and typesetting become stale. |
| S4 Translation edit. | PASS | New TranslationResult becomes active; prior translation remains; typesetting becomes stale. |
| S5 Provider refusal. | PASS | ToolRunLog, WorkflowAttempt, QualityIssue, WorkflowDecision, and optional evidence artifact are persisted; profile controls fallback/manual/block. |
| S6 Complex cleaning skipped. | PASS | TextBlock cleaning status can be skipped; warning QualityIssue and WorkflowDecision allow ready-for-export-with-warnings when profile permits. |
| S7 Typeset overflow. | PASS | Preview artifact is retained; `typeset_overflow` QualityIssue and WorkflowDecision decide warning, retry, pause, or block. |
| S8 Glossary changed. | PASS | Glossary edit creates a new GlossaryVersion; old TranslationResults keep previous glossary version/hash. |
| S9 Failed raw payload. | PASS | Invalid LLM JSON is retained as a failed attempt artifact by default with attempt/log/issue/decision metadata. |
| S10 Project soft delete. | PASS | Project soft delete moves or marks workspace/files for trash; restore validates artifacts; permanent deletion requires confirmation. |

## Additional Goal Scenario Replay

| Scenario | Result | Validation |
| --- | --- | --- |
| Successful LLM raw payload is cleaned under default policy but attempt metadata remains. | PASS | Successful payload artifacts may become `metadata_only_cleaned`; attempt/log/result metadata and hashes remain. |
| Two Projects contain the same page filename but remain isolated. | PASS | Separate `project.db`, project ids, and project-relative artifact paths prevent filename collision across Projects. |
| Export attempted with unresolved blocking issue is rejected. | PASS | ExportRecord is blocked/rejected, blocker counts/hash/snapshot are recorded, and no normal output artifact is created. |
| Export attempted with warning only follows ProcessingProfile policy. | PASS | Warning export uses immutable ProcessingProfileSnapshot policy and records warning issue snapshot/hash. |
| User reruns a TextBlock with unchanged input/config. | PASS | Stage idempotency keys and cache lookup rules allow reuse and avoid duplicate provider calls. |

## Evaluation Scores

| Criterion | Score | Notes |
| --- | ---: | --- |
| Recovery support | 3 | Durable tasks, attempts, decisions, active pointers, artifact states, and crash vocabulary support restart recovery. |
| Idempotency support | 3 | Stage-specific key inputs and reuse records are explicit. |
| Traceability | 3 | Results, attempts, tool logs, decisions, issues, exports, and artifacts are linked. |
| Simplicity | 2 | Model is intentionally rich; generic target references and workflow audit tables add complexity but are justified by recovery/export requirements. |
| Migration readiness | 2 | Migration strategy and schema ledgers exist; exact SQL constraints and migration scripts are deferred. |
| ORM friendliness | 2 | Entity boundaries are clear; polymorphic targets and no cross-db FKs will need careful repository validation. |
| Avoidance of over-design | 2 | P1/P2 candidates are separated from P0, but P0 still includes comprehensive audit and quality relations. |
| Artifact lifecycle clarity | 3 | Artifact states, retention classes, safety flags, ownership, and cleanup guards are explicit. |
| QualityIssue expressiveness | 3 | Scope, attribution, severity, blocking flag, status, provenance, and export semantics are covered. |
| Project isolation | 3 | app.db/project.db split and project-relative paths isolate Projects. |
| Future extensibility | 3 | ProcessingProfileSnapshot, stable strings, schema versions, and P1/P2 boundaries support extension without rewriting history. |

## Missing Fields

No blocking missing field was found.

Non-blocking details to settle during schema/implementation design:

- Exact enum values and whether they are represented by lookup tables or application constants.
- Exact ID format and public/internal id conventions.
- Exact retention TTLs and cleanup eligibility timestamps for successful payloads, debug artifacts, rebuildable crops, and replaced previews.
- Exact `ProcessingArtifact.relative_path` semantics after `metadata_only_cleaned` or `deleted` states: keep historical path, allow null, or store last-known path plus cleanup timestamp.
- Exact export issue snapshot representation: normalized `ExportIssueSnapshot`, structured artifact, or both.
- Whether warning-only export requires per-export user acknowledgement in addition to ProcessingProfileSnapshot policy.

## Ambiguous Ownership

No blocking ambiguous ownership was found.

Ownership boundaries are consistent with the HLD:

- WorkflowLoopEngine owns retry, fallback, skip, warning, block, and recovery decisions.
- QualityCheckService owns issue detection and discovered/root-stage attribution.
- ArtifactService owns official artifact paths, hashes, registration, retention, cleanup, trash, and restore checks.
- Repository/DAO owns SQLite access.
- Provider Adapters own provider calls only and do not persist database state or official artifact lifecycle records.

Non-blocking clarification: if a reduced first implementation spike omits `WorkflowDecisionIssue`, it must still keep WorkflowDecision and QualityIssue histories queryable without making ad hoc issue-id lists the long-term source of truth. The final design recommends the normalized relation.

## Duplicated Source-of-Truth Risks

No duplicated source-of-truth blocker was found.

- Active OCR/translation selection uses TextBlock pointers only; result-row active flags are rejected.
- Active page outputs use Page artifact pointers; artifact metadata remains in ProcessingArtifact.
- Workflow decisions are not inferred only from logs; WorkflowDecision is persisted.
- Export gate state is recomputed from open blocking QualityIssues and recorded in ExportRecord snapshots.

Residual risk: active pointer/status drift is possible in implementation if updates are not transactional. The final design mitigates this with atomic update guidance and recovery reconciliation.

## Recovery Gaps

No blocking recovery gap was found.

Covered recovery evidence:

- ProcessingTask status and heartbeat.
- WorkflowAttempt status, inputs, config/context/profile hashes, and attempt numbers.
- WorkflowDecision history.
- Active pointers and stale flags.
- ProcessingArtifact storage states and hashes.
- QualityIssue status and attribution.
- ToolRunLog sanitized tool/provider traces.

Non-blocking implementation detail: exact abandoned-task timeout, lock behavior, and recovery scan algorithm are deferred to WorkflowLoopEngine and repository design.

## Idempotency Gaps

No blocking idempotency gap was found.

Covered idempotency evidence:

- Stage-specific input/config/context/profile hashes.
- Result cache indexes for OCR and translation.
- Reuse represented as WorkflowAttempt `reused_cached` or WorkflowDecision `reuse_cached_result`.
- Failed/refused attempts are not successful cache hits but still count toward retry/fallback/block decisions.

Non-blocking implementation detail: exact hash canonicalization for page context, glossary terms, prompts, generation config, and export issue snapshots must be defined before code.

## Artifact Lifecycle Gaps

No blocking artifact lifecycle gap was found.

Covered artifact lifecycle evidence:

- File bytes remain outside SQLite.
- ProcessingArtifact records path, hash, type, ownership, scope, retention, safety flags, and storage state.
- Original images, active outputs, failed attempt payloads, and export outputs are protected by retention rules.
- Successful raw payload bytes may be cleaned while metadata remains.
- Soft delete/trash and restore validation are represented.

Non-blocking implementation detail: exact filesystem layout, temp directory behavior, atomic write strategy, orphan recovery, and cleanup scheduler are deferred.

## Export Blocking Gaps

No blocking export gap was found.

Covered export behavior:

- Normal export rejects open blocking QualityIssues in scope.
- Warning export follows ProcessingProfileSnapshot policy.
- Blocked export attempts are retained as ExportRecords and may have no output artifact.
- ExportRecord stores precheck status, issue counts, issue snapshot hash/artifact, profile snapshot/hash, and output/manifest artifacts when present.

Non-blocking implementation detail: exact export manifest schema and any P1 forced/incomplete export semantics are deferred.

## Internal Consistency

PASS.

- `data-model-dd-v0.1.md`, `schema-outline.md`, `erd.mmd`, and `state-data-impact.md` use the same P0 entities and ownership boundaries.
- The ERD renders successfully with Mermaid CLI.
- ADRs exist for the major decisions called out by the final design.
- The final design, schema outline, and open questions avoid SQL DDL, ORM definitions, API handlers, frontend code, prompt templates, and provider integration implementation.

## Acceptance Decision

Final acceptance: PASS.

The data model detailed design loop can close. The design is ready to feed the next backend skeleton design stage, provided that stage first resolves the non-blocking implementation details for enum values, ID strategy, constraint shape, artifact path semantics, retention defaults, and recovery/idempotency hash canonicalization.
