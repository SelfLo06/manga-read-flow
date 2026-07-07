# Execution Contract Open Questions v0.1

No blocking open questions remain for final synthesis.

The questions below are non-blocking for planning the FakeProvider single-Page backend vertical slice.

## Non-blocking open questions

| Question | Deferred owner/stage |
| --- | --- |
| Exact enum enforcement mechanism: application constants, lookup tables, or ORM-level validation. | Persistence / repository design. |
| Exact ID format for task, attempt, artifact, result, issue, and decision ids. | Persistence design. |
| Exact artifact directory layout, file naming, staging/orphan/quarantine paths, and cleanup TTLs. | ArtifactService implementation design. |
| Exact central sanitization helper/module name and API. Boundary is fixed; implementation shape is deferred. | Config/security design. |
| Whether `classification_version` is persisted on every QualityIssue or only on QualityCheckReport/debug evidence. | Quality/persistence design. |
| Whether message params are persisted as structured JSON or derived at API read time. | API/UI/persistence design. |
| Whether partial Page translation creates an optional Page summary issue in addition to TextBlock issues. | Quality report/UI design. |
| Whether warning export later requires explicit per-export user acknowledgement beyond `ProcessingProfileSnapshot.allow_warning_export`. | Export design. |
| Exact child-safety refusal policy for future profiles. MVP-0 default remains non-export-effective while required output is absent. | Policy/export/security design. |
| Where artifact integrity check events are persisted for long-term audit: decision rationale, ToolRunLog, attempt metadata, or maintenance log. | Persistence/recovery design. |
| Whether `requires_gpu = optional|required|false` is stored directly or encoded in capabilities JSON over a boolean field. | Provider config/persistence design. |
| Exact cleanup behavior for missing failed/debug payloads when active outputs do not depend on them. | Artifact retention design. |
| Whether cleanup failures become user-visible QualityIssues or maintenance-only records. | Artifact/quality design. |
| Exact successful raw payload retention TTL and transition timing to `metadata_only_cleaned`. | Artifact retention/profile design. |
| Exact real provider schemas, prompt templates, and response parsers. | Real provider adapter design/spike. |
| Exact FakeProvider fixture image format and dimensions. | FakeProvider implementation plan. |
| Exact Repository/DAO method names and transaction helper APIs. | Repository / persistence minimal design. |

## Deferred decisions already out of scope

- SQL DDL, ORM models, migrations, and indexes.
- FastAPI routes and frontend DTOs.
- Real OCR, LLM, cleaning, and typesetting integration.
- Full ProcessingProfile defaults.
- ExportRecord/ZIP manifest details.
- Forced/incomplete export semantics.
- Full UI localization copy.
- Privacy purge UI.
- Plugin framework, provider ranking, dynamic probing, and marketplace-style extension.
