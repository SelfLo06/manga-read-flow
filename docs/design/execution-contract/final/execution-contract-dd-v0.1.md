# Execution Contract Detailed Design v0.1

## 1. Design goals

This design defines the MVP execution contracts among Provider Adapters, ArtifactService, QualityCheckService, StageExecutor, and WorkflowLoopEngine for the next milestone:

```text
FakeProvider single-Page backend vertical slice
```

Goals:

- Preserve the architecture boundaries fixed by SRS, HLD, data-model, and workflow-state designs.
- Make one Page executable without real OCR, LLM, cleaning, or typesetting tools.
- Keep provider outputs, official artifacts, quality issues, workflow decisions, and active pointer acceptance separately explainable.
- Support restart recovery, idempotent rerun, partial failure, provider refusal, missing artifact detection, and warning/blocking export readiness.
- Keep the design documentation-only and minimal. No SQL DDL, ORM, API, frontend, real provider integration, or real prompt template is defined here.

## 2. Source documents

Read and synthesized:

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/PROJECT-PLAN.md`
- `docs/design/execution-contract/GOAL.md`
- `docs/design/execution-contract/HARNESS.md`
- `docs/design/execution-contract/PLAN.md`
- all `docs/design/execution-contract/proposals/*.md`
- all `docs/design/execution-contract/reviews/*.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/workflow-state/final/state-vocabulary.md`
- `docs/design/workflow-state/final/stage-transition-table.md`
- `docs/design/workflow-state/final/decision-matrix.md`
- `docs/design/workflow-state/final/recovery-rules.md`
- `docs/design/workflow-state/final/stale-propagation-rules.md`

No blocking conflict was found. `docs/HLD.md` is now the current HLD v0.2 baseline. The final design follows `docs/HLD.md` plus the newer data-model and workflow-state final documents where older SRS/HLD examples use broader vocabulary.

## 3. Final document map

| Document | Owns |
| --- | --- |
| `provider-adapter-contract.md` | Provider result envelope, error envelope, metadata/capability metadata, and five stage-specific provider contracts. |
| `artifact-service-contract.md` | Official artifact lifecycle, artifact type/storage/retention vocabulary, temp promotion, missing detection, and cleanup boundary. |
| `quality-check-contract.md` | QualityCheckService input/output, issue drafts, attribution, severity/blocking, message/action keys, and boundary rules. |
| `stage-executor-contract.md` | StageExecutor context/result contracts, execution sequence, transaction boundaries, and WorkflowLoopEngine decision input. |
| `error-and-issue-taxonomy-minimal.md` | Minimal error, issue, severity, root-stage, message, and suggested-action vocabulary. |
| `fakeprovider-readiness.md` | Required FakeProvider/FakeQuality modes, fixtures, and HARNESS scenario replay. |
| `open-questions.md` | Non-blocking open questions and deferred decisions. |

## 4. Cross-cutting decisions

| Decision | Final choice |
| --- | --- |
| Provider envelope | Use `ProviderResult` with `outcome = success | partial_success | failure | refusal | invalid_output`. |
| Provider errors | Nest standardized `error` inside `ProviderResult`; separate coarse `kind` from stage-specific `code`. |
| Provider refusal | First-class `outcome = refusal`, `is_provider_refusal = true`, refused attempt/log evidence, `provider_refusal` issue, `root_stage = provider_policy`. |
| Provider temp files | Providers may return temp refs under an attempt temp root only. They never return official artifact ids or official paths. |
| Official artifacts | ArtifactService promotion plus committed metadata makes an official artifact. Artifact registration does not select active pointers. |
| Quality issue persistence | For MVP-0, QualityCheckService returns `QualityCheckReport` with issue drafts and lifecycle suggestions; WorkflowLoopEngine persists issue updates with the decision/acceptance transaction. |
| Candidate results | StageExecutor returns result drafts/candidates. Accepted OCR/TranslationResult rows are persisted by WorkflowLoopEngine acceptance. If later implementations persist candidates earlier, they must remain unselected historical candidates. |
| Acceptance transaction | WorkflowLoopEngine coordinates one repository transaction for WorkflowDecision, issue lifecycle updates, accepted result rows, active pointers, retry budget after, and stage statuses. |
| Redaction | A central sanitization step must run before ToolRunLog, retained payload artifacts, QualityIssue drafts, WorkflowDecision rationale, or debug summaries are persisted. Exact helper/module name is deferred. |
| FakeProvider modes | Fake modes are deterministic and durable/test-visible through profile snapshot or task test config copied into sanitized attempt/tool metadata. Hidden process globals are not sufficient. |

## 5. Hard invariants

| Invariant | Preserved by |
| --- | --- |
| Provider Adapter only calls tools and returns structured outputs/errors/provider metadata. | Provider contract. |
| Provider Adapter does not access SQLite, register official artifacts, create QualityIssues, or decide retry/fallback/skip/warning/pause/cancel/block. | Provider and StageExecutor contracts. |
| ArtifactService is the only official artifact lifecycle entry. | Artifact contract. |
| ArtifactService does not decide workflow retry/fallback/warning/block/readiness. | Artifact and StageExecutor contracts. |
| Repository / DAO is the only SQLite access entry. | StageExecutor transaction guidance; all services use repository boundaries. |
| WorkflowLoopEngine owns workflow decisions. | StageExecutor output is evidence only. |
| QualityCheckService checks outputs and classifies issues but does not advance workflow state or update active pointers. | Quality contract. |
| StageExecutor executes one stage but does not make final workflow decisions. | StageExecutor contract. |
| Original images are never overwritten. | Artifact lifecycle and import rule. |
| Image files and large payloads are not stored in SQLite. | Artifact retention/safety rules. |
| Active pointers remain source of truth for current OCR, translation, cleaned image, and typeset image. | Data-model alignment and acceptance transaction. |
| Provider refusal is a first-class workflow path, not a crash. | Provider/quality/stage contracts and ADR 0001. |
| No provider policy bypass or evasion logic is allowed. | Provider refusal, suggested-action, and redaction rules. |
| FakeProvider does not require real OCR, LLM, cleaning, or typesetting tools. | FakeProvider readiness. |

## 6. WorkflowLoopEngine decision input

WorkflowLoopEngine decides from:

- `StageResult` evidence from StageExecutor.
- `ProviderResult` outcome, error/refusal evidence, and provider metadata.
- Artifact registration or integrity reports from ArtifactService.
- `QualityCheckReport` issue drafts, summary counts, severity/blocking, root/discovered stage, and suggested action keys.
- Current task state, attempt history, retry budgets, fallback visited state, and cancellation/pause requests.
- `ProcessingProfileSnapshot` policy, including quality strictness, retry/fallback/refusal policy, warning export policy, auto-skip allowlist, and retention/debug hints.
- Active pointers, result dependency hashes, artifact storage states, TextBlock stage statuses, and Page aggregate state.

WorkflowLoopEngine may decide only the canonical workflow-state decisions:

```text
continue
reuse_cached_result
retry_same_stage
fallback_provider
retry_upstream_stage
skip_target
mark_warning
pause_for_user
block
finish_ready_for_export
finish_ready_for_export_with_warnings
cancel
```

## 7. Transaction boundary summary

| Boundary | Rule |
| --- | --- |
| Before provider call | Persist running WorkflowAttempt in a short transaction. Optional running ToolRunLog is allowed. |
| Provider call | Hold no SQLite write transaction. Provider may use only supplied input refs and attempt temp root. |
| Provider return | StageExecutor normalizes provider output/error/refusal and records sanitized tool evidence through Repository. |
| Artifact registration | ArtifactService promotes/registers official artifacts in short transaction(s). Registered artifacts are official but unselected. |
| Quality check | QualityCheckService returns report/drafts; it does not advance workflow state. |
| Workflow acceptance | WorkflowLoopEngine persists decision, issue lifecycle, accepted results, active pointers, retry budget after, and statuses together. |

## 8. HARNESS scenario replay

Detailed scenario replay is in `fakeprovider-readiness.md`. Summary:

| HARNESS area | Result | Notes |
| --- | --- | --- |
| Provider Adapter P01-P05 | PASS | Success, timeout/failure, refusal, invalid output, and partial translation are covered by `ProviderResult`. |
| ArtifactService A01-A05 | PASS | Original registration, temp promotion, failed evidence, missing artifact, and cleanup boundary are covered. |
| QualityCheckService Q01-Q06 | PASS | Empty OCR, invalid translation, missing block, refusal, cleaning skip, and overflow map to deterministic issue drafts. |
| StageExecutor S01-S05 | PASS | One-stage sequence, provider failure, registration failure, blocking issue, and warning issue are evidence-only paths. |
| FakeProvider F01-F07 | PASS | Required fake modes and fixture artifacts cover happy path, retry, invalid JSON, refusal, skip, overflow, and missing artifact setup. |
| Boundary failure checks | PASS | No final contract gives provider, artifact, quality, or stage executor workflow ownership. |

## 9. Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| Provider returns domain rows such as OCRResult or TranslationResult. | Couples tools to persistence, versioning, active pointers, and workflow decisions. |
| Provider writes official workspace files or registers artifacts. | Violates ArtifactService ownership of path, hash, retention, storage state, and cleanup. |
| Provider creates QualityIssues or returns `should_retry`/`should_skip`. | Violates QualityCheckService and WorkflowLoopEngine ownership. |
| Artifact registration automatically updates active pointers. | Skips quality/workflow acceptance and can make bad output export-effective. |
| QualityCheckService persists workflow state or returns WorkflowDecision. | Splits decision ownership and weakens recovery auditability. |
| StageExecutor performs retry/fallback/skip/block logic. | Turns it into a hidden WorkflowLoopEngine. |
| Recovery promotes orphan temp files by default. | Bypasses normal artifact registration, quality classification, and workflow acceptance. |
| Store image bytes or raw provider payloads in SQLite. | Violates data-model invariants and increases privacy/storage risk. |
| Treat provider refusal as generic failure. | Loses policy semantics and risks unsafe same-provider retry behavior. |
| Implement real OCR/LLM/cleaning/typesetting for Goal 2. | Hides contract defects behind tool behavior and blocks FakeProvider validation. |

## 10. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Boundary drift from hints into decisions. | Provider retry hints, artifact rebuildability hints, and quality suggested actions are explicitly non-binding evidence. |
| Partial success becomes ambiguous. | `partial_success` requires valid target payloads plus explicit missing/invalid target evidence; active pointer acceptance stays loop-owned. |
| Artifact DB/filesystem drift. | ArtifactService validates hash/path and marks `missing`; WorkflowLoopEngine decides rebuild/pause/block. |
| Registered but unselected artifacts confuse recovery. | Official unselected artifacts are audit/reuse candidates only, never export-effective by timestamp. |
| Quality issue persistence races active pointer updates. | MVP-0 persists issue lifecycle updates in WorkflowLoopEngine acceptance transaction. |
| Provider refusal hidden inside malformed output. | Adapter can return `invalid_output`; QualityCheck may classify refusal only from sanitized evidence when confident. |
| Debug/failed payloads leak secrets. | Central sanitization, safety flags, no raw secrets, and failed/debug retention only as filesystem artifacts. |
| Fake modes hide real integration complexity. | FakeProvider uses the real envelope and artifact boundary; real-provider spike is a later validation step. |

## 11. ADR list

- `docs/design/execution-contract/adr/0001-provider-result-envelope-and-refusal.md`
- `docs/design/execution-contract/adr/0002-artifact-promotion-and-unselected-official-artifacts.md`
- `docs/design/execution-contract/adr/0003-qualitycheck-issue-drafts-and-acceptance-transaction.md`
- `docs/design/execution-contract/adr/0004-stageexecutor-evidence-boundary.md`
- `docs/design/execution-contract/adr/0005-fakeprovider-deterministic-modes.md`
- `docs/design/execution-contract/adr/0006-redaction-sanitization-boundary.md`

## 12. Open questions

See `open-questions.md`. All listed questions are non-blocking for final synthesis and for planning the FakeProvider single-Page backend vertical slice.

## 13. Decisions deferred to later design stages

- Exact SQL DDL, ORM models, migrations, indexes, and repository method names.
- Exact FastAPI routes, request/response DTOs, and frontend behavior.
- Exact provider prompt templates and real provider JSON schemas.
- Exact artifact directory layout, temp naming, fsync mechanics, cleanup scheduler, and retention TTLs.
- Exact ProcessingProfile defaults for fast/balanced/strict.
- Exact API key storage implementation and OS secret store integration.
- Full export design, ZIP manifest schema, and forced/incomplete export behavior.
- Full UI message localization and quality report rendering.
- Real OCR, translation, cleaning, and typesetting tool integration details.
