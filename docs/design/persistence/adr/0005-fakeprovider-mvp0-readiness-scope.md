# ADR 0005: FakeProvider MVP-0 Persistence Subset and Readiness-Only Scope

Status: Accepted

## Context

The next implementation milestone is a FakeProvider single-Page backend vertical slice. The design must be small enough to implement, but real enough to validate repository boundaries, transactions, recovery, idempotency, artifact metadata, and QualityIssue gating.

## Decision

MVP-0 persistence scope stops at `ready_for_export`.

Actual `ExportRecord`, output image export, ZIP, and manifest are follow-up unless explicitly added later.

Immediate tables include Project registry, ProjectMetadata, Batch, Page, TextBlock, OCRResult, TranslationResult, GlossaryVersion, ProcessingProfileSnapshot, ProcessingTask, WorkflowAttempt, WorkflowDecision, WorkflowDecisionIssue, ProcessingArtifact, ToolRunLog, QualityIssue, and schema_migrations.

app-level provider_configs and processing_profiles may be skeletal if a deterministic project-local ProcessingProfileSnapshot exists for FakeProvider.

Import is an ApplicationService/import use case for MVP-0, while `import` remains a workflow vocabulary stage for future task-based import.

## Rationale

The slice must validate persistence mechanics without waiting for full API/UI/export/provider/profile systems.

Readiness is enough to test active pointers, artifact metadata, blocker queries, and workflow acceptance.

## Rejected Alternatives

- Full export implementation before readiness.
- In-memory fake persistence.
- Full provider/profile configuration before FakeProvider.
- Treat import as a WorkflowLoopEngine stage in MVP-0.
- Implement all P1/P2 entities before the first slice.

## Consequences

- A later export design or implementation slice must add `ExportRecord` behavior.
- FakeProvider tests still need failure modes, not only happy path.
- Skeleton app config tables must not become a substitute for real provider/profile design later.
