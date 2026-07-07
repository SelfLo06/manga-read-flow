# Open Questions

Final synthesis resolves the cross-review blockers. No blocking open question remains for MVP data model design.

## Resolved Decisions

| Former blocker | Final decision |
| --- | --- |
| Active pointer vs active flag | Use active pointers as the only P0 active source of truth. Do not maintain independent active flags. |
| Export gate semantics | Normal export blocks any open blocking QualityIssue in scope. Warning export follows ProcessingProfileSnapshot. |
| Provider refusal persistence | Persist provider refusal as ToolRunLog + WorkflowAttempt + QualityIssue + WorkflowDecision, with retained evidence artifacts when available. |
| SRS ProjectConfig mapping | Map to Project defaults, ProcessingProfile templates, provider config references, and project.db ProcessingProfileSnapshot. No separate P0 ProjectConfig table. |
| Artifact storage states | Use `present`, `metadata_only_cleaned`, `moved_to_trash`, `missing`, and `deleted`. |
| Page-level translation partial output | Keep one page-scoped attempt/log; create TranslationResults for valid blocks and QualityIssues for missing/invalid blocks. |
| ProcessingProfile snapshot representation | Editable templates in app.db; immutable snapshot rows in project.db. |
| Crash recovery vocabulary | Use `interrupted`, `recovering`, and `abandoned_after_crash` for stale running task/attempt reconciliation. |
| TranslationResult source link | Store both `source_ocr_result_id` and `source_text_hash`. |
| TextBlock geometry | Keep geometry fields on TextBlock for P0. Defer `GeometryRevision` to P1. |

## Non-Blocking Open Questions

1. Exact enum spellings for statuses, stages, issue types, decision types, artifact types, retention classes, and error codes.
2. Exact primary key format: UUIDv7, ULID, integer plus public id, or another stable id strategy.
3. Exact retention TTLs for successful raw payloads, debug artifacts, rebuildable crops, and replaced preview artifacts.
4. Whether warning export needs explicit per-export user acknowledgement in addition to ProcessingProfileSnapshot policy.
5. Whether cleanup failures should create user-visible QualityIssues or maintenance-only records when they do not affect recovery/export.
6. Whether failed attempt payloads should be retained until Project deletion or have a long configurable TTL while still being persisted by default.
7. Whether GlossaryVersion snapshot artifacts are retained by default in strict/debug profiles or only on demand.
8. Whether OCR crop artifacts are retained by default for review or treated as rebuildable after a grace period.
9. Whether project soft delete should immediately move the full workspace to trash or first mark it trash-pending until no task is running.
10. Whether Batch/Page aggregate status is persisted with reconciliation or mostly derived in early implementation.

## Deferred Design-Stage Questions

1. Exact SQL DDL and SQLite-enforceable constraints.
2. Exact SQLAlchemy mapping style and repository method names.
3. Exact Pydantic DTOs and API route shapes.
4. Exact WorkflowLoopEngine state machine and retry budget arithmetic.
5. Exact QualityCheckService issue taxonomy and user-facing message catalog.
6. Exact artifact directory layout, atomic write strategy, and cleanup scheduler.
7. Exact provider capability/license metadata schema and secret store integration.
8. Exact export manifest schema.
9. Exact P1 forced/incomplete export semantics.
10. Exact P1 GeometryRevision schema and migration from TextBlock geometry fields.
