# Persistence Readiness Open Questions v0.1

These questions are non-blocking for FakeProvider single-Page persistence readiness.

## 1. Repository and DTO Details

- Exact repository method names.
- Exact DTO and evidence snapshot shapes.
- Exact package/module layout.
- Whether implementation uses one connection per Unit of Work in tests or a shared test connection with transaction boundaries simulated.

## 2. SQLite and ORM Details

- Exact SQL DDL.
- Exact ORM mappings.
- Exact constraint names.
- Exact partial index syntax.
- Exact isolation mode, lock timeout, and savepoint policy.
- Exact optimistic concurrency implementation, beyond the required guards on active pointer ids, dependency hashes, and stage statuses.

## 3. Migration Details

- Exact migration tool topology.
- Migration file naming convention.
- Workspace identity format.
- Project restore/relink user flow.
- Project identity collision policy.
- Newer-app/newer-project compatibility UX.
- Backup manifest format.
- Orphan Project directory cleanup policy.

## 4. Recovery and Idempotency Details

- Exact heartbeat stale threshold.
- Exact recovery timeout.
- Exact crash retry ceiling values.
- Whether those values live in app config, ProcessingProfileSnapshot, task policy, or a combination.
- Exact ToolRunLog crash/interrupt status mapping if narrower than WorkflowAttempt statuses.
- Cleanup policy for official but unselected artifacts after recovery.
- Whether recovery records a standalone decision for every `abandoned_after_crash` repair or only when user-visible workflow state changes.

## 5. Artifact and Retention Details

- Retention TTLs for successful payloads, debug bundles, rebuildable crops, and official unselected artifacts.
- Whether cleanup failures create user-facing QualityIssues or maintenance-only records.
- Exact temp directory layout, atomic promotion mechanics, and fsync policy.
- Exact required fake evidence artifacts beyond original, cleaned, and typeset.

## 6. Export Details

- Exact ExportRecord schema and repository contract.
- ZIP manifest schema.
- Warning export acknowledgement rules.
- Forced/incomplete export semantics.
- Whether a future single-page export milestone should create output artifacts before Batch export exists.

## 7. Provider/Profile Details

- Full provider capability/license metadata schema.
- Exact ProcessingProfile defaults for fast, balanced, and strict.
- Full app-level provider_configs and processing_profiles implementation timing.
- OS secret store integration.
- Provider availability checks and secret_ref resolution mechanics.

## 8. API/UI Details

- API routes and DTOs for Project open, migration blocking, recovery, readiness, and issue display.
- UI behavior for repair-only Projects.
- UI behavior for warning readiness, blocked readiness, and provider refusal.
- User-facing localization/message catalog.

## 9. P1/P2 Deferred Decisions

- GeometryRevision schema.
- Multi-page ContextPack.
- TermCandidate flow.
- TaskSummaryIndex.
- Full ArtifactRetentionPolicy table.
- Advanced backup/restore UX.
- Multi-process desktop locking.

## 10. Resolved for MVP-0

These are no longer open for MVP-0:

- MVP-0 stops at `ready_for_export`.
- Import is an ApplicationService/import use case for MVP-0.
- QualityCheckService is repository-free for MVP-0.
- StageExecutor may use only a narrow StageEvidenceWriter.
- Project open verifies identity and migrations before project repositories are exposed.
- Acceptance guards expected active pointer ids, dependency hashes, and stage statuses.
- Official unselected artifacts are evidence/reuse candidates only.
- WorkflowDecisionIssue is required when decisions link persisted QualityIssues.
- app-level `projects` and `schema_migrations` are immediate; provider/profile tables may be skeletal with deterministic project-local snapshots.
