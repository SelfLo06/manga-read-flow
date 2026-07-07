## 1. Scope

This proposal defines the minimum Provider Adapter contract for the FakeProvider single-Page backend vertical slice.

In scope:

| Area | Decision focus |
| --- | --- |
| Common envelope | One result shape for Detector, OCR, Translation, Cleaner, and Typesetter. |
| Minimal stage DTOs | Inputs and outputs needed to simulate each stage without real tools. |
| Temp file boundary | Provider may return temp file references; ArtifactService promotes them. |
| Responsibility split | Provider output vs StageExecutor vs ArtifactService vs QualityCheckService vs WorkflowLoopEngine. |

Out of scope: implementation code, SQL/ORM, API DTOs, real provider schemas, prompt templates, retention scheduler, full issue taxonomy, and full capability metadata.

## 2. Role Bias

Bias: maximize separation of concerns and keep Provider Adapters workflow-unaware.

Provider Adapter is a tool-call adapter only:

```text
structured input -> tool/local fake behavior -> structured output or standardized error + sanitized metadata
```

It must not become an artifact owner, retry engine, quality gate, recovery engine, cache, or workflow policy interpreter.

## 3. Assumptions

| Assumption | Rationale |
| --- | --- |
| StageExecutor constructs provider inputs from durable context. | Provider should not read SQLite or follow message chains across domain objects. |
| StageExecutor validates DTO shape enough to report invalid provider output. | Some invalid structured output is only knowable after parsing/schema validation. |
| ArtifactService promotes only files returned as temp references. | Provider cannot decide official workspace paths. |
| QualityCheckService receives provider result evidence and returns issue classifications/candidates. | Current GOAL/HARNESS require provider not to create QualityIssue. |
| WorkflowLoopEngine decides retry, fallback, skip, warning, pause, cancel, block, and active pointer acceptance. | Preserves workflow-state final design. |
| FakeProvider can produce deterministic payloads and temp files without real OCR/LLM/cleaning/typesetting. | Required for MVP-0 architecture validation. |

Source tension noted: HLD/data-model text sometimes says QualityCheckService "generates" or persists QualityIssue, while the execution-contract GOAL emphasizes boundary clarity. This proposal treats QualityCheckService as the classifier/issue-candidate owner; Repository/DAO persistence remains outside the Provider Adapter contract.

## 4. Proposed Contract

### Common provider result envelope

Every Provider Adapter returns exactly one `ProviderResult` envelope.

| Field | Required | Meaning |
| --- | --- | --- |
| `schema_version` | Yes | Contract version, e.g. `provider-result-v0.1`. |
| `stage` | Yes | `detection`, `ocr`, `translation`, `cleaning`, or `typesetting`. |
| `provider_identity` | Yes | Sanitized provider name/version/model/tool metadata. |
| `outcome` | Yes | `success`, `partial_success`, `failure`, `refusal`, or `invalid_output`. |
| `payload` | On success/partial | Stage-specific structured output. Empty/null on hard failure/refusal unless partial evidence exists. |
| `error` | On failure/refusal/invalid | Standardized provider error object. |
| `temp_files` | Optional | Temp file references produced by provider/tool. Not official artifacts. |
| `metrics` | Optional | Duration and safe usage estimates such as token counts; no prices required for MVP. |
| `diagnostics` | Optional | Sanitized debug hints and raw payload temp refs, if retained by policy. |

### Outcome meanings

| Outcome | Provider meaning | StageExecutor next responsibility |
| --- | --- | --- |
| `success` | Provider returned schema-valid, complete stage payload. | Register temp files if any, invoke quality check, return normalized stage evidence. |
| `partial_success` | Provider returned usable payload for some targets plus explicit missing/invalid target evidence. | Preserve valid payload, register relevant temp files, pass gaps to QualityCheckService. |
| `failure` | Provider/tool failed before usable output or returned standardized non-refusal error. | Persist attempt/tool evidence through workflow-side handling; QualityCheck may classify. |
| `refusal` | Provider refused content or policy path explicitly. | Record first-class refusal evidence; no bypass/evasion; loop decides next action. |
| `invalid_output` | Adapter or StageExecutor detected unparseable/schema-invalid provider output. | Optionally retain raw output temp ref; classify as invalid output; loop decides retry/block. |

### Standard error object

| Field | Required | Notes |
| --- | --- | --- |
| `error_code` | Yes | Minimal codes: `provider_unavailable`, `provider_timeout`, `provider_refusal`, `invalid_input`, `invalid_output`, `model_error`, `dependency_missing`, `file_io_error`, `unsupported_content`, `unknown_error`. |
| `error_class` | Yes | `transient`, `permanent`, `refusal`, `input`, `output`, `infrastructure`, or `unknown`. This is classification evidence, not a decision. |
| `is_provider_refusal` | Yes | True only for explicit refusal/policy outcomes. |
| `sanitized_message` | Yes | User/debug safe summary, no secrets or raw authorization. |
| `provider_error_ref` | Optional | Safe provider-side request/error id if available. |
| `raw_output_temp_ref` | Optional | Temp reference to raw response/error payload if retention policy allows. |

Provider may label an error `transient`; it may not decide "retry".

## 5. Minimal Vocabulary / Fields

### Common input fields

StageExecutor passes a stage-specific `ProviderRequest` with these common fields.

| Field | Required | Boundary rule |
| --- | --- | --- |
| `schema_version` | Yes | DTO version. |
| `stage` | Yes | One canonical workflow stage. |
| `request_id` | Yes | Correlation id generated outside provider. Not a database dependency. |
| `target` | Yes | Minimal target ids needed for echo/correlation: page and/or text_block ids. |
| `input_refs` | Yes | Official artifact ids plus resolved read-only file paths supplied by StageExecutor. |
| `language` | When relevant | Source/target language codes. |
| `config` | Yes | Sanitized provider config and generation/layout options. No secrets. |
| `idempotency_evidence` | Optional | Input/config/context hashes for provider echo/debug only. Provider does not decide cache reuse. |

### Provider identity and metadata

| Field | Required | Example |
| --- | --- | --- |
| `provider_name` | Yes | `fake_provider`, `manga_ocr`, `openai_compatible`. |
| `provider_kind` | Yes | `detector`, `ocr`, `translation`, `cleaner`, `typesetter`. |
| `provider_version` | Yes | Adapter or fake provider version. |
| `model_id` | Optional | Model or engine id. |
| `tool_version` | Optional | Local package/tool version. |
| `is_local` | Yes | True for local/fake/Pillow-style tools. |
| `capability_flags` | Optional | Sanitized facts such as `supports_page_translation`. |

### Temporary file reference

| Field | Required | Notes |
| --- | --- | --- |
| `temp_ref_id` | Yes | Opaque id unique within the provider result. |
| `kind` | Yes | `image`, `mask`, `json`, `text`, `preview`, `raw_request`, `raw_response`, `diagnostic`. |
| `temp_path` | Yes | Path under StageExecutor/provider temp directory only. |
| `media_type` | Optional | MIME/media hint. ArtifactService verifies later. |
| `expected_artifact_type` | Optional | Hint such as `cleaned_image`, `typeset_image`, `raw_provider_response`. |
| `safety_flags` | Yes | May contain original image/OCR/translation/provider response/secret-redacted marker. |

Temporary references are hints and evidence only. They are not official artifacts, not active pointers, and not valid for export.

### What must never be included

| Forbidden item | Reason |
| --- | --- |
| Raw API keys, tokens, credentials, authorization headers | Secrets must not enter logs, project.db, artifacts, or DTO examples. |
| Official artifact paths or artifact ids created by provider | ArtifactService owns official lifecycle and registration. |
| SQLite row writes, Repository handles, DAO method names | Provider must not access persistence. |
| `QualityIssue` ids or issue rows created by provider | QualityCheckService/Repository side owns classification/persistence. |
| Workflow decisions: retry/fallback/skip/warning/pause/cancel/block | WorkflowLoopEngine owns decisions. |
| Active pointer updates or result version numbers | Workflow acceptance and Repository own active selection. |
| Prompt templates or provider policy evasion instructions | Out of scope and unsafe. |
| Large image bytes inline | Filesystem artifacts only; SQLite and DTOs should not carry image BLOBs. |

## 6. Normal Path

### Stage sequence

| Step | Owner | Provider boundary |
| --- | --- | --- |
| 1. Load durable context | StageExecutor/Repository | Provider receives only distilled DTO. |
| 2. Create/start attempt | Workflow/Repository side | Provider does not persist attempt. |
| 3. Call provider | StageExecutor -> Provider Adapter | Provider returns `ProviderResult`. |
| 4. Promote temp files | StageExecutor -> ArtifactService | Provider temp refs become official only here. |
| 5. Validate/check output | QualityCheckService | Provider does not create issues. |
| 6. Return stage evidence | StageExecutor | WorkflowLoopEngine decides continue/retry/etc. |
| 7. Accept result/pointers | WorkflowLoopEngine + Repository | Provider never updates active pointers. |

### Stage-specific minimal payloads

| Stage | Minimal request | Minimal successful payload |
| --- | --- | --- |
| Detector | Page original input ref, page id, detection config. | `text_blocks[]` with provider-local block id, bbox/polygon optional, `source_direction`, `reading_order`, confidence, optional `mask_temp_ref`. |
| OCR | Page/block ids, crop or original+bbox input refs, language, OCR config. | `ocr_items[]` with text_block id, `source_text`, optional confidence, optional direction, optional `raw_output_temp_ref`. |
| Translation | Page id, ordered active OCR block texts, source/target languages, glossary snapshot identity/hash, context hash, sanitized config. | `translations[]` with text_block id, `translation_text`, optional used_terms, confidence label, needs_review flag, note; optional `glossary_candidates[]` only as ignored/deferred evidence. |
| Cleaner | Page id, base image ref, masks/geometry refs, block ids, cleaning mode. | `cleaned_image_temp_ref` for page-level output; optional `block_results[]` with cleaned/skipped flags and reason codes. |
| Typesetter | Page id, cleaned/base image ref, block geometry, active translation texts, font/layout config. | `typeset_image_temp_ref`; `layout_results[]` with text_block id, fitted flag, overflow flag, final font size/line count; optional preview temp ref. |

The payload intentionally contains content/results only, not database row shapes.

## 7. Failure / Edge Path

| Edge case | Provider envelope | Notes |
| --- | --- | --- |
| Timeout | `outcome = failure`, `error_code = provider_timeout`, `error_class = transient`. | Loop decides retry/fallback/pause/block. |
| Provider unavailable/API key missing | `failure`, `provider_unavailable` or `dependency_missing`. | Provider reports sanitized config absence; no secret details. |
| Explicit refusal | `refusal`, `provider_refusal`, `is_provider_refusal = true`. | First-class path; no evasion or transformed retry request. |
| Invalid JSON from translation | `invalid_output`, `invalid_output`, optional raw response temp ref. | If adapter cannot parse raw provider response, it still returns standardized invalid output. |
| Partial page translation | `partial_success` with valid `translations[]` and `missing_targets[]` or `invalid_targets[]`. | Valid block translations remain usable; gaps become quality/workflow evidence. |
| OCR empty text | Prefer `success` with empty `source_text` if tool completed honestly. | QualityCheckService classifies `ocr_no_text`; provider does not decide failure unless tool failed. |
| Cleaning complex background | Prefer `partial_success` or `success` with block result `skipped_by_provider_hint`. | This is evidence, not a workflow skip decision. Loop decides actual skip/warning/block. |
| Typesetting overflow | `partial_success` with preview temp ref and `overflow = true`. | Preview may be promoted; QualityCheck classifies overflow. |
| Temp file missing before registration | Provider may return `failure file_io_error` if it detects it. | If detected later, StageExecutor/ArtifactService reports registration failure. |

## 8. Boundary Rules

| Owner | Owns | Does not own |
| --- | --- | --- |
| Provider Adapter | Tool invocation, stage payload mapping, standardized provider errors, sanitized metadata, temp file emission. | DB access, official artifact registration, QualityIssue creation, workflow decisions, cache/reuse, active pointers, result versioning, retention. |
| StageExecutor | One-stage execution, request construction, provider call, basic output validation, ArtifactService call, normalized stage evidence. | Final retry/fallback/skip/warning/block decision, active pointer acceptance outside loop decision. |
| ArtifactService | Official path, copy/move/promotion, hash, size/media metadata, storage state, retention/cleanup checks. | Provider execution, workflow decisions, quality classification. |
| QualityCheckService | Output/error/artifact evidence classification, severity/blocking/root-stage/suggested-action candidates. | Provider calls, artifact lifecycle, workflow advancement, active pointer updates. |
| WorkflowLoopEngine | Continue/retry/fallback/skip/warning/pause/cancel/block/readiness decisions. | Tool calls, official artifact file operations, raw quality detection. |
| Repository/DAO | SQLite persistence and transactions. | Provider behavior and file lifecycle decisions. |

Hard rules:

- Provider must not write under official workspace artifact directories.
- Provider must not accept mutable domain objects; DTOs are value snapshots.
- Provider must not interpret ProcessingProfile beyond sanitized config values needed to run the tool.
- Provider must not retry internally except low-level transport retries hidden inside a client library that do not alter workflow semantics; if exposed, attempts must still be represented outside provider.
- Provider must not delete temp files after returning until StageExecutor/ArtifactService has had a chance to consume them.

## 9. FakeProvider or FakeQuality Implications

FakeProvider should implement the same envelope and stage payloads.

| Fake mode | Stage(s) | Required output |
| --- | --- | --- |
| `happy_path` | All | Deterministic text blocks, OCR text, translations, cleaned temp image, typeset temp image. |
| `ocr_fail_once` | OCR | First call `provider_timeout` or `model_error`; second call `success`. |
| `ocr_empty` | OCR | `success` with empty source text for one block. |
| `translation_invalid_json` | Translation | `invalid_output` with raw response temp ref. |
| `translation_refusal` | Translation | `refusal` with sanitized refusal metadata. |
| `translation_partial` | Translation | `partial_success`, valid translations for some blocks, missing target evidence for others. |
| `cleaning_complex_background` | Cleaning | `partial_success` or success payload with block-level cannot-clean evidence and optional unchanged/preview temp image. |
| `typesetting_overflow` | Typesetting | `partial_success`, preview temp ref, overflow layout result. |
| `missing_artifact_setup` | Any artifact stage | Fake/test setup removes official artifact after registration; provider contract only supports producing temp refs. |

FakeQuality is not required by this provider proposal, but it can classify based on envelope evidence: empty OCR text, invalid output, missing translation targets, refusal, cleaning cannot-clean hint, and overflow flag.

## 10. Recovery / Audit Impact

| Evidence | Recovery/audit value |
| --- | --- |
| `schema_version`, `stage`, `request_id` | Correlates ToolRunLog/WorkflowAttempt without provider reading DB. |
| Provider identity | Explains provider/model/tool provenance and cache keys. |
| Outcome/error code/class | Supports refused/failed/invalid/interrupted recovery paths. |
| Input/config/context hashes echoed in diagnostics | Helps audit mismatch; not cache authority. |
| Temp file refs and safety flags | Lets ArtifactService register failed evidence or successful outputs with correct safety metadata. |
| Partial target lists | Explains why one page attempt produced some results and issues for other blocks. |
| Sanitized messages | UI/debug trace without leaking secrets. |

Recovery rule: a temp file mentioned only in a ProviderResult is never accepted evidence after crash unless it is replayed through normal ArtifactService registration, QualityCheckService classification, and WorkflowLoopEngine acceptance. Official artifacts and committed result rows remain recovery truth.

## 11. HARNESS Scenario Coverage

| Scenario | Coverage | Proposal answer |
| --- | --- | --- |
| P01 Provider success result | PASS | `success` envelope with payload, metadata, optional temp refs; provider does not access DB/artifacts/issues. |
| P02 Provider timeout/transient failure | PASS | Standard `failure` with `provider_timeout` and `transient` evidence; loop decides. |
| P03 Provider refusal | PASS | `refusal` outcome, `is_provider_refusal`, sanitized metadata; no bypass path. |
| P04 Invalid structured output | PASS | `invalid_output` outcome; raw response may be temp evidence. |
| P05 Partial page translation | PASS | `partial_success` supports valid translations plus missing/invalid target evidence. |
| A02 Promote temp provider output | PASS | Temp refs only; ArtifactService promotion required. |
| A03 Failed attempt evidence | PASS | Raw request/response/diagnostic temp refs with safety flags support failed evidence registration. |
| Q01 OCR empty result | PASS | Empty OCR can be successful provider output, classified by QualityCheck. |
| Q02 Translation invalid JSON | PASS | `invalid_output`; provider does not create issue or decision. |
| Q03 Translation missing TextBlock | PASS | `partial_success` with missing target list. |
| Q04 Provider refusal issue | PASS | Envelope carries refusal evidence for QualityCheck/WorkflowLoopEngine. |
| Q05 Cleaning complex background | PASS | Provider can report cannot-clean evidence; loop decides skip/warning/block. |
| Q06 Typesetting overflow | PASS | Provider can return overflow flag and preview temp ref. |
| S01 Happy path execution | PASS | Sequence supports provider -> ArtifactService -> QualityCheck -> loop decision. |
| S02 Provider fails before artifact | PASS | Failure envelope has no required temp files and still provides audit evidence. |
| S03 Artifact registration fails | PASS | Provider output remains non-official; StageExecutor/ArtifactService report failure. |
| F01-F06 FakeProvider modes | PASS | Minimal deterministic modes listed. |
| F07 Fake missing artifact | PASS | Contract does not fake official artifacts; missing official artifact is ArtifactService/recovery test setup. |

## 12. Rejected Alternatives

| Alternative | Rejected because |
| --- | --- |
| Provider returns domain rows like `OCRResult` or `TranslationResult`. | Couples provider to persistence/versioning and active pointer rules. |
| Provider writes official artifacts directly. | Violates ArtifactService-only lifecycle, hash, retention, and missing-state invariants. |
| Provider creates `QualityIssue`. | Collapses tool output with quality policy and root-stage attribution. |
| Provider returns `should_retry`, `should_skip`, or `blocking`. | Makes Provider Adapter workflow-aware and conflicts with WorkflowLoopEngine. |
| Separate unrelated envelope per provider type. | Increases StageExecutor branching and weakens uniform failure/refusal handling. |
| Inline image bytes/base64 in DTOs. | Violates no-large-payload/SQLite discipline and bloats audit logs. |
| Treat provider refusal as generic failure. | Loses first-class policy/refusal semantics and risks unsafe retry behavior. |
| Make FakeProvider use simplified non-contract outputs. | Would fail to validate the actual StageExecutor/provider boundary. |

## 13. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `partial_success` semantics become too broad. | StageExecutor/QualityCheck may disagree on accepted valid outputs. | Limit to explicit valid targets plus explicit missing/invalid target evidence. |
| Provider metadata too sparse for idempotency audit. | Recovery/cache explanation weakens. | Require provider/model/tool identity and allow echoed input/config/context hashes. |
| Temp path misuse causes path traversal or official path writes. | File safety issue. | StageExecutor allocates temp root; ArtifactService validates/copies; provider gets no official path authority. |
| Error class mistaken for decision. | Provider could indirectly drive retry/block. | Name it classification evidence; WorkflowLoopEngine remains sole decision owner. |
| Raw payload temp refs leak sensitive content. | Privacy/security risk. | Safety flags, redaction marker, no secrets, retention policy outside provider. |
| FakeProvider masks real integration complexity. | Later provider schemas may need extension. | Keep schema versioned and minimal; defer production provider-specific fields to later adapter design. |

## 14. Open Questions

| Question | Blocking for this proposal? |
| --- | --- |
| Exact enum spelling for envelope fields and whether validation uses application constants or lookup tables. | No |
| Whether `partial_success` should be accepted for OCR per block or represented as multiple block-scoped provider calls. | No |
| Exact temp directory ownership and cleanup timing between StageExecutor and ArtifactService. | No, belongs to ArtifactService/StageExecutor synthesis. |
| Whether raw request payload temp refs should be allowed by default or only in debug/failed-attempt policy. | No, retention policy final design must decide. |
| Whether `glossary_candidates[]` belongs in TranslationProvider P0 payload or should be omitted entirely until P1. | No; FakeProvider can omit it. |
| Exact provider capability metadata beyond identity/local/GPU/license notes. | No, covered by another provider proposal. |
| Whether invalid structured output is detected inside adapter or by StageExecutor schema validation for each provider type. | No; both map to `invalid_output`. |
