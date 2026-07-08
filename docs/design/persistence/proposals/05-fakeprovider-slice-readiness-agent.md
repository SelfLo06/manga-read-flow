## 1. Scope

This proposal covers the minimum persistence scope needed to implement and test:

```text
create project -> import one page -> run FakeProvider workflow -> ready_for_export
```

The scope is documentation-only. It does not define SQL DDL, ORM mappings, migrations, API routes, frontend behavior, real provider integration, prompt templates, or full export behavior.

The proposal assumes the first implementation milestone is a single local Project, one Batch, one Page, deterministic FakeProvider stages, local filesystem artifacts, temporary SQLite integration tests, and no real OCR/LLM/cleaning/typesetting tools.

No blocking conflict was found among the required inputs for this slice. The main tension is priority, not model shape: the data-model baseline lists a broader P0 set, while this proposal ranks which parts must be implemented first to prove the FakeProvider slice.

## 2. Role Bias

This agent biases toward implementation readiness for the first backend vertical slice. The goal is to make the smallest persistence surface that can prove the architecture boundaries, not to complete the full MVP schema in one pass.

Biases:

- Prefer real durable rows over mocks for Project, Page, active pointers, attempts, decisions, artifacts, tool logs, issues, and result versions.
- Prefer skeletal persistence for P0 concepts that are needed for provenance but not exercised deeply by the happy path.
- Defer P1/P2 concepts and complete export/accounting/profile/provider configuration details.
- Require temporary SQLite tests to use the same repository boundaries that production code will use.
- Avoid building a generic persistence framework before the first workflow proves it needs one.

## 3. Assumptions

- `app.db` and one `project.db` are both real SQLite databases in tests, even when created under a temporary directory.
- `Project` is registered in `app.db`; Project-owned content and workflow evidence live in `project.db`.
- The first FakeProvider workflow may generate one or more deterministic `TextBlock` rows from a fake detection stage.
- Fake OCR, translation, cleaning, and typesetting use the real Provider Adapter envelope and real ArtifactService boundary, but no real external tools.
- The workflow ends at persisted Page status `ready_for_export`; actual image/ZIP export may be a later slice.
- Active pointers remain the source of truth: `TextBlock.active_ocr_result_id`, `TextBlock.active_translation_result_id`, `Page.original_artifact_id`, `Page.active_cleaned_artifact_id`, and `Page.active_typeset_artifact_id`.
- `Page.status` is a repairable aggregate, not recovery truth.
- A minimal empty `GlossaryVersion` is enough for translation provenance in the first slice.
- A minimal `ProcessingProfileSnapshot` is required, even if created from a hardcoded/default FakeProvider profile.

## 4. Minimal Proposal

Minimum persistence scope for the happy path:

1. Register a Project in `app.db`.
2. Create and verify a matching `project.db` with `ProjectMetadata`.
3. Create one Batch and one Page in `project.db`.
4. Register the original image as a `ProcessingArtifact`; do not store bytes in SQLite and do not overwrite the original file.
5. Create a `ProcessingTask` and immutable `ProcessingProfileSnapshot`.
6. For each fake workflow stage, persist `WorkflowAttempt`, sanitized `ToolRunLog` where a fake tool is invoked, `WorkflowDecision`, and stage status updates.
7. Create `TextBlock` rows from fake detection.
8. Create immutable `OCRResult` rows and atomically select them with `TextBlock.active_ocr_result_id`.
9. Create immutable `TranslationResult` rows tied to active OCR and an empty/current `GlossaryVersion`, then atomically select them with `TextBlock.active_translation_result_id`.
10. Register cleaned and typeset image artifacts through ArtifactService and atomically select them with Page active artifact pointers after quality/workflow acceptance.
11. Query open blocking `QualityIssue` rows for the Page before setting pure `ready_for_export`.

Required immediately:

| Database | Entity/table | Why required now |
| --- | --- | --- |
| `app.db` | `projects` | Project registry, workspace/project.db path, default languages, lifecycle. |
| `app.db` | `schema_migrations` | App database lifecycle must be explicit from the first test. |
| `project.db` | `project_metadata` | Project identity verification and per-project migration boundary. |
| `project.db` | `schema_migrations` | Independent project migration lifecycle. |
| `project.db` | `batches` | Required ownership spine even for one Page. |
| `project.db` | `pages` | Original/cleaned/typeset active artifact pointers and aggregate status. |
| `project.db` | `text_blocks` | Detection output, stage statuses, geometry, active OCR/translation pointers. |
| `project.db` | `ocr_results` | Immutable OCR versions and OCR idempotency evidence. |
| `project.db` | `translation_results` | Immutable translation versions and translation idempotency evidence. |
| `project.db` | `glossary_versions` | Translation provenance requires a glossary version, even when empty. |
| `project.db` | `processing_profile_snapshots` | Historical policy source for retry/warning decisions. |
| `project.db` | `processing_tasks` | Durable workflow command, heartbeat, recovery entry point. |
| `project.db` | `workflow_attempts` | Attempt metadata is always persisted. |
| `project.db` | `workflow_decisions` | WorkflowLoopEngine decisions must be auditable. |
| `project.db` | `processing_artifacts` | Official artifact metadata for original, cleaned, typeset, and optional fake evidence files. |
| `project.db` | `tool_run_logs` | Sanitized fake provider/tool invocation trace. |
| `project.db` | `quality_issues` | Export/readiness gate and refusal/warning/blocking tests. |

Minimal skeletons acceptable in the first implementation milestone:

| Entity/table | Skeleton behavior |
| --- | --- |
| `glossary_terms` | May exist empty; no glossary UI or term editing is needed. |
| `workflow_decision_issues` | Prefer a minimal relation once QualityIssues are persisted; happy path may not exercise it. |
| `export_records` | Not required to reach `ready_for_export`; may be skeletal if the same milestone also tests actual export blocking. |
| `provider_configs` | Can be deferred or skeletal; FakeProvider identity can live in snapshot/attempt/log metadata without secrets. |
| `processing_profiles` | Can be skeletal if snapshots are bootstrapped from a default profile; full profile editing is deferred. |
| `global_settings` | Not needed unless workspace selection is implemented in the same slice. |

Deferred for this slice:

- `GeometryRevision`, `PageTranslationContext`, `ContextPack`, `TermCandidate`, `TaskSummaryIndex`, `ArtifactRetentionPolicy`, detailed export issue snapshots, full manifest schema, cost/token rollups, advanced cleanup scheduler records, full provider capability catalog, full profile UI/config, multi-page context, ZIP export details, forced/incomplete export semantics, and P1/P2 review/edit workflows.

## 5. Repository / Transaction / Migration Implications

Minimal repository capabilities:

- App database: initialize/open `app.db`, run app migrations, create/list/load Project registry rows, resolve project workspace and `project.db` path.
- Project database lifecycle: initialize/open `project.db`, run project migrations, verify `ProjectMetadata`, and refuse to operate when app/project identities disagree.
- Import/content: create Batch/Page, register original artifact metadata, and set `Page.original_artifact_id`.
- Workflow task: create/update `ProcessingTask`, heartbeat running work, find stale running tasks, and update terminal status.
- Stage evidence: create/update `WorkflowAttempt`, `ToolRunLog`, `WorkflowDecision`, and optional `WorkflowDecisionIssue`.
- Domain results: create TextBlocks, OCRResults, TranslationResults, empty/current GlossaryVersion, and active pointer updates.
- Artifacts: persist ArtifactService metadata updates, load artifact metadata by id, and update storage state such as `missing`.
- Quality/readiness: create/update/query QualityIssues, especially open blocking issues in Page scope.
- Idempotency: find reusable OCR/translation/results/artifacts by documented input/config/provider/context keys.

Transaction implications:

- Do not keep a database write transaction open across a FakeProvider or future real provider call.
- Persist task/attempt start before each stage call in a short transaction.
- Register official artifacts through ArtifactService before they are selected as active.
- Acceptance of a stage should be one short transaction containing the WorkflowDecision, relevant issue lifecycle changes, accepted result rows, active pointer update, retry budget after, and stage status/Page status updates.
- Import original artifact registration and `Page.original_artifact_id` should be atomic enough that a Page is never treated as import-complete without an official original artifact.
- app.db/project.db creation cannot rely on cross-database transactions; use clear ordered steps and compensating cleanup/failed status if project.db initialization fails.

Migration implications:

- Both databases need a migration ledger from the first temporary SQLite test.
- The first project migration should include only the tables needed for the FakeProvider slice plus chosen skeletons.
- Stable string enum values should be used so later values can be added without rewriting audit rows.
- Migration tests should prove an empty app database and an empty project database can be initialized independently.

## 6. Software Engineering Principle Checks

- Single Responsibility: Repository / DAO persists and queries SQLite only; ArtifactService owns file lifecycle; WorkflowLoopEngine owns decisions; QualityCheckService classifies issues; Provider Adapter only returns structured fake outputs.
- Information Hiding: WorkflowLoopEngine and StageExecutor should request repository capabilities such as "load active page state" or "accept stage result", not SQL/table/session details.
- High Cohesion / Low Coupling: Repository groups should follow workflow needs: app project registry, project lifecycle, content/result state, workflow evidence, artifact metadata, quality/readiness.
- Dependency Inversion: WorkflowLoopEngine, ArtifactService, StageExecutor, and QualityCheckService depend on repository contracts, not concrete ORM/session internals.
- Testability: The same repository contracts must run against temporary `app.db`, temporary `project.db`, and temporary workspace files.
- Recoverability: Recovery queries use ProcessingTask, WorkflowAttempt, active pointers, result hashes, artifact states, ToolRunLog, QualityIssue, and WorkflowDecision; never only Page status.
- Traceability: The happy path still leaves attempts, decisions, tool logs, artifacts, active pointers, result versions, and readiness evidence.
- Scope Control: No generic repository framework, event sourcing, CQRS, distributed transactions, plugin persistence layer, or full export/profile/provider subsystem is needed for MVP-0.

## 7. Recovery / Idempotency Impact

The minimum slice should persist enough evidence to support these recovery and idempotency tests even before full recovery UX exists:

- Crash after OCR acceptance: repository can find a stale running task/attempt, load active OCRResult pointers, and resume at translation without rerunning OCR.
- Crash after artifact registration but before active pointer update: registered artifact remains official but unselected; recovery must not select by latest timestamp.
- Missing active artifact: ArtifactService can validate/mark storage state; WorkflowLoopEngine decides rebuild, pause, warning, or block.
- Rerun unchanged OCR: repository can find a matching OCRResult by TextBlock/input/config/provider/tool identity and create auditable reuse evidence.
- Rerun unchanged translation: repository can find matching TranslationResult by source OCR/source hash/context/glossary/provider/model/prompt/config identity and avoid duplicate active rows.
- Rerun unchanged cleaned/typeset output: repository plus ArtifactService can verify compatible artifact provenance and hash before reuse.

For the first slice, recovery logic may be simple and deterministic, but the persisted data must not block later implementation of the documented recovery rules.

## 8. FakeProvider Slice Impact

The FakeProvider slice should exercise real persistence boundaries with deterministic fake outputs:

- Fake detection creates deterministic TextBlocks and optional mask artifacts.
- Fake OCR creates deterministic OCRResults and optional raw/crop artifacts.
- Fake translation creates deterministic TranslationResults using the active OCR pointers and the current empty GlossaryVersion.
- Fake translation check creates no open blocking issues on the happy path.
- Fake cleaning registers a cleaned image artifact and selects it only after workflow acceptance.
- Fake typesetting registers a typeset image artifact and selects it only after workflow acceptance.
- Fake export check queries open blocking QualityIssues before `Page.status = ready_for_export`.

Temporary SQLite integration tests this design should enable:

- Initialize `app.db`, create Project, initialize `project.db`, and verify project identity.
- Import one Page and prove original image bytes are filesystem-only while artifact metadata is in SQLite.
- Run the happy path to `ready_for_export` and verify active OCR, translation, cleaned, and typeset pointers.
- Verify attempts, decisions, tool logs, artifacts, result rows, and profile snapshot are persisted for each executed stage.
- Rerun the same Page and verify reusable results/artifacts are found and audited instead of duplicated blindly.
- Simulate crash after OCR acceptance and verify recovery can continue from translation.
- Simulate provider refusal or invalid fake translation output and verify ToolRunLog, WorkflowAttempt, QualityIssue, and WorkflowDecision are persisted.
- Simulate registered-but-unselected artifact and verify it is not export-effective.
- Simulate missing active artifact and verify storage state can be marked without ArtifactService making workflow decisions.
- Verify open blocking QualityIssue prevents pure `ready_for_export`.
- Verify app/project migration ledgers are created independently.

## 9. HARNESS Scenario Coverage

| HARNESS area | Coverage by this proposal |
| --- | --- |
| P01 Create Project and project database | Immediate scope: app Project row, project.db, ProjectMetadata, independent migrations. |
| P02 Import one Page | Immediate scope: Batch/Page plus original ProcessingArtifact metadata; bytes remain outside SQLite. |
| P03 Happy-path single Page workflow | Immediate scope: TextBlocks, OCRResults, TranslationResults, cleaned/typeset artifacts, attempts, decisions, logs, active pointers, readiness gate. |
| P04 Acceptance transaction | Immediate scope: accepted results, active pointers, issue lifecycle, decision, retry budget after, and statuses commit together. |
| R01 Crash after OCR result committed | Immediate test target: active OCR pointer and OCRResult allow resume from translation. |
| R02 Crash after provider temp file before artifact registration | Boundary covered: temp/orphan files are not official artifacts; filesystem scan details can stay in ArtifactService design. |
| R03 Crash after artifact registration before active pointer update | Immediate test target: official unselected artifact is not export-effective by timestamp. |
| R04 Missing active artifact | Immediate test target: repository loads metadata; ArtifactService marks missing; workflow decision is separate. |
| I01 Unchanged OCR rerun | Immediate repository lookup target. |
| I02 Unchanged translation rerun | Immediate repository lookup target, including glossary/context/source hashes. |
| I03 Unchanged cleaned/typeset artifacts | Immediate repository plus ArtifactService lookup target. |
| Q01 Provider refusal persistence | Should be enabled by first failure-mode test, even if not in the first happy-path command. |
| Q02 Blocking issue prevents readiness/export | Immediate readiness gate query. |
| Q03 Cleaning skip warning state | Skeleton support through QualityIssue/decision/stage status; full skip UX deferred. |
| S01 OCR edit | Deferred use case, but result versioning and active pointer rules must not preclude it. |
| S02 Translation edit | Deferred use case, but result versioning and active pointer rules must not preclude it. |
| M01 Initialize app.db | Immediate migration test. |
| M02 Initialize project.db | Immediate migration and identity verification test. |
| M03 Add enum value later | Supported by stable string status/decision/issue values; exact enum taxonomy remains deferred. |

This is proposal coverage, not completed validation.

## 10. Rejected Alternatives

- Implement all P0 tables with full production behavior before FakeProvider. Rejected because it delays the vertical slice and increases schema churn before workflow evidence is proven.
- Use in-memory dictionaries or mocks for Project/Page/results during FakeProvider. Rejected because it would not validate recovery, idempotency, migration, or repository boundaries.
- Store fake image or payload bytes directly in SQLite for convenience. Rejected because it violates the artifact invariant and hides filesystem drift risks.
- Derive active OCR/translation/typeset output from latest timestamp. Rejected because active pointers are the documented source of truth.
- Let FakeProvider write repository rows or official artifact records. Rejected because it would normalize an architecture violation before real providers arrive.
- Make `Page.status` the readiness/recovery source of truth. Rejected because it cannot explain partial acceptance, abandoned attempts, stale pointers, or missing artifacts.
- Build a generic Unit of Work/repository framework with plugins and cross-database transactions. Rejected as MVP-0 overengineering.
- Require full ExportRecord/ZIP/manifest implementation before `ready_for_export`. Rejected unless the first milestone explicitly includes actual export, because readiness can be proven through active pointers and QualityIssue gating.

## 11. Risks

- Under-scoping persistence could make the happy path pass while recovery/idempotency remain untestable. Mitigation: include real attempts, decisions, logs, artifacts, pointers, result hashes, and migration ledgers from the first slice.
- Over-scoping persistence could turn MVP-0 into a full schema project. Mitigation: implement required tables plus small skeletons only where they protect P0 invariants.
- Active pointer/status drift could make stale or unaccepted outputs export-effective. Mitigation: acceptance transaction and export-effective checks must be part of the repository contract.
- app.db/project.db lifecycle errors could strand a Project between databases. Mitigation: identity verification and explicit failed/cleanup path for project creation.
- FakeProvider may hide real provider complexity. Mitigation: make FakeProvider use the same ProviderResult, ArtifactService, QualityCheckService, and repository boundaries as real providers.
- Export readiness could be confused with actual export. Mitigation: name the first slice as `ready_for_export`; treat ExportRecord/output artifacts as separate unless explicitly included.
- Skeleton tables may become accidental permanent weak designs. Mitigation: mark skeleton behavior in final design and add follow-up design/implementation gates before expanding them.

## 12. Open Questions

- Does MVP-0 stop at `ready_for_export`, or must it also create an actual single-page export artifact and `ExportRecord`?
- Should `workflow_decision_issues` be implemented with the first QualityIssue support, or can the very first happy path omit it until refusal/warning tests?
- Should import be represented as a workflow stage with its own attempt/decision, or as an Application Service operation that only creates Page/artifact evidence?
- Are app-level `processing_profiles` and `provider_configs` required for the first implementation, or may a default profile be converted directly into a project-local `ProcessingProfileSnapshot`?
- Which fake artifacts are mandatory for the first slice beyond original, cleaned, and typeset: mask, crop, raw OCR output, raw translation payload, quality report?
- Should temporary SQLite tests run one database connection per Unit of Work to mimic production session boundaries, or is a shared connection acceptable for MVP-0 tests?
