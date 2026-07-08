# 05 Artifact Taxonomy, Retention, and Safety Proposal

## 1. Scope

This proposal covers the minimum MVP-0 artifact taxonomy and retention/safety contract needed for the FakeProvider single-Page backend vertical slice.

In scope:

- Official artifact types for import, OCR support files, provider payload evidence, cleaning, typesetting, export-aware cleanup, and debug evidence.
- Storage states, retention classes, and safety flags for `ProcessingArtifact`.
- Cleanup boundaries that protect original images, active outputs, failed/refusal evidence, and recovery inputs.
- Classification of failed provider payloads and debug artifacts.

Out of scope:

- SQL DDL, ORM mappings, migrations, directory layout details, API handlers, frontend behavior, real provider prompts, and real provider integrations.
- Full export manifest design and full cleanup scheduler design.

## 2. Role Bias

Bias: maximize privacy and data safety while preserving recovery evidence.

Design stance:

- Prefer conservative safety flags. If content is uncertain, mark the relevant `may_contain_*` flag true.
- Retain enough failed/refusal evidence to explain workflow decisions, but never retain known secrets.
- Clean successful large payload bytes when safe, but never clean artifacts required for current export-effective state.
- Treat debug artifacts as sensitive opt-in diagnostics, not normal recovery inputs.

## 3. Assumptions

| Assumption | Rationale |
| --- | --- |
| `docs/HLD.md` is the latest HLD baseline. | It does not conflict on artifact safety. |
| Artifact type names are stable string vocabulary, not database enum DDL. | Exact enum enforcement is deferred by the data-model baseline. |
| `ProcessingArtifact` stores metadata only in SQLite. | Image bytes and large/raw payload bytes stay in the filesystem. |
| Text in `OCRResult` and `TranslationResult` may be stored as domain result data. | Raw provider request/response payloads are separate file artifacts when retained. |
| A "failed provider payload" means sanitized retained evidence. | API keys, tokens, secret headers, and raw credentials must never be persisted. |
| FakeProvider may create temp files only. | ArtifactService is the only official artifact lifecycle entry. |

## 4. Proposed Contract

### Decisions

| Decision | Contract | Rationale |
| --- | --- | --- |
| D1 | Official artifacts are only files registered by ArtifactService with path, hash, size, media type, retention class, storage state, provenance, and safety flags. | Prevents provider-owned paths and path-only domain rows. |
| D2 | MVP-0 uses a small artifact type vocabulary: `original_image`, `mask_image`, `ocr_input_crop`, `provider_raw_request`, `provider_raw_response`, `cleaned_image`, `typeset_image`, `typeset_preview_image`, `export_output`, `issue_snapshot`, `debug_bundle`. | Covers harness scenarios without a broad plugin/file taxonomy. |
| D3 | Storage states stay exactly: `present`, `metadata_only_cleaned`, `moved_to_trash`, `missing`, `deleted`. | Matches data-model and HLD v0.2 baseline. |
| D4 | Retention classes stay exactly: `permanent_original`, `active_result`, `failed_attempt_payload`, `successful_payload`, `debug`, `cache_rebuildable`, `export_output`, `trash_pending_delete`. | Matches the data-model baseline and separates safety from cleanup. |
| D5 | Failed/refusal/invalid-output payload evidence is `failed_attempt_payload` by default after redaction/sanitization. | Keeps retry/refusal/block decisions auditable. |
| D6 | Successful raw provider payload bytes are `successful_payload` and may become `metadata_only_cleaned`. | Result rows, hashes, attempts, logs, and decisions remain enough for recovery. |
| D7 | Active original, active mask, active cleaned, active typeset, export output, and retained failed-attempt evidence are not ordinary cleanup candidates. | Prevents cleanup from breaking preview, export readiness, recovery, or audit. |
| D8 | Debug artifacts are `debug`, `is_debug = true`, and retained only when the effective debug policy enables them. | Debug files may contain local images, OCR text, translations, and provider responses. |

### MVP-0 Artifact Types

| Artifact type | Typical stage | Required for MVP-0 | Default retention | Cleanup/rebuild rule | Safety flags |
| --- | --- | --- | --- | --- | --- |
| `original_image` | `import` | Yes | `permanent_original` | Never ordinary cleanup; only explicit permanent Project/Page delete. | `may_contain_original_image = true` |
| `mask_image` | `detection`, `cleaning` | Yes when mask materialized | `active_result` while active | Active mask not cleaned; replaced masks may become `cache_rebuildable` if geometry/source can rebuild. | Usually `may_contain_original_image = true` |
| `ocr_input_crop` | `ocr` | Yes when OCR uses a materialized crop | `cache_rebuildable` | Eligible after grace period if original, geometry, and config remain. | `may_contain_original_image = true`, may contain source text visually |
| `provider_raw_request` | Provider stages | Only when retained by policy/failure/debug | `failed_attempt_payload`, `successful_payload`, or `debug` | Failed retained; successful cleanable; debug policy controlled. | Set all applicable content flags; secrets must be absent/redacted |
| `provider_raw_response` | Provider stages | Yes for failed/refused/invalid output if safe to retain | `failed_attempt_payload` by default | Retained for audit; not ordinary cleanup in MVP-0. | `may_contain_provider_response = true`; maybe OCR/translation flags |
| `cleaned_image` | `cleaning` | Yes on accepted cleaning output | `active_result` while active | Active cleaned image protected; superseded cleanable only if rebuildable. | `may_contain_original_image = true` |
| `typeset_image` | `typesetting` | Yes on accepted typeset output | `active_result` while active | Active typeset protected; superseded cleanable only if rebuildable. | `may_contain_original_image = true`, `may_contain_translation = true` |
| `typeset_preview_image` | `typesetting` overflow/warning | Yes for overflow preview when produced | `failed_attempt_payload` if explaining issue, else `successful_payload` | Retain while issue open; later cleanup only after superseded/resolved policy. | `may_contain_original_image = true`, `may_contain_translation = true` |
| `export_output` | export service | Export-aware, actual export design owns creation | `export_output` | Not ordinary cleanup; user/export deletion or Project delete only. | Image/translation flags as applicable |
| `issue_snapshot` | `export_check`, export, quality/debug | Optional MVP-0 | `successful_payload` or `debug` | Cleanable unless referenced by ExportRecord/profile policy. | May contain OCR/translation/provider summaries |
| `debug_bundle` | any | Opt-in only | `debug` | Controlled by explicit debug retention policy. | Conservative flags, `is_debug = true` |

## 5. Minimal Vocabulary / Fields

No new P0 fields are required beyond the data-model baseline.

Required artifact metadata groups:

| Field group | Minimum fields |
| --- | --- |
| Identity/scope | `artifact_id`, `project_id`, optional `batch_id`, `page_id`, `text_block_id` |
| Owner | `owner_type`, `owner_id` |
| Classification | `artifact_type`, `source_stage`, `media_type` |
| Location/integrity | `relative_path`, `file_hash`, `hash_algorithm`, `byte_size`, `mime_type`, optional dimensions |
| Provenance | `workflow_attempt_id`, `tool_run_id`, optional `source_artifact_id` |
| Retention | `retention_class`, `storage_state`, `cleanup_eligible_at`, `cleaned_at`, `deleted_at` |
| Safety | `is_debug`, `may_contain_original_image`, `may_contain_ocr_text`, `may_contain_translation`, `may_contain_provider_response`, `contains_secret_redacted` |

Storage state semantics:

| State | Meaning | Boundary |
| --- | --- | --- |
| `present` | Registered file exists and hash matches. | Only state usable for preview/export/reuse as bytes. |
| `metadata_only_cleaned` | Bytes removed by retention policy; metadata remains. | Never use as file input. |
| `moved_to_trash` | File moved to Project trash by soft delete. | Restore requires hash validation. |
| `missing` | Expected file absent or hash mismatch. | ArtifactService reports; WorkflowLoopEngine decides. |
| `deleted` | Permanently removed after explicit delete or eligible cleanup. | Metadata can remain for audit if policy requires. |

Important non-states:

- `temp` is not an official storage state. Temp files are outside `ProcessingArtifact`.
- `orphan` is a recovery classification, not an official artifact state.

## 6. Normal Path

| Step | Artifact behavior | Acceptance boundary |
| --- | --- | --- |
| Import image | ArtifactService registers `original_image` as `present` and `permanent_original`; Page points to `original_artifact_id`. | Original file is never overwritten. |
| Detection | Register active `mask_image` if a mask file is produced. Optional overlays belong in `debug_bundle`, not MVP core. | TextBlock rows reference artifact IDs, not paths. |
| OCR | Register `ocr_input_crop` if materialized; retain raw OCR response only by failure/debug/strict policy. | OCRResult links input/raw artifacts when retained. |
| Translation | Successful translations become TranslationResult rows. Raw request/response is normally not retained unless profile/debug requires it. | Page-level attempt can create per-block results. |
| Cleaning | Cleaner temp output is promoted to `cleaned_image`; if accepted, Page active cleaned pointer is updated by workflow transaction. | Artifact registration alone does not make it active. |
| Typesetting | Typesetter temp output is promoted to `typeset_image`; accepted output becomes active via workflow decision. | Overflow preview uses `typeset_preview_image`. |
| Export check | No artifact required for readiness. Export output, when produced by export design, is `export_output`. | Export readiness requires active typeset artifact `present` and hash-valid. |

## 7. Failure / Edge Path

| Edge case | Artifact classification | Workflow/audit effect |
| --- | --- | --- |
| Provider timeout before output | No output artifact required; optional sanitized error evidence may be `provider_raw_response` with `failed_attempt_payload`. | Attempt/log/issue/decision explain retry/fallback/block. |
| Invalid translation JSON | Retain sanitized `provider_raw_response` as `failed_attempt_payload`; no TranslationResult for invalid blocks. | QualityCheck can create invalid-output issue. |
| Partial Page translation | Valid block outputs become TranslationResults; retained raw response is `failed_attempt_payload` if needed to explain missing blocks. | One page attempt remains auditable. |
| Provider refusal | Retain sanitized refusal response/evidence as `provider_raw_response` with `failed_attempt_payload`. | Refusal is first-class evidence, not a crash. |
| File produced but registration fails | Temp file is not official; no active pointer can reference it. | Recovery treats it as abandoned/orphan unless replayed through normal registration. |
| Active artifact missing or hash-invalid | ArtifactService sets `storage_state = missing`. | WorkflowLoopEngine decides rebuild, warning, pause, or block. |
| Successful raw payload cleanup | Set `storage_state = metadata_only_cleaned`; keep hash/provenance and attempt/log/result metadata. | Recovery may reuse committed result rows, not cleaned bytes. |
| Debug bundle retained | Classify as `debug`, `is_debug = true`, with conservative safety flags. | Useful for inspection, not required for workflow correctness. |

## 8. Boundary Rules

- Provider Adapters may return temp file references and structured metadata only.
- Provider Adapters must not choose official `relative_path`, `storage_state`, `retention_class`, or active pointers.
- ArtifactService owns official registration, path generation, hash calculation, storage state, retention class application, cleanup, trash moves, and missing checks.
- ArtifactService must not decide retry, fallback, skip, warning, pause, block, or export readiness.
- Repository / DAO is the only SQLite writer. SQLite stores artifact metadata, never image BLOBs or raw large payload bytes.
- QualityCheckService may classify issues from artifact/provider evidence, but must not update active pointers or storage states.
- WorkflowLoopEngine owns whether a registered artifact becomes accepted/current through active pointer updates and decisions.
- Cleanup must check active pointers and protected retention classes immediately before deleting bytes.
- If secret redaction is uncertain, do not persist the full raw payload. Persist sanitized metadata or a sanitized evidence artifact instead.

## 9. FakeProvider or FakeQuality Implications

| Fake mode | Required fake artifact behavior |
| --- | --- |
| Happy path | Fake outputs temp mask, crop if needed, cleaned image, and typeset image; ArtifactService registers official artifacts. |
| OCR failure then retry | First attempt may produce sanitized failed `provider_raw_response`; second attempt produces valid OCR evidence/result. |
| Translation invalid JSON | Fake returns invalid raw response; StageExecutor/ArtifactService can retain it as failed payload. |
| Provider refusal | Fake returns refusal metadata and optional sanitized raw response; no bypass or prompt mutation appears. |
| Partial translation | Fake returns valid translations for some TextBlocks and missing others; raw response may be retained as failed/partial evidence. |
| Cleaning skip | Fake cleaner produces no cleaned output or a skipped marker; no active cleaned pointer unless workflow accepts a valid base strategy. |
| Typesetting overflow | Fake typesetter produces `typeset_preview_image`; QualityCheck can classify overflow. |
| Missing artifact | Test setup deletes a registered active artifact; ArtifactService marks `missing`. |

FakeQuality implication:

- FakeQuality should be able to assert issue classification from provider result and artifact metadata without reading secrets or requiring raw payload bytes.
- Safety flag expectations should be deterministic per fake mode.

## 10. Recovery / Audit Impact

| Artifact class | Recovery role | Audit role |
| --- | --- | --- |
| `permanent_original` | Required root input. Missing original blocks recovery/export. | Proves source file identity. |
| `active_result` | Required for active mask/cleaned/typeset preview/export when applicable. | Proves selected current file output. |
| `failed_attempt_payload` | Not normally accepted as domain output, but supports retry/refusal/invalid-output explanation. | Preserved by default for workflow decisions. |
| `successful_payload` | Not required after committed result rows exist. | May be cleaned to metadata-only. |
| `cache_rebuildable` | Can be regenerated from protected upstream inputs and hashes. | Useful but not essential. |
| `debug` | No recovery dependency unless separately classified as failed evidence. | Sensitive diagnostic aid only. |
| `export_output` | Does not define workflow readiness. Missing export output affects export history/re-export only. | User-visible export history. |

Recovery rules:

- Recovery trusts committed domain rows, active pointers, official artifacts, hashes, attempts, logs, issues, and decisions.
- Recovery does not promote temp/orphan files into active results in MVP-0.
- `metadata_only_cleaned` preserves audit metadata but is not a usable file input.
- Missing failed/debug payload should degrade diagnostics, not block the page, unless a current decision explicitly depends on that evidence.

## 11. HARNESS Scenario Coverage

| Scenario | Coverage |
| --- | --- |
| P01 Provider success result | Success payloads can be unretained/metadata-only while committed results and official output artifacts remain. |
| P03 Provider refusal | Refusal evidence is `failed_attempt_payload` with provider-response safety flags and no evasion path. |
| P04 Invalid structured output | Invalid raw response can be retained as failed evidence without creating result rows. |
| P05 Partial Page translation | Valid result rows and failed/partial response evidence can coexist under one attempt. |
| A01 Register original image | `original_image` is `permanent_original`, hash-recorded, and never overwritten. |
| A02 Promote temporary provider output | Temp files become official only through ArtifactService registration. |
| A03 Register failed attempt evidence | Failed/refusal/debug classifications, retention classes, and safety flags are defined. |
| A04 Missing active artifact | `missing` is a storage state set by ArtifactService; workflow decides response. |
| A05 Artifact cleanup boundary | Protected classes and active pointers prevent cleanup from breaking recovery/export. |
| S03 File produced but registration fails | Unregistered temp output is non-official and cannot become active. |
| F03 Fake translation invalid JSON | Fake raw response retention is testable. |
| F04 Fake provider refusal | Refusal evidence and safety flags are testable. |
| F06 Fake typesetting overflow | `typeset_preview_image` retention is testable. |
| F07 Fake missing artifact | Missing state transition is testable. |

## 12. Rejected Alternatives

| Alternative | Rejection rationale |
| --- | --- |
| Store images or raw payload BLOBs in SQLite. | Violates hard invariant and worsens privacy, backup, and cleanup behavior. |
| Let Provider Adapter write official workspace paths. | Breaks ArtifactService ownership and makes recovery unsafe. |
| Use only file paths on Page/OCR/Translation rows. | Loses hash, retention, safety, and missing-state evidence. |
| One generic `file` artifact type. | Cleanup and safety policy would become ambiguous. |
| Retain all successful raw provider payloads forever. | Increases sensitive data exposure and storage without improving MVP recovery. |
| Auto-clean failed/refusal payloads as soon as a retry succeeds. | Loses audit trail for retry budget, refusal handling, and invalid-output decisions. |
| Treat debug bundles as failed evidence. | Debug retention may be short-lived and opt-in; failed evidence must be explicitly protected. |
| Add rich P1 visual artifacts now, such as detection overlays and full export manifests. | Useful later, but not required for MVP-0 execution contract. |

## 13. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Sensitive failed/debug payload retention | Local OCR text, translations, original image snippets, or provider responses may be exposed. | Redact secrets, set safety flags, make debug opt-in, and keep future explicit privacy purge as an open design. |
| Over-cleaning active outputs | Preview/export/recovery breaks. | Cleanup must re-check active pointers and protected retention classes. |
| Under-cleaning successful payloads | Workspace grows and stores avoidable sensitive data. | Use `successful_payload -> metadata_only_cleaned` when committed results are enough. |
| Rebuildability misclassified | Cleanup may remove a file that cannot actually be rebuilt. | Require source artifact ids, hashes, config hashes, and provider/tool identity before `cache_rebuildable`. |
| Typeset preview ambiguity | Overflow preview might be mistaken for accepted output. | Use `typeset_preview_image` unless workflow accepts it as active warning output. |
| Redaction metadata too weak | `contains_secret_redacted` may not explain how sanitization happened. | Keep as MVP field; consider artifact-level sanitization version later. |
| Missing failed/debug payload | Audit quality degrades. | Mark artifact `missing`; do not fabricate evidence or block unless current workflow requires it. |

## 14. Open Questions

| Question | Blocking for MVP-0? |
| --- | --- |
| Exact cleanup TTLs for `successful_payload`, `debug`, `cache_rebuildable`, and superseded previews. | No |
| Whether `typeset_preview_image` should remain a separate artifact type or become `typeset_image` plus owner/status convention. | No, but decide before final enum freeze. |
| Whether `issue_snapshot` is required in MVP-0 execution contract or should remain export-design only. | No |
| Whether users need an explicit privacy purge for failed payloads before Project deletion, and what audit summary remains. | No |
| Whether active masks are always protected individually or whether a page-composite active mask can replace per-block masks. | No |
| Whether `ProcessingArtifact` needs artifact-level `sanitization_version` in addition to ToolRunLog sanitization metadata. | No |
| When a superseded `active_result` image becomes eligible for cleanup if it is still useful for review history. | No |
