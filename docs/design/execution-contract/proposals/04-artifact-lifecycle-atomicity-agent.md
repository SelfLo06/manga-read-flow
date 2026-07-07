# 04 Artifact Lifecycle and Atomicity Proposal

## 1. Scope

This proposal covers the ArtifactService execution contract for:

- official artifact definition;
- temporary provider/local tool output promotion;
- path, hash, media type, size, and storage-state recording;
- crash-safe file write/copy/promotion behavior;
- coordination with Repository / DAO transactions;
- relationship between artifact registration and active pointer updates.

Non-goals:

- no SQL DDL, ORM model, migration, API, frontend, provider integration, or real prompt design;
- no full artifact taxonomy, retention scheduler, trash UI, or export manifest design;
- no workflow decision algorithm beyond the artifact evidence it must expose.

## 2. Role Bias

Maximize file safety and crash safety, even if that creates extra recovery evidence.

Primary bias decisions:

| Bias | Contract consequence |
| --- | --- |
| File bytes are dangerous to lose or silently corrupt. | ArtifactService computes and records integrity metadata itself; it does not trust provider-reported hash/size/media. |
| Official artifacts must have one owner. | Provider Adapters may only return temp references; ArtifactService is the only official lifecycle entry. |
| SQLite and filesystem are not one atomic resource. | The design favors recoverable two-resource transitions over pretending full atomicity exists. |
| Active output selection is more important than latest output. | Artifact registration never implies active pointer update or export-effectiveness. |

## 3. Assumptions

| Assumption | Design stance |
| --- | --- |
| `app.db + project.db` and project-local workspace are fixed. | Artifact paths are project-relative and stored in `project.db` metadata. |
| Repository / DAO is the only SQLite entry. | ArtifactService asks Repository / DAO to persist artifact metadata; it does not bypass it. |
| Provider output may be a temp file or diagnostic payload. | Temp output is not official until ArtifactService promotion and metadata registration succeed. |
| No distributed transaction exists between SQLite and filesystem. | Atomicity is scoped and recovery-visible. |
| HLD wording mentions active result flags, but data-model final rejects them. | This proposal follows final data-model active pointers only. |
| WorkflowState final uses `export_check`, while data-model export records remain separate. | ArtifactService supplies readiness evidence; export decisions stay outside ArtifactService. |

## 4. Proposed Contract

### Decisions

| Decision | Contract | Rationale |
| --- | --- | --- |
| Official artifact requires metadata. | A file is an official artifact only after a `processing_artifact` record is committed by Repository / DAO for bytes managed by ArtifactService. | A file alone cannot explain scope, hash, retention, safety flags, or recovery behavior. |
| Official-present artifact requires metadata plus bytes. | A normal usable artifact has `storage_state = present`, a registered project-relative path, and hash-valid bytes at that path. | Prevents stale DB rows and orphan files from being mistaken for current outputs. |
| Provider paths are never official paths. | Provider Adapters return temp file references only. ArtifactService validates, copies or moves, hashes, and registers. | Preserves Provider boundary and prevents path/retention drift. |
| Artifact registration is not active selection. | ArtifactService returns an `artifact_id` and metadata; WorkflowLoopEngine/Repository decide whether result rows and active pointers are updated. | Quality checks and workflow policy must run before outputs become current/effective. |
| Acceptance is a separate atomic DB unit. | Result creation, QualityIssue updates, WorkflowDecision, active pointer updates, and stage-status changes must commit together when the workflow accepts output. | Avoids active pointer/status/decision drift. |

### Minimal ArtifactService operations

| Operation | Input | Output | Must not do |
| --- | --- | --- | --- |
| Register original | Uploaded/local source file, Project/Batch/Page scope, original filename metadata. | Official original artifact id and metadata. | Overwrite original bytes or store bytes in SQLite. |
| Promote temp output | Temp file candidate, artifact type, stage, scope, owner refs, retention/safety flags, attempt/tool refs. | Official artifact id and metadata or registration failure. | Accept provider-chosen official path, update active pointers, decide retry/block. |
| Register failed/debug evidence | Sanitized temp payload or file, failure/refusal scope, retention/safety flags. | Official failed/debug artifact id or failure evidence. | Store secrets or let Provider create artifact rows. |
| Validate artifact | Artifact id or metadata row. | `present` and hash-valid, or `missing`/hash-invalid evidence. | Decide rebuild, retry, warning, or block. |

## 5. Minimal Vocabulary / Fields

### Vocabulary

| Term | Meaning |
| --- | --- |
| Temp candidate | Provider/StageExecutor-owned file path under an allowed temp/attempt area. Not official. |
| Promoted bytes | Bytes copied/moved by ArtifactService into an official workspace location, before or during metadata registration. |
| Official artifact | Committed `processing_artifact` row created through ArtifactService/Repository. |
| Present official artifact | Official artifact whose registered file exists and matches recorded hash/size expectations. |
| Orphan file | File bytes without a committed artifact row. Non-official, even if located in an official-looking directory. |
| Unselected artifact | Official artifact not referenced by an active pointer. Audit/reuse candidate, not export-effective. |
| Active pointer | Domain pointer such as `Page.active_typeset_artifact_id` or `TextBlock.active_mask_artifact_id`. Owned by workflow/repository acceptance logic, not ArtifactService alone. |
| Export-effective | Active pointer plus fresh dependencies, hash-valid official bytes, accepted status, and no open blocking issue. |

### Minimal fields recorded at registration

| Field group | Fields |
| --- | --- |
| Identity/scope | `artifact_id`, `project_id`, `batch_id`, `page_id`, `text_block_id` when applicable. |
| Owner/provenance | `owner_type`, `owner_id`, `source_stage`, `workflow_attempt_id`, `tool_run_id`, optional `source_artifact_id`. |
| Classification | `artifact_type`, `retention_class`, safety flags. |
| Location/integrity | `relative_path`, `file_hash`, `hash_algorithm`, `byte_size`, `media_type`/`mime_type`, optional dimensions. |
| State | `storage_state = present` on successful registration, later `missing`, `metadata_only_cleaned`, `moved_to_trash`, or `deleted` by lifecycle operations. |
| Safety | `is_debug`, `may_contain_original_image`, `may_contain_ocr_text`, `may_contain_translation`, `may_contain_provider_response`, `contains_secret_redacted`. |

Path, hash, media, dimensions, and size are recorded after ArtifactService has produced the official bytes and before/with the metadata commit. Provider-supplied metadata may be retained as advisory evidence only.

## 6. Normal Path

| Step | Owner | Contract |
| --- | --- | --- |
| 1. Persist attempt start | WorkflowLoopEngine / Repository | Attempt/task state is durable before any provider call. No write transaction is held across the call. |
| 2. Produce temp output | Provider Adapter or local tool via StageExecutor | Output is a temp path or structured payload reference. No official workspace path or DB row is created. |
| 3. Submit candidate | StageExecutor | Passes temp reference, scope, artifact type, stage, owner refs, retention, and safety flags to ArtifactService. |
| 4. Validate candidate | ArtifactService | Confirms path is allowed, exists, is a file, matches allowed type expectations, and is not an official path supplied by Provider. |
| 5. Promote bytes | ArtifactService | Copies/writes to a staging path under the project workspace, fsyncs where practical, and atomically renames within the same filesystem to the final relative path. Cross-device input is copied into local staging first. |
| 6. Compute metadata | ArtifactService | Computes recorded hash, byte size, media/mime, and dimensions from promoted bytes, not provider claims. |
| 7. Register metadata | ArtifactService + Repository | Inserts `processing_artifact` with `storage_state = present` in a short Repository transaction. |
| 8. Return evidence | ArtifactService | Returns artifact id plus metadata to StageExecutor/WorkflowLoopEngine. |
| 9. Quality and decision | QualityCheckService + WorkflowLoopEngine | Issues and workflow decision are derived from provider output, artifact evidence, profile, and current state. |
| 10. Accept output | WorkflowLoopEngine + Repository | In one DB transaction, create result rows if any, update/create QualityIssues, create WorkflowDecision, update active pointer(s) if accepted, and update stage statuses. |

For import, the same flow applies with the uploaded source file as the temp/source candidate and `Page.original_artifact_id` updated only after the original artifact is successfully registered and accepted.

## 7. Failure / Edge Path

| Edge case | Required behavior |
| --- | --- |
| Temp file missing before promotion | ArtifactService returns registration failure. No artifact row. StageExecutor reports artifact registration failure. |
| Provider returns official-looking path | ArtifactService rejects it unless it was created by an ArtifactService-issued temp area for this attempt. Provider output remains non-official. |
| Path traversal or path outside allowed temp roots | Reject candidate and record sanitized failure evidence if available. |
| Hash/media validation fails | Do not register usable artifact. Retain failed evidence only if policy/safety allows. |
| File write/copy succeeds but DB registration fails | File is orphan/non-official. ArtifactService attempts cleanup or quarantine under attempt/orphan area. Recovery treats it as non-official unless replayed through normal registration. |
| Crash after final rename but before DB row commit | File may exist as orphan. Recovery scans temp/orphan/final directories, but MVP must not make it active without normal ArtifactService registration and validation. |
| DB registration succeeds but active pointer update does not happen | Artifact is official but unselected. It is not export-effective. Recovery may reuse/select it only through a workflow decision and atomic pointer/status update. |
| DB artifact row exists but file is missing/hash-invalid later | ArtifactService marks `storage_state = missing`; WorkflowLoopEngine decides rebuild, retry, warning, pause, or block. |
| Active pointer points at missing artifact | ArtifactService reports missing/hash-invalid; `export_check` cannot pass normal readiness. |
| Result row exists but active pointer did not commit | Result/artifact remain historical candidates. Recovery selects only if accepted validation evidence exists or a new `reuse_cached_result` decision is persisted. |
| Attempt has output artifact but QualityCheck blocks it | Artifact remains auditable; active pointer is not updated as export-effective. WorkflowLoopEngine chooses retry/fallback/pause/block. |
| Duplicate content hash appears | ArtifactService may register a separate scoped artifact or reuse only if Repository/Workflow explicitly decide reuse. Hash equality alone is not active selection. |

## 8. Boundary Rules

| Component | May do | Must not do |
| --- | --- | --- |
| Provider Adapter | Create temp files; return structured temp references and metadata. | Access SQLite, register artifacts, write official paths, create QualityIssues, decide retry/fallback/skip/block. |
| StageExecutor | Pass candidates to ArtifactService; return normalized stage evidence. | Treat temp files as official, update active pointers outside accepted workflow decisions, hold DB write transactions across provider calls. |
| ArtifactService | Generate official paths, promote bytes, hash, register metadata, validate presence/hash, update storage state, cleanup/trash by policy. | Decide workflow outcome, update OCR/translation result pointers, mark Page ready, bypass Repository. |
| Repository / DAO | Persist `processing_artifact` and coordinated acceptance transactions. | Own filesystem bytes or accept provider-direct DB writes. |
| WorkflowLoopEngine | Decide continue/retry/fallback/warning/pause/block and coordinate active pointer acceptance. | Let ArtifactService or Provider decide workflow policy. |
| QualityCheckService | Classify artifact/provider/output issues. | Advance workflow state or update active pointers. |

Hard invariants:

- no image BLOBs or large payload bytes in SQLite;
- original images are never overwritten;
- domain rows reference artifact ids, not authoritative raw paths;
- API keys and secrets never enter logs, artifacts, or snapshots;
- failed attempt artifacts are retained by default when safe and sanitized.

## 9. FakeProvider or FakeQuality Implications

| Fake mode | Artifact implication |
| --- | --- |
| Fake happy path | FakeProvider writes temp files only. ArtifactService promotion must produce official cleaned/typeset/evidence artifacts. |
| Fake invalid JSON | Raw invalid output may be retained as failed/debug artifact; no valid TranslationResult is required. |
| Fake provider refusal | Refusal evidence may be a sanitized payload artifact; retention class should default to failed attempt payload. |
| Fake cleaning skip | FakeCleaner should not create an official cleaned artifact unless it produced bytes. Skip reason and QualityIssue drive workflow. |
| Fake typesetting overflow | FakeTypesetter may produce a temp preview; ArtifactService registers it as auditable preview/output evidence, but WorkflowLoopEngine decides active/export-effective status. |
| Fake missing artifact | Test setup removes registered bytes after official registration. ArtifactService validation must mark `missing`; workflow receives evidence. |
| Fake registration failure | Fake or test harness can force Repository insert failure after file promotion. Expected result: orphan/non-official file and artifact registration failure evidence. |

FakeQuality should consume artifact ids and validation evidence, never temp paths, when checking stages that require official artifacts.

## 10. Recovery / Audit Impact

| Recovery evidence | Interpretation |
| --- | --- |
| Official artifact row with `present` and hash-valid bytes | Durable candidate for reuse or active selection by workflow decision. |
| Official artifact row with missing/hash-invalid bytes | Storage drift. ArtifactService marks `missing`; workflow decides response. |
| File without artifact row | Orphan. Non-official. Cleanup/quarantine or replay through normal registration only. |
| Registered artifact without active pointer | Audit/reuse candidate, not current output. |
| Active pointer to registered artifact with stale dependencies | Selected for review/history, not export-effective. |
| Failed/debug artifact | Audit evidence; absence should reduce diagnostics but not necessarily block workflow if active outputs do not depend on it. |

Audit requirements:

- `WorkflowAttempt` metadata is always persisted around provider/tool execution.
- Artifact metadata links to attempt/tool when known.
- Registration failures should be visible as attempt/tool/workflow evidence, not silent cleanup.
- Recovery must prefer committed results, official artifacts, active pointers, hashes, ToolRunLogs, QualityIssues, and WorkflowDecisions over Page aggregate status.

## 11. HARNESS Scenario Coverage

| Scenario | Coverage from this proposal |
| --- | --- |
| A01 Register original image | Original becomes official only through ArtifactService; hash/media/size/path recorded; Page points to artifact id; original never overwritten. |
| A02 Promote temporary provider output | Provider temp output is copied/moved by ArtifactService; provider cannot choose official path; metadata recorded before returning artifact id. |
| A03 Register failed attempt evidence | Failed/debug/refusal payloads can be official artifacts with failed/debug retention and safety flags; secrets are prohibited. |
| A04 Missing active artifact | ArtifactService detects path/hash failure and marks missing; WorkflowLoopEngine gets evidence and decides response. |
| A05 Artifact cleanup boundary | Cleanup is a lifecycle operation, not provider execution; active originals/results/exports and retained failed evidence are protected by retention class. |
| S01 Happy path stage execution | No DB write transaction across provider call; artifacts registered before quality/decision; active pointer update is coordinated later. |
| S03 File produced but artifact registration fails | File remains non-official; StageExecutor reports registration failure; recovery treats orphan as non-official unless replayed. |
| S04 QualityCheck blocking issue after registration | Artifact remains auditable; active/export-effective pointer is not updated unless workflow accepts. |
| F01 Fake happy path | Fake outputs can validate temp-to-official promotion for all file-producing stages. |
| F03 Fake invalid JSON | Raw invalid response can be retained as failed evidence artifact without result acceptance. |
| F06 Fake typesetting overflow | Preview artifact retention is testable without making it normal ready output. |
| F07 Fake missing artifact | Removing official bytes exercises `missing` detection and workflow decision input. |

## 12. Rejected Alternatives

| Alternative | Rejected because |
| --- | --- |
| Provider writes directly into official workspace paths. | Violates ArtifactService ownership, path safety, and recovery invariants. |
| Provider registers `processing_artifact` rows. | Violates Repository and Provider boundaries. |
| Treat final-path file as official without DB row. | Cannot explain scope, retention, safety flags, hash, or recovery. |
| Store artifact bytes in SQLite for atomicity. | Violates hard invariant and harms performance/cleanup. |
| Update active pointer inside ArtifactService registration. | Bypasses QualityCheckService and WorkflowLoopEngine decisions. |
| Use latest artifact by timestamp as current output. | Breaks locked/manual/reuse semantics and active pointer source of truth. |
| Pretend filesystem rename and SQLite commit are one atomic transaction. | False on local filesystem plus SQLite; recovery must handle partial states. |
| Delete all registration-failed files silently. | Hides crash/debug evidence and makes recovery/audit weaker. Cleanup should be best-effort and recorded when possible. |

## 13. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Orphan files accumulate after crashes or DB failures. | Workspace bloat and user confusion. | Keep temp/orphan directories under project scope; recovery/cleanup scans; never treat orphan as official. |
| DB row and filesystem drift. | Preview/export can fail. | Validate hash/path before readiness/export; mark `missing`; keep workflow decision outside ArtifactService. |
| Active pointer transaction omitted or split. | Artifact/result/status drift. | Require WLE acceptance transaction to include decision, issues, result rows, active pointer, and statuses together. |
| Hashing large images costs time. | Slower stages. | Required for integrity; optimize implementation later with streaming hash, but keep contract. |
| Media sniffing differs by platform/library. | Inconsistent metadata. | Record stable hash/size as primary integrity; media type is descriptive and validated against allowed types. |
| Debug artifacts expose sensitive local content. | Privacy risk. | Safety flags, redaction, retention policy, no secrets, explicit debug policy. |
| Registered but unselected successful artifacts become ambiguous. | Reuse or cleanup uncertainty. | Store owner/attempt/source hashes/retention; select only via explicit workflow decision. |

## 14. Open Questions

| Question | Why it matters |
| --- | --- |
| Should ArtifactService expose transaction-bound registration so artifact row insertion can be included in the same DB transaction as result rows and active pointer updates? | Stronger DB consistency, but more complex because filesystem promotion still cannot roll back atomically. |
| What exact directory/naming scheme should separate temp, staging, final, orphan, trash, and attempts? | Needed for implementation and recovery scans. |
| Should orphan final-path files be moved to a dedicated quarantine during startup recovery, or left until cleanup with a report? | Affects user visibility and disk hygiene. |
| Are dimensions required for every image artifact in MVP, or only original/cleaned/typeset/export images? | Impacts registration cost and preview/export validation. |
| Should content-addressed paths be used for successful payloads, or artifact-id paths for easier audit and deletion? | Affects dedupe, cleanup, and path stability. |
| Which registration failures create user-facing QualityIssues versus internal workflow/tool errors only? | Belongs partly to QualityCheck and StageExecutor contracts. |
| How much of failed registration evidence is retained if the failure is caused by disk-full or permission errors? | Important for crash diagnostics without worsening storage failures. |
