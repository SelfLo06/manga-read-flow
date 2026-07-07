# 11 FakeProvider Vertical Slice Readiness Proposal

## 1. Scope

This Phase 1C proposal tests whether the Phase 1A contracts and Phase 1B debate decisions are ready for the Goal 2 implementation milestone:

```text
FakeProvider single-Page backend vertical slice
```

Focus:

- end-to-end FakeProvider testability;
- required fake modes, artifacts, issues, and deterministic scenario control;
- minimal backend vertical slice readiness;
- rejection of contracts that cannot be exercised without real OCR, translation, cleaning, typesetting, or prompt templates.

Out of scope: production code, migrations, DDL, ORM models, API handlers, frontend code, real provider integrations, and real prompt templates.

## 2. Readiness Verdict

Yes, the proposed contracts can run the single-Page FakeProvider happy path if final synthesis adopts these minimums:

| Required final choice | Readiness impact |
| --- | --- |
| Canonical `ProviderResult` envelope with `success`, `partial_success`, `failure`, `refusal`, `invalid_output`. | Makes every fake stage and edge path normalized. |
| FakeProvider modes are explicit task/profile/test inputs and appear in sanitized attempt/tool metadata. | Makes retry and recovery assertions deterministic. |
| File-producing fake stages write temp files only; ArtifactService promotes all official artifacts. | Tests the real artifact boundary instead of bypassing it. |
| QualityCheckService returns deterministic issue drafts/report from provider and artifact evidence. | Tests issue creation without provider-owned policy. |
| WorkflowLoopEngine persists decisions before retry/fallback/skip/warning/block. | Tests bounded loops and restart evidence. |
| Missing active artifact is a harness/artifact-integrity setup, not a provider mode that deletes official files. | Keeps Provider boundary clean. |

If any of these remain vague, the vertical slice can still fake a green path but cannot prove the execution contract.

## 3. Decisions

| Decision | Contract requirement | Rationale |
| --- | --- | --- |
| D1 | FakeProvider must implement the same Provider Adapter envelope as real providers. | Tests StageExecutor, QualityCheckService, and WorkflowLoopEngine against the future contract, not a test-only shortcut. |
| D2 | Fake scenario control must be deterministic by `stage + target_id + input_hash + config_hash + fake_mode + call_index_policy`. | Required for retry, idempotency, and recovery tests. |
| D3 | Fake modes must be stage-scoped, not hidden globals. | Parallel tests and reruns must not bleed state across Projects or tasks. |
| D4 | FakeProvider may emit temp files and raw payload temp refs, never official artifact ids or official paths. | ArtifactService promotion, hashing, storage state, and missing detection must be exercised for real. |
| D5 | FakeQualityCheck should classify fake evidence into issue drafts; it must not emit WorkflowDecisions. | Keeps quality classification testable while preserving WorkflowLoopEngine ownership. |
| D6 | Partial translation is `partial_success` only when valid block outputs and missing/invalid target evidence are explicit. | Allows valid TranslationResults and blocking missing-block issues under one page attempt. |
| D7 | Cleaning skip and typesetting overflow are visible issue paths, not happy-path silence. | Prevents pure `ready_for_export` with hidden incomplete output. |
| D8 | Missing active artifact is tested by deleting or corrupting an official registered artifact after promotion. | Proves ArtifactService integrity reports and recovery decisions without provider boundary drift. |

## 4. Required Fake Modes

| Mode | Stage | Provider outcome | Required downstream evidence |
| --- | --- | --- | --- |
| `happy_path` | all | `success` | Attempts/logs succeed; official original/mask/cleaned/typeset artifacts exist; no open issues; final `finish_ready_for_export`. |
| `ocr_fail_once` | `ocr` | First call `failure` with `ocr_timeout` or `ocr_model_error`; second call `success`. | Failed attempt, `provider_call_failed` issue or equivalent evidence, `retry_same_stage` decision, later active OCR pointer. |
| `translation_invalid_json` | `translation` | `invalid_output` with raw response temp ref. | Failed/refused-style evidence artifact if retained, `stage_output_invalid`, retry or block decision. |
| `provider_refusal` | `translation` | `refusal`, `is_provider_refusal = true`. | Attempt/log `refused`, `provider_refusal` issue, root `provider_policy`, fallback/manual/warn/skip/block decision, no bypass hint. |
| `translation_partial` | `translation` | `partial_success`. | Valid block TranslationResults plus `translation_missing_block` issue for omitted block. |
| `cleaning_skip` | `cleaning` | `partial_success` or success-shaped output with `skipped_regions`. | `cleaning_skipped_complex_region` warning; no pure ready unless resolved. |
| `typesetting_overflow` | `typesetting` | `partial_success` with preview temp ref and overflow metrics. | Preview artifact, `typesetting_overflow` issue, warning/pause/block/upstream-retry decision. |
| `missing_active_artifact` | artifact/recovery setup | Not a provider outcome. | ArtifactService marks `missing` or hash mismatch; `artifact_unavailable` issue; rebuild/block decision input. |
| `temp_artifact_missing_before_promotion` | file-producing stage | Provider returns temp ref; harness removes temp before promotion. | Artifact registration failure; no official artifact; S03 path testable. |

## 5. Required Fake Artifacts

| Artifact | Minimum fixture | Why needed |
| --- | --- | --- |
| `original_image` | Tiny valid PNG or JPG imported through normal ArtifactService registration. | Root input, original safety, hash/path validation. |
| `mask_image` | Deterministic small mask temp file from detection if masks are materialized. | Cleaning input and artifact promotion coverage. |
| `ocr_input_crop` | Optional tiny crop file when OCR fixture uses materialized crop. | OCR artifact linkage and cleanup/rebuildability tests. |
| `provider_raw_response` | Sanitized invalid JSON/refusal payload temp file. | Invalid-output/refusal audit without storing raw payload in SQLite. |
| `cleaned_image` | Deterministic image temp file, preferably copy of original with trivial mark/fill. | Active cleaned pointer and typesetting input. |
| `typeset_image` | Deterministic image temp file. | Final active output and export readiness. |
| `typeset_preview_image` | Deterministic overflow preview temp file. | Overflow issue review and failed/warning artifact retention. |

Debug bundles and issue snapshots are not required for Goal 2 unless final synthesis makes them part of the HARNESS.

## 6. Required Fake Issues

Use the compact P0 issue vocabulary from the quality debate. Exact final names can be normalized, but these conditions must be assertable:

| Fake condition | Required issue |
| --- | --- |
| OCR failure/timeout before usable output | `provider_call_failed` with `error_code = ocr_timeout` or `ocr_model_error`. |
| OCR success with empty text, if tested separately | `ocr_text_missing`. |
| Translation invalid JSON | `stage_output_invalid` with `error_code = translation_invalid_json`. |
| Provider refusal | `provider_refusal`, `root_stage = provider_policy`. |
| Partial translation missing one block | `translation_missing_block`, TextBlock-scoped. |
| Cleaning complex background skip | `cleaning_skipped_complex_region`, warning by default. |
| Typesetting overflow | `typesetting_overflow`, TextBlock or Page scoped. |
| Missing/hash-invalid active artifact | `artifact_unavailable`, blocking when required for active output/export. |
| Temp promotion/registration failure | `artifact_unavailable` or stage execution error evidence with `artifact_registration_failed`. |

## 7. Scenario Answers

| Required question | Answer |
| --- | --- |
| Can the proposed contracts run the single-Page happy path? | Yes. Fake detection creates deterministic TextBlocks; OCR and translation create active result versions; cleaning/typesetting temp images are promoted; export_check reaches `ready_for_export`. |
| Can they simulate OCR failure then retry? | Yes, if `ocr_fail_once` persists call index/evidence and WorkflowLoopEngine consumes retry budget through `retry_same_stage`, not provider retry logic. |
| Can they simulate invalid translation JSON? | Yes, through `ProviderResult.outcome = invalid_output`, sanitized raw response temp ref, `stage_output_invalid`, and retry/block decision. |
| Can they simulate provider refusal? | Yes, through `outcome = refusal`, attempt/log `refused`, refusal issue root `provider_policy`, and no prompt rewrite or evasion path. |
| Can they simulate partial translation? | Yes, through explicit `partial_success` with valid translations plus missing target ids. |
| Can they simulate cleaning skip? | Yes, if skip is provider evidence and WorkflowLoopEngine decides `skip_target` or `mark_warning`; provider must not decide skip. |
| Can they simulate typesetting overflow? | Yes, with preview temp artifact plus overflow metrics/affected ids and a deterministic overflow issue. |
| Can they simulate missing artifact? | Yes, but only as ArtifactService/HARNESS setup after official registration, or temp promotion failure before registration. FakeProvider must not mutate official artifacts. |
| What minimal fixtures are needed? | One tiny page image, two deterministic TextBlocks, deterministic OCR/translation maps, empty glossary version, fake profile snapshot with budgets/modes, temp image/raw payload writers, and expected issue/decision assertions. |

## 8. Minimal Fixture Set

| Fixture | Minimum content |
| --- | --- |
| Project/Batch/Page | One Project, one Batch, one Page, registered original image. |
| Image | Small valid PNG/JPG with stable hash and dimensions; no real manga content required. |
| TextBlocks | Two blocks with stable caller-assigned ids, bbox, polygon, direction, reading order 1/2. |
| OCR map | Block 1 `こんにちは`; block 2 `ありがとう`; optional empty-text variant. |
| Translation map | Block 1 `你好`; block 2 `谢谢`; partial mode omits block 2. |
| Glossary | Empty Project glossary plus initial `GlossaryVersion`/hash. |
| ProcessingProfileSnapshot | Retry budget at least 1 for OCR and translation invalid-output tests; warning export toggle for skip/overflow tests; fake modes in sanitized settings or test harness config. |
| Provider configs | Fake detector, OCR, cloud translator, optional local translator, cleaner, typesetter; sanitized capability metadata only. |
| Temp files | Deterministic cleaned/typeset/preview images and raw invalid/refusal response payloads under attempt temp root. |
| Expected checks | Assertions for attempts, ToolRunLogs, official artifacts, QualityIssues, WorkflowDecisions, active pointers, and final Page/Task status. |

## 9. Minimal Backend Slice

The vertical slice is ready only if it exercises this sequence for each stage:

```text
load durable context
create running WorkflowAttempt
call FakeProvider or local fake stage
register temp files through ArtifactService
run QualityCheckService
return StageExecutor evidence
persist WorkflowLoopEngine decision
accept result/artifact pointers only through workflow acceptance
```

No write transaction should be held across the fake provider call. A FakeProvider test that directly inserts result rows, artifact rows, issues, or decisions is not a valid Goal 2 proof.

## 10. Rationale

- Goal 2 is a contract proof, so the fake path must stress the same boundaries as real providers.
- The happy path alone is insufficient; invalid JSON, refusal, partial output, skip, overflow, and missing artifacts are the contract edges most likely to collapse boundaries.
- Deterministic fake modes make retry budget, call history, recovery, and idempotent rerun assertions cheap and reliable.
- Official artifact promotion must remain real because many architecture invariants depend on path safety, hash validation, storage state, and active pointer separation.
- Provider refusal must be testable without real cloud APIs so safety behavior is not postponed until late integration.

## 11. Rejected Alternatives

| Alternative | Rejected because |
| --- | --- |
| FakeProvider writes official artifact rows or official workspace paths. | Bypasses ArtifactService and invalidates artifact HARNESS coverage. |
| FakeProvider creates QualityIssues directly. | Bypasses QualityCheckService and root-stage classification. |
| FakeProvider returns `should_retry`, `should_skip`, or `ready_for_export`. | Bypasses WorkflowLoopEngine and retry/skip/warning policy. |
| Random fake failures. | Makes retry/recovery tests flaky and unrepeatable. |
| Single all-purpose fake success mode only. | Cannot prove refusal, invalid output, partial output, artifact failure, or warning paths. |
| Missing artifact as a provider behavior that deletes active files. | Violates provider boundary; active artifact drift belongs to ArtifactService/recovery setup. |
| Real prompt templates or real OCR/LLM tools in Goal 2. | Expands scope and hides contract defects behind tool behavior. |

## 12. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Final enum names remain unsettled. | Fake tests become brittle or delayed. | Freeze a minimal Goal 2 vocabulary before implementation. |
| Fake modes live only in hidden process state. | Retry/recovery cannot be audited. | Include fake mode and call index policy in sanitized attempt/tool metadata. |
| Partial translation acceptance is ambiguous. | Valid block results may become active despite unresolved blockers. | Require WorkflowLoopEngine acceptance transaction to handle result rows, issues, decisions, active pointers, and statuses together. |
| Warning paths accidentally produce pure ready. | Cleaning skip or overflow becomes invisible to export_check. | Assert pure `ready_for_export` is illegal with unresolved skips/warnings. |
| Raw fake payloads include secrets by accident in future tests. | Secret leakage pattern normalizes. | Use sanitized canned payloads only and mark safety flags. |
| Artifact promotion failures are not covered. | S03 remains theoretical. | Add `temp_artifact_missing_before_promotion` harness setup. |

## 13. HARNESS Coverage

| HARNESS area | Status | Required proof |
| --- | --- | --- |
| F01 Fake happy path | PASS if decisions above adopted | End-to-end single Page reaches `finish_ready_for_export`. |
| F02 Fake OCR failure then retry | PASS | First attempt fails, retry decision persists, second attempt succeeds. |
| F03 Fake translation invalid JSON | PASS | Invalid raw response retained if policy allows; invalid-output issue and retry/block decision exist. |
| F04 Fake provider refusal | PASS | Refused attempt/log, provider-refusal issue, safe decision path, no bypass. |
| F05 Fake cleaning skip | PASS | Visible warning issue; warning-ready only if profile allows; never pure ready. |
| F06 Fake typesetting overflow | PASS | Preview artifact, overflow issue, workflow decision. |
| F07 Fake missing artifact | PASS with boundary rule | Official artifact is removed/corrupted by harness; ArtifactService reports missing. |
| P01-P05 provider scenarios | PASS | ProviderResult envelope and fake modes cover success, failure, refusal, invalid output, partial output. |
| A01-A04 artifact scenarios | PASS | Real ArtifactService promotion and validation are exercised. |
| Q01-Q06 quality scenarios | PASS | FakeQuality issue mappings are deterministic. |
| S01-S05 StageExecutor scenarios | PASS if final StageExecutor output is normalized | Sequence and transaction boundaries remain testable. |

## 14. Open Questions

| Question | Blocking for Goal 2 implementation? |
| --- | --- |
| Where exactly does `fake_mode` live: ProcessingProfileSnapshot settings, test-only task config, or StageExecutor scenario input? | Yes. It must be durable enough for retry/recovery assertions. |
| Does QualityCheckService persist issues itself or return issue drafts for the caller to persist with decisions? | Yes. The StageExecutor/WLE transaction boundary depends on it. |
| What exact enum spellings are final for fake modes, outcomes, issue types, artifact types, and decision types? | Yes for test implementation, no for design intent. |
| Is partial translation allowed to update active translation pointers before missing-block handling completes? | Yes. Proposal recommends only through WorkflowLoopEngine acceptance with linked issues/decision. |
| Should overflow preview be `typeset_preview_image` or `typeset_image` with owner/status convention? | No, but decide before fixture assertions. |
| Is `temp_artifact_missing_before_promotion` part of FakeProvider modes or a harness mutation between provider and ArtifactService? | No, but proposal recommends harness mutation to avoid provider owning artifact failure. |
