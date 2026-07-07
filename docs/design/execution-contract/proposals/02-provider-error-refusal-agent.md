# 02 Provider Error, Refusal, and Metadata Proposal

## 1. Scope

This proposal defines the MVP provider error/refusal contract for the FakeProvider single-Page vertical slice.

In scope:

| Area | Decision focus |
| --- | --- |
| Provider errors | Stable error classes/codes for timeout, unavailable, invalid input, invalid output, provider refusal, and unexpected tool failure. |
| Refusal evidence | Provider refusal is explicit workflow evidence, not a generic failed attempt. |
| Metadata | Sanitized provider/tool/model/request metadata retained for audit, retry budget, fallback, and recovery. |
| Payload retention | Which raw request/response/error payloads may become ProcessingArtifacts. |
| Secret safety | Redaction requirements before logs, artifacts, issues, decisions, and user messages. |

Out of scope: implementation code, SQL/DDL, ORM models, provider prompts, real provider integrations, full API DTOs, UI messages beyond message keys, and full QualityIssue taxonomy.

## 2. Role Bias

Bias: maximize auditable failure behavior while preventing refusal from being collapsed into normal failure.

Design stance:

| Concern | Decision |
| --- | --- |
| Auditability | Every provider call outcome must be explainable through WorkflowAttempt, ToolRunLog, optional artifact evidence, QualityIssue, and WorkflowDecision. |
| Refusal safety | Refusal has its own class, attempt status, issue type/code, and root attribution. |
| Policy boundary | No retry prompt mutation, content laundering, or evasion metadata is allowed. |
| Minimality | Use a small error vocabulary; add provider-specific details only as sanitized metadata. |

## 3. Assumptions

- StageExecutor creates/persists attempt start before calling a provider and does not hold a write transaction during the call.
- Provider Adapter returns a structured success or structured error; it does not access SQLite.
- Provider Adapter may create temporary files or in-memory raw payloads, but ArtifactService owns official artifact registration.
- QualityCheckService maps provider errors/refusals into QualityIssues; Provider Adapter does not create issues.
- WorkflowLoopEngine decides retry, fallback, skip, warning, pause, or block.
- ProcessingProfileSnapshot contains provider refs, retry/fallback/refusal policy, and retention hints, but no secrets.

## 4. Proposed Contract

### Error Envelope

Every provider error should be returned in a normalized envelope:

| Field | Required | Meaning |
| --- | --- | --- |
| `ok = false` | Yes | Distinguishes error from success. |
| `stage` | Yes | Stage that called the provider: `detection`, `ocr`, `translation`, `cleaning`, `typesetting`. |
| `provider_name` | Yes | Sanitized configured provider identity. |
| `provider_kind` | Yes | Capability kind, not implementation class internals. |
| `model_id` | Optional | Sanitized model/deployment id when known. |
| `error_class` | Yes | Coarse stable class used by workflow policy. |
| `error_code` | Yes | Stage-specific stable code used by issues/UI/audit. |
| `is_provider_refusal` | Yes | True only for policy/safety/content refusal. |
| `retry_hint` | Yes | `transient`, `non_retryable`, `unknown`; advisory only, not a workflow decision. |
| `sanitized_message` | Yes | Short human-safe summary, no secrets/raw provider dump. |
| `provider_metadata` | Yes | Sanitized, bounded metadata map. |
| `temporary_payloads` | Optional | Temp raw request/response/error payload refs for possible ArtifactService registration. |
| `started_at`, `finished_at`, `duration_ms` | Yes | Timing for ToolRunLog and audit. |

Rationale: the adapter identifies what happened; StageExecutor/QualityCheck/WorkflowLoopEngine decide what it means.

### MVP Error Classes

| `error_class` | Typical status | Refusal? | Retry hint default | Notes |
| --- | --- | --- | --- | --- |
| `provider_timeout` | `failed` | No | `transient` | Timeout or cancelled external call deadline. |
| `provider_unavailable` | `failed` | No | `transient` or `non_retryable` | Network, rate limit, quota, missing/invalid API key, provider disabled. |
| `invalid_input` | `failed` | No | `non_retryable` | StageExecutor/provider input violates contract or file missing before call. |
| `invalid_output` | `failed` | No | `unknown` | Provider returned malformed JSON/schema-invalid/unsupported file. |
| `provider_refusal` | `refused` | Yes | `non_retryable` | Provider explicitly refuses content/policy class. |
| `model_error` | `failed` | No | `unknown` | Provider/tool internal error, OCR crash, model exception. |
| `dependency_missing` | `failed` | No | `non_retryable` | Local binary/model/GPU/font dependency missing. |
| `file_io_error` | `failed` | No | `unknown` | Temp read/write failure before ArtifactService promotion. |
| `unsupported_content` | `failed` | No | `non_retryable` | Provider cannot handle input type/size/language, but did not refuse on policy. |
| `unknown_error` | `failed` | No | `unknown` | Last resort; should be rare and sanitized. |

### Stage Error Codes

| Stage | MVP codes |
| --- | --- |
| Detection | `detection_provider_unavailable`, `detection_timeout`, `detection_invalid_input`, `detection_invalid_output`, `detection_model_error`, `detection_unsupported_content` |
| OCR | `ocr_provider_unavailable`, `ocr_timeout`, `ocr_invalid_input`, `ocr_invalid_output`, `ocr_no_text`, `ocr_model_error`, `ocr_dependency_missing` |
| Translation | `translation_provider_unavailable`, `translation_timeout`, `translation_rate_limited`, `translation_quota_exceeded`, `translation_invalid_input`, `translation_invalid_json`, `translation_schema_invalid`, `translation_partial_output`, `translation_provider_refused`, `translation_nsfw_policy_refused`, `translation_child_safety_refused`, `translation_model_error` |
| Cleaning | `cleaning_provider_unavailable`, `cleaning_timeout`, `cleaning_invalid_input`, `cleaning_invalid_output`, `cleaning_complex_background`, `cleaning_model_error`, `cleaning_dependency_missing`, `cleaning_file_io_error` |
| Typesetting | `typesetting_invalid_input`, `typesetting_invalid_output`, `typeset_overflow`, `typesetting_font_missing`, `typesetting_file_io_error`, `typesetting_model_error` |
| Cross-cutting | `provider_missing_config`, `provider_invalid_config`, `provider_unknown_error`, `artifact_registration_failed` |

`artifact_registration_failed` is not a Provider Adapter error when ArtifactService fails after a provider succeeds. StageExecutor reports it as stage execution evidence for QualityCheck/WorkflowLoopEngine.

### Refusal Representation

Provider refusal must use all of these markers:

| Surface | Required representation |
| --- | --- |
| Provider error | `error_class = provider_refusal`, `is_provider_refusal = true`. |
| WorkflowAttempt | `status = refused`, `error_code` set to refusal code, sanitized message only. |
| ToolRunLog | `status = refused`, `is_provider_refusal = true`, same error class/code. |
| QualityIssue | `issue_type = provider_refusal` or stage-specific refusal issue, `root_stage = provider_policy`. |
| WorkflowDecision input | Refusal error, issue, attempt, tool log, provider metadata, evidence artifact ids if retained. |

Provider refusal examples:

| Provider signal | Normalized code | Notes |
| --- | --- | --- |
| Generic safety/content refusal | `translation_provider_refused` | Default refusal code. |
| NSFW/content policy refusal | `translation_nsfw_policy_refused` | Do not include raw policy text if it contains sensitive content. |
| Child-safety refusal | `translation_child_safety_refused` | Blocking by default unless later policy says otherwise. |
| Refusal-like assistant text in valid response | `translation_provider_refused` plus invalid/quality issue as needed | QualityCheckService may detect refusal phrase in output. |

Refusal is not retryable against the same provider unless later evidence proves the first event was misclassified as a transient transport error. No automatic prompt rewriting or obfuscation is part of the contract.

## 5. Minimal Vocabulary / Fields

### Sanitized Provider Metadata

Retain only bounded, non-secret metadata:

| Field | Keep? | Notes |
| --- | --- | --- |
| `provider_name`, `provider_kind` | Yes | Stable configured identity/capability. |
| `provider_config_ref` | Yes | Reference/id only; no secret value. |
| `endpoint_host_hash` | Optional | Hash or label only; no full URL with credentials/query tokens. |
| `model_id`, `model_version` | Yes | Sanitized printable string. |
| `adapter_version`, `tool_version` | Yes | Supports repeatability. |
| `request_id` / `trace_id` | Optional | Keep only if not secret-bearing; otherwise hash/redact. |
| `http_status` | Optional | Useful for unavailable/rate/quota. |
| `rate_limit_reset_at` | Optional | Metadata only; WorkflowLoopEngine decides waiting/retry. |
| `usage_tokens`, `estimated_cost` | Optional | Cost accounting; no raw text. |
| `input_hash`, `config_hash`, `context_hash` | Yes | Audit/retry/idempotency keys. |
| `sanitization_version` | Yes | Redaction traceability. |

Never retain API keys, bearer tokens, cookies, secret headers, raw Authorization values, signed URLs, unredacted base URLs with credentials, environment variable dumps, or raw exception strings that include secrets.

### Raw Payload Artifact Boundaries

| Payload | May register? | Default retention | Safety flags |
| --- | --- | --- | --- |
| Raw request | Yes, only if debug/strict/failed policy allows and redacted first | Failed/debug only by default | `is_debug`, content flags, `contains_secret_redacted` when applicable |
| Raw response | Yes for failed/refused/invalid output evidence; optional for success | Failed/refusal retained by default; successful payload cleanup eligible | `may_contain_provider_response`, text/image flags |
| Raw invalid JSON | Yes | Failed-attempt payload retained by default | `may_contain_provider_response`, `may_contain_translation` if relevant |
| Refusal response excerpt | Prefer sanitized text metadata; raw response optional | Failed-attempt payload when useful | Provider response flag; no secrets |
| Stack trace / exception | Prefer sanitized log metadata; raw debug artifact only if redacted | Debug only | `is_debug`, `contains_secret_redacted` |
| Image/crop/output temp file | Yes through ArtifactService only | Depends on artifact type/attempt outcome | image/original flags as appropriate |

Raw payloads are never SQLite BLOBs. Provider Adapter returns temp refs or raw bytes to StageExecutor; ArtifactService decides official path, hash, metadata, retention class, and storage state.

## 6. Normal Path

| Step | Contract behavior |
| --- | --- |
| 1 | StageExecutor loads durable context, hashes, profile snapshot, and provider config refs. |
| 2 | StageExecutor persists WorkflowAttempt `running` before provider call. |
| 3 | Provider Adapter validates input contract without DB access and calls FakeProvider/real tool. |
| 4 | Provider returns success envelope with sanitized metadata and any temp file refs. |
| 5 | StageExecutor asks ArtifactService to register official artifacts where needed. |
| 6 | StageExecutor persists ToolRunLog with `status = succeeded`, sanitized metadata, artifact ids. |
| 7 | QualityCheckService inspects output/artifacts and creates zero or more QualityIssues. |
| 8 | StageExecutor returns normalized stage evidence to WorkflowLoopEngine. |
| 9 | WorkflowLoopEngine persists WorkflowDecision and accepted result/pointer/status updates through Repository/DAO. |

No provider secret is copied into project.db, ToolRunLog, WorkflowAttempt, raw payload artifact, QualityIssue, or WorkflowDecision.

## 7. Failure / Edge Path

| Edge case | Provider Adapter result | Attempt/log evidence | Quality/decision input |
| --- | --- | --- | --- |
| Timeout | `provider_timeout`, retry hint `transient` | Attempt `failed`; ToolRunLog `failed` | QualityCheck may create timeout/provider issue; WorkflowLoopEngine may retry/fallback/pause/block. |
| API key missing/invalid | `provider_unavailable` + `provider_missing_config` or `provider_invalid_config` | Attempt `failed`; no secret in message | WorkflowLoopEngine may pause for config, fallback, or block. |
| Rate limited/quota | `provider_unavailable` + stage code | Attempt `failed`; sanitized HTTP/status/reset metadata | Retry/fallback/block decided by loop/profile. |
| Invalid input | `invalid_input` | Attempt `failed`; input hash/config hash retained | Usually non-retryable until upstream/config changes. |
| Invalid JSON/schema | `invalid_output`; raw response temp ref optional | Attempt `failed`; raw response artifact if retained | Quality issue such as `translation_invalid_json`; loop may retry/fallback/block. |
| Partial translation | Success or partial-success envelope with missing block ids, or `invalid_output` if schema unusable | One page attempt remains explainable | Valid block results may persist; missing blocks get issues; loop decides retry/warning/pause/block. |
| Provider refusal | `provider_refusal`, `is_provider_refusal = true` | Attempt `refused`; ToolRunLog refused | QualityIssue root `provider_policy`; loop chooses safe fallback/manual/skip/warning/block. |
| Cleaner complex background | Structured non-refusal error/result code `cleaning_complex_background` | Attempt may be `failed` or `skipped` after loop decision, not adapter decision | Quality issue warning/blocking per profile; skip only by WorkflowLoopEngine. |
| Typeset overflow | Structured output with preview temp file and overflow flag, or `typeset_overflow` error if no usable output | Attempt/log preserve preview artifact if registered | Quality issue `typeset_overflow`; loop decides shorten/retry/warning/pause/block. |
| Artifact registration fails after success | Provider success remains non-official | StageExecutor reports `artifact_registration_failed` | Provider is not blamed unless temp file was invalid; loop decides retry/block. |

Concrete edge rule: if a provider returns HTTP 200 with a natural-language refusal instead of expected JSON, the adapter may classify `invalid_output` when schema parsing fails, but QualityCheckService must still be able to classify refusal if sanitized content/evidence indicates policy refusal. The final evidence should not lose refusal semantics.

## 8. Boundary Rules

| Component | Must do | Must not do |
| --- | --- | --- |
| Provider Adapter | Return structured success/error, sanitized metadata, temp refs, coarse retry hint. | Access SQLite, register artifacts, create QualityIssues, update attempts/logs, decide retry/fallback/skip/warn/block, mutate prompts to bypass policy. |
| StageExecutor | Persist attempt/log evidence through Repository/DAO, call ArtifactService, call QualityCheckService, return normalized stage evidence. | Hold write transaction across provider call, make final workflow decision, mark active pointers accepted outside loop decision. |
| ArtifactService | Promote temp files, hash, register artifacts, set retention/safety/storage state. | Decide workflow retry/fallback/warning/block. |
| QualityCheckService | Classify provider errors/refusals into issues, severity/blocking, discovered/root stage, suggested action. | Advance workflow state, update active pointers, decide fallback/retry/skip. |
| WorkflowLoopEngine | Decide retry/fallback/manual/skip/warning/pause/block from evidence/profile. | Reinterpret raw secrets, perform provider-policy evasion. |

Security boundary rules:

- Redaction occurs before any provider error enters logs, artifacts, issues, or decisions.
- Raw payload artifact registration must include safety flags and retention class.
- Failed/refusal payloads are retained by default only after redaction and only as filesystem artifacts.
- Successful raw payloads are cleanup eligible unless debug/strict policy says otherwise.
- Secret-looking values found during redaction are replaced, not hashed into user-visible text.

## 9. FakeProvider or FakeQuality Implications

FakeProvider should support deterministic modes for this proposal:

| Mode | Required output |
| --- | --- |
| `success` | Valid success envelope with sanitized metadata. |
| `timeout` | `provider_timeout`, no output artifact. |
| `unavailable` | `provider_unavailable`; variants for `provider_missing_config`, `translation_rate_limited`, `translation_quota_exceeded`. |
| `invalid_input` | `invalid_input` to test non-retryable upstream/config cases. |
| `invalid_json` | Translation raw response temp payload plus `translation_invalid_json`. |
| `schema_invalid` | Parsed but contract-invalid output plus `translation_schema_invalid`. |
| `partial_translation` | Valid translations for some TextBlocks plus missing block ids. |
| `provider_refusal` | `provider_refusal`, `is_provider_refusal = true`, refusal code and sanitized refusal metadata. |
| `complex_background` | Cleaning issue evidence without provider-policy refusal. |
| `typeset_overflow` | Preview temp file plus overflow evidence. |

FakeProvider should never require real OCR, LLM, cleaning, or typesetting tools. FakeQuality should be able to convert these outputs/errors into deterministic QualityIssues without inspecting any real provider payload.

## 10. Recovery / Audit Impact

| Evidence | Recovery/audit use |
| --- | --- |
| WorkflowAttempt status/error | Distinguishes `failed`, `refused`, `abandoned_after_crash`, `reused_cached`, and `succeeded`. |
| ToolRunLog metadata | Explains provider/tool/model/version, hashes, status, refusal marker, sanitized message, timing, retained artifact ids. |
| Raw failed/refusal artifacts | Optional replay/debug evidence; not accepted output unless replayed through normal validation. |
| QualityIssue | Export gate and user-visible problem source with discovered/root attribution. |
| WorkflowDecision | Explains whether the loop retried, fell back, paused, warned, skipped, or blocked. |

Recovery rules:

- Refusal evidence in ToolRunLog means a running attempt can reconcile to `refused`, not `abandoned_after_crash`.
- Failed invalid-output payloads may support diagnosis but do not become accepted results during MVP recovery unless normal validation/acceptance is replayed.
- Missing failed-attempt payloads reduce diagnostics but do not invalidate committed active results.
- Provider refusal tied to obsolete inputs may become `stale`/`superseded` as a QualityIssue, but the attempt/log remain audit history.
- Retry budgets are consumed only by persisted WorkflowDecision values, not by the adapter's `retry_hint`.

## 11. HARNESS Scenario Coverage

| Scenario | Coverage |
| --- | --- |
| P01 Provider success result | PASS: success envelope has structured output/metadata; adapter has no DB/artifact/issue ownership. |
| P02 Provider timeout or transient failure | PASS: `provider_timeout`/`provider_unavailable` carry standardized error evidence for retry/fallback/pause/block decisions. |
| P03 Provider refusal | PASS: refusal uses `provider_refusal`, `is_provider_refusal`, attempt `refused`, ToolRunLog refused, QualityIssue root `provider_policy`; no evasion behavior. |
| P04 Invalid structured output | PASS: `invalid_output` plus `translation_invalid_json`/`translation_schema_invalid`; raw response may be retained as failed artifact. |
| P05 Page translation partial output | PASS: one page attempt can preserve valid block outputs plus missing-block issue evidence. |
| A03 Register failed attempt evidence | PASS: failed/refusal raw payloads can be registered as redacted failed/debug artifacts through ArtifactService. |
| Q02 Translation invalid JSON | PASS: standardized error maps cleanly to invalid-output QualityIssue. |
| Q04 Provider refusal issue | PASS: refusal remains distinct from generic failure and feeds safe user guidance. |
| S02 Provider call fails before artifact output | PASS: attempt/log/error evidence exist without output artifact. |
| F03 Fake translation invalid JSON | PASS: FakeProvider mode produces invalid JSON evidence. |
| F04 Fake provider refusal | PASS: FakeProvider mode produces full refusal evidence chain. |

UNCLEAR until final synthesis: exact final enum spellings and whether `partial_success` is an explicit provider envelope state or a success envelope with issue candidates.

## 12. Rejected Alternatives

| Alternative | Rejected because |
| --- | --- |
| Collapse refusal into `provider_unavailable` or `model_error` | Loses policy semantics, weakens audit, and risks unsafe retry behavior. |
| Let Provider Adapter create QualityIssue | Violates architecture boundary and couples providers to persistence taxonomy. |
| Let Provider Adapter decide retry/fallback | Violates WorkflowLoopEngine ownership and makes retry budgets unrecoverable. |
| Store raw request/response JSON in SQLite | Violates large payload/artifact rules and increases secret leakage risk. |
| Keep full provider HTTP headers for debugging | Headers commonly contain secrets/cookies/tokens. |
| Preserve raw provider refusal text as user message | May expose sensitive content or provider internals; use sanitized message/message key. |
| Add provider-specific error enums for every vendor | Over-designed for MVP and makes FakeProvider slice harder. |
| Automatic prompt rewrite after refusal | Policy evasion risk and explicitly outside system boundary. |

## 13. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Refusal hidden inside invalid JSON/natural-language output | Workflow may retry unsafely or show wrong message. | QualityCheckService should detect refusal indicators in sanitized invalid-output evidence and produce refusal issue when confident. |
| Redaction misses a secret in debug artifacts | Secret leakage into local workspace. | Central redaction before artifact registration, `sanitization_version`, secret-pattern tests, default to not retaining successful raw payloads. |
| Over-broad raw payload retention | Privacy/storage growth. | Failed/refusal retained by default, success cleanup eligible, debug/strict policy explicit. |
| Error vocabulary too coarse | Workflow cannot distinguish pause-for-config vs retry. | Use stable `error_class` plus stage-specific `error_code` and sanitized metadata. |
| Error vocabulary too large | Implementation drift and UI complexity. | Keep MVP table small; add new codes only through design/update. |
| FakeProvider refusal differs from real provider shape | False confidence. | FakeProvider should simulate both explicit refusal error and refusal-like text in malformed output. |
| `retry_hint` mistaken for a decision | Boundary violation. | Name it advisory and require WorkflowDecision for all retry/fallback outcomes. |

## 14. Open Questions

1. Should the provider envelope include an explicit `partial_success` status, or should partial translation be represented as success with missing-block evidence consumed by QualityCheckService?
2. Should `provider_missing_config` and `provider_invalid_config` be `provider_unavailable` codes or separate `config_error` class? MVP can keep them under `provider_unavailable`.
3. What exact redaction component owns secret scanning before ArtifactService registration: StageExecutor helper, Config/Security service, or ArtifactService precondition?
4. Should raw refusal responses be retained by default, or only sanitized refusal summaries plus provider request ids?
5. How much provider HTTP metadata is safe: status code and retry-after only, or also sanitized response headers allowlist?
6. Should child-safety refusal always be blocking by default across profiles, or can profile policy route to pause/manual without export readiness?
7. Should `ToolRunLog.user_message` store only message keys for MVP, with localized text resolved elsewhere?
