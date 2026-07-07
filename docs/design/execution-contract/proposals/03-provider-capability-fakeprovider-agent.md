# Provider Capability and FakeProvider Proposal

## 1. Scope

This proposal defines the minimum Provider capability metadata and FakeProvider behavior needed for the FakeProvider single-Page backend vertical slice.

In scope:

| Area | Decision focus |
| --- | --- |
| Provider capability metadata | Small compatibility and audit fields only. |
| Local/cloud distinction | Enough for privacy, fallback, API-key, and refusal handling. |
| GPU requirement | Enough for MVP resource downgrade and provider selection. |
| License note | Human-readable warning/trace field, not legal automation. |
| FakeProvider | Deterministic stage outputs, failures, and evidence hooks. |

Out of scope: generic plugin registry, marketplace, provider discovery protocol, real provider prompts, real OCR/LLM/cleaning/typesetting integrations, DDL, ORM, migrations, API handlers, frontend code, and real provider JSON schemas.

## 2. Role Bias

Bias: make FakeProvider implementation-ready while keeping Provider capability metadata intentionally boring.

Design pressure:

| Prefer | Avoid |
| --- | --- |
| Static built-in fake provider configs | Dynamic plugin loading. |
| Stable string fields already aligned with `ProviderConfig` | Deep capability negotiation. |
| Deterministic fixture-style outputs keyed by mode | Randomized fake behavior. |
| StageExecutor/WorkflowLoopEngine decides from evidence | FakeProvider embedding workflow decisions. |

## 3. Assumptions

| Assumption | Rationale |
| --- | --- |
| `ProviderConfig` lives in `app.db`; execution evidence lives in `project.db`. | Matches data-model baseline. |
| Capability metadata is read before execution by workflow/config code, not by Provider Adapter from SQLite. | Preserves Provider Adapter boundary. |
| FakeProvider may use temp files but never official artifact paths. | ArtifactService owns official lifecycle. |
| The first vertical slice uses one Page and deterministic fixture IDs supplied by StageExecutor context. | Keeps tests reproducible. |
| `docs/HLD-v0.2.md` is the current HLD input because it is present and accepted as detailed-design baseline. | Matches task instruction. |

No blocking conflict found for this proposal. One vocabulary drift is already resolved by workflow-state final docs: use `export_check`, `done`, and `succeeded/succeeded_with_warnings` rather than older HLD/SRS names.

## 4. Proposed Contract

Decision: provider capability metadata should be a small static record associated with provider configuration and copied into sanitized execution metadata. It should answer "can this provider be selected for this stage and how should evidence be interpreted?", not "how do we dynamically integrate arbitrary tools?"

Minimal capability record:

| Field | Required now | Purpose |
| --- | --- | --- |
| `provider_name` | Yes | Audit, cache key, issue/debug display. |
| `provider_type` | Yes | One of `detector`, `ocr`, `translation`, `cleaner`, `typesetter`. |
| `provider_version` or `tool_version` | Yes | Cache/idempotency and audit. FakeProvider uses stable fake versions. |
| `default_model_id` | Yes, nullable | Cache/audit. Required for translation/OCR if model-like. |
| `capabilities` | Yes | Compact stage-specific booleans/strings listed below. |
| `is_local` | Yes | Privacy/API-key/fallback distinction. |
| `requires_gpu` | Yes | Resource precheck and downgrade routing. |
| `license_note` | Yes, nullable | Human review of GPL/non-commercial/restricted tools. |
| `enabled` | Yes | Provider selection eligibility. |
| `secret_ref` | Yes, nullable | Cloud provider credential reference only; never raw secret. |

Provider result metadata returned per call:

| Metadata | Required now | Notes |
| --- | --- | --- |
| `provider_name`, `provider_type`, `provider_version`, `model_id` | Yes | Mirrors config/snapshot. |
| `is_local` | Yes | Evidence for cloud/local behavior and refusal paths. |
| `capability_profile_hash` | Yes | Hash of selected capability/config subset for audit. |
| `fake_mode` | FakeProvider only | Records deterministic mode used. |
| `call_index` | FakeProvider only | Supports retry/idempotency tests. |
| `sanitization_version` | Yes for errors/raw evidence | Confirms no secrets in logs/artifacts. |

## 5. Minimal Vocabulary / Fields

### Required Now

`capabilities` should be JSON-like but shallow. The final design can choose exact serialization; these are the required concepts.

| Provider type | Minimal capabilities now |
| --- | --- |
| `detector` | `outputs_text_blocks`, `outputs_masks`, `supports_reading_order`, `supports_direction`, `supported_image_mime_types`. |
| `ocr` | `supported_source_languages`, `outputs_confidence`, `outputs_direction`, `accepts_crop_artifact`, `accepts_bbox`. |
| `translation` | `source_languages`, `target_languages`, `page_level`, `structured_output`, `supports_glossary`, `may_refuse_by_policy`, `supports_local_endpoint`. |
| `cleaner` | `cleaning_modes`, `outputs_image_file`, `outputs_mask_artifact`, `can_skip_complex_background`, `requires_gpu`. |
| `typesetter` | `layout_modes`, `outputs_image_file`, `detects_overflow`, `supports_preview_artifact`, `font_requirements_note`. |

Cross-cutting fields:

| Field | Values / shape | Why now |
| --- | --- | --- |
| `execution_location` | `local`, `cloud`, `local_compatible_api` | More explicit than boolean for translation fallback. |
| `requires_gpu` | `false`, `optional`, `required` | SRS requires CPU downgrade and no high-end GPU requirement. |
| `license_note` | short string or `null` | SRS requires license awareness without legal automation. |
| `policy_surface` | `none`, `provider_policy_possible` | Needed to interpret cloud refusal safely. |

### Deferred

| Deferred metadata | Reason |
| --- | --- |
| Hardware sizing such as VRAM, CUDA version, model quantization | Needed for real local models, not FakeProvider vertical slice. |
| Dynamic capability negotiation or probing | Over-designed for MVP and risks plugin-framework drift. |
| Full provider-specific JSON schema registry | Execution-contract final docs should define minimal DTOs only. |
| Cost/pricing tables | Cost rollups are P1-ish and not needed for FakeProvider. |
| Safety taxonomy beyond refusal capability | Quality/error taxonomy owns issue classification. |
| License compatibility automation | `license_note` is trace metadata only for now. |
| Provider ranking/scoring | Workflow profile/fallback policy can reference configured providers directly. |

## 6. Normal Path

| Stage | FakeProvider success output | Temp files | Expected downstream evidence |
| --- | --- | --- | --- |
| `detection` | Two deterministic TextBlock candidates with bbox, polygon, direction, reading order, confidence, mask temp refs. | Optional mask temp files. | TextBlocks persisted by Repository; mask artifacts promoted by ArtifactService if retained. |
| `ocr` | For each block: `source_text`, confidence, direction, raw metadata. | Optional raw OCR payload temp file and crop echo. | `OCRResult` rows, active OCR pointers, ToolRunLog, attempt success. |
| `translation` | Page-level structured output with one translation per requested TextBlock, used terms, confidence, needs_review false. | Optional raw request/response temp payloads depending retention/debug policy. | `TranslationResult` rows, active translation pointers, shared attempt/tool run. |
| `cleaning` | Cleaned image temp file plus per-block cleaning report. | Cleaned image temp file. | ArtifactService promotes cleaned image; active cleaned pointer after accepted decision. |
| `typesetting` | Typeset image temp file plus layout report with no overflow. | Typeset image temp file. | ArtifactService promotes typeset image; active typeset pointer after accepted decision. |

Normal capability metadata for built-in FakeProvider configs:

| Fake config | `provider_type` | `execution_location` | `requires_gpu` | `license_note` |
| --- | --- | --- | --- | --- |
| `fake-detector` | `detector` | `local` | `false` | `Test-only fake provider; no external license dependency.` |
| `fake-ocr` | `ocr` | `local` | `false` | Same. |
| `fake-translator-cloud` | `translation` | `cloud` | `false` | Test-only; simulates provider policy/refusal. |
| `fake-translator-local` | `translation` | `local_compatible_api` | `optional` | Test-only; simulates local fallback path. |
| `fake-cleaner` | `cleaner` | `local` | `false` | Same. |
| `fake-typesetter` | `typesetter` | `local` | `false` | Same. |

Rationale: separate fake cloud and fake local translator configs let tests prove provider replacement/fallback without changing workflow code or adding real APIs.

## 7. Failure / Edge Path

Deterministic fake modes should be selected by stage and target through the test profile or StageExecutor input, not through hidden globals.

| Mode | Applies to | Provider return | Evidence required |
| --- | --- | --- | --- |
| `success` | All provider types | Structured success payload. | Successful attempt/tool metadata and optional artifacts. |
| `empty_output` | OCR, detection, translation | Success-shaped payload with empty text/list. | QualityCheck can create `ocr_no_text`, `detect_no_text`, or missing translation issue. |
| `transient_failure_once` | All provider types | First call returns `provider_timeout`; second call with same key returns success. | Retry path: failed attempt, `retry_same_stage`, later success; call index proves retry. |
| `provider_timeout` | All provider types | Standardized error `provider_timeout`, retryable hint true. | No QualityIssue from provider; StageExecutor preserves error evidence. |
| `provider_unavailable` | Cloud/local endpoint-like providers | Standardized error `provider_unavailable` or config/dependency missing. | Workflow can fallback/pause/block; no provider-owned decision. |
| `provider_refusal` | Translation primarily; optional OCR/cleaner unsupported-content tests | Standardized error `provider_refusal`, `is_provider_refusal = true`, sanitized refusal code. | ToolRunLog refused, attempt refused, QualityIssue root `provider_policy`, decision fallback/manual/warn/block. |
| `invalid_json` | Translation | Returns raw response temp payload plus standardized `invalid_output` or success with unparseable raw body caught by StageExecutor. | Raw response artifact may be retained; invalid-output issue; retry/block test. |
| `partial_translation` | Translation | Valid structured response omits one requested TextBlock and optionally marks one invalid. | Valid results persist; missing/invalid block issue; page-scoped attempt remains explainable. |
| `cleaning_complex_background` | Cleaner | Structured result marks specific block/region `skipped_reason = complex_background`; may omit cleaned change for that region. | Warning issue, `skip_target`/`mark_warning` decision; no pure ready_for_export if unresolved skip remains. |
| `typeset_overflow` | Typesetter | Temp preview file plus layout report with overflow block ids. | Preview artifact registration, overflow issue, decision warning/pause/block/retry_upstream. |
| `missing_artifact` | Artifact/recovery test setup, not provider-owned | FakeProvider may return a temp path that test deletes before registration only for S03-style tests; active artifact deletion should be external setup. | ArtifactService detects missing/hash mismatch; workflow receives artifact-state evidence. |

Boundary note: `missing_artifact` is not a normal provider mode for active artifacts. Provider may simulate "temp output disappeared before registration" for StageExecutor/ArtifactService failure tests, but deleting official active artifacts is a harness/test setup action outside Provider Adapter.

## 8. Boundary Rules

| Rule | Capability/FakeProvider implication |
| --- | --- |
| Provider Adapter must not access SQLite. | FakeProvider receives all mode/config/context as input; it never reads provider_configs or project.db. |
| Provider Adapter must not register official artifacts. | FakeProvider returns temp file references only. |
| Provider Adapter must not create QualityIssue. | FakeProvider returns structured output/error evidence; QualityCheckService classifies. |
| Provider Adapter must not decide retry/fallback/skip/warning/block. | Fake modes may expose hints such as retryable, but WorkflowLoopEngine owns decisions. |
| Provider Adapter must not own artifact cleanup. | Temp cleanup policy belongs outside provider or to StageExecutor/ArtifactService boundary design. |
| Provider Adapter must not bypass policy. | Refusal mode returns refusal evidence; no prompt mutation or evasion branch. |
| Capability metadata must not contain secrets. | `secret_ref` only; snapshots/logs copy sanitized identity only. |
| Image/large payload bytes must not enter SQLite. | Fake raw payloads and temp images are files if retained; DB stores artifact metadata only. |
| Original images are never overwritten. | Fake cleaner/typesetter always create new temp output files from inputs. |

## 9. FakeProvider or FakeQuality Implications

FakeProvider should be deterministic across reruns for the same scenario key.

Recommended scenario key:

```text
stage + target_type + target_id + input_hash + config_hash + fake_mode + call_index_policy
```

Deterministic payload guidance:

| Provider | Stable fake output |
| --- | --- |
| Detector | Fixed two-block layout proportional to image dimensions; block ids are assigned by caller/repository, not provider. |
| OCR | Text from `reading_order`: e.g. block 1 "こんにちは", block 2 "ありがとう"; confidence `0.98` / `0.94`. |
| Translation | Chinese text mapped by source hash or reading order; one page group key; stable used_terms empty list unless glossary fixture says otherwise. |
| Cleaner | Writes a simple deterministic image copy/marking to temp output; reports skipped regions in skip mode. |
| Typesetter | Writes deterministic preview/typeset image temp file; overflow report lists target block ids in overflow mode. |

FakeProvider must emit enough non-secret metadata for:

| Test need | Evidence |
| --- | --- |
| Retry | `fake_mode`, `call_index`, attempt status/error, retryable error class. |
| Refusal | `error_code`, `is_provider_refusal`, sanitized refusal reason, cloud/local metadata. |
| Invalid output | raw response temp artifact ref or invalid-output error with parser location summary. |
| Skip | structured `skipped_regions` / `skipped_text_block_ids` without deciding workflow skip. |
| Overflow | preview temp file ref plus `overflow_text_block_ids`, min font size, fitted false. |
| Missing artifact | temp file path plus artifact registration failure evidence, or external deletion of official artifact for recovery tests. |

FakeQuality implication: FakeQualityCheck should not need its own independent scenario engine for these cases. It can classify deterministic FakeProvider outputs/errors. A tiny forced-issue mode may be useful later for export-gate tests, but this proposal does not require it for provider capability.

## 10. Recovery / Audit Impact

| Evidence target | What must be persisted by workflow-side services |
| --- | --- |
| Capability identity | Sanitized provider name/type/version/model, capability hash, local/cloud/GPU/license summary. |
| Attempt replay | Stage, target, input/config/context hashes, fake mode, call index, status/error. |
| Tool run audit | Status, standardized error, `is_provider_refusal`, sanitized message, raw payload artifact ids when retained. |
| Artifact recovery | Official artifact metadata only after ArtifactService promotion; temp paths are not recovery truth. |
| Idempotency | Same input/config/context and provider metadata should produce reusable fake outputs; retry/failure evidence is not a successful cache hit. |
| Refusal recovery | Refusal remains auditable even if later local/manual fallback succeeds. |

Recovery decisions remain outside FakeProvider:

| Recovery condition | Owner |
| --- | --- |
| Running fake attempt with no durable evidence after crash | Recovery rules mark `abandoned_after_crash`. |
| Fake output temp file exists but no official artifact row | ArtifactService/StageExecutor may inspect, but MVP recovery treats it as non-official unless replayed through normal validation. |
| Official active artifact deleted | ArtifactService marks `missing`; WorkflowLoopEngine decides rebuild/retry/warn/block. |
| Fake retry mode succeeded on second call before crash | Reuse only if committed result/artifact/active pointer evidence exists. |

## 11. HARNESS Scenario Coverage

| Scenario | Coverage from this proposal |
| --- | --- |
| P01 Provider success result | PASS: capability metadata plus structured fake success outputs for all provider types. |
| P02 Provider timeout/transient failure | PASS: `provider_timeout` and `transient_failure_once` modes produce standardized errors and call-index evidence. |
| P03 Provider refusal | PASS: fake cloud translator refusal is first-class, sanitized, and marked provider-policy capable. |
| P04 Invalid structured output | PASS: `invalid_json` mode returns invalid raw payload/error evidence without provider deciding retry. |
| P05 Page translation partial output | PASS: `partial_translation` persists valid block outputs and missing-block evidence under one page attempt. |
| A02 Promote temporary provider output | PASS: cleaner/typesetter return temp refs only; ArtifactService promotion is required. |
| A03 Register failed attempt evidence | PASS: fake invalid/refusal/failure modes provide raw payload refs when retention/debug policy asks. |
| A04 Missing active artifact | PARTIAL: fake provider can help produce artifacts, but active artifact removal must be harness setup; ArtifactService owns detection. |
| Q01 OCR empty result | PASS: `empty_output` OCR mode produces empty text evidence. |
| Q02 Translation invalid JSON | PASS: `invalid_json` mode. |
| Q03 Translation missing TextBlock | PASS: `partial_translation` mode. |
| Q04 Provider refusal issue | PASS: refusal evidence includes root-policy metadata for QualityCheck classification. |
| Q05 Cleaning complex background | PASS: `cleaning_complex_background` mode. |
| Q06 Typesetting overflow | PASS: `typeset_overflow` mode with preview temp file. |
| S01 Happy path stage execution | PASS: all fake providers support success path with temp files and metadata. |
| S02 Provider call fails before artifact output | PASS: timeout/unavailable/refusal can return no output artifact. |
| S03 File produced but artifact registration fails | PASS: `missing_artifact` temp deletion variant covers provider-produced temp file failure, with StageExecutor reporting registration failure. |
| F01 Fake happy path | PASS: deterministic success modes for all stages. |
| F02 Fake OCR failure then retry | PASS: OCR `transient_failure_once`. |
| F03 Fake translation invalid JSON | PASS. |
| F04 Fake provider refusal | PASS. |
| F05 Fake cleaning skip | PASS. |
| F06 Fake typesetting overflow | PASS. |
| F07 Fake missing artifact | PASS with boundary note: official active missing is test setup plus ArtifactService detection. |

## 12. Rejected Alternatives

| Alternative | Rejection rationale |
| --- | --- |
| Design a generic plugin framework now. | Not needed for FakeProvider vertical slice and risks scope creep. |
| Let providers self-describe capabilities at runtime by probing. | Adds error modes and side effects before basic workflow contracts exist. |
| Store detailed hardware compatibility in capability metadata now. | Real GPU/model integration is later; MVP only needs required/optional/false downgrade signal. |
| Treat FakeProvider as one generic "do everything" provider type. | Hides stage-specific contracts and weakens provider replacement tests. |
| Make FakeProvider write official workspace artifacts directly. | Violates ArtifactService boundary and misses promotion failure tests. |
| Represent cloud refusal as `provider_timeout` or generic `failed`. | Loses policy semantics and can trigger unsafe retry/evasion-like behavior. |
| Random fake failures. | Makes recovery, idempotency, and retry tests flaky. |
| Put fake modes in global mutable state only. | Hurts reproducibility and parallel tests; mode must be part of task/profile/test input evidence. |

## 13. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Capability metadata becomes a plugin schema by accident. | Delays MVP and invites unsupported extension points. | Keep required fields aligned to `ProviderConfig` and stage selection only. |
| `requires_gpu` too coarse for real local tools. | Later provider selection may need more detail. | Defer VRAM/runtime fields to real-provider spike. |
| FakeProvider outputs diverge from future DTOs. | Tests may need churn. | Keep fake outputs minimal and stage-specific; final provider contract should reuse these evidence concepts. |
| Fake local/cloud translator split feels like real fallback automation. | Could imply P1 automatic fallback is done. | Capability only enables WorkflowLoopEngine tests; final profile decides manual/automatic fallback. |
| Missing artifact simulation crosses provider boundary. | Could teach implementation to let providers manage official files. | Restrict provider missing mode to temp registration failure; active artifact missing is external harness setup. |
| License note under-specifies legal risk. | Future real provider integration could miss restrictions. | Treat `license_note` as visible trace metadata now; require real-provider spike to revisit license review. |

## 14. Open Questions

| Question | Blocking? |
| --- | --- |
| Exact spelling of `provider_type`, `execution_location`, and `requires_gpu` enum-like values. | No; final design can standardize strings. |
| Should `requires_gpu` be boolean in `ProviderConfig` for P0 or tri-state in contract? | Non-blocking tension: schema outline says boolean, SRS downgrade needs nuance. Proposal recommends contract tri-state while storage may map `optional` through capabilities JSON. |
| Should FakeProvider call counters persist in ToolRunLog metadata or remain test-observable only through provider metadata? | No; retry tests need durable enough evidence, exact field can be final-design choice. |
| Should invalid JSON be represented as provider `invalid_output` or StageExecutor parse failure after provider success? | No; both can normalize to same StageExecutor result, but final contract should choose the main path. |
| Should `fake_mode` live in ProcessingProfileSnapshot settings or an implementation-only test harness config? | No; for auditability in architecture validation, it should be visible in sanitized attempt/tool metadata when used. |
| What minimal image fixture format should fake cleaner/typesetter write? | No; implementation can use tiny PNGs or derived copies as long as ArtifactService sees real files. |
