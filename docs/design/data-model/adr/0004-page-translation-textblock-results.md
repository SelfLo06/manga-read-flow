# ADR 0004: Page Translation with TextBlock Results

## Status

Accepted.

## Context

HLD requires Page-level translation context, but review, edit, retry, lock, quality issues, and typesetting operate at TextBlock granularity.

## Decision

Use one page-scoped `WorkflowAttempt` and `ToolRunLog` for a Page translation call. Persist one `TranslationResult` per valid returned TextBlock. For missing or invalid block outputs, create `QualityIssue` records without discarding valid block results.

## Rationale

This preserves page context and provider call trace while keeping local correction and typesetting block-level.

## Rejected alternatives

- One Page-level TranslationResult blob: blocks TextBlock-level edit/retry/lock.
- One provider call per TextBlock by default: loses page context and increases cost.
- Reject entire page output on partial validity: loses valid work and harms recovery.

## Consequences

- TranslationResult links to shared attempt/tool run and records `page_translation_group_key`.
- Partial page results require issue records for missing/invalid blocks.
- Single-block retranslation still carries page context.

## Validation

Supports page-context translation, provider invalid JSON, partial valid output, single-block retry, and restart recovery after partial translation.
