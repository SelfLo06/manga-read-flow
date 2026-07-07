# Provider Adapter Contract v0.1

## 1. Scope

This contract covers the common Provider Adapter result/error envelope, provider metadata, capability metadata, and minimal stage contracts for:

- DetectorProvider
- OCRProvider
- TranslationProvider
- CleanerProvider
- TypesetterProvider

Provider Adapters call tools or fake tools. They do not own persistence, official artifacts, quality issues, retry/fallback/skip/warning/block decisions, cache reuse, active pointers, or policy evasion.

## 2. Common result envelope

Every provider call returns one `ProviderResult`.

| Field | Required | Meaning |
| --- | --- | --- |
| `schema_version` | Yes | `provider-result-v0.1`. |
| `stage` | Yes | `detection`, `ocr`, `translation`, `cleaning`, or `typesetting`. |
| `request_id` | Yes | Correlation id supplied by StageExecutor. |
| `provider` | Yes | Sanitized provider identity and metadata. |
| `outcome` | Yes | `success`, `partial_success`, `failure`, `refusal`, or `invalid_output`. |
| `payload` | Success/partial | Stage-specific structured output. Null for hard failure/refusal unless partial evidence exists. |
| `error` | Failure/refusal/invalid | Standard error envelope. |
| `temp_files` | Optional | Temp references only. They are not official artifacts. |
| `diagnostics` | Optional | Sanitized bounded metadata and debug hints. |
| `metrics` | Optional | Safe duration/usage estimates. Canonical timing belongs to StageExecutor/ToolRunLog. |

Outcome rules:

| Outcome | Meaning | Boundary rule |
| --- | --- | --- |
| `success` | Schema-valid complete output for the requested target. | Still requires artifact registration, quality check, and workflow acceptance. |
| `partial_success` | Some target outputs are valid and missing/invalid targets are explicit. | Valid outputs remain candidates; WorkflowLoopEngine decides acceptance. |
| `failure` | Tool/provider failed without usable output or refused semantics. | Loop decides retry/fallback/pause/block. |
| `refusal` | Provider explicitly refused content or policy path. | First-class refusal path; no bypass or evasion behavior. |
| `invalid_output` | Adapter or StageExecutor detected unparseable/schema-invalid output. | Raw payload may be retained after sanitization. |

## 3. Standard error envelope

`ProviderResult.error` has:

| Field | Required | Meaning |
| --- | --- | --- |
| `kind` | Yes | Coarse stable kind. |
| `code` | Yes | Stage-specific stable code. |
| `is_provider_refusal` | Yes | True only for explicit refusal/policy outcomes. |
| `retry_hint` | Optional | `transient`, `non_retryable`, or `unknown`; advisory only. |
| `sanitized_message` | Yes | Safe summary with no secrets or raw provider dump. |
| `provider_error_ref` | Optional | Safe provider request/error id when available. |
| `raw_output_temp_ref` | Optional | Temp ref to sanitized raw response/error payload if retention allows. |

Allowed `kind` values:

```text
provider_timeout
provider_unavailable
provider_refusal
invalid_input
invalid_output
model_error
dependency_missing
file_io_error
unsupported_content
unknown_error
```

`retry_hint` never consumes retry budget and never means `should_retry`. WorkflowLoopEngine decides all retries.

## 4. Provider metadata

Per-result provider metadata:

| Field | Required | Notes |
| --- | --- | --- |
| `provider_name` | Yes | Sanitized configured identity, for example `fake-translator-cloud`. |
| `provider_type` | Yes | `detector`, `ocr`, `translation`, `cleaner`, or `typesetter`. |
| `provider_version` | Yes | Adapter/provider version. |
| `model_id` | Nullable | Model/deployment id when applicable. |
| `tool_version` | Nullable | Local tool/library version when applicable. |
| `execution_location` | Yes | `local`, `cloud`, or `local_compatible_api`. |
| `capability_profile_hash` | Yes | Hash of selected capability/config subset. |
| `sanitization_version` | Required for errors/raw evidence | Redaction version used before persistence. |
| `fake_mode` | Fake only | Deterministic mode used. |
| `call_index` | Fake only | Durable/test-visible call index for retry tests. |

No raw API key, token, cookie, authorization header, signed URL, credential, or secret-bearing endpoint may appear.

## 5. Capability metadata

Capability metadata is small static selection/audit data, not a plugin framework.

Common capability fields:

| Field | Values |
| --- | --- |
| `provider_name` | Stable configured name. |
| `provider_type` | `detector`, `ocr`, `translation`, `cleaner`, `typesetter`. |
| `provider_version` / `tool_version` | Stable version string. |
| `default_model_id` | Nullable string. |
| `execution_location` | `local`, `cloud`, `local_compatible_api`. |
| `requires_gpu` | `false`, `optional`, `required`. |
| `policy_surface` | `none`, `provider_policy_possible`. |
| `license_note` | Nullable human-readable note. |
| `enabled` | Boolean selection eligibility. |
| `secret_ref` | Nullable reference only; never a secret value. |

Minimal stage capability flags:

| Provider type | Minimal flags |
| --- | --- |
| `detector` | `outputs_text_blocks`, `outputs_masks`, `supports_reading_order`, `supports_direction`, `supported_image_mime_types`. |
| `ocr` | `supported_source_languages`, `outputs_confidence`, `outputs_direction`, `accepts_crop_artifact`, `accepts_bbox`. |
| `translation` | `source_languages`, `target_languages`, `page_level`, `structured_output`, `supports_glossary`, `may_refuse_by_policy`, `supports_local_endpoint`. |
| `cleaner` | `cleaning_modes`, `outputs_image_file`, `can_skip_complex_background`, `requires_gpu`. |
| `typesetter` | `layout_modes`, `outputs_image_file`, `detects_overflow`, `supports_preview_artifact`, `font_requirements_note`. |

Deferred: dynamic probing, provider ranking, hardware sizing, pricing, vendor-specific schema registries, and license automation.

## 6. Common provider request fields

StageExecutor builds `ProviderRequest` DTOs from durable context.

| Field | Required | Rule |
| --- | --- | --- |
| `schema_version` | Yes | Request contract version. |
| `stage` | Yes | Canonical provider stage. |
| `request_id` | Yes | Correlation only. |
| `target` | Yes | Page/TextBlock ids for echo/correlation. |
| `input_refs` | Yes | Official artifact ids plus read-only paths supplied by StageExecutor. |
| `language` | When relevant | Source and target language codes. |
| `config` | Yes | Sanitized provider config. No secrets. |
| `hashes` | Yes | Input/config/context hashes for audit/request construction only. |
| `attempt_temp_root` | Yes for file output | Provider may write temp files only under this root. |

Providers receive value snapshots, not live domain objects or repository handles.

## 7. Temporary file references

| Field | Required | Meaning |
| --- | --- | --- |
| `temp_ref_id` | Yes | Unique within the provider result. |
| `kind` | Yes | `image`, `mask`, `json`, `text`, `preview`, `raw_request`, `raw_response`, or `diagnostic`. |
| `temp_path` | Yes | Under the attempt temp root only. |
| `media_type` | Optional | Provider hint; ArtifactService verifies. |
| `expected_artifact_type` | Optional | Hint such as `cleaned_image`; ArtifactService derives/validates final type. |
| `safety_flags` | Yes | Possible content flags; ArtifactService may only strengthen them. |

Temp refs are never official artifacts, never active pointers, and never recovery truth after crash unless replayed through normal registration, quality classification, and workflow acceptance.

## 8. Stage-specific minimal contracts

### Detector

Request:

- Page id and original image official artifact id/read-only path.
- Detection config hash.
- Image metadata when available.

Success payload:

| Field | Required | Notes |
| --- | --- | --- |
| `text_blocks[]` | Yes | Provider-local candidates. |
| `provider_block_ref` | Yes | Correlation only; Repository assigns real TextBlock ids. |
| `bbox` | Yes | Rectangle in image coordinates. |
| `polygon` | Optional | Polygon if available. |
| `source_direction` | Yes | `horizontal`, `vertical`, or `unknown`. |
| `reading_order` | Optional | Candidate order. |
| `confidence` | Optional | Numeric confidence if available. |
| `mask_temp_ref` | Optional | Temp mask candidate only. |

Detector does not OCR text and does not create TextBlock rows.

### OCR

Request:

- Page/TextBlock ids.
- Crop artifact or original artifact plus bbox/geometry.
- Source language and OCR config hash.

Success payload:

| Field | Required | Notes |
| --- | --- | --- |
| `ocr_items[]` | Yes | Usually one per target TextBlock. |
| `text_block_id` | Yes | Caller-supplied id. |
| `source_text` | Yes | May be empty if tool completed but found no text. |
| `confidence` | Optional | Null allowed. |
| `detected_direction` | Optional | Direction evidence. |
| `raw_output_temp_ref` | Optional | Sanitized raw payload temp ref. |

Empty OCR text is provider success evidence; QualityCheckService classifies `ocr_text_missing`.

### Translation

Request:

- Page id.
- Ordered active OCR source text by TextBlock.
- Source/target languages.
- Glossary version id/number/hash.
- Page context hash.
- Sanitized generation config and provider metadata.

Success payload:

| Field | Required | Notes |
| --- | --- | --- |
| `translations[]` | Yes | One per translated TextBlock. |
| `text_block_id` | Yes | Required for every item. |
| `translation_text` | Yes | Candidate Chinese translation. |
| `used_terms` | Optional | Term ids/texts used. |
| `confidence` | Optional | `low`, `medium`, `high`, or provider-specific safe label. |
| `needs_review` | Optional | Provider evidence only. |
| `note` | Optional | Sanitized short note. |

Partial payload:

- `translations[]` for valid blocks.
- `missing_targets[]` for omitted TextBlocks.
- `invalid_targets[]` for block outputs present but unusable.

Page-level translation can produce valid per-block result candidates and issues for missing/invalid blocks under one attempt.

### Cleaner

Request:

- Page id.
- Base image official artifact id/read-only path.
- Masks/geometry refs.
- TextBlock ids and cleaning mode.

Success payload:

| Field | Required | Notes |
| --- | --- | --- |
| `cleaned_image_temp_ref` | Optional | Page-level cleaned temp image if produced. |
| `block_results[]` | Optional | Per-block evidence. |
| `text_block_id` | Per block | Caller id. |
| `status_hint` | Per block | `cleaned`, `unchanged`, or `cannot_clean`. Evidence only. |
| `reason_code` | Optional | Example: `cleaning_complex_background`. |

Cleaner may report cannot-clean evidence. It does not decide workflow skip.

### Typesetter

Request:

- Page id.
- Cleaned/base image official artifact id/read-only path.
- Active translation texts and hashes.
- TextBlock geometry.
- Font/layout config hash.

Success payload:

| Field | Required | Notes |
| --- | --- | --- |
| `typeset_image_temp_ref` | Optional | Main output if produced. |
| `preview_temp_ref` | Optional | Preview for overflow/warning. |
| `layout_results[]` | Yes | Per-block layout evidence. |
| `text_block_id` | Per block | Caller id. |
| `fitted` | Per block | Whether text fit target constraints. |
| `overflow` | Per block | True if overflow occurred. |
| `final_font_size` | Optional | Evidence only. |
| `line_count` | Optional | Evidence only. |

Overflow evidence is classified by QualityCheckService. WorkflowLoopEngine decides upstream retry, warning, pause, or block.

## 9. Forbidden responsibilities

Provider Adapter must never:

- Access SQLite, Repository, DAO, or project.db.
- Register official artifacts, choose official relative paths, or write official workspace paths.
- Create QualityIssues or message keys.
- Decide retry, fallback, upstream retry, skip, warning, pause, cancel, block, readiness, or export.
- Update active OCR, translation, cleaned, typeset, or mask pointers.
- Decide cache reuse or idempotent rerun.
- Consume retry/fallback budgets.
- Interpret provider refusal with prompt rewriting, content laundering, obfuscation, jailbreak, or policy-evasion logic.
- Persist secrets or include raw credentials in diagnostics, logs, or temp payloads.

## 10. Refusal handling

Refusal requires:

| Surface | Required marker |
| --- | --- |
| ProviderResult | `outcome = refusal`. |
| Error envelope | `kind = provider_refusal`, `is_provider_refusal = true`, stage-specific refusal `code`. |
| Provider metadata | Sanitized provider/model/config refs only. |
| Quality issue draft | `issue_type = provider_refusal`, `root_stage = provider_policy`. |
| Workflow decision input | Refusal outcome, attempt/log refs, issue draft, profile snapshot, fallback/refusal policy. |

Provider refusal is not retryable against the same provider as an evasion tactic. Allowed next paths, chosen only by WorkflowLoopEngine, are configured fallback/local provider, manual input, allowed warning/skip when valid, pause, or block.
