## 1. Summary of each proposal.

- Proposal 01 defines the strongest provider boundary: one `ProviderResult` envelope, minimal stage DTOs, temp file refs only, and clear separation from DB, official artifacts, QualityIssues, workflow decisions, cache, and active pointers.
- Proposal 02 focuses on auditable error/refusal handling: standardized errors, first-class provider refusal, sanitized metadata, redaction, and raw payload retention boundaries.
- Proposal 03 defines small capability metadata and deterministic FakeProvider modes for the single-Page vertical slice, especially local/cloud distinction, GPU/license notes, and retry/refusal/invalid/partial/overflow scenarios.

## 2. Agreements.

- Provider Adapter is only a structured tool-call boundary.
- Provider Adapter must not access SQLite, register official artifacts, create QualityIssues, update active pointers, or decide retry/fallback/skip/warning/block.
- StageExecutor constructs provider DTOs from durable context and receives provider evidence.
- ArtifactService promotes temp files, assigns official paths, hashes, retention, and cleanup.
- QualityCheckService classifies output/error evidence into issue candidates or QualityIssues.
- WorkflowLoopEngine owns all loop decisions and acceptance of results.
- Provider refusal must be distinct from generic failure and must not trigger policy bypass or prompt laundering.
- FakeProvider must use the same contract as real providers and return deterministic evidence.
- Secrets, API keys, large image bytes, and official workspace paths must not appear in provider DTOs or logs.

## 3. Conflicts.

- Envelope shape conflicts: Proposal 01 uses `ProviderResult.outcome`; Proposal 02 uses an `ok = false` error envelope. Use Proposal 01 as canonical and nest Proposal 02 error fields inside it.
- Error taxonomy conflicts: Proposal 01 uses generic `error_code` values while Proposal 02 mixes coarse classes and stage-specific codes. Final design should separate `error.kind` from `error.code`.
- Partial output semantics vary between explicit `partial_success`, success-with-evidence, and invalid output. Prefer explicit `partial_success` when valid target outputs are separable from missing/invalid targets.
- `retry_hint` in Proposal 02 risks becoming a provider-owned decision. If retained, it must be optional advisory evidence and never consume retry budget.
- Proposal 03 recommends tri-state `requires_gpu`; current high-level schema language is closer to boolean. Use tri-state in capability metadata, with storage mapping decided elsewhere.
- Proposal 03 cites `docs/HLD-v0.2.md` as a baseline. This review treated only `docs/HLD.md` and the allowed proposal files as authoritative.

## 4. Missing contract details.

- Final enum names for `stage`, `outcome`, `error.kind`, `error.code`, `execution_location`, and `requires_gpu`.
- Exact request DTOs for each stage, including required target ids, input refs, language fields, config fields, and hash fields.
- Exact successful payload schemas for detection, OCR, translation, cleaning, and typesetting.
- Temp directory ownership, path validation, allowed temp roots, cleanup timing, and crash behavior before promotion.
- Redaction owner and sequence before ToolRunLog, WorkflowAttempt, artifact registration, QualityIssue, and WorkflowDecision persistence.
- Who performs schema parsing vs semantic validation when provider output is malformed.
- Whether raw request/response payload retention is default for failed/refused attempts or only enabled by debug/strict policy.
- How partial results become durable: persist immediately as evidence, or only after WorkflowLoopEngine acceptance.
- Capability metadata storage shape and how ProcessingProfileSnapshot references provider capabilities.
- Provider timeout and cancellation semantics, including whether client-library retries are visible as attempts.

## 5. Boundary violations.

- No proposal intentionally gives Provider Adapter DB, official artifact, QualityIssue, or workflow-decision ownership.
- Proposal 02 places attempt/log/refusal persistence details inside the provider-error proposal; final wording must make StageExecutor/Repository the persistence owners.
- Proposal 02 requiring `started_at`, `finished_at`, and `duration_ms` from the provider could blur authoritative timing. StageExecutor/ToolRunLog should own canonical timing; provider timings may be diagnostics only.
- Proposal 02 `retry_hint` must not become `should_retry`.
- Proposal 03 storage claims about `ProviderConfig` in `app.db` and execution evidence in `project.db` belong to data-model synthesis, not the provider module contract.
- Proposal 03 FakeProvider call counters must not rely on hidden global state for workflow correctness; they may be test evidence only.
- Provider payload terms like `skipped`, `skip`, or `can_skip` must remain provider evidence, not actual workflow skip decisions.

## 6. Over-designed parts.

- Dynamic capability negotiation, probing, plugin-registry implications, and provider ranking should stay out of Phase 1B.
- Cost fields, endpoint host hashing, rate-limit metadata, and detailed HTTP metadata are useful later but not required for the FakeProvider vertical slice.
- Detailed raw payload retention policy belongs mainly to ArtifactService/security synthesis.
- Full stage-specific error-code tables may be too broad for MVP; keep only codes needed by the harness and SRS refusal/error cases.
- `license_note` is acceptable as trace metadata, but license automation should be deferred.

## 7. Under-designed parts.

- The exact provider request/response schemas are still too loose for implementation.
- Redaction is recognized as critical but lacks a concrete owning component and validation scenarios.
- Partial-success commit and recovery behavior need sharper rules.
- Temp file path safety, path traversal prevention, and missing temp file handling need final ArtifactService alignment.
- Capability metadata use in provider selection, fallback eligibility, and privacy warnings is not fully specified.
- Refusal hidden in malformed natural-language output needs a clear adapter/QualityCheck split.
- Provider cancellation and deadline behavior is not yet contractually defined.

## 8. Recommended module-level decisions.

- Adopt Proposal 01 `ProviderResult` as the canonical envelope with `success`, `partial_success`, `failure`, `refusal`, and `invalid_output`.
- Put Proposal 02 error details inside `ProviderResult.error`: generic kind, stage-specific code, refusal marker, sanitized message, safe provider ref, and optional raw temp refs.
- Treat all provider metadata as sanitized evidence only; no secrets, no raw authorization, no official artifact ids or paths.
- Permit Provider Adapter to write only under a StageExecutor-owned temp root and return temp refs; ArtifactService alone promotes files.
- Make QualityCheckService the only owner of quality classification and root-stage attribution.
- Make WorkflowLoopEngine the only owner of retry, fallback, skip, warning, block, pause, cancel, readiness, and active result acceptance.
- Preserve refusal as first-class evidence and prohibit automatic prompt rewriting or content laundering after refusal.
- Keep provider capabilities small and static: identity, type, version/model, local/cloud, GPU need, policy surface, license note, enabled flag, secret ref.
- Implement FakeProvider against the real provider envelope and deterministic modes from Proposal 03.
- Allow `partial_success` only when valid target payloads and missing/invalid target evidence are explicit.

## 9. Blocking issues.

- Final synthesis must choose one canonical provider envelope and enum vocabulary.
- Redaction ownership must be decided before any raw provider payload, error, or diagnostic can be retained.
- Temp file ownership, validation, and cleanup must be decided with ArtifactService before implementation.
- Refusal handling must explicitly prevent retry/fallback logic from bypassing provider policy.
- Partial-success acceptance must be decided with WorkflowLoopEngine and Repository before valid block outputs are persisted as active results.
- The `docs/HLD-v0.2.md` reference in Proposal 03 must be removed or reconciled with the actual authoritative baseline.

## 10. Non-blocking issues.

- Exact fake OCR/translation fixture text can be chosen during implementation.
- `glossary_candidates[]` can be deferred until P1.
- `estimated_cost`, detailed HTTP metadata, and rate-limit reset hints can be deferred unless needed by the harness.
- Tri-state GPU metadata can live in capabilities JSON even if a later storage column remains boolean.
- Raw refusal response retention can be stricter than raw invalid-output retention.
- Fake missing official artifact should remain a harness/ArtifactService setup case, not provider behavior.

## 11. Open questions.

- Which component owns central secret redaction: StageExecutor helper, ArtifactService precondition, Config/Security service, or shared infrastructure?
- Should provider adapters parse raw provider responses themselves, or should StageExecutor perform final schema validation?
- Should failed/refused raw responses be retained by default, or only sanitized refusal summaries plus request ids?
- What is the final root-stage value for provider policy refusal?
- Can child-safety refusal ever route to manual/fallback, or is it always blocking for export readiness?
- Should advisory recoverability hints exist at all, or should WorkflowLoopEngine infer everything from code/profile/history?
- How are provider call deadlines, cancellation, and low-level client retries represented in WorkflowAttempt history?

## 12. What the cross-module reviewer must inspect.

- Artifact module: temp refs, official promotion, hash/media validation, retention, failed evidence, path traversal prevention, and cleanup.
- Quality module: classification for empty OCR, invalid JSON, missing translations, provider refusal, complex background, and typeset overflow.
- Workflow module: retry budgets, fallback, skip/warning/block decisions, partial-success acceptance, refusal safety, recovery, and active pointer updates.
- Data model: ToolRunLog, WorkflowAttempt, WorkflowDecision, result versioning, provider metadata, artifact rows, and no BLOB/secrets invariants.
- Config/security: API key storage, `secret_ref`, local/cloud privacy warnings, provider policy surface, and redaction tests.
- Harness: FakeProvider modes must cover success, transient failure, invalid output, refusal, partial translation, cleaning skip, overflow, and missing temp artifact promotion failure.
