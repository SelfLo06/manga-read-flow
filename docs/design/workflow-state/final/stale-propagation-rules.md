# Stale Propagation Rules v0.1

Stale propagation is dependency invalidation, not deletion. Old results, artifacts, attempts, decisions, and issues remain auditable. Active pointers may remain selected for review even when downstream output is no longer export-effective.

## Export-effective rule

An output is export-effective only when all are true:

- selected by the relevant active pointer;
- stage status is `done` or accepted warning state;
- dependency hashes match current active upstream inputs;
- required official artifact is `present` and hash-valid;
- no open blocking QualityIssue exists in export scope;
- unresolved warnings/skips are allowed by the relevant ProcessingProfileSnapshot.

## OCR edit propagation

When the user edits OCR text for a TextBlock:

1. Create a new OCRResult with user-edit provenance and parent pointer to previous active OCR when available.
2. Set `TextBlock.active_ocr_result_id` to the new OCRResult.
3. Set `TextBlock.ocr_status = done` if the edit passes basic validation; otherwise `needs_review` or `blocked` by issue policy.
4. Set `TextBlock.translation_status = stale`.
5. Set `TextBlock.translation_check_status = stale`.
6. Set `TextBlock.typesetting_status = stale`.
7. Set `TextBlock.review_status = needs_review`.
8. Set Page `translation_context_stale = true`.
9. Set/recompute Page `has_stale_blocks = true`.
10. Keep `TextBlock.active_translation_result_id` for review, but it is not export-effective until regenerated or revalidated against active OCR.
11. Keep `Page.active_typeset_artifact_id` for preview/history, but it is not export-effective.
12. Mark downstream issues tied to old translation/typeset inputs as `stale` or `superseded`.

OCR edit does not make the cleaned image stale by default because geometry/mask/background did not change.

## Translation edit propagation

When the user edits translation text for a TextBlock:

1. Create a new TranslationResult with user-edit provenance, parent pointer when available, and current active OCR source ids/hashes.
2. Set `TextBlock.active_translation_result_id` to the new TranslationResult.
3. Set `TextBlock.translation_status = done` if the edit passes basic persistence validation.
4. Set `TextBlock.translation_check_status = stale`.
5. Set `TextBlock.typesetting_status = stale`.
6. Set `TextBlock.review_status = needs_review`.
7. Set/recompute Page `has_stale_blocks = true`.
8. Do not set Page `translation_context_stale = true` solely because target translation changed.
9. Keep `Page.active_typeset_artifact_id` for preview/history, but it is not export-effective.
10. Mark prior translation/typesetting/export issues tied to old translation text/hash as `stale` or `superseded`.

Translation edit does not make cleaning stale by default.

## Downstream stale matrix

| Trigger | OCR | Translation | Translation check | Cleaning | Typesetting | Page context | Page readiness |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OCR edit | New active OCR `done`/review | `stale` | `stale` | unchanged | `stale` | `translation_context_stale = true` | withdraw ready/export-effective |
| Translation edit | unchanged | New active translation `done`/review | `stale` | unchanged | `stale` | unchanged | withdraw ready/export-effective |
| Re-translation after OCR edit | unchanged | `done` if accepted | `done` if check passed | unchanged | remains `stale` until rerender | clear when all active OCR covered | recompute |
| Translation check rerun | unchanged | unchanged | `done`, warning, or blocked | unchanged | unchanged unless issue requires rework | unchanged | recompute |
| Re-typeset after edit | unchanged | unchanged | unchanged | unchanged | `done` if accepted | unchanged | recompute |

## QualityIssue stale/supersede rules

Use `stale` when active inputs changed and the old issue no longer applies. Use `superseded` when a newer issue records the same target/root cause under current inputs.

After OCR edit, stale/supersede:

- translation issues based on previous OCR;
- translation_check issues for old Page context;
- typesetting issues caused by old translated text;
- export blockers caused only by old translation/typeset output.

Keep open when still applicable:

- detection/geometry issues;
- cleaning/background issues;
- validation issues for the new OCR;
- provider refusal history as audit evidence unless tied only to obsolete attempted output and no current path depends on it.

After translation edit, stale/supersede:

- translation quality issues tied to old TranslationResult when the edit addresses them;
- typesetting overflow/layout issues tied to old translation text/hash;
- export blockers caused by old typeset output.

Keep open when still applicable:

- OCR issues;
- cleaning issues;
- provider refusal issues for blocks still lacking active user/local translation;
- new review/check issues for edited translation.

## Locked translation rule

Locking is not a stage status. `locked_translation_result_id` and lock metadata preserve user-selected translation. Automatic retranslation must not replace it without explicit override. A locked result can still cause downstream `stale` status if upstream OCR changes; the workflow should pause/block for user choice rather than silently replace it.

## Rework resume rules

- After OCR edit, resume from `translation` or `translation_check` according to selected rework scope and profile; do not rerun OCR.
- After translation edit, resume from `translation_check` or `typesetting`; do not rerun OCR or cleaning unless another dependency requires it.
- Page-level translation may update multiple TextBlocks because context changed; valid partial results update only their own active pointers.
- Typesetting rework creates a new official artifact through ArtifactService and updates Page active typeset pointer atomically after acceptance.
