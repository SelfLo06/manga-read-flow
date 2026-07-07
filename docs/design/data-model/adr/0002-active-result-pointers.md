# ADR 0002: Active Result Pointers

## Status

Accepted.

## Context

OCRResult and TranslationResult are versioned. The system must know which version is currently selected without creating duplicate active sources of truth.

## Decision

Use owner pointers as the P0 source of truth:

- `TextBlock.active_ocr_result_id`
- `TextBlock.active_translation_result_id`
- `TextBlock.locked_translation_result_id`
- Page active artifact pointers for original, cleaned, and typeset outputs

Do not use independent active flags on result rows.

## Rationale

Pointers make the selected result explicit from the owning object, avoid multiple-active rows, simplify recovery reads, and make user edits transactionally clear.

## Rejected alternatives

- `is_active` flags on results: can drift and require partial uniqueness constraints.
- Latest timestamp wins: breaks locked/manual selection.
- Clearing active pointers on stale: loses review context.

## Consequences

- Pointer target must be validated to belong to the same TextBlock/Page.
- Active means selected, not necessarily export-effective.
- Stale checks and export gates remain required.

## Validation

Supports OCR edit, translation edit, locked translation, restart after crash, and cache reuse without ambiguous current result selection.
