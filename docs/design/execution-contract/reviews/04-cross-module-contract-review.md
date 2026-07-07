## 1. Provider ↔ ArtifactService contract conflicts.

- No hard conflict: all proposals preserve that Provider Adapters return structured payloads/errors and temp refs only; ArtifactService alone promotes official artifacts.
- Resolve in synthesis: Providers may emit `expected_artifact_type`, `kind`, and safety hints, but ArtifactService derives/validates final artifact type, relative path, hash, media, retention class, storage state, and safety flags.
- Resolve in synthesis: Provider temp refs are never recovery truth. Temp/orphan replay is deferred unless replayed through normal registration, quality classification, and workflow acceptance.
- Risk: provider terms such as `skipped`, `preview`, `can_skip`, or `retry_hint` can imply policy. Final wording must label them evidence only.

## 2. Provider ↔ QualityCheckService contract conflicts.

- No hard conflict: Provider Adapter must not create `QualityIssue`; QualityCheckService classifies provider output/error evidence.
- Final synthesis should adopt a canonical `ProviderResult` envelope and feed its `outcome`, `error`, partial-target evidence, refusal marker, and sanitized metadata into `QualityCheckReport`.
- Refusal hidden inside malformed natural-language output needs a split: adapter may report `invalid_output`; QualityCheckService may classify refusal only when sanitized evidence confidently supports it.
- `retry_hint` is acceptable only as advisory provider evidence; it must not map directly to retry budget consumption or a `WorkflowDecision`.

## 3. ArtifactService ↔ QualityCheckService contract conflicts.

- No hard conflict: ArtifactService reports objective storage/registration facts; QualityCheckService turns relevant facts into issues.
- Final synthesis must distinguish `artifact_registration_failed`, `artifact_missing`, `artifact_hash_mismatch`, `metadata_only_cleaned`, and orphan temp evidence.
- ArtifactService must not create `QualityIssue`; QualityCheckService must not update `storage_state`.
- Missing failed/debug evidence should degrade diagnostics, not automatically create user-facing blockers unless current recovery/export depends on it.

## 4. StageExecutor boundary risks.

- Highest risk: StageExecutor becomes a hidden loop if it interprets provider errors, quality summaries, or artifact failures as retry/fallback/skip/block decisions.
- It should execute exactly one bounded attempt, normalize evidence, register artifacts through ArtifactService, invoke QualityCheckService, and return `StageResult`.
- It may perform defensive precondition checks and output schema normalization, but active pointer selection, cache reuse, fallback provider choice, and warning acceptance remain WorkflowLoopEngine-owned.
- It must not hold a SQLite write transaction across provider/tool calls.

## 5. WorkflowLoopEngine ownership risks.

- WorkflowLoopEngine must own all decisions: `continue`, `reuse_cached_result`, retry, fallback, upstream retry, skip, warning, pause, block, cancel, and readiness finish.
- Final design should make `is_blocking` mean "not export-effective while open", not "stop the task now".
- Cleaning skip and typesetting overflow can become warning-ready only through WorkflowLoopEngine plus `ProcessingProfileSnapshot`, never through provider or quality wording.
- Provider refusal fallback must mean an allowed configured alternative, local/manual path, warning/skip if valid, pause, or block; never policy evasion.

## 6. Repository / DAO boundary risks.

- Repository / DAO remains the only SQLite writer. Provider, ArtifactService, QualityCheckService, and StageExecutor should use repository APIs rather than direct SQLite access.
- Final synthesis must choose whether QualityCheckService persists issues via Repository or returns issue drafts. Preferred for MVP-0: return issue drafts/reports; WorkflowLoopEngine acceptance transaction persists issues, decisions, result rows, active pointers, and statuses together.
- If artifact metadata registration happens before workflow acceptance, registered artifacts are official but unselected; recovery may reuse/select only through an explicit decision.
- Exact DAO methods/DDL remain out of scope, but transaction ownership must be clear enough for implementation planning.

## 7. Recovery evidence gaps.

- Registration failure evidence needs a concrete `StageResult` shape: provider success plus artifact failure is not provider failure.
- Integrity check events need a persistence home or durable reference path: ToolRunLog, WorkflowAttempt, WorkflowDecision rationale, or later maintenance log. Synthesis can choose minimal decision evidence for MVP-0.
- Orphan temp behavior should be final: scan/report/quarantine is allowed, but no active promotion in MVP without normal replay.
- Recovery should prefer committed result rows, active pointers, official artifacts, hashes, attempts, tool logs, quality issues, and workflow decisions over Page aggregate status.

## 8. FakeProvider readiness gaps.

- FakeProvider is ready conceptually if it implements the real `ProviderResult` envelope and stage-specific payloads.
- Fake modes must be durable/test-visible enough for retry/recovery assertions: fake mode, scenario key, and call index policy should appear in sanitized attempt/tool metadata.
- Missing active artifact is not a provider mode; it is harness setup after official registration. Missing temp before promotion can be a harness mutation around a provider temp ref.
- Final synthesis must freeze minimal fake modes, fixture artifacts, expected issues, and decision assertions before implementation.

## 9. Issue taxonomy gaps.

- Proposals disagree between compact issue types and stage-specific issue names. Final design should use compact `issue_type` plus specific `error_code` and `message_key`.
- Recommended P0 issue types: `provider_call_failed`, `provider_refusal`, `stage_output_invalid`, `ocr_text_missing`, `translation_missing_block`, `translation_quality_problem`, `cleaning_skipped_complex_region`, `typesetting_overflow`, `artifact_unavailable`; `export_precondition_failed` only for direct readiness defects not already represented.
- Need explicit defaults for provider refusal, invalid JSON, partial translation, cleaning skip, typesetting overflow, and missing active artifacts.
- Partial translation targeting must be clear: valid block outputs are candidates; missing blocks get TextBlock-scoped issues; optional Page summary may be derived.

## 10. Artifact taxonomy gaps.

- Artifact type vocabulary is mostly sufficient: `original_image`, `mask_image`, `ocr_input_crop`, `provider_raw_request`, `provider_raw_response`, `cleaned_image`, `typeset_image`, `typeset_preview_image`, `export_output`, optional `issue_snapshot`, optional `debug_bundle`.
- Keep `temp`, `orphan`, `staging`, and `quarantine` out of official `storage_state`.
- Final design should decide whether `typeset_preview_image` is separate. Recommended: keep separate for MVP clarity so overflow previews cannot be mistaken for accepted output.
- `issue_snapshot` and `debug_bundle` are not required for the FakeProvider vertical slice unless explicitly used as retained evidence.

## 11. Error envelope gaps.

- Adopt one canonical envelope: `ProviderResult` with `outcome = success | partial_success | failure | refusal | invalid_output`.
- Nest standardized error fields: `error_kind`/class, stage-specific `error_code`, `is_provider_refusal`, sanitized message, safe provider ref, optional raw temp refs, optional advisory retry hint.
- StageExecutor owns canonical timing for attempts/tool logs; provider-supplied duration is diagnostic only.
- Final vocabulary should distinguish provider invalid output, StageExecutor parse/schema invalid output, and ArtifactService registration failure while allowing all to become quality/workflow evidence.

## 12. Transaction boundary ambiguities.

- Required sequence: persist running attempt; release transaction; call provider/tool; register official artifacts in short transaction(s); run quality classification; persist workflow acceptance in one loop-owned transaction.
- Final design must choose candidate result timing. Preferred: candidate result drafts remain in `StageResult`; accepted OCR/TranslationResult rows are persisted in the WorkflowLoopEngine acceptance transaction. If persisted earlier, they must be unselected historical candidates.
- Quality issue persistence timing is the main ambiguity. Preferred: QualityCheckService returns drafts; WorkflowLoopEngine persists issue lifecycle updates with the decision.
- Artifact metadata registration may be separate from acceptance; active pointer updates must not happen during artifact registration.

## 13. Security and secret leakage risks.

- Redaction ownership is under-specified. Final synthesis should name a central sanitization step before ToolRunLog, retained payload artifact, QualityIssue, WorkflowDecision, or debug summary persistence.
- Raw provider requests/responses may contain OCR text, translations, original-image snippets, provider policy text, or secrets. Failed/refusal evidence may be retained only after sanitization and safety flagging.
- Provider configs and profile snapshots may store `secret_ref` only, never raw API keys, bearer tokens, cookies, signed URLs, or secret headers.
- User-facing refusal messages must not include bypass, jailbreak, prompt rewrite, obfuscation, or policy-evasion guidance.

## 14. P1/P2 scope creep.

- Defer plugin frameworks, dynamic provider probing, provider ranking, full HTTP metadata catalogs, cost/pricing tables, hardware sizing, license automation, full message localization, forced/incomplete export, privacy purge UI, export manifest details, and cleanup scheduler TTLs.
- Keep Goal 2 focused on FakeProvider single-Page execution contracts, not full Provider Adapter, ArtifactService, QualityCheckService, export, API, or UI design.
- Local/cloud capability metadata should remain small: identity, type, version/model, local/cloud, GPU need, policy surface, license note, enabled, secret ref.

## 15. Recommended final decisions.

- Canonicalize `ProviderResult` and `StageResult` as evidence envelopes, not policy outputs.
- QualityCheckService should return `QualityCheckReport` with issue drafts for MVP-0; WorkflowLoopEngine persists issues/decisions/acceptance together.
- ArtifactService registration creates official but unselected artifacts; WorkflowLoopEngine acceptance selects active pointers.
- Failed/refusal/invalid-output payload evidence defaults to retained `failed_attempt_payload` only after sanitization; successful raw payloads are cleanup eligible.
- Use compact `issue_type`, specific `error_code`, stable `message_key`, and non-binding `suggested_action_key`.
- Treat provider refusal as first-class: provider outcome/refusal marker, refused attempt/tool log, provider-refusal issue with `root_stage = provider_policy`, and a safe WorkflowDecision.
- Defer orphan replay; report/quarantine only unless normal validation/registration/quality/decision replay is implemented.

## 16. ADR candidates.

- Provider result envelope and refusal representation.
- Temp-to-official artifact promotion and unselected official artifacts.
- QualityCheckReport issue-draft model versus direct QualityIssue persistence.
- WorkflowLoopEngine-owned acceptance transaction for results, issues, decisions, active pointers, and statuses.
- FakeProvider deterministic scenario control and no official artifact mutation.
- Redaction/sanitization boundary for logs, payload artifacts, issues, and decisions.

## 17. Blocking issues.

None requiring proposal revision before synthesis.

The unresolved items are synthesis decisions, not evidence gaps requiring Phase 1A/1C rewrites. Synthesis must still make them explicit before implementation planning.

## 18. Non-blocking issues.

- Exact enum spellings for provider outcomes, error codes, issue types, artifact types, and fake modes.
- Exact temp directory layout, file naming, orphan quarantine duration, and cleanup TTLs.
- Whether `ToolRunLog` starts before provider call or is written after return, as long as `WorkflowAttempt.running` exists first.
- Whether Page-level partial translation creates a Page summary issue in addition to TextBlock issues.
- Whether message params and classification version are persisted now or deferred to API/UI/persistence design.
- Whether warning export later requires per-export user acknowledgement beyond `ProcessingProfileSnapshot.allow_warning_export`.

## 19. Open questions that block synthesis.

None. The proposal set gives enough material for the synthesizer to choose final contracts without another revision round.

## 20. Open questions that do not block synthesis.

- Which component is named as the central redaction owner: shared security helper, StageExecutor precondition, ArtifactService precondition, or Config/Security service?
- Are candidate OCR/TranslationResult rows always persisted only on acceptance, or can pre-acceptance historical candidates exist?
- Is `export_precondition_failed` kept as a P0 issue type or represented by existing blockers plus ExportRecord/decision evidence?
- Should `requires_gpu` be tri-state in contract while storage remains boolean plus capabilities JSON?
- Should child-safety refusal always block export readiness, or can it pause for manual/user action without producing an export-effective output?
- Where are artifact integrity check events persisted for long-term audit?
