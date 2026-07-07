## 1. Scope

This proposal covers the minimal user-facing message contract and FakeQualityCheck behavior needed for the FakeProvider single-Page backend vertical slice.

In scope:

| Area | Decision |
| --- | --- |
| QualityIssue messages | Stable `message_key`, small safe `message_params`, and `suggested_action_key`. |
| Provider refusal presentation | Explain refusal safely without bypass, evasion, or prompt advice. |
| Cleaning skip | Explain skipped automatic cleaning as a visible warning, not silent success. |
| Typesetting overflow | Explain layout overflow with safe remediation options. |
| FakeQualityCheck | Deterministic issue creation for HARNESS replay and debug usefulness. |

Out of scope:

- Final UI copy, localization, page layouts, toasts, dialogs, route DTOs, or frontend behavior.
- Real provider prompts, prompt-repair wording, provider-policy interpretation, or bypass logic.
- Full IssueType catalog, full severity matrix, SQL DDL, ORM models, or migrations.

## 2. Role Bias

Prefer messages that help an ordinary reader understand what happened, what is affected, and what safe next steps exist.

Bias decisions:

| Preference | Rationale |
| --- | --- |
| Message keys over hardcoded prose | Keeps backend small, stable, localizable, and testable. |
| Safe remediation over technical detail | Users need retry/manual/edit/review choices, not provider internals. |
| Deterministic fake issues | FakeProvider vertical slice must be replayable and debuggable. |
| Explicit refusal boundary | Prevents accidental policy-bypass suggestions in UI or logs. |

## 3. Assumptions

- `docs/HLD-v0.2.md` is the accepted HLD baseline and does not materially conflict with `docs/HLD.md`; it strengthens the same architecture direction.
- QualityCheckService creates/classifies issues but does not advance workflow state, update active pointers, or choose retry/fallback/skip/warning/block.
- WorkflowLoopEngine owns decisions such as `fallback_provider`, `skip_target`, `mark_warning`, `pause_for_user`, and `block`.
- Provider Adapters return structured success/error/refusal evidence and sanitized metadata; they do not create QualityIssue records.
- Final UI/API design may translate message keys into Chinese or other user-facing text later.
- Message examples below are design guidance only, not final product copy.

## 4. Proposed Contract

**QualityIssue message contract**

Each QualityIssue produced by QualityCheckService should include:

| Field | Required | Purpose |
| --- | --- | --- |
| `message_key` | Yes | Stable, testable user-facing reason identifier. |
| `message_params` | Optional | Small sanitized values such as counts, stage, block id, provider display name. |
| `suggested_action_key` | Yes | Safe action hint for UI/API to render later. |
| `debug_summary` | Optional | Sanitized developer/review summary, not shown as primary user copy. |
| `safe_detail_level` | Optional | `user`, `review`, or `debug` visibility hint. |

`sanitized_message` may exist for logs/review, but it must not be the durable primary UI contract. Durable behavior should key off `issue_type`, `error_code`, `message_key`, `severity`, `is_blocking`, and `suggested_action_key`.

**Minimal decision table**

| Issue condition | Message key | Suggested action key | Safety rule |
| --- | --- | --- | --- |
| OCR empty | `ocr.no_text` | `action.enter_or_retry_ocr` | No claim that image is invalid. |
| Translation invalid JSON | `translation.invalid_output` | `action.retry_or_review_translation` | Do not show raw model output by default. |
| Translation missing TextBlock | `translation.missing_text_block` | `action.retry_or_manual_translate` | Preserve valid block results. |
| Provider refusal | `provider.refused` or stage-specific key | `action.use_allowed_alternative_or_manual` | No bypass, prompt rewrite, or evasion suggestion. |
| Cleaning complex background | `cleaning.skipped_complex_background` | `action.review_skip_or_retry_cleaning` | Explain original content remains visible. |
| Typesetting overflow | `typesetting.overflow` | `action.shorten_or_review_layout` | Suggest edit/retry/review, not hiding overflow. |
| Missing artifact | `artifact.missing` | `action.rebuild_or_restore_artifact` | Do not imply data was deleted intentionally. |

## 5. Minimal Vocabulary / Fields

**Message keys**

Minimum P0 message keys:

| Key | Target | Default severity | Blocking default | User meaning |
| --- | --- | --- | --- | --- |
| `ocr.no_text` | TextBlock | `error` | Profile-dependent | OCR returned no usable text. |
| `translation.invalid_output` | Page or TextBlock | `error` | Yes until repaired | Translation output could not be parsed or trusted. |
| `translation.missing_text_block` | TextBlock | `warning` or `error` | Profile-dependent | A page translation omitted this block. |
| `translation.partial_output` | Page | `warning` | Profile-dependent | Some translations are usable; some need attention. |
| `provider.refused` | Page or TextBlock | `error` | Profile-dependent | Provider declined the request under its rules. |
| `provider.refused.translation` | Page or TextBlock | `error` | Profile-dependent | Translation provider refused this text/page. |
| `provider.unavailable` | Stage target | `error` | Profile-dependent | Required provider/config is unavailable. |
| `cleaning.skipped_complex_background` | TextBlock or Page | `warning` | Usually no | Automatic cleaning skipped a risky area. |
| `cleaning.mask_missing` | TextBlock | `error` | Usually yes | Cleaning cannot run because mask evidence is missing. |
| `typesetting.overflow` | TextBlock or Page | `warning` or `error` | Profile-dependent | Translation did not fit in the target area. |
| `artifact.missing` | Artifact owner | `error` | Yes for required active outputs | Expected official artifact is absent or hash-invalid. |
| `export.blocked_by_open_issue` | Page or Batch | `blocking` | Yes | Export readiness is blocked by open issues. |

**Suggested action keys**

Minimum P0 `suggested_action_key` values:

| Key | Meaning | Decision owner |
| --- | --- | --- |
| `action.retry_same_stage` | Retry may help if budget/profile allows. | WorkflowLoopEngine |
| `action.use_allowed_alternative_or_manual` | Use configured fallback/local/manual path when allowed. | WorkflowLoopEngine/user |
| `action.enter_or_retry_ocr` | User can enter OCR text or rerun OCR. | User/WorkflowLoopEngine |
| `action.retry_or_manual_translate` | Retry translation or provide manual translation. | User/WorkflowLoopEngine |
| `action.review_skip_or_retry_cleaning` | Review skipped cleaning, retry, or accept warning if allowed. | User/WorkflowLoopEngine |
| `action.shorten_or_review_layout` | Shorten translation or review layout/region. | User |
| `action.rebuild_or_restore_artifact` | Rebuild when possible or restore missing file. | WorkflowLoopEngine/user |
| `action.none_required` | Informational issue only. | None |

These are action hints, not workflow decisions. The final decision must still be persisted as WorkflowDecision.

**Safe message params**

Allowed params:

| Param | Example | Rule |
| --- | --- | --- |
| `stage` | `translation` | Canonical workflow stage only. |
| `target_type` | `TextBlock` | No raw path. |
| `target_label` | `Block 3` | User-readable label, not internal secret. |
| `provider_display_name` | `Cloud translation provider` | Sanitized; no API key/base URL. |
| `missing_count` | `1` | Counts only. |
| `total_count` | `5` | Counts only. |
| `artifact_type` | `typeset_image` | Stable artifact vocabulary only. |

Forbidden params:

- Raw provider payloads by default.
- API keys, tokens, credentials, secret refs, headers, base URLs with credentials.
- Prompt text intended to avoid provider refusal.
- Unredacted filesystem paths when not needed for UI.
- Sensitive provider rationale text unless sanitized and explicitly retained as debug artifact.

## 6. Normal Path

| Step | Behavior | Evidence |
| --- | --- | --- |
| Provider succeeds | StageExecutor passes structured output to ArtifactService and QualityCheckService. | Attempt/log/artifact/result metadata. |
| QualityCheck passes | No user-facing issue required, or optional `info` issue only when useful for review. | `continue` decision by WorkflowLoopEngine. |
| Non-blocking warning exists | QualityIssue includes message/action keys; output remains usable if profile allows. | `mark_warning` or later warning-ready decision. |
| Export readiness | No open blockers; warnings/skips only if snapshot permits. | `finish_ready_for_export` or `finish_ready_for_export_with_warnings`. |

Normal messages should stay quiet. The primary review surface should show only relevant open warnings/errors, not a verbose log of successful checks.

## 7. Failure / Edge Path

**Provider refusal**

Decision:

- Represent refusal as first-class evidence with `issue_type = provider_refusal` or stage-specific equivalent.
- Use `message_key = provider.refused.translation` for translation refusal in MVP.
- Use `suggested_action_key = action.use_allowed_alternative_or_manual`.

Safe user presentation:

| Do | Do not |
| --- | --- |
| Say the selected provider declined the request. | Say how to bypass, jailbreak, reword, or evade policy. |
| Say the workflow can use only allowed configured alternatives or manual input. | Suggest retrying the same provider with hidden prompt changes after policy refusal. |
| Say provider details are recorded safely for review. | Show raw provider payload by default. |
| Let WorkflowLoopEngine choose fallback/pause/block. | Let QualityCheckService or Provider Adapter choose fallback. |

Example safe meaning: "The translation provider declined this request. You can use an allowed configured alternative, enter a translation manually, or leave the item blocked."

**Cleaning skip**

Decision:

- `cleaning.skipped_complex_background` is a warning by default unless profile/issue policy makes it blocking.
- It must remain visible because pure `ready_for_export` is illegal when required content is skipped.
- It may lead to warning readiness only through WorkflowLoopEngine and ProcessingProfileSnapshot.

User meaning: automatic cleaning skipped an area because it might damage the image; the original region remains visible.

**Typesetting overflow**

Decision:

- `typesetting.overflow` records overflow at TextBlock or Page scope.
- If a preview artifact exists, it may be retained for review through ArtifactService.
- Suggested action is `action.shorten_or_review_layout`.
- WorkflowLoopEngine decides `retry_upstream_stage`, `mark_warning`, `pause_for_user`, or `block`.

User meaning: the translation is too long for the current area under current layout limits; the user can shorten text, review layout, or rerun allowed steps.

**Partial translation**

Decision:

- Valid translations remain usable and versioned.
- Missing blocks get `translation.missing_text_block`.
- Page-level aggregate may also get `translation.partial_output` for review summary.

Edge case: If all blocks are missing, do not present it as partial success; classify as invalid/failed translation output.

## 8. Boundary Rules

| Boundary | Rule |
| --- | --- |
| Provider Adapter | Does not create messages, QualityIssues, decisions, official artifacts, or remediation advice. |
| QualityCheckService | Creates/classifies issue, message key, severity, blocking flag, root/discovered stage, and suggested action key. |
| WorkflowLoopEngine | Decides retry/fallback/skip/warning/pause/block/readiness. |
| ArtifactService | Registers artifacts and reports storage state; does not decide user remediation. |
| Repository / DAO | Persists issue/message fields; does not invent messages. |
| UI/API | May render/localize keys later; should not infer provider bypass guidance. |

Boundary edge cases:

| Case | Required boundary behavior |
| --- | --- |
| Provider returns raw refusal text | Adapter sanitizes metadata; QualityCheck maps to safe key; raw text retained only under artifact policy. |
| QualityCheck sees overflow | It may suggest `action.shorten_or_review_layout`; it does not rerun translation. |
| Cleaning provider says "skip" | QualityCheck records warning; WorkflowLoopEngine decides `skip_target` or other path. |
| Missing active artifact | ArtifactService marks missing; QualityCheck may create `artifact.missing`; WorkflowLoopEngine decides rebuild/block. |

## 9. FakeProvider or FakeQuality Implications

**FakeQualityCheck deterministic modes**

FakeQualityCheck should be deterministic from explicit fake mode, stage, target id, and structured fake output. It should not use randomness.

| Fake mode | Stage | FakeQualityCheck issue |
| --- | --- | --- |
| `happy_path` | all | No open issue. |
| `ocr_empty` | `ocr` | `ocr.no_text`, `issue_type = ocr_no_text`. |
| `translation_invalid_json` | `translation` or `translation_check` | `translation.invalid_output`, blocking by default. |
| `translation_missing_block` | `translation_check` | `translation.missing_text_block` for configured block id; optional page `translation.partial_output`. |
| `provider_refusal` | `translation` | `provider.refused.translation`, `root_stage = provider_policy`. |
| `cleaning_complex_background` | `cleaning` | `cleaning.skipped_complex_background`, warning by default. |
| `typesetting_overflow` | `typesetting` | `typesetting.overflow`, preview artifact reference if present. |
| `missing_artifact` | `export_check` or recovery | `artifact.missing`, blocking if required active artifact. |

**Predictable issue payloads**

For every fake issue, use stable fixtures:

| Field | Fake rule |
| --- | --- |
| `target_type` / `target_id` | Use configured fake target or first deterministic TextBlock. |
| `message_key` | Exact key from this proposal. |
| `message_params` | Counts and labels only. |
| `suggested_action_key` | Exact key from this proposal. |
| `debug_summary` | Include fake mode, stage, and sanitized cause. |
| `input_hash` / `config_hash` | Use deterministic fake hashes from the test fixture. |

FakeQualityCheck should support review/debug output that explains why an issue appeared, but that explanation must be sanitized and clearly marked fake/debug.

## 10. Recovery / Audit Impact

| Event | Audit impact | Recovery impact |
| --- | --- | --- |
| Provider refusal | ToolRunLog, refused attempt, QualityIssue, WorkflowDecision link remain explainable. | Resume cannot silently retry same provider with bypass; must follow snapshot policy. |
| Cleaning skip | Warning issue and skip reason remain visible. | Pure readiness stays withdrawn until issue resolved or warning-ready path accepted. |
| Typesetting overflow | Preview artifact and issue remain linked to attempt if available. | Rerun/edit can stale or supersede issue; old preview remains audit/history per retention. |
| Fake issue | Deterministic issue can be replayed from fake mode. | Harness can assert exact key/action/severity/blocking behavior. |
| Message catalog changes later | Stable keys preserve historical meaning. | UI copy can evolve without rewriting audit records. |

QualityIssue status rules:

- Use `open` while issue applies to active evidence.
- Use `stale` when active input/result changed and the old issue no longer applies.
- Use `superseded` when a current newer issue replaces the old one.
- Use `accepted_warning` only when warning acceptance is explicit under workflow/export policy.

## 11. HARNESS Scenario Coverage

| HARNESS scenario | Coverage from this proposal |
| --- | --- |
| P03 Provider refusal | Safe `provider.refused.translation` message and no bypass suggestions. |
| P04 Invalid structured output | `translation.invalid_output` key and retry/review action hint. |
| P05 Partial output | Valid block results preserved; missing block key plus page summary key. |
| Q01 OCR empty result | `ocr.no_text` key with manual/retry action. |
| Q02 Translation invalid JSON | Blocking-capable invalid-output issue key. |
| Q03 Translation missing TextBlock | TextBlock-scoped missing key and deterministic fake target. |
| Q04 Provider refusal issue | `root_stage = provider_policy`, safe message/action, no evasion. |
| Q05 Cleaning complex background | Warning skip key and explanation that original content remains. |
| Q06 Typesetting overflow | Overflow key, preview artifact usefulness, shorten/review action. |
| S04 Blocking quality issue | Message key is issue evidence; WorkflowLoopEngine still owns block decision. |
| S05 Warning quality issue | Warning remains visible and auditable. |
| F03 Fake invalid JSON | Deterministic `translation_invalid_json` fake issue. |
| F04 Fake provider refusal | Deterministic refusal issue without real provider. |
| F05 Fake cleaning skip | Deterministic cleaning warning. |
| F06 Fake typesetting overflow | Deterministic overflow warning/error with optional preview artifact. |
| F07 Fake missing artifact | Deterministic `artifact.missing` blocker for required active output. |

Validation approach for this proposal: document review against HARNESS scenarios and architecture invariants only. No tests were run because this is a documentation-only Phase 1A proposal.

## 12. Rejected Alternatives

| Alternative | Rejected because |
| --- | --- |
| Store final English/Chinese prose only | Hard to localize, hard to test, and brittle for audit. |
| Let Provider Adapter return user-facing remediation text | Violates boundary and risks provider-specific bypass suggestions. |
| Treat provider refusal as generic failure message | Loses compliance semantics and HARNESS P03/Q04 evidence. |
| Include raw provider refusal text in normal UI message | Can expose sensitive text and unsafe policy details. |
| Make every warning blocking | Too strict for ordinary-reader MVP and contradicts warning export design. |
| Hide cleaning skips in happy path | Misleads user and violates pure readiness rules. |
| Random FakeQualityCheck behavior | Makes recovery, retry, and HARNESS validation non-repeatable. |
| Design full UI copy catalog now | Scope creep; UI/API localization belongs to later design. |

## 13. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Message keys drift from final IssueType taxonomy | Tests and UI copy may fragment. | Keep keys minimal; final synthesis should normalize names. |
| Safe refusal message feels too vague | User may not know what to do. | Provide safe action keys: allowed alternative, manual input, pause/block. |
| Suggested action mistaken for workflow decision | Boundary violation risk. | Name as `suggested_action_key`; persist actual WorkflowDecision separately. |
| Debug summary leaks provider payload | Privacy/compliance risk. | Require sanitization and safety flags for retained raw artifacts. |
| Cleaning skip looks like successful cleaning | Export/readiness confusion. | Always create visible warning issue for skip. |
| Overflow warning lets unreadable output export | Quality risk. | Profile controls severity/blocking and warning export; issue remains visible. |
| Too few message keys | Some edge cases may use generic keys. | Allow final taxonomy to add keys without changing this minimal contract. |

## 14. Open Questions

| Question | Blocking? | Notes |
| --- | --- | --- |
| Should `message_params` be a first-class persisted field or folded into `sanitized_message` until API design? | No | This proposal recommends first-class params for testability. |
| Should `suggested_action_key` replace or supplement the data-model `suggested_action` field name? | No | Final contract should choose one spelling. |
| Should `provider.refused.translation` be stage-specific or use only `provider.refused` plus `stage = translation`? | No | Stage-specific key is clearer for UI; generic key is smaller. |
| Should warning export require per-export user acknowledgement in addition to profile policy? | No | Already deferred by data/workflow designs; message keys can support either. |
| Should FakeQualityCheck be a distinct test double or a mode inside QualityCheckService? | No | Contract only requires deterministic behavior and no real provider dependency. |
| What is the final localization source of truth for Chinese UI copy? | No | Defer to UI/API design. |
