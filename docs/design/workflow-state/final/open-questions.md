# Workflow State Open Questions v0.1

No blocking open question remains for the MVP workflow-state synthesis.

## Non-blocking open questions

1. Exact enum enforcement mechanism and migration details for stages/statuses/decisions/reason codes.
2. Exact heartbeat stale threshold for interrupted tasks.
3. Whether recovery auto-resumes by default or waits for the user for some profiles.
4. Exact hard global automatic decision ceiling per task.
5. Exact default retry budgets for fast/balanced/strict profiles.
6. Exact issue classes eligible for automatic skip in default profiles.
7. Whether warning export requires per-export user acknowledgement in addition to `ProcessingProfileSnapshot.allow_warning_export`.
8. Exact QualityIssue taxonomy, severity mapping, root-stage catalog, and user-facing message keys.
9. Exact Provider Adapter DTO/error schema and capability metadata.
10. Exact ArtifactService directory layout, temp/orphan cleanup, retention TTLs, and rebuildability matrix.
11. Exact repository method names, transaction helpers, SQL constraints, and ORM mappings.
12. Whether cleanup failures become user-visible QualityIssues or maintenance-only records when export/recovery are unaffected.
13. Exact UI/API semantics for lock/unlock translation and manual review completion.
14. Exact ExportRecord precheck status and manifest schema in export design.

## Decisions deferred to later detailed design stages

| Area | Deferred decisions |
| --- | --- |
| QualityCheckService | Full issue taxonomy, severity/blocking policy, root-stage attribution rules, message catalog. |
| Provider Adapter | DTOs, standardized error classes, capability metadata, local/cloud provider config shape. |
| ArtifactService | Workspace directories, atomic write details, hash algorithm policy, retention/cleanup scheduler, orphan handling. |
| ProcessingProfile | Profile templates, default budget values, UI configuration, strictness maps. |
| Repository / DAO | SQL DDL, migrations, transaction API, idempotency indexes, enum storage strategy. |
| Export | ExportRecord details, warning acknowledgement, manifest schema, batch export behavior. |
| API/UI | Pause/resume/cancel endpoints, review flows, lock/unlock behavior, issue resolution UX. |
| P1/P2 | Forced/incomplete export, GeometryRevision, multi-page translation context, distributed workers, advanced typesetting. |

## ADR list

- `docs/design/workflow-state/adr/0001-canonical-workflow-vocabulary.md`
- `docs/design/workflow-state/adr/0002-retry-budget-and-crash-attempts.md`
- `docs/design/workflow-state/adr/0003-export-check-and-warning-readiness.md`
- `docs/design/workflow-state/adr/0004-recovery-committed-results-first.md`
