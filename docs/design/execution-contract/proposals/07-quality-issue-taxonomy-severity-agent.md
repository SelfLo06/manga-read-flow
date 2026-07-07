## 1. Scope

This proposal defines the minimal P0 `QualityIssue` taxonomy for the FakeProvider single-Page execution contract.

In scope:

- Minimal `issue_type` values needed for OCR, translation, cleaning, typesetting, artifact, export_check, and provider failures.
- Severity vocabulary.
- `is_blocking` semantics.
- Difference between `error_code` and `issue_type`.
- Stage-specific issue grouping and FakeQuality behavior.

Out of scope:

- SQL DDL, ORM models, API DTOs, UI message text, prompt templates, real provider integrations, and full enterprise issue catalogs.
- Detailed root-cause scoring or LLM-based quality review.

No blocking conflict was found in the source documents for this slice. `HLD-v0.2.md` is treated as the richer accepted HLD baseline, and the workflow-state final documents rename readiness from `export` to `export_check`.

## 2. Role Bias

Prefer a small, durable taxonomy with enough coverage to drive retry/fallback/skip/warning/block decisions.

Bias:

- Make `issue_type` user/workflow meaningful.
- Put provider/tool-specific detail in `error_code`.
- Avoid stage-specific duplicates unless they change remediation.
- Do not add P1/P2 quality categories just because they are foreseeable.

## 3. Assumptions

| Assumption | Impact |
| --- | --- |
| P0 target is FakeProvider single Page. | The taxonomy covers required fake modes, not every real OCR/LLM failure. |
| `QualityIssue` fields from the data-model final are available. | No new persistence fields are proposed. |
| `QualityCheckService` creates/classifies issues. | Provider Adapter and ArtifactService never create `QualityIssue`. |
| `WorkflowLoopEngine` consumes issues and decides actions. | Severity and `is_blocking` are decision inputs, not workflow decisions. |
| Provider refusal is first-class. | Refusal is not collapsed into timeout, crash, or generic failure. |
| Export readiness uses `export_check`. | Actual ExportRecord and ZIP manifest details stay in export design. |

## 4. Proposed Contract

Decision: use exactly three layers of classification.

| Layer | Owner | Meaning | Example |
| --- | --- | --- | --- |
| `error_code` | Provider Adapter, StageExecutor, ArtifactService, or QualityCheckService source evidence | Specific observed condition. May be stage/tool/provider-specific. | `translation_invalid_json`, `provider_timeout`, `artifact_hash_mismatch` |
| `issue_type` | QualityCheckService | Compact workflow/user-facing category. Stable enough for filters, gates, and reports. | `stage_output_invalid`, `artifact_unavailable` |
| `severity` + `is_blocking` | QualityCheckService using stage evidence and profile snapshot | Presentation urgency plus export/workflow gate. | `severity = warning`, `is_blocking = false` |

Decision: P0 uses this minimal `issue_type` set.

| IssueType | Main use | Default severity | Default `is_blocking` | Rationale |
| --- | --- | --- | --- | --- |
| `provider_call_failed` | Timeout, unavailable, dependency/config/model/tool failures. | `error` | true while required output is absent | One bucket is enough; `error_code` preserves exact cause. |
| `provider_refusal` | Policy/content refusal from provider. | `error` | true while required output is absent | First-class compliance path without evasion logic. |
| `stage_output_invalid` | Structured output invalid, unparseable, or schema-invalid. | `error` | true if no usable accepted output exists | Covers invalid JSON and invalid provider payloads. |
| `ocr_text_missing` | OCR returns empty/unusable text for a processable TextBlock. | `error` | true unless skipped/manual path accepted | Required by Q01 and OCR fallback/manual flow. |
| `translation_missing_block` | Page translation omits or invalidates one TextBlock. | `error` | true for that TextBlock unless skip/manual/warning path accepted | Supports partial Page translation without losing valid block results. |
| `translation_quality_problem` | Empty translation, untranslated text, term mismatch, overlong text, obvious quality risk. | `warning` or `error` by `error_code` | profile-dependent | Keeps P0 checks without separate issue types for every translation smell. |
| `cleaning_skipped_complex_region` | Cleaner cannot safely clean complex background/region. | `warning` | false by default | Complex areas may be skipped in MVP and must remain visible. |
| `typesetting_overflow` | Text cannot fit target area after allowed layout attempts. | `warning` | profile/output-dependent | Required by Q06; preview may still be usable. |
| `artifact_unavailable` | Official artifact missing, hash-invalid, or registration failed. | `blocking` for required active artifacts; otherwise `error` | true for required active artifacts | Covers recovery/export missing artifact and S03. |
| `export_precondition_failed` | `export_check` finds direct readiness failure not already represented by another open issue. | `blocking` | true | Keeps export readiness data-driven without duplicating every blocker. |

## 5. Minimal Vocabulary / Fields

Required severity vocabulary is exactly:

| Severity | Meaning | Gate implication |
| --- | --- | --- |
| `info` | Audit-only or diagnostic note. Rare in P0. | Never blocking. |
| `warning` | Output is usable but imperfect/incomplete. | Non-blocking unless profile converts to error/blocker. |
| `error` | Target output is failed, missing, or suspect. | May or may not block export depending on scope/profile/accepted skip. |
| `blocking` | Normal workflow/export cannot proceed for the target scope. | Always `is_blocking = true`. |

`is_blocking` is not a synonym for severity.

| Field | Rule |
| --- | --- |
| `severity` | Describes quality urgency and UI/report prominence. |
| `is_blocking` | Boolean gate used by export/readiness queries: `is_blocking = true and status = open`. |
| `severity = blocking` | Must imply `is_blocking = true`. |
| `severity = warning/info` | Must imply `is_blocking = false`. |
| `severity = error` | Can be blocking or non-blocking depending on target, usable output, accepted skip, and `ProcessingProfileSnapshot`. |

Minimal fields consumed by this taxonomy:

| Field | P0 use |
| --- | --- |
| `target_type`, `target_id`, common scope ids | Page/TextBlock/artifact-scoped issue targeting. |
| `discovered_stage` | Stage where the issue was detected, e.g. `translation_check`, `export_check`. |
| `root_stage` | Likely cause boundary, e.g. `ocr`, `translation`, `provider`, `provider_policy`, `artifact`. |
| `issue_type` | One of the P0 values above. |
| `error_code` | Specific observed condition; can be more numerous than `issue_type`. |
| `severity`, `is_blocking`, `status` | Gate and lifecycle behavior. |
| `message_key`, `suggested_action` | Stable UI hooks; exact text is deferred. |
| Attempt/tool/artifact/result refs | Audit, retry, recovery, and stale/supersede behavior. |

## 6. Normal Path

Normal stage result:

1. Provider returns valid structured output and sanitized metadata.
2. StageExecutor registers official artifacts through ArtifactService where needed.
3. QualityCheckService checks provider output, registered artifacts, and result metadata.
4. If no issue applies, it returns an empty issue list and may mark older related open issues `resolved`, `stale`, or `superseded`.
5. WorkflowLoopEngine receives stage evidence plus empty/non-blocking issues and decides `continue` or final readiness.

No `info` issue should be created for a happy path by default. Successful attempts are explained by `WorkflowAttempt`, `ToolRunLog`, artifacts, result rows, and `WorkflowDecision`.

## 7. Failure / Edge Path

| Edge case | IssueType | Example `error_code` | Target | Default gate |
| --- | --- | --- | --- | --- |
| OCR returns empty text | `ocr_text_missing` | `ocr_no_text` | TextBlock | Blocking until retry, fallback, manual OCR, or accepted skip. |
| OCR provider times out | `provider_call_failed` | `ocr_timeout` | TextBlock or Page | Blocking for required OCR output while unresolved. |
| Translation JSON invalid | `stage_output_invalid` | `translation_invalid_json` | Page attempt or affected TextBlocks | Blocking until retry/fallback/manual path. |
| Translation omits one TextBlock | `translation_missing_block` | `translation_missing_text_block` | TextBlock | Blocking for that TextBlock; Page may continue only through warning/skip/manual policy. |
| Translation is empty/untranslated | `translation_quality_problem` | `translation_empty` / `translation_untranslated` | TextBlock | Usually blocking until corrected. |
| Translation violates term or is too long | `translation_quality_problem` | `translation_term_mismatch` / `translation_too_long` | TextBlock | Warning by default; strict profile may block. |
| Provider refuses content | `provider_refusal` | `translation_provider_refused`, `translation_nsfw_policy_refused`, `translation_child_safety_refused` | Page or TextBlock | Blocking while required output absent; fallback/manual/skip/warning/block is WorkflowLoopEngine-owned. |
| Cleaner skips complex background | `cleaning_skipped_complex_region` | `cleaning_complex_background` | TextBlock | Warning by default. Pure `ready_for_export` not allowed while unresolved. |
| Typesetter overflows | `typesetting_overflow` | `typeset_overflow` | TextBlock or Page | Warning if preview usable and profile allows; blocking if unreadable/no usable output/strict. |
| Output file missing/hash mismatch | `artifact_unavailable` | `artifact_missing`, `artifact_hash_mismatch` | Artifact plus Page/TextBlock scope | Blocking when active original/cleaned/typeset is required. |
| Artifact registration fails | `artifact_unavailable` | `artifact_registration_failed` | Page/TextBlock | Blocking; provider temp file is not official. |
| Export readiness sees stale/missing active output | `export_precondition_failed` or `artifact_unavailable` | `export_active_typeset_missing`, `export_stale_output` | Page/Batch | Blocking. |
| Export readiness sees existing open blocker | no new issue by default | `export_blocked_by_open_issue` on ExportRecord/decision if needed | Page/Batch | Existing blocking issue remains source of truth. |

## 8. Boundary Rules

- Provider Adapter returns structured outputs/errors and sanitized metadata only.
- Provider Adapter must not access SQLite, register official artifacts, create `QualityIssue`, or decide retry/fallback/skip/warning/pause/cancel/block.
- ArtifactService may report artifact registration/validation evidence such as missing/hash mismatch, but must not decide rebuild/retry/warning/block.
- QualityCheckService creates/classifies `QualityIssue`, assigns severity, `is_blocking`, `discovered_stage`, `root_stage`, message key, and suggested action.
- QualityCheckService must not advance workflow state, update active pointers, or decide retry/fallback/skip/export readiness.
- StageExecutor may normalize stage evidence and invoke QualityCheckService, but final decision belongs to WorkflowLoopEngine.
- WorkflowLoopEngine owns retry, fallback, skip, warning acceptance, pause, block, and readiness decisions.
- Open blocking issues block normal export/readiness only through the data query: `is_blocking = true and status = open` in scope.
- Provider refusal messages must not suggest prompt evasion, policy bypass, or retrying the same provider in a way intended to avoid policy enforcement.

## 9. FakeProvider or FakeQuality Implications

FakeQualityCheck should be deterministic and use the same taxonomy as production checks.

| Fake mode | Fake output/evidence | Expected issue |
| --- | --- | --- |
| happy path | Valid OCR/translation/cleaned/typeset outputs. | No issue. |
| `ocr_empty` | OCR success-shaped output with empty text. | `ocr_text_missing`, `ocr_no_text`. |
| `ocr_fail_once` | First attempt standardized timeout/model error, second valid output. | `provider_call_failed` on first attempt, later resolved/superseded. |
| `translation_invalid_json` | Raw invalid payload retained as failed/debug artifact when policy says so. | `stage_output_invalid`, `translation_invalid_json`. |
| `translation_partial` | Valid translations for some TextBlocks, omitted ids for others. | `translation_missing_block` per missing TextBlock. |
| `provider_refusal` | Standardized refusal with sanitized metadata. | `provider_refusal`; `root_stage = provider_policy`. |
| `cleaning_skip` | Cleaner reports complex background and no destructive output. | `cleaning_skipped_complex_region`. |
| `typeset_overflow` | Preview artifact plus overflow metrics/flag. | `typesetting_overflow`. |
| `missing_artifact` | Test setup removes or invalidates active artifact after registration. | `artifact_unavailable` discovered by ArtifactService/QualityCheck/export_check. |

FakeProvider must not create official artifact records or QualityIssues. FakeQualityCheck may be a simple rule engine over fake result fields and standardized errors.

## 10. Recovery / Audit Impact

| Concern | Contract impact |
| --- | --- |
| Provider refusal | Persist ToolRunLog, WorkflowAttempt, failed evidence artifact if retained, `provider_refusal` issue, and WorkflowDecision. |
| Invalid output | Raw response may be retained as failed/debug artifact; issue links attempt/tool/artifact refs. |
| Partial translation | Valid TranslationResults remain; missing blocks carry TextBlock-scoped issues under the same page attempt. |
| Missing artifact | ArtifactService marks storage state; QualityCheck/export_check emits `artifact_unavailable` only when it affects workflow/readiness. |
| Edits/stale state | Issues tied to obsolete input/result hashes become `stale` or `superseded`; old issues remain auditable. |
| Export gate | Query open blocking issues, not severity strings alone. Warning-only readiness depends on `ProcessingProfileSnapshot`. |

`root_stage` should identify the cause boundary, not merely the detection point:

| Situation | `discovered_stage` | `root_stage` |
| --- | --- | --- |
| Translation invalid JSON detected after provider call | `translation` or `translation_check` | `translation` or `provider` |
| Provider policy refusal during translation | `translation` | `provider_policy` |
| Typesetting overflow caused by long translation | `typesetting` | `translation` or `typesetting` based on evidence |
| Active typeset file missing at export_check | `export_check` | `artifact` |

## 11. HARNESS Scenario Coverage

| Scenario | Coverage |
| --- | --- |
| P01, S01, F01 happy path | Empty issue list; attempts/artifacts/results explain success. |
| P02 provider timeout/transient failure | `provider_call_failed` plus specific `error_code`; WorkflowLoopEngine decides retry/fallback/block. |
| P03, Q04, F04 provider refusal | `provider_refusal`, `root_stage = provider_policy`; no bypass behavior. |
| P04, Q02, F03 invalid structured output | `stage_output_invalid`, `translation_invalid_json`, failed evidence artifact eligible for retention. |
| P05, Q03 partial translation | Valid block results persist; missing blocks get `translation_missing_block`. |
| A04, F07 missing active artifact | `artifact_unavailable`; ArtifactService detects storage state, WorkflowLoopEngine decides rebuild/block. |
| Q01 OCR empty result | `ocr_text_missing` with severity/blocking/action fields. |
| Q05, F05 cleaning complex background | `cleaning_skipped_complex_region`, warning by default, never pure ready while unresolved. |
| Q06, F06 typesetting overflow | `typesetting_overflow`, preview artifact can be retained, profile determines blocking. |
| S02 provider fails before artifact output | `provider_call_failed`; no provider-created issue. |
| S03 artifact registration failure | `artifact_unavailable`; provider temp file remains non-official. |
| S04 blocking quality issue | Any issue with `is_blocking = true` prevents accepted export-effective pointer/readiness. |
| S05 warning quality issue | `is_blocking = false`; issue remains visible and warning readiness depends on profile. |

## 12. Rejected Alternatives

| Alternative | Reason rejected |
| --- | --- |
| Make every SRS error code an IssueType. | Too large for MVP and duplicates `error_code`. |
| Use only generic `quality_failed`. | Too vague for retry/fallback/manual guidance and quality reports. |
| Use severity alone for export gates. | Export must query explicit `is_blocking`; `error` can be non-blocking after accepted skip/warning. |
| Remove `blocking` severity because `is_blocking` exists. | HLD/data-model already require it; useful for UI prominence and unambiguous blockers. |
| Stage-specific refusal issue types only, e.g. `translation_provider_refused`. | Better as `issue_type = provider_refusal` plus stage/error_code details. |
| Let export_check create a new issue for every existing blocker. | Duplicates root issues and makes resolution confusing. |
| Let Provider Adapter create QualityIssues directly. | Violates architecture boundaries and harms recovery/testability. |

## 13. Risks

| Risk | Mitigation |
| --- | --- |
| Taxonomy too generic for UI filtering. | Preserve detail in `error_code`, `message_key`, `suggested_action`, and stage/root fields. |
| Profile-dependent `is_blocking` causes inconsistent behavior. | Always store the `ProcessingProfileSnapshot`/hash on attempts/decisions and keep severity/blocking auditable. |
| `translation_quality_problem` becomes a junk drawer. | Limit P0 error codes; promote subtypes later only when UI/workflow needs diverge. |
| Export_check issues duplicate upstream issues. | Create `export_precondition_failed` only for direct readiness defects not already represented. |
| Provider refusal under-blocks unsafe/no-output cases. | Default refusal blocks while required output is absent; fallback/manual/skip must produce changed evidence. |
| Artifact cleanup noise becomes user-facing. | Emit `artifact_unavailable` only when active output, recovery, or export readiness is affected. |

## 14. Open Questions

1. Should `severity = error` with `is_blocking = false` be allowed in final enum rules, or should accepted skips downgrade severity to `warning`?
2. Should `export_precondition_failed` remain a P0 IssueType, or should export_check rely only on existing upstream/artifact issues plus ExportRecord status?
3. Which exact `translation_quality_problem` error codes are required in MVP-0: empty, untranslated, term mismatch, too long, or all four?
4. Should warning export require per-export user acknowledgement in addition to `ProcessingProfileSnapshot.allow_warning_export`?
5. Should non-active debug/failed-evidence artifact cleanup failures create user-visible issues or maintenance-only audit records?
