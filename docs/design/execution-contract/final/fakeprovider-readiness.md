# FakeProvider Readiness v0.1

## 1. Readiness verdict

The final contracts are ready for FakeProvider single-Page backend vertical slice planning.

Readiness depends on these requirements:

- FakeProvider implements the real `ProviderResult` envelope.
- FakeProvider never writes official artifact paths or artifact rows.
- FakeQualityCheck returns deterministic issue drafts/reports, not WorkflowDecisions.
- ArtifactService promotion and validation are real contract paths, even when bytes are fake fixture files.
- WorkflowLoopEngine persists decisions and active pointer acceptance.
- Fake modes are durable/test-visible, not hidden globals.

## 2. Fake scenario control

Fake scenario key:

```text
stage + target_type + target_id + input_hash + config_hash + context_hash + fake_mode + call_index_policy
```

`fake_mode` and `call_index_policy` must be stored in test-only profile snapshot settings or task test config copied into sanitized attempt/tool metadata. Hidden process global state is not sufficient for retry, idempotency, or recovery assertions.

## 3. Required FakeProvider modes

| Mode | Stage | Provider outcome | Required evidence |
| --- | --- | --- | --- |
| `happy_path` | all provider stages | `success` | Deterministic payloads, temp files where needed, no issues. |
| `ocr_fail_once` | `ocr` | First `failure`, second `success` | First attempt error, retry decision, later OCR result candidate. |
| `ocr_empty` | `ocr` | `success` with empty text | `ocr_text_missing` issue draft. |
| `translation_invalid_json` | `translation` | `invalid_output` | Sanitized raw response temp ref, invalid-output issue. |
| `translation_refusal` | `translation` | `refusal` | Refusal marker, provider-policy root issue, no bypass hint. |
| `translation_refusal_as_text` | `translation` | `invalid_output` with sanitized refusal-like payload | QualityCheck may classify refusal when evidence is confident. |
| `translation_partial` | `translation` | `partial_success` | Valid translations for subset plus explicit missing target ids. |
| `provider_unavailable` | any provider stage | `failure` | Provider/config/dependency unavailable evidence. |
| `cleaning_skip` | `cleaning` | `partial_success` or success-shaped cannot-clean evidence | Complex background warning issue. |
| `typesetting_overflow` | `typesetting` | `partial_success` | Preview temp ref and overflow layout evidence. |
| `temp_artifact_missing_before_promotion` | file-producing stage | Provider returns temp ref; harness removes temp before promotion | Artifact registration failure evidence. |
| `missing_active_artifact` | artifact/recovery setup | Not a provider outcome | Harness deletes/corrupts official artifact after registration; ArtifactService reports missing/hash mismatch. |

FakeProvider must not mutate official active artifacts. Missing active artifact is a harness/ArtifactService setup.

## 4. Required fake artifacts

| Artifact | Minimum fixture |
| --- | --- |
| `original_image` | Tiny valid PNG/JPG imported through normal ArtifactService registration. |
| `mask_image` | Deterministic mask temp file when detection materializes masks. |
| `ocr_input_crop` | Optional deterministic crop temp file when OCR uses materialized crops. |
| `provider_raw_response` | Sanitized invalid JSON/refusal payload temp file. |
| `cleaned_image` | Deterministic image temp file, usually derived copy of original. |
| `typeset_image` | Deterministic final page image temp file. |
| `typeset_preview_image` | Deterministic overflow preview temp file. |

Debug bundles and issue snapshots are optional for Goal 2.

## 5. Required FakeQualityCheck modes

| Fake evidence | Issue draft |
| --- | --- |
| Happy path complete output | No open issue. |
| OCR empty text | `issue_type = ocr_text_missing`, `error_code = ocr_no_text`. |
| Provider failure | `issue_type = provider_call_failed`, stage-specific error code. |
| Translation invalid JSON | `issue_type = stage_output_invalid`, `error_code = translation_invalid_json`. |
| Provider refusal | `issue_type = provider_refusal`, `root_stage = provider_policy`. |
| Missing translation block | `issue_type = translation_missing_block`, TextBlock target. |
| Cleaning complex background | `issue_type = cleaning_skipped_complex_region`, warning by default. |
| Typesetting overflow | `issue_type = typesetting_overflow`, preview artifact ref when present. |
| Missing/hash-invalid artifact | `issue_type = artifact_unavailable`, blocking when active required artifact. |
| Registration failure | `issue_type = artifact_unavailable`, `error_code = artifact_registration_failed`. |

FakeQualityCheck must be deterministic by `classification_version` and fixture input. It must not emit WorkflowDecision values.

## 6. Minimal fixture set

| Fixture | Minimum content |
| --- | --- |
| Project/Batch/Page | One Project, one Batch, one Page. |
| Image | Small valid image with stable hash and dimensions. |
| TextBlocks | Two deterministic blocks with bbox, direction, reading order 1/2. |
| OCR map | Block 1 `fake_source_1`, block 2 `fake_source_2`; empty variant for `ocr_empty`. |
| Translation map | Block 1 `fake_translation_1`, block 2 `fake_translation_2`; partial mode omits block 2. |
| Glossary | Empty Project glossary with initial GlossaryVersion/hash. |
| ProcessingProfileSnapshot | Retry budget >= 1 for OCR/invalid translation tests; warning export toggle for skip/overflow tests; fake mode config. |
| Provider configs | Fake detector, OCR, cloud translator, optional local translator, cleaner, typesetter. |
| Temp files | Deterministic cleaned/typeset/preview images and raw invalid/refusal payloads. |
| Expected assertions | Attempts, ToolRunLogs, artifacts, QualityIssue drafts/rows, WorkflowDecisions, active pointers, Page/Task status. |

## 7. Minimal backend slice sequence

Every fake stage should exercise:

```text
load durable context
create running WorkflowAttempt
call FakeProvider or local fake stage
register temp files through ArtifactService
run QualityCheckService
return StageResult evidence
persist WorkflowLoopEngine decision
accept result/artifact pointers only through workflow acceptance
```

A fake test that inserts result rows, artifact rows, QualityIssues, or decisions directly is not a valid execution-contract proof.

## 8. HARNESS scenario replay

| ID | Result | Replay summary |
| --- | --- | --- |
| P01 Provider success result | PASS | Provider returns `success` payload and metadata; StageExecutor routes temp files to ArtifactService; QualityCheck checks; loop receives continue evidence. |
| P02 Provider timeout/transient failure | PASS | Provider returns `failure` with `provider_timeout`; no issue from provider; StageResult carries failure evidence for retry/fallback/pause/block. |
| P03 Provider refusal | PASS | Provider returns `refusal`; attempt/log can be refused; QualityCheck drafts provider-refusal issue; no bypass path. |
| P04 Invalid structured output | PASS | Provider or StageExecutor normalizes to `invalid_output`; raw response may be retained; QualityCheck drafts invalid-output issue. |
| P05 Page translation partial output | PASS | `partial_success` includes valid translations and missing target ids; valid results remain candidates; missing blocks get issues. |
| A01 Register original image | PASS | ArtifactService registers `original_image`; Page points to artifact id only after acceptance; original is never overwritten. |
| A02 Promote temporary provider output | PASS | Provider temp output is non-official until ArtifactService promotion and metadata commit. |
| A03 Register failed attempt evidence | PASS | Failed/refusal/invalid payloads can become sanitized `failed_attempt_payload` artifacts. |
| A04 Missing active artifact | PASS | ArtifactService validates path/hash, marks `missing`, and returns integrity evidence; loop decides response. |
| A05 Artifact cleanup boundary | PASS | Protected retention classes and active pointer recheck prevent cleanup from removing originals/active outputs/failed evidence. |
| Q01 OCR empty result | PASS | OCR success with empty text maps to `ocr_text_missing`; loop decides retry/fallback/manual/skip/block. |
| Q02 Translation invalid JSON | PASS | Invalid output maps to `stage_output_invalid`; retryability is workflow policy, not provider/quality decision. |
| Q03 Translation missing TextBlock | PASS | Missing block gets TextBlock issue; valid translations remain candidates. |
| Q04 Provider refusal issue | PASS | `provider_refusal` plus `root_stage = provider_policy`; safe message/action keys; no evasion guidance. |
| Q05 Cleaning complex background | PASS | Cleaner cannot-clean evidence maps to warning by default; skip is only a workflow decision; pure ready is forbidden while unresolved. |
| Q06 Typesetting overflow | PASS | Preview artifact may be retained; `typesetting_overflow` issue records affected target; loop decides shorten/upstream/warn/pause/block. |
| S01 Happy path stage execution | PASS | Sequence is context, attempt, provider, ArtifactService, QualityCheck, StageResult, WorkflowLoopEngine decision, repository acceptance. |
| S02 Provider call fails before artifact output | PASS | Running attempt exists; provider error/refusal evidence persists; QualityCheck can classify; loop has retry/fallback/block input. |
| S03 File produced but artifact registration fails | PASS | Temp file is non-official; StageResult reports `artifact_registration_failed`; recovery treats orphan as non-official. |
| S04 QualityCheck returns blocking issue | PASS | Output may remain audit evidence; active/export-effective acceptance waits for loop decision. |
| S05 QualityCheck returns warning issue | PASS | Warning issue remains visible; loop may mark warning; readiness depends on profile snapshot. |
| F01 Fake happy path | PASS | Fake providers can run all stages without real external tools and reach ready output. |
| F02 Fake OCR failure then retry | PASS | `ocr_fail_once` records failed attempt, retry decision, second success, and active OCR acceptance. |
| F03 Fake translation invalid JSON | PASS | Invalid raw payload, issue draft, and retry/block path are testable. |
| F04 Fake provider refusal | PASS | Refused attempt/log, provider-refusal issue, safe decision path, no bypass. |
| F05 Fake cleaning skip | PASS | Cleaning skip warning and warning-bearing page path are testable; pure ready is illegal. |
| F06 Fake typesetting overflow | PASS | Preview artifact, overflow issue, and warning/pause/block path are testable. |
| F07 Fake missing artifact | PASS | Harness removes/corrupts official artifact; ArtifactService reports missing; recovery/rebuild/block input exists. |

## 9. Boundary checks

| Boundary failure check | Result |
| --- | --- |
| Provider creates QualityIssue | PASS: forbidden. |
| Provider accesses Repository/DAO | PASS: forbidden. |
| Provider registers official artifacts | PASS: forbidden. |
| Provider decides retry/fallback/skip/warning/block | PASS: forbidden. |
| QualityCheckService advances workflow state | PASS: forbidden. |
| QualityCheckService updates active pointers | PASS: forbidden. |
| ArtifactService decides workflow retry/fallback/warning/block | PASS: forbidden. |
| StageExecutor replaces WorkflowLoopEngine decision logic | PASS: forbidden. |
| Images or large payloads stored in SQLite | PASS: forbidden. |
| Original image overwrite allowed | PASS: forbidden. |
| Provider refusal only generic failure | PASS: final envelope has `refusal`. |
| FakeProvider requires real tools | PASS: fake fixtures only. |
