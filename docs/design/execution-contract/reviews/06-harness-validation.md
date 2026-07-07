# Phase 5 HARNESS Validation: Execution Contract

## Scope

Validation agent: Phase 5 HARNESS validation.

Validated sources:

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/design/execution-contract/HARNESS.md`
- `docs/design/execution-contract/final/*.md`
- `docs/design/execution-contract/adr/*.md`

Task boundary: documentation-only validation. No implementation, schema, API, provider, frontend, prompt, dependency, commit, push, pull, or rebase work performed.

## Invariant Checklist

| Invariant | Result | Evidence |
| --- | --- | --- |
| Provider Adapter does not access SQLite/Repository/DAO. | PASS | Provider forbidden responsibilities and ADR 0001 forbid DB access. |
| Provider Adapter does not register official artifacts. | PASS | Temp refs only; ArtifactService owns promotion and official rows. |
| Provider Adapter does not create QualityIssues. | PASS | Provider returns result/error evidence; QualityCheckService classifies issue drafts. |
| Provider Adapter does not decide retry/fallback/skip/warning/block/readiness. | PASS | `retry_hint` is advisory only; WorkflowLoopEngine owns decisions. |
| Provider refusal is first-class, not generic failure. | PASS | `outcome = refusal`, `kind = provider_refusal`, `is_provider_refusal = true`. |
| No provider policy bypass/evasion path exists. | PASS | ADR 0001 and ADR 0006 forbid bypass, prompt laundering, and evasion guidance. |
| ArtifactService owns official path, hash, metadata, retention, storage state, cleanup. | PASS | Artifact contract defines official artifact as promoted bytes plus committed metadata. |
| ArtifactService does not decide workflow retry/fallback/warning/block/readiness. | PASS | Artifact reports integrity/registration evidence only. |
| Original images are never overwritten. | PASS | Original import rule and cleanup boundary protect `original_image`. |
| Images/large payloads are not stored in SQLite. | PASS | Artifact metadata in SQLite only; bytes live in workspace. |
| QualityCheckService owns classification but not workflow state. | PASS | Returns `QualityCheckReport` issue drafts and lifecycle suggestions only. |
| QualityCheckService does not update active pointers. | PASS | Explicitly forbidden; acceptance transaction is loop-owned. |
| StageExecutor executes one bounded attempt and does not replace WorkflowLoopEngine. | PASS | StageResult excludes decisions, next stage, fallback provider, budget mutation, and pointer mutation. |
| No write transaction is held across provider calls. | PASS | StageExecutor transaction boundary requires short attempt-start transaction and no DB write transaction during provider call. |
| WorkflowLoopEngine owns active pointer acceptance and decisions. | PASS | Acceptance transaction owns WorkflowDecision, issues, result rows, active pointers, budgets, statuses. |
| WorkflowAttempt metadata is always persisted before provider call. | PASS | StageExecutor sequence persists/marks running attempt before provider call. |
| Failed/refused/invalid evidence can be retained after sanitization. | PASS | Artifact contract supports `failed_attempt_payload`; ADR 0006 requires redaction first. |
| FakeProvider does not require real OCR/LLM/cleaning/typesetting tools. | PASS | Fake modes use real envelope plus deterministic fixture temp files. |
| Recovery trusts committed evidence, not orphan files. | PASS | Artifact recovery rule requires replay through registration, quality, loop acceptance. |
| Exact persistence/API/module names are defined. | UNCLEAR | Deferred intentionally to later persistence/API/config designs; non-blocking for contract validation. |

## Missing Provider Contract Details

- Exact real provider schemas, prompt templates, response parsers, and vendor error mappings are deferred.
- Exact enum enforcement mechanism for provider outcome/error/capability values is deferred.
- Exact fake fixture image dimensions and deterministic file contents are deferred.
- Exact provider config persistence shape for capability flags such as `requires_gpu` is deferred.

These are non-blocking for FakeProvider contract validation because the boundary DTOs, outcome vocabulary, refusal semantics, metadata, temp-file rule, and forbidden responsibilities are specified.

## Missing Artifact Contract Details

- Exact artifact directory layout, staging/orphan/quarantine paths, temp naming, cleanup TTLs, and fsync/atomic file mechanics are deferred.
- Exact integrity-check event persistence location is deferred.
- Exact successful raw payload retention TTL and transition to `metadata_only_cleaned` are deferred.
- Exact cleanup behavior for missing failed/debug payloads is deferred.

These are non-blocking for the vertical slice if implementation uses ArtifactService for all official registration and treats unregistered files as non-official.

## Missing Quality Issue Contract Details

- Exact persistence location for `classification_version` is deferred.
- Exact message params persistence versus API-time derivation is deferred.
- Optional Page summary issue for partial Page translation is deferred.
- Full OCR confidence bands, translation naturalness categories, and localized UI copy are deferred.

These are non-blocking because P0 IssueTypes, error codes, severity/blocking rules, message keys, suggested action keys, and root-stage rules cover all HARNESS scenarios.

## Missing StageExecutor Boundary Details

- Exact Repository/DAO method names and transaction helper APIs are deferred.
- Exact shape of `StageExecutionContext` and `StageResult` as implementation DTOs is deferred.
- Exact pause/cancel polling mechanics at safe boundaries are deferred.
- Exact ToolRunLog timing, whether before or after provider return, allows variation as long as running WorkflowAttempt exists before the call.

These are non-blocking because the required sequence, forbidden decisions, transaction boundaries, and evidence fields are explicit enough for FakeProvider planning.

## Recovery Evidence Gaps

- Exact recovery algorithm and task reconciliation loop are not specified in this design set.
- Exact handling of abandoned running attempts after crash is described conceptually but not reduced to a transition table here.
- Exact integrity-check audit storage location is deferred.
- Exact orphan cleanup/quarantine mechanics are deferred.

No hard blocker: the design provides sufficient recovery evidence inputs for the vertical slice: running WorkflowAttempt, ToolRunLog when present, official artifacts with hashes/storage state, QualityIssue drafts/rows after acceptance, WorkflowDecision, active pointers, and repository statuses.

## FakeProvider Readiness Gaps

- Exact fixture files, image dimensions, and deterministic bytes remain to be chosen.
- Exact `fake_mode` storage field and profile/test config schema remain to be designed.
- Exact call-index policy implementation remains to be designed.
- Exact assertions for each backend test are listed as required evidence but not written as test cases.

No hard blocker: FakeProvider readiness is acceptable because all fake modes must use the real ProviderResult envelope, temp artifact path, ArtifactService promotion, FakeQualityCheck drafts, and WorkflowLoopEngine acceptance path.

## Boundary Violations

No hard boundary violation found in the final design or ADRs.

Observed near-boundary risks:

- `retry_hint`, artifact `rebuildability_hint`, and quality `suggested_action_key` could drift into decisions during implementation. The documents mark them as non-binding evidence.
- StageExecutor could become a hidden loop engine if it consumes retry budgets or accepts warnings. The contract forbids this.
- Artifact registration could be mistaken for active pointer acceptance. ADR 0002 explicitly separates official-but-unselected artifacts from export-effective outputs.
- QualityCheckService issue persistence could split from pointer/status acceptance. ADR 0003 keeps MVP-0 persistence loop-owned.

## Scenario Replay Results

Legend: "Loop input" means evidence available to WorkflowLoopEngine, not a decision already made by another component.

| ID | Result | Stage involved | Provider output or error | ArtifactService behavior | QualityCheckService behavior | StageExecutor behavior | WorkflowLoopEngine decision input | Persistence or recovery evidence | Boundary check |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | PASS | Any provider stage, especially detection/OCR/translation/cleaning/typesetting. | `ProviderResult.outcome = success` with structured payload and metadata. | Promotes temp outputs when present; computes hash/metadata; returns artifact ids. | Checks complete candidate output; zero or non-blocking issue drafts. | Creates running attempt, calls one provider, registers artifacts, returns StageResult. | Success outcome, artifacts, candidate drafts, quality summary for `continue`. | WorkflowAttempt, ToolRunLog, processing_artifact rows, later decision/active pointer transaction. | Provider has no DB/artifact/issue/decision ownership. |
| P02 | PASS | Any provider stage. | `outcome = failure`, e.g. `kind = provider_timeout`, retry hint advisory only. | Registers sanitized failed/debug payload if available; otherwise no output artifact. | Can classify `provider_call_failed` when required output absent. | Preserves standardized error evidence; no retry decision. | Failure kind/code, attempt history, profile, budgets, fallback availability. | Running/failed attempt, ToolRunLog error, issue draft after quality, WorkflowDecision after loop. | Provider creates no QualityIssue and does not decide retry/fallback/block. |
| P03 | PASS | Translation or any policy-facing provider stage. | `outcome = refusal`, `kind = provider_refusal`, sanitized metadata/code. | May register sanitized refusal payload as failed-attempt evidence. | Drafts `provider_refusal`, `root_stage = provider_policy`, safe action. | Normalizes refusal and returns StageResult. | Refusal evidence, issue draft, fallback/manual/profile refusal policy. | Refused attempt/log, retained evidence artifact when safe, issue/decision records. | No bypass/evasion behavior; refusal not generic crash. |
| P04 | PASS | Translation primarily; any structured provider output possible. | `outcome = invalid_output` from adapter or StageExecutor normalization. | May register sanitized raw invalid output per retention policy. | Drafts `stage_output_invalid` with `translation_invalid_json` or schema code. | Reports invalid output and retained raw refs without accepting result. | Invalid-output issue, raw evidence, retry budget/profile/fallback policy. | Attempt/log with invalid output, raw response artifact if retained, decision later. | Provider/StageExecutor report evidence; loop owns retry/block. |
| P05 | PASS | Page-level translation. | `outcome = partial_success`; valid translations plus explicit missing/invalid targets. | Registers raw response/debug evidence if retained; no artifact needed for normal text result. | Valid blocks remain candidates; missing blocks get TextBlock-scoped issue drafts. | Returns partial target map and TranslationResult drafts for valid blocks. | Partial map, missing-block issues, profile/budget/warning/block policy. | One page-scoped attempt/log plus accepted result rows only if loop accepts candidates. | Partial success does not auto-accept active pointers. |
| A01 | PASS | Import. | No provider required. | Registers `original_image`, hash, media type, size/dimensions, permanent retention. | Can check import/artifact integrity if needed. | Calls ArtifactService for original import and returns evidence. | Valid original artifact id or registration failure evidence. | `processing_artifact` row; Page `original_artifact_id` only after acceptance. | Original not overwritten; domain should reference artifact id, not raw path. |
| A02 | PASS | File-producing provider stage: detection mask, cleaning, typesetting. | Provider returns temp ref under attempt temp root. | Validates temp path, copies/promotes to official workspace, computes hash, registers metadata. | Checks candidate artifact and related output evidence. | Passes artifact intent/scope/safety flags; receives artifact id or failure. | Registered artifact candidate, quality report, profile. | Official but unselected artifact row until loop acceptance. | Provider does not choose official path or artifact id. |
| A03 | PASS | Failed/refused/invalid provider attempt. | Error/refusal/invalid output may include sanitized raw temp ref. | Registers failed/debug evidence with retention class and safety flags, or rejects unsafe payload. | May classify issue from sanitized evidence. | Supplies failure scope and retained payload intent. | Error/refusal evidence, artifact id if retained, issue draft. | Failed attempt metadata, ToolRunLog, evidence artifact, decision. | Secrets are precluded by sanitization boundary. |
| A04 | PASS | Recovery/export_check/reuse_check. | No provider output; active artifact missing/hash-invalid. | Validates artifact, marks `storage_state = missing`, returns integrity report. | Drafts `artifact_unavailable` for required active artifact. | Calls validation when bytes are required; reports integrity evidence. | Integrity report, active reference, rebuildability hint, profile. | Storage state update, integrity evidence in attempt/decision path. | ArtifactService does not decide rebuild/retry/warning/block. |
| A05 | PASS | Cleanup/retention. | No provider output. | Rechecks scope, active pointers, retention, issues, attempts; preserves protected artifacts. | Not primary actor; may later surface missing active bytes if discovered. | Not a workflow execution unless cleanup is invoked by maintenance/recovery. | Cleanup result or missing-active report if cleanup discovers a problem. | Artifact storage states/trash metadata and active-reference evidence. | Cleanup separated from provider execution and workflow readiness. |
| Q01 | PASS | OCR. | OCR provider success with empty `source_text`. | Registers raw OCR output/crop if retained; no accepted OCR result yet. | Drafts `ocr_text_missing`, `ocr_no_text`, blocking while required output absent. | Returns OCRResult draft with empty text and quality report. | Empty OCR issue, provider metadata, OCR retry/fallback/manual options. | Attempt/log, issue draft then issue row on loop transaction, no active OCR unless accepted path. | Provider treats empty text as evidence; QualityCheck classifies. |
| Q02 | PASS | Translation. | `invalid_output` or schema-invalid JSON. | May retain sanitized raw response. | Drafts `stage_output_invalid`, `translation_invalid_json`; blocking current output. | Normalizes invalid output and invokes QualityCheck. | Invalid-output issue, retry/fallback budget, profile. | Attempt/log/raw artifact/decision. | Provider Adapter does not decide retry; QualityCheck does not block task by itself. |
| Q03 | PASS | Translation/translation_check. | Page translation missing one TextBlock with valid others. | Optional raw/debug retention only. | Drafts `translation_missing_block` for missing TextBlock; valid candidates remain usable. | Returns partial target map and candidate drafts. | Missing target issue, valid candidates, profile warning/block/retry policy. | Page attempt plus per-block accepted rows only if loop accepts; issue row for missing block. | Valid partial output does not erase failed/missing evidence. |
| Q04 | PASS | Translation refusal. | `refusal` with specific refusal code. | Retains sanitized refusal payload when safe. | Drafts `provider_refusal`, `root_stage = provider_policy`, safe message/action. | Reports refusal evidence and no bypass suggestion. | Refusal issue, fallback/manual options, refusal policy. | Refused attempt/log, quality issue, WorkflowDecision. | No evasion/bypass instruction. |
| Q05 | PASS | Cleaning. | Cleaner returns cannot-clean or partial success with `reason_code = cleaning_complex_background`. | Registers cleaned image only if produced; preserves base/original artifacts. | Drafts `cleaning_skipped_complex_region`, warning by default. | Returns block-level cleaning evidence; does not skip target. | Warning issue, profile skip/warning/export policy, active content state. | Attempt/log, issue, possible unselected artifact; final ready-with-warnings if loop accepts. | Stage skip only through WorkflowLoopEngine; pure ready forbidden while unresolved skip remains. |
| Q06 | PASS | Typesetting. | Typesetter returns overflow evidence, possibly preview temp ref. | Registers preview as `typeset_preview_image`; accepted final type only if loop accepts usable output. | Drafts `typesetting_overflow`, with root stage translation or typesetting as evidence supports. | Returns layout evidence and preview artifact ids. | Overflow issue, preview usability, profile strictness, shorten/upstream/warning/block options. | Attempt/log, preview artifact, quality issue, decision. | WorkflowLoopEngine owns shorten/retry/warning/block. |
| S01 | PASS | Any happy path stage. | Provider/local tool succeeds. | Registers official artifacts where applicable. | Runs after provider normalization/artifact registration. | Loads durable context, starts attempt, calls one provider, returns StageResult. | Complete StageResult for `continue`. | Running attempt before call; ToolRunLog; artifacts; loop acceptance transaction. | No DB write transaction across provider call; no final decision in StageExecutor. |
| S02 | PASS | Any provider stage before file output. | Failure/refusal before output. | No output promotion; failed evidence only if safe payload exists. | Classifies provider failure/refusal from standardized error. | Marks/preserves failed/refused evidence and returns StageResult. | Error/refusal issue, budgets, fallback availability, profile. | Running attempt can be recovered; later log/decision if committed. | Failure is not provider-owned decision. |
| S03 | PASS | File-producing stage. | Provider produces temp file successfully. | Registration fails; temp remains non-official/orphan. | May draft `artifact_unavailable`, `artifact_registration_failed`. | Reports artifact registration failure; does not treat temp as accepted output. | Registration failure issue, retry/pause/block options. | Orphan/non-official file; no active pointer; attempt/decision evidence. | Recovery ignores orphan unless normal replay occurs. |
| S04 | PASS | Any stage with output quality blocker. | Provider output and artifact registration succeed. | Registered artifact may remain official but unselected. | Drafts blocking issue. | Returns quality report and candidate artifacts/results. | Blocking issue, candidate evidence, retry/fallback/pause/block policy. | Official unselected artifact, issue, no active pointer until loop acceptance. | QualityCheck does not advance workflow state. |
| S05 | PASS | Any stage with warning. | Provider output usable with warning. | Registers artifacts normally if produced. | Drafts warning, `is_blocking = false`. | Returns warning evidence. | Warning issue, `allow_warning_export`, profile strictness. | Issue remains visible; decision can mark warning; readiness later profile-dependent. | Warning acceptance is loop-owned. |
| F01 | PASS | Detection, OCR, translation, cleaning, typesetting. | Fake providers return deterministic `success` payloads and temp files. | Registers original, masks/cleaned/typeset artifacts through real path. | FakeQualityCheck emits no open issue. | Executes same sequence as real providers. | Complete evidence for `continue` through stages and final readiness. | Attempts/logs/artifacts/decisions/active pointers/Page status. | No real external tools required. |
| F02 | PASS | OCR. | First fake OCR `failure`, second `success` via durable call index. | Registers failed evidence if any; later OCR artifacts/drafts as applicable. | First issue `provider_call_failed`; second pass clears/supersedes per lifecycle suggestion. | Returns two separate StageResults across attempts. | Retry budget, attempt history, failure then success evidence. | Attempt 1 failure, retry decision, attempt 2 success, active OCR acceptance. | Retry chosen by WorkflowLoopEngine, not fake provider. |
| F03 | PASS | Translation. | Fake translation returns `invalid_output`/invalid JSON. | Retains sanitized raw invalid payload artifact when safe. | Drafts `stage_output_invalid`. | Reports invalid-output StageResult. | Retry or block path evidence. | Attempt/log/raw artifact/issue/decision. | Invalid output path testable without real LLM. |
| F04 | PASS | Translation. | Fake translation returns `refusal`. | Registers sanitized refusal evidence if safe. | Drafts `provider_refusal`, `root_stage = provider_policy`. | Returns refused StageResult. | Fallback/manual/pause/block input; no bypass. | Refused attempt/log/issue/decision. | Refusal path testable without real provider. |
| F05 | PASS | Cleaning. | Fake cleaner returns complex-background cannot-clean evidence. | Registers any produced temp files only through ArtifactService; original remains intact. | Drafts warning `cleaning_skipped_complex_region`. | Returns warning StageResult; does not skip. | Warning/skip/export policy input. | Attempt/log/issue/decision; page may become ready-with-warnings only. | Pure ready forbidden if skipped content unresolved. |
| F06 | PASS | Typesetting. | Fake typesetter returns overflow and preview temp ref. | Registers preview artifact separately from accepted typeset output. | Drafts `typesetting_overflow`. | Returns layout/preview evidence. | Shorten/upstream/warning/pause/block input. | Preview artifact, issue, decision evidence. | Preview is not mistaken for export-effective image. |
| F07 | PASS | Export_check/recovery/artifact validation. | No provider output; harness removes/corrupts official artifact. | Detects missing/hash mismatch and marks/report state. | Drafts `artifact_unavailable` for required active artifact. | Calls validation and returns integrity evidence if in stage path. | Rebuild/retry/restore/pause/block input. | Artifact storage state, integrity report, issue/decision. | FakeProvider does not mutate official artifacts; harness/setup does. |

## Acceptability for FakeProvider Single-Page Backend Vertical Slice

Result: ACCEPTABLE WITH NON-BLOCKING GAPS.

The final design is acceptable for planning and implementing the FakeProvider single-Page backend vertical slice. It covers all HARNESS P01-P05, A01-A05, Q01-Q06, S01-S05, and F01-F07 scenarios with explicit evidence flow and no hard boundary violations.

Hard blockers: none found.

Non-blocking gaps to carry into implementation planning:

- Define exact Repository/DAO transaction helpers and DTO shapes.
- Define exact fake fixture files, fake mode storage, and call-index policy.
- Define exact artifact path/staging/orphan/quarantine layout and cleanup TTLs.
- Define exact sanitization helper API and test assertions.
- Define exact recovery reconciliation behavior for abandoned running attempts.

Final verdict: acceptable with non-blocking gaps.
