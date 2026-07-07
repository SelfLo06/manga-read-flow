# Recovery Rules v0.1

Recovery is evidence reconciliation. It must not rely only on `Page.status`.

## Startup reconciliation

1. Find `ProcessingTask` rows in `running`, `pausing`, or `cancelling` with stale or missing heartbeat.
2. Mark each stale task `interrupted`, then `recovering`, in short transactions.
3. Load running attempts, active pointers, result rows, dependency hashes, artifacts, ToolRunLogs, QualityIssues, WorkflowDecisions, and the relevant ProcessingProfileSnapshot.
4. Mark each running attempt according to durable evidence.
5. Recompute TextBlock stage freshness and Page aggregate status.
6. Persist a recovery decision explaining reuse, retry, fallback, pause, warning, or block.
7. Return the task to `running`/`queued` only when auto-resume policy and evidence allow it; otherwise `paused`, `blocked`, `failed`, `succeeded`, or `succeeded_with_warnings`.

Heartbeat stale threshold is implementation-defined and should be configurable. The design requires the threshold to exist, not a specific value.

## Running attempt reconciliation

| Evidence | Attempt outcome |
| --- | --- |
| Accepted result row, active pointer, matching hashes, and required artifact present | `succeeded` or `reused_cached` decision. |
| ToolRunLog/provider metadata shows refusal | `refused`; apply refusal decision policy. |
| ToolRunLog shows failure or invalid output | `failed`; apply retry/fallback/block policy. |
| Output file exists but no official artifact/result/pointer acceptance committed | `abandoned_after_crash` for MVP, unless replay through normal validation/acceptance path is explicitly implemented. |
| No durable completion evidence | `abandoned_after_crash`. |
| Pause/cancel was safely reached | `interrupted` or `cancelled` as appropriate. |

MVP recovery should reuse already committed results and official artifacts. Parsing retained raw provider output into accepted domain results is deferred, except through the same validation, ArtifactService registration, QualityCheckService classification, and WorkflowLoopEngine acceptance path used for normal execution.

## Reuse rules

Reuse requires current dependency evidence, not Page summary status.

| Output | Reuse requirements |
| --- | --- |
| OCRResult | Same TextBlock, matching input/config/geometry/provider key, active pointer or selectable historical result, not invalidated by user edit. |
| TranslationResult | Matching `source_ocr_result_id`, `source_text_hash`, context/glossary/provider/prompt/config hashes, and no locked-translation conflict. |
| Cleaned artifact | Official artifact `present`, matching original/mask/geometry/config hash, no current blocking cleaning issue. |
| Typeset artifact | Official artifact `present`, matching active translations/layout/config/source image hashes, no current blocking typesetting issue. |

If a historical non-active result matches current requirements, the workflow may select it as active only through an explicit `reuse_cached_result` decision and atomic pointer update. It must not create duplicate active result rows.

## Missing artifact rules

| Missing artifact | Recovery behavior |
| --- | --- |
| Original image | Block. Original cannot be rebuilt or overwritten. |
| Failed-attempt/debug payload | Keep workflow usable if no active output depends on it; record reduced diagnostic evidence. |
| OCR/translation raw payload | Reuse committed result rows if present; otherwise retry/fallback/pause/block. |
| Cleaned image | Rebuild cleaning if original, geometry/mask, config, and budget allow; otherwise warning only if not required for output, else block. |
| Typeset image | Rebuild typesetting if active translations and base image are fresh; otherwise block export readiness. |
| Export output | Does not change workflow readiness; export design decides re-export behavior. |

ArtifactService validates path/hash/storage state and marks artifacts `missing`; WorkflowLoopEngine decides rebuild, retry, warning, pause, or block.

## Idempotent rerun rules

- A rerun first performs the same evidence check as crash recovery.
- Existing active OCR/translation results are reused when hashes match.
- Existing cleaned/typeset artifacts are reused when present and provenance matches.
- New provider/tool calls are made only when required evidence is absent, stale, incompatible, explicitly regenerated, or blocked by lock/profile/user choice.
- Reuse creates `WorkflowAttempt.status = reused_cached` or `WorkflowDecision.decision_type = reuse_cached_result` where audit is useful. For stages affecting cost/provider calls, record at least one durable reuse explanation.
- Rerun after OCR edit must not treat old TranslationResults as export-effective if `source_ocr_result_id` or `source_text_hash` mismatches active OCR.
- Rerun with locked translation preserves the locked active translation unless user explicitly overrides it.

## Crash scenario replay

| Scenario | Expected recovery |
| --- | --- |
| Crash after OCR commit before translation | Task `interrupted` -> `recovering`; OCR attempt/result reused; resume at `translation`; OCR provider not called again. |
| Crash during provider call | Running attempt `abandoned_after_crash` unless durable success/refusal/failure evidence exists; automatic retry only within crash retry and stage policy. |
| Crash after file write before artifact registration | Treat temp/orphan as not official for MVP; ArtifactService may clean or later inspect. Do not make it active without normal registration/validation. |
| Crash after result row before active pointer update | Select as active only if transaction evidence or recovery decision proves accepted validation. Otherwise keep historical and retry/pause/block. |
| Crash after user edit transaction | Active edited result remains; downstream stale statuses drive resume from translation/check/typesetting. |

## Auto-resume policy

Auto-resume after recovery is allowed only when:

- no pause/cancel request exists;
- snapshot/task resume policy allows it;
- no user action is required;
- retry/crash budget remains if another attempt is needed;
- active evidence is consistent.

Otherwise recovery ends in `paused` or `blocked` with a visible decision rationale.
