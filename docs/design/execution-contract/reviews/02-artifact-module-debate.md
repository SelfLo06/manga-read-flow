## 1. Summary of each proposal.

- Proposal 04 defines artifact lifecycle and atomicity. Its core position is that an artifact becomes official only after ArtifactService-managed bytes have committed metadata through Repository / DAO, while active pointer selection remains a separate workflow acceptance step.
- Proposal 05 defines taxonomy, retention, and safety. Its core position is that MVP-0 needs a small explicit artifact vocabulary, protected retention classes for originals/active outputs/failed evidence, and conservative safety flags for sensitive local content and provider payloads.
- Proposal 06 defines recovery and integrity. Its core position is that ArtifactService reports objective storage facts such as missing paths, hash mismatch, metadata-only cleanup, and orphan temp files, while WorkflowLoopEngine decides rebuild, retry, warning, pause, or block.

## 2. Agreements.

- Provider Adapters may create temp files only; they must not access SQLite, register official artifacts, create QualityIssue rows, or decide retry/fallback/skip/warning/block.
- ArtifactService is the only official artifact lifecycle entry: path generation, file promotion, hashing, metadata registration, storage-state updates, cleanup/trash, and integrity validation.
- Repository / DAO remains the only SQLite access path; images and large payload bytes stay on the filesystem.
- Original images are protected and never overwritten.
- Artifact registration does not imply result acceptance, active pointer update, export readiness, or workflow success.
- Active pointers and result/status/decision updates belong to workflow acceptance transactions, not ArtifactService.
- Missing or hash-invalid artifacts are evidence for WorkflowLoopEngine, not direct workflow decisions.
- Failed/refusal/invalid-output payloads should be retained by default when safe and sanitized.
- Temp/orphan files are never official by location alone.

## 3. Conflicts.

- Proposal 04 allows ArtifactService to apply retention/safety flags supplied by callers; Proposal 05 implies ArtifactService owns retention class application. The final contract should say StageExecutor supplies intent and context, while ArtifactService validates/derives the final classification from allowed vocabulary.
- Proposal 05 says storage states stay exactly `present`, `metadata_only_cleaned`, `moved_to_trash`, `missing`, `deleted`; Proposal 04 also mentions orphan/quarantine concepts. Final wording should keep orphan/quarantine as non-official recovery classifications, not storage states.
- Proposal 06 says validation may "repair stale `present` metadata" in limited cases. This is dangerous wording: ArtifactService may restore `present` only after explicit restore/validation of the originally registered path/hash, not silently rewrite integrity metadata.
- Proposal 05 treats `export_output` as protected from ordinary cleanup; HLD says export readiness is based on active typeset output, not prior export bytes. Final design should distinguish protected export history from workflow readiness.
- Proposal 04 suggests result rows, QualityIssues, WorkflowDecision, active pointer updates, and statuses commit together after quality. Cross-module synthesis must confirm whether artifact metadata registration happens before that transaction or can be included in a shared DB transaction after file promotion.

## 4. Missing contract details.

- Exact ArtifactService return shapes are not settled: registration success, registration failure, integrity report, and cleanup result need minimal fields for StageExecutor and WorkflowLoopEngine.
- The contract needs a precise difference between "register artifact failed" and "provider failed before output"; both must be representable without a QualityIssue being created by ArtifactService.
- The final design should specify who records artifact registration failures as ToolRunLog, WorkflowAttempt evidence, workflow error evidence, or QualityIssue candidates.
- Safe payload sanitization is underspecified: the contract needs a minimal redaction requirement, especially for raw provider request/response artifacts.
- Caller-supplied versus ArtifactService-derived safety flags need a rule. Recommended: callers declare possible contents; ArtifactService may only preserve or strengthen risk flags, not weaken them.
- The active pointer acceptance boundary needs explicit examples for original image, mask, cleaned image, typeset image, and overflow preview.
- Cleanup eligibility needs a P0 gate: re-check active pointers, protected retention classes, storage state, and project scope immediately before deleting bytes.
- The final contract should define whether `issue_snapshot` is MVP-0 core or deferred. It looks deferrable.

## 5. Boundary violations.

- No hard violation is present in the proposals.
- Risk: Proposal 05's wording that ArtifactService owns cleanup and retention class application could drift into workflow policy if it decides whether an artifact is required for export. It must only enforce storage policy and report evidence.
- Risk: Proposal 06's `rebuildability_hint` and `safe_to_cleanup_hint` can become hidden decisions. They must remain hints and require WorkflowDecision or cleanup policy invocation before action.
- Risk: Any ArtifactService operation that "restores" or "repairs" state must not update active pointers, result rows, Page status, or export readiness.

## 6. Over-designed parts.

- Detailed fsync, cross-device copy, staging, final rename, orphan quarantine, and trash mechanics are useful implementation notes but too deep for the MVP execution contract unless expressed as principles.
- The taxonomy may be slightly broad for FakeProvider MVP-0. `issue_snapshot` and `debug_bundle` should be optional/deferred unless a harness case requires them.
- Cleanup TTLs, privacy purge UI, export manifest interaction, and long-term debug retention should stay outside the P0 contract.
- `restore_validate` is probably P1 unless the vertical slice explicitly tests trash/manual repair.

## 7. Under-designed parts.

- Artifact registration failure handling needs a clearer StageExecutor output contract. S03 depends on this path.
- Missing/hash-invalid active artifact handling needs a minimal issue mapping contract with QualityCheckService, even if IssueType naming is owned elsewhere.
- Original image registration needs explicit import acceptance wording: Page should reference the original artifact id only after successful official registration and project-scope validation.
- Partial page translation needs a clear artifact/result split: raw response evidence may be retained while valid per-block TranslationResults can still be accepted or withheld by workflow decision.
- The contract should define whether ArtifactService validates media type by sniffing, extension, or both, at least enough to reject unsafe upload/path cases.

## 8. Recommended module-level decisions.

- Define official artifact as: a Repository-committed `processing_artifact` row for bytes promoted or written by ArtifactService under the owning Project workspace, with project-relative path, hash, size, media type, storage state, provenance, retention class, and safety flags.
- Define usable artifact as: official artifact with `storage_state = present` and hash-valid bytes. Active pointer alone is not enough for preview/export/reuse.
- Keep temp, orphan, staging, and quarantine files outside the official storage-state vocabulary.
- Use Proposal 05's MVP artifact types, but mark `issue_snapshot` and `debug_bundle` optional unless final FakeProvider scenarios need them.
- Use Proposal 05's storage states and retention classes as the P0 vocabulary.
- Failed/refusal/invalid-output evidence defaults to `failed_attempt_payload` after sanitization; successful large raw payloads may become `metadata_only_cleaned`.
- ArtifactService may update objective storage states such as `missing`, `metadata_only_cleaned`, `moved_to_trash`, or `deleted`, but must not update active OCR/translation/cleaned/typeset pointers.
- WorkflowLoopEngine/Repository acceptance must own active pointer updates and final result/status/decision persistence.
- ArtifactService should return structured evidence, not policy outcomes: `artifact_registered`, `artifact_registration_failed`, `artifact_valid`, `artifact_missing`, `artifact_hash_mismatch`, `artifact_metadata_only`, `orphan_temp_found`.

## 9. Blocking issues.

- The final contract must explicitly prevent ArtifactService from deciding workflow retry/fallback/warning/block/export readiness or updating active pointers. The proposals agree, but synthesis must preserve this as a hard rule.
- Artifact registration failure output is not yet precise enough for implementation. Without it, S03 and FakeProvider registration-failure tests remain unclear.
- The final contract must resolve whether artifact metadata registration is always a separate transaction before quality/acceptance, or whether a transaction-bound mode is allowed. This affects crash recovery and active pointer consistency.
- Sanitization minimums for failed/debug provider payload artifacts are blocking for safe retention because raw provider requests can contain OCR text, translations, provider responses, and possibly secrets.

## 10. Non-blocking issues.

- Exact directory and file naming scheme can be deferred if the contract requires project-relative paths, path traversal prevention, and ArtifactService-generated official paths.
- Cleanup TTLs and debug retention durations can be deferred.
- Orphan quarantine retention length can be deferred.
- Whether hash-equal duplicate files are deduplicated can be deferred; hash equality must not imply active selection.
- Export output retention can be finalized by export design, as long as export readiness depends on active present typeset output and unresolved blocking issues.

## 11. Open questions.

- Should ArtifactService expose a transaction-bound registration API, or should it always register artifact metadata before workflow acceptance?
- Which component persists integrity-check events: ToolRunLog, WorkflowAttempt, WorkflowDecision rationale, or a separate maintenance log?
- What is the minimum sanitization contract and metadata for retained provider request/response artifacts?
- Should `typeset_preview_image` remain separate from `typeset_image`, or should preview/accepted status be represented only by owner/status?
- Is `issue_snapshot` part of MVP-0 execution contract, or should it be deferred to export/quality reporting?
- Can orphan temp output replay be allowed in MVP-0, or should it be fully deferred and treated as abandoned evidence only?

## 12. What the cross-module reviewer must inspect.

- Verify StageExecutor never treats temp files as official and always routes file outputs through ArtifactService.
- Verify Provider contracts never include official paths, retention decisions, SQLite writes, QualityIssue creation, or retry/fallback/skip decisions.
- Verify QualityCheckService consumes artifact ids, provider envelopes, and ArtifactService evidence without updating storage states or active pointers.
- Verify WorkflowLoopEngine receives enough artifact evidence to decide continue/retry/fallback/skip/warning/block without ArtifactService making those decisions.
- Verify active pointer updates are coordinated with WorkflowDecision, QualityIssue updates, result rows, and stage statuses.
- Verify provider refusal, invalid JSON, partial translation, cleaning skip, typesetting overflow, missing artifact, and registration failure all have auditable evidence paths.
- Verify export readiness requires active present/hash-valid artifacts and no unresolved blocking issue, not merely the latest artifact or export output path.
