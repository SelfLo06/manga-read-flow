# ADR 0001: Repository and Unit of Work Boundary

Status: Accepted

## Context

MVP-0 needs SQLite persistence for Project registry, Project-owned workflow state, result versions, artifacts, issues, and recovery evidence. The architecture requires Repository / DAO as the only SQLite access entry. Provider Adapters, WorkflowLoopEngine, ArtifactService, QualityCheckService, StageExecutor, API handlers, and UI must not depend on SQL or ORM internals.

## Decision

Use repository contracts grouped by workflow need and expose write transactions through named Unit of Work operations.

Do not expose generic repositories, ORM sessions, SQL strings, query builders, or row dictionaries to workflow/application modules.

Use separate app.db and project.db Unit of Work boundaries. No cross-database transaction is required for MVP-0.

StageExecutor may use only a narrow StageEvidenceWriter for ToolRunLog and attempt tool evidence.

QualityCheckService remains repository-free for MVP-0 and returns issue drafts/lifecycle suggestions.

## Rationale

This preserves information hiding, keeps SQLite changes testable, and prevents workflow decisions from leaking into persistence adapters.

Named operations are enough for the FakeProvider slice and avoid an enterprise persistence framework.

## Rejected Alternatives

- Passing ORM sessions into WorkflowLoopEngine or StageExecutor.
- One repository per table exposed to application services.
- A generic `Repository<T>` or generic query API.
- Provider Adapter database access.
- QualityCheckService mutating issue rows directly for MVP-0.

## Consequences

- Implementation must define repository contracts before workflow code writes state.
- Some operations, especially acceptance and recovery repair, will be larger named operations instead of simple CRUD.
- Tests can run the same contracts against temporary SQLite databases.
