# Persistence HARNESS Validation

Role: Phase 5 HARNESS Validation agent for Goal 3 Persistence Readiness Design.

Validation target: whether the persistence readiness design is acceptable before implementing the FakeProvider single-Page backend vertical slice.

## 1. Inputs Read

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/HLD.md`, because the final persistence design names it as the reconciled HLD baseline
- `docs/design/persistence/HARNESS.md`
- `docs/design/persistence/PLAN.md`
- all files under `docs/design/persistence/final/*.md`
- all files under `docs/design/persistence/adr/*.md`
- existing persistence review files for phase context

No implementation code, DDL, ORM mapping, Alembic migration, API route, frontend behavior, provider integration, prompt template, log, cache, or unrelated file was created or modified.

## 2. Overall Validation Result

| Area | Result | Notes |
| --- | --- | --- |
| Invariants | PASS | The final design preserves repository, artifact, provider, quality, workflow, active pointer, project isolation, and storage invariants. |
| Scenario replay | PASS | P01-P04, R01-R04, I01-I03, Q01-Q03, S01-S02, M01-M03, and boundary failure checks are covered. |
| Blocking gaps | PASS | No FAIL or blocking UNCLEAR was found. |
| Deferred details | PASS | Remaining gaps are implementation details explicitly deferred by the design rules, not blockers for the FakeProvider persistence slice. |
| FakeProvider slice acceptability | PASS | Acceptable for FakeProvider single-Page backend vertical slice implementation. |

Validation decision: acceptable.

Rationale: the design gives clear repository boundaries, transaction boundaries, migration gates, recovery evidence, idempotency keys, and temporary SQLite validation expectations. The remaining open questions are exact method names, DTO shapes, DDL, migration tool topology, heartbeat values, cleanup TTLs, and UI/API/export details, all of which are outside this design phase.

Scope caveat: the SRS full MVP includes actual export, but this Goal 3 HARNESS validates persistence readiness only through `ready_for_export`. The final design's readiness-only scope is acceptable for the FakeProvider backend slice and does not satisfy the later full export milestone by itself.

## 3. Invariant Checklist

| Invariant | Result | Evidence in final design |
| --- | --- | --- |
| Repository / DAO is the only SQLite access entry. | PASS | Repository contracts hide SQL, ORM sessions, cursors, and row-shaped APIs. |
| `app.db` and per-Project `project.db` remain separated. | PASS | app.db owns Project registry and app migrations; project.db owns Project content, workflow, quality, artifacts, and project migrations. |
| No cross-database foreign key or cross-database transaction is required for MVP-0. | PASS | Project creation is an ordered recoverable lifecycle, not a distributed transaction. |
| Project open verifies identity and migrations before project repositories are exposed. | PASS | ProjectStore gate requires app registry, project.db path, ProjectMetadata identity, and migration readiness. |
| Images and large payloads are not stored in SQLite. | PASS | SQLite stores metadata, hashes, paths, scopes, provenance, and storage state only. |
| Original images are never overwritten. | PASS | Originals are official artifacts; cleaned, typeset, and export outputs are new artifacts. |
| Artifact metadata is persisted in `processing_artifacts`. | PASS | ArtifactService registers official artifacts through ArtifactMetadataRepository. |
| ArtifactService owns official artifact lifecycle but not workflow decisions. | PASS | ArtifactService can register, hash, move, mark missing/deleted, retain, and clean artifacts; WorkflowLoopEngine decides rebuild/warn/block. |
| Provider Adapters do not access SQLite. | PASS | Provider Adapters receive no repository or persistence interface. |
| Provider Adapters do not own artifact lifecycle. | PASS | Providers may use temp refs only; official promotion/registration belongs to ArtifactService. |
| Provider Adapters do not decide retry, fallback, skip, warning, or block. | PASS | WorkflowLoopEngine owns loop decisions. |
| QualityCheckService does not advance workflow state. | PASS | For MVP-0 it is repository-free and returns issue drafts and lifecycle suggestions. |
| StageExecutor has only narrow evidence write authority. | PASS | StageExecutor may use StageEvidenceWriter for ToolRunLog and attempt evidence, not active pointers, decisions, or issues. |
| Active OCR, translation, cleaned image, and typeset image are selected by active pointers. | PASS | Active pointers on TextBlock/Page are the source of truth. |
| P0 does not use independent result-row active flags. | PASS | The design rejects timestamp selection and independent active flags for current result selection. |
| Acceptance transaction is the semantic commit point. | PASS | Accepted result rows, active pointers, issue lifecycle, decision links, retry budget, task progress, and statuses commit together. |
| Provider calls are outside SQLite write transactions. | PASS | Stage sequence reserves attempt, calls provider/tool outside write transaction, then persists evidence and acceptance in short transactions. |
| Recovery does not rely only on `Page.status`. | PASS | Recovery bundle includes tasks, attempts, decisions, logs, active pointers, results, artifacts, issues, hashes, statuses, and profile snapshot. |
| Idempotent reuse is keyed and auditable. | PASS | OCR, translation, cleaned, and typeset reuse keys are defined; reuse records decisions and/or attempts. |
| Provider refusal is first-class persisted evidence. | PASS | Refusal persists through ToolRunLog, WorkflowAttempt, QualityIssue, WorkflowDecision, and decision-issue links when applicable. |
| The design does not introduce bypass/evasion data. | PASS | Refusal is handled by fallback/manual/warning/block policy, not prompt evasion. |
| API keys and raw secrets are not stored in project.db or logs. | PASS | ConfigService uses secret references; snapshots and logs must not contain raw secrets. |
| Open blocking QualityIssues block normal readiness/export. | PASS | Readiness queries check open blocking issues; warning readiness is controlled by ProcessingProfileSnapshot. |
| app.db and project.db migrations are tracked independently. | PASS | Both databases have separate `schema_migrations` ledgers. |
| Stable string values can evolve additively. | PASS | Historical audit rows are not rewritten to rename statuses, stages, decisions, issue types, artifact states, or error codes. |
| No P1/P2 feature is required before MVP-0. | PASS | Full export, real providers, provider/profile UI, advanced cleanup, multi-page context, and P1/P2 entities are deferred. |

## 4. Scenario Replay Results

### 4.1 Core Persistence Scenarios

| Scenario | Required repository capability | Required transaction boundary | Required persisted evidence | Recovery or idempotency impact | Boundary check | Result |
| --- | --- | --- | --- | --- | --- | --- |
| P01: Create Project and project database | ProjectCatalogRepository registers Project and project.db path in app.db; ProjectIdentityRepository initializes/verifies ProjectMetadata and project schema ledger. | App lifecycle UoW and Project lifecycle UoW are ordered but not cross-database atomic; project repositories are exposed only after Project open passes. | app `projects`, app `schema_migrations`, project `project_metadata`, project `schema_migrations`, project-relative path evidence. | Missing, mismatched, or incompatible project.db becomes repair-only; no cross-db FK is needed for recovery. | app.db owns global registry; project.db owns Project data; no provider/artifact/workflow module bypasses the open gate. | PASS |
| P02: Import one Page | ArtifactMetadataRepository via ArtifactService registers original metadata; ContentStateRepository creates Batch/Page and stores `Page.original_artifact_id`. | Import UoW must make Page import completion depend on committed official original artifact metadata and pointer selection. | original `processing_artifact` row with path/hash/type, Batch, Page, `original_artifact_id`, import status. | Original can be reused after restart; Page is not treated as imported without original pointer; file bytes stay outside SQLite. | ArtifactService owns original file registration; ApplicationService/import use case owns Page import state; original bytes are never overwritten. | PASS |
| P03: Run happy-path single Page workflow | Content, result, glossary, workflow, artifact, quality, and readiness repositories persist TextBlocks, OCRResults, TranslationResults, artifacts, attempts, decisions, issues, logs, profile snapshot, and active pointers. | Stage sequence uses attempt reservation, provider/tool outside write transaction, tool evidence UoW, artifact metadata UoW, quality check, then acceptance UoW. | TextBlocks, OCRResults, TranslationResults, cleaned/typeset artifacts, active pointers, WorkflowAttempts, WorkflowDecisions, ToolRunLogs, QualityIssues, ProcessingProfileSnapshot, readiness status. | Recovery can reload accepted outputs; idempotency can reuse previous successful stage evidence; Page can reach `ready_for_export`. | Provider, QualityCheckService, ArtifactService, WorkflowLoopEngine, and Repository ownership boundaries remain separated. | PASS |
| P04: Acceptance transaction | WorkflowExecutionRepository, ResultVersionRepository, ContentStateRepository, QualityIssueRepository, and ArtifactMetadata read snapshots support a guarded acceptance command. | Acceptance UoW commits accepted result rows or active artifact pointer changes, active pointers, issue lifecycle, WorkflowDecision, decision-issue links, retry budget after, task progress, and stage statuses together. Provider call is not inside this transaction. | accepted OCR/translation rows, active pointer updates, issue rows/lifecycle, WorkflowDecision, WorkflowDecisionIssue rows when linked, retry budget, task/stage status, guard inputs. | Partial current-state drift is either impossible by SQLite atomicity or detected by expected-state guard failure and reloaded. | Selection happens only at acceptance; artifact registration alone and latest timestamp never make output current. | PASS |

### 4.2 Recovery Scenarios

| Scenario | Required repository capability | Required transaction boundary | Required persisted evidence | Recovery or idempotency impact | Boundary check | Result |
| --- | --- | --- | --- | --- | --- | --- |
| R01: Crash after OCR result committed | Recovery queries find stale running task, running/incomplete attempt, active OCR pointer, OCRResult row, stage statuses, ToolRunLog, and latest decision. | Recovery claim/repair UoW marks task/attempt interrupted or recovering; subsequent translation uses normal stage/acceptance transactions. | ProcessingTask heartbeat/status, WorkflowAttempt, active OCR pointer, OCRResult dependency hashes, OCR status, ToolRunLog/decision evidence. | Recovery resumes from translation without rerunning OCR when OCR acceptance committed. | Recovery source of truth is committed evidence and active pointers, not `Page.status`. | PASS |
| R02: Crash after provider temp file but before artifact registration | Repository can load running attempt/task and absence of official artifact metadata; ArtifactService can distinguish temp/orphan files from official artifacts. | Provider/temp work is outside write transaction; recovery repair UoW marks attempt abandoned/interrupted or retries under WorkflowLoopEngine policy. | Running attempt, stale heartbeat, optional ToolRunLog if outcome persisted, no official `processing_artifact` for the temp file. | Temp/orphan files do not become official or export-effective; rerun is safe and explainable. | ArtifactService handles temp/orphan lifecycle; Repository does not promote files; WorkflowLoopEngine decides retry/abandon. | PASS |
| R03: Crash after artifact registration but before active pointer update | ArtifactMetadataRepository can load registered artifact; ContentStateRepository shows active pointer unchanged; WorkflowExecutionRepository loads attempt/log/decision evidence. | Artifact metadata UoW may have committed; acceptance UoW did not. Recovery decision is persisted in a short repair or acceptance transaction. | official `processing_artifact` with `storage_state = present`, unchanged Page active pointer, attempt/log evidence, no acceptance decision selecting it. | Artifact is official evidence/reuse candidate only; it is not selected by timestamp. | ArtifactService registers; WorkflowLoopEngine decides reuse/retry/pause/block; active selection remains acceptance-only. | PASS |
| R04: Missing active artifact | Repository can load active artifact metadata and owner scope; ArtifactService validates path/hash and updates storage state to `missing`. | Artifact storage-state update is a short ArtifactService transaction; WorkflowLoopEngine decision/issue/status repair is separate short transaction or acceptance. | ProcessingArtifact path/hash/storage_state, active pointer, missing marker, QualityIssue/WorkflowDecision if user-visible. | Missing file cannot become ready/export-effective; WorkflowLoopEngine decides rebuild, warning, pause, or block. | ArtifactService marks missing but does not decide workflow outcome. | PASS |

### 4.3 Idempotency Scenarios

| Scenario | Required repository capability | Required transaction boundary | Required persisted evidence | Recovery or idempotency impact | Boundary check | Result |
| --- | --- | --- | --- | --- | --- | --- |
| I01: Rerun unchanged OCR stage | ResultVersionRepository supports OCR lookup by TextBlock, input/geometry hash, OCR config hash, provider, model, tool version, and source language. | Reuse is accepted through a cache-reuse/acceptance transaction that records a reuse decision or attempt. | prior OCRResult, dependency hashes, provider/model/tool provenance, active pointer or reusable historical result, `reuse_cached_result`/`reused_cached` evidence. | Avoids duplicate provider call; reuse remains auditable. | Provider Adapter does not own cache decisions; Repository finds evidence, WorkflowLoopEngine decides reuse. | PASS |
| I02: Rerun unchanged translation stage | ResultVersionRepository supports translation lookup by source OCR id/hash, source text hash, context hash, glossary version/hash, provider, model, prompt template, config hash, target language. | Reuse acceptance guards active OCR/source hashes and locked translation pointer; no duplicate active result row is created. | prior TranslationResult, source OCR linkage, glossary/context/prompt/config hashes, lock state, reuse decision/attempt evidence. | Compatible translation can be reused; locked translation is not overwritten without explicit user override. | WorkflowLoopEngine owns reuse policy; Provider Adapter does not decide cache hit. | PASS |
| I03: Rerun unchanged cleaned/typeset artifacts | ArtifactMetadataRepository and ArtifactService support lookup/validation by provenance, owner, artifact type, path, hash, storage state, and dependency hashes. | Artifact validation occurs before reuse; active pointer update happens only in guarded acceptance. | ProcessingArtifact path/hash/storage_state/provenance, cleaned/typeset dependency hashes, active pointers, reuse decision. | Present compatible artifacts can be reused; missing or incompatible artifacts remain non-effective. | ArtifactService verifies files; WorkflowLoopEngine decides reuse; Repository persists metadata. | PASS |

### 4.4 Issue and Export Gate Scenarios

| Scenario | Required repository capability | Required transaction boundary | Required persisted evidence | Recovery or idempotency impact | Boundary check | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Q01: Provider refusal persistence | WorkflowExecutionRepository persists ToolRunLog, attempt status, WorkflowDecision, and decision-issue links; QualityIssueRepository persists refusal issue. | Refusal acceptance commits refused attempt outcome, QualityIssue, WorkflowDecision, WorkflowDecisionIssue row when linked, retry budget after, and stage/task status. | ToolRunLog refusal metadata, WorkflowAttempt `refused`, provider/error code, QualityIssue, WorkflowDecision fallback/pause/warning/skip/block. | Refusal is recoverable as workflow evidence, not treated as a crash or cache hit. | No bypass/evasion prompt data; Provider Adapter returns standard refusal, WorkflowLoopEngine decides policy. | PASS |
| Q02: Blocking issue prevents normal readiness/export | QualityIssueRepository queries open blocking issues by Page/Batch/TextBlock scope; ReadinessQueryRepository checks active output freshness and profile warning policy. | Export-readiness acceptance records ready, warning, or blocked state with decision and issue linkage. | open blocking QualityIssue, ProcessingProfileSnapshot warning policy, readiness decision, Page/task readiness state. | Normal readiness/export is blocked with unresolved blockers; warning readiness is profile-controlled. | QualityCheckService classifies; WorkflowLoopEngine decides; full ExportRecord implementation is deferred but not required for readiness. | PASS |
| Q03: Cleaning skip creates warning-bearing state | ContentStateRepository persists cleaning skipped/warning state; QualityIssueRepository persists warning issue; WorkflowExecutionRepository persists decision. | Cleaning acceptance commits skipped state, warning QualityIssue, decision, retry budget, and downstream readiness status together. | cleaning status or skipped marker, warning QualityIssue, WorkflowDecision `mark_warning` or related type, readiness status. | Page can reach warning readiness but not pure `ready_for_export` while unresolved warning/skip applies. | CleanerProvider does not decide skip/warning; WorkflowLoopEngine owns the outcome. | PASS |

### 4.5 User Edit and Stale Scenarios

| Scenario | Required repository capability | Required transaction boundary | Required persisted evidence | Recovery or idempotency impact | Boundary check | Result |
| --- | --- | --- | --- | --- | --- | --- |
| S01: OCR edit | ResultVersionRepository creates new OCRResult; ContentStateRepository updates active OCR pointer and downstream stale statuses; QualityIssueRepository stales/supersedes downstream issues. | User edit UoW commits new OCRResult, active pointer, translation/translation_check/typesetting stale statuses, page stale flags, and issue lifecycle changes atomically. | new OCRResult with `source_type = user_edit`, parent link, active OCR pointer, stale downstream statuses, page stale flags, issue stale/supersede evidence. | Translation and typesetting are not silently reused against stale OCR; recovery sees consistent pointer/status state. | User edit path does not involve Provider Adapter; active selection remains pointer-based. | PASS |
| S02: Translation edit | ResultVersionRepository creates new TranslationResult; ContentStateRepository updates active translation pointer and stale downstream statuses. | User edit UoW commits new TranslationResult, active pointer, translation_check/typesetting stale statuses, page stale flags, and issue lifecycle changes atomically. | new TranslationResult with source OCR id/hash and parent link, active translation pointer, stale translation_check/typesetting, old typeset artifact retained but unselected. | Old typeset artifact remains preview/history and is not export-effective after translation edit. | Active pointer, not latest timestamp, selects current translation/typeset state. | PASS |

### 4.6 Migration Scenarios

| Scenario | Required repository capability | Required transaction boundary | Required persisted evidence | Recovery or idempotency impact | Boundary check | Result |
| --- | --- | --- | --- | --- | --- | --- |
| M01: Initialize app.db | App lifecycle repository initializes/verifies app schema ledger and Project registry. | Apply one app migration at a time; commit migration effects and ledger update together before Project listing/open is exposed. | app `schema_migrations`, checksums, `projects` table/rows when created. | Startup mutation blocks on checksum mismatch or incompatible schema; Project listing is not exposed until ready. | app.db migration state is independent from project.db migration state. | PASS |
| M02: Initialize project.db | Project lifecycle repository initializes/verifies project schema ledger and ProjectMetadata identity. | Apply one project migration at a time; commit effects and ledger update together; no workflow while migrating. | project `schema_migrations`, ProjectMetadata project/workspace identity evidence. | Recovery and workflow run only after identity and migration readiness pass. | Project db belongs to selected Project; no silent replacement of missing/mismatched db. | PASS |
| M03: Add enum value later | Migration strategy and repositories use stable additive strings for stages, statuses, decisions, issue types, artifact states, and error codes. | Compatible migration may add values without rewriting historical rows. | existing attempts, decisions, issues, artifacts, logs, statuses, and migration ledger remain readable. | Historical audit evidence remains interpretable; recovery does not need destructive rewrites. | Stable string evolution is explicit; exact enum validation mechanism is deferred. | PASS |

### 4.7 Boundary Failure Checks

| Boundary failure check | Required repository capability | Required transaction boundary | Required persisted evidence | Recovery or idempotency impact | Boundary check | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Provider Adapter accesses SQLite. | None; adapters receive no repository/session/DAO capability. | None inside provider calls. | Evidence is persisted later through StageEvidenceWriter, ArtifactService, and acceptance. | Preserves crash recovery and cache policy outside provider code. | Forbidden by repository contract, module dependency rules, and ADR 0001. | PASS |
| Provider Adapter writes repository records. | None; no write contract is exposed to adapters. | Provider/tool call is outside SQLite write transaction. | Tool logs/results/artifacts are written by designated boundaries after provider return. | Avoids hidden current-state changes and unrecoverable side effects. | Forbidden; providers may return temp refs and metadata only. | PASS |
| ArtifactService decides retry, fallback, warning, or block. | ArtifactMetadataRepository only. | Artifact metadata UoW updates metadata/storage state; workflow decision is separate. | artifact path/hash/storage_state/provenance. | Missing/unselected artifacts are evidence; WorkflowLoopEngine decides outcome. | ArtifactService is lifecycle owner, not policy owner. | PASS |
| QualityCheckService advances workflow state. | None for MVP-0. | QualityCheckService has no write transaction. | issue drafts and lifecycle suggestions only, later persisted in acceptance. | Prevents issue/status drift outside acceptance. | Repository-free QualityCheckService is explicit. | PASS |
| WorkflowLoopEngine depends directly on SQL or ORM session internals. | WorkflowLoopEngine receives repository contracts and evidence snapshots only. | Named UoW operations hide transaction internals. | decisions, issues, pointers, attempts persisted by repositories. | Recovery remains testable against repository contracts. | SQL/ORM/session leakage is forbidden. | PASS |
| UI or API handler bypasses Repository / DAO. | API handlers call ApplicationService; repositories are not exposed directly to UI. | API does not own workflow write transactions. | ApplicationService/WorkflowService writes evidence through repository contracts. | Avoids state changes outside lifecycle gates. | HLD and final module rules prohibit direct UI/API database/tool bypass. | PASS |
| Recovery relies only on `Page.status`. | Recovery repositories load rich recovery bundles. | Recovery repair UoW uses task/attempt/evidence guards. | tasks, attempts, decisions, logs, active pointers, artifacts, issues, hashes, TextBlock statuses. | Page.status can be repaired from durable facts. | Explicitly forbidden by final design and ADR 0004. | PASS |
| Active result is derived from latest timestamp. | ContentStateRepository exposes active pointers; ResultVersionRepository exposes history/reuse candidates. | Active selection happens through guarded acceptance. | active OCR/translation/artifact pointer ids, result rows, artifact metadata. | Prevents locked/user-edited/unselected evidence from being overwritten by recency. | Timestamp selection is rejected by final design and ADR 0002/0004. | PASS |
| Image files or large payloads are stored in SQLite. | ArtifactMetadataRepository stores metadata only. | File writes/promotions are ArtifactService operations outside repository payload storage. | file path, hash, byte size, media type, scope, provenance, storage state. | Recovery validates filesystem state via ArtifactService. | SQLite BLOB storage is forbidden. | PASS |
| Design requires full API, frontend, real provider integration, or P1/P2 features before MVP-0. | FakeProvider slice uses minimal repositories and temporary SQLite files. | Backend persistence UoWs only; no UI/API/export/provider transaction is required. | Project, Page, TextBlock, results, artifacts, attempts, decisions, logs, issues, profile snapshot, readiness state. | FakeProvider can validate recovery/idempotency without real providers or P1/P2 features. | Full export/API/frontend/provider/profile details are deferred. | PASS |

## 5. Repository Boundary Gaps

Blocking repository boundary gaps: none.

Non-blocking implementation details:

- Exact repository method names, DTO field shapes, package layout, and read-model shapes remain deferred.
- Exact StageEvidenceWriter method surface remains deferred, but its authority is bounded tightly enough to implement.
- The app-level provider/profile table shape may be skeletal or deferred behind deterministic ProcessingProfileSnapshot bootstrap for FakeProvider. This is acceptable because the snapshot requirement is immediate.
- Exact ConfigService secret reference mechanics remain deferred, but raw secrets are explicitly barred from Project persistence and logs.
- Exact ExportRepository behavior is deferred because the validated slice stops at readiness, not actual export.

## 6. Transaction Boundary Gaps

Blocking transaction boundary gaps: none.

Non-blocking implementation details:

- Exact SQLite isolation mode, busy timeout, savepoint strategy, and retry policy for aborted acceptance remain deferred.
- Exact optimistic concurrency mechanics are deferred, but required guards are clear: expected active pointer ids, dependency hashes, task/current stage, stage statuses, and locked translation pointer when relevant.
- The import implementation must preserve the final design intent that Page import completion cannot commit without an official original artifact pointer. Whether the artifact metadata insert is composed inside the same repository UoW or handled as a recoverable preceding ArtifactService commit is an implementation choice, but orphan official originals must not make a Page imported by themselves.
- Exact filesystem atomic promotion, fsync, and temp cleanup mechanics belong to ArtifactService implementation/design and are not blockers for repository readiness.
- Exact recovery decision recording granularity for every `abandoned_after_crash` repair remains deferred, but the design requires repair evidence or decisions when user-visible state changes.

## 7. Migration Strategy Gaps

Blocking migration gaps: none.

Non-blocking implementation details:

- Exact migration tool topology is deferred, including Alembic dual streams versus a lightweight runner.
- Migration file naming, checksum storage format, and workspace identity string format are deferred.
- Project migration locking is minimal: no workflow while migrating is required, but exact lock implementation is deferred.
- Restore/relink UX, identity collision UX, orphan Project directory cleanup, and newer-version read-only inspection are deferred.
- Downgrade migrations and legacy backfills are out of MVP-0 scope.

## 8. Recovery and Idempotency Gaps

Blocking recovery/idempotency gaps: none.

Non-blocking implementation details:

- Heartbeat stale threshold, recovery timeout, and crash retry ceiling values are deferred.
- Exact storage location for those values, such as app config, task policy, ProcessingProfileSnapshot, or a combination, remains open.
- Exact ToolRunLog crash/interruption status mapping is deferred as long as it remains compatible with WorkflowAttempt statuses.
- Cleanup policy for official but unselected artifacts after recovery is deferred; the required behavior is that they remain evidence/reuse candidates only until validated and accepted.
- Exact serialization of reuse keys and dependency hashes is deferred, but required key components are specified for OCR, translation, cleaned artifacts, and typeset artifacts.
- Exact cache conflict resolution after guard failure is deferred beyond rollback, evidence reload, and WorkflowLoopEngine redecision.

## 9. FakeProvider Slice Readiness Gaps

Blocking FakeProvider readiness gaps: none.

Non-blocking implementation details:

- Exact SQL DDL, ORM mappings, and migration files remain to be written during implementation.
- Exact fake artifact set beyond original, cleaned, and typeset is deferred; masks/crops/raw payloads/quality reports can be optional unless needed by a failure test.
- Exact deterministic FakeProvider fixture modes are not specified here, but required failure modes are: refusal or invalid/partial translation, crash after OCR acceptance, registered-but-unselected artifact, missing active artifact, and open blocking issue.
- Actual `ExportRecord`, ZIP, manifest, and export output artifacts are deferred. The slice must still implement readiness checks and blocking/warning readiness states.
- Full app-level provider_configs, processing_profiles UI, OS secret store integration, and provider capability catalog are deferred.

## 10. Software Engineering Principle Check Results

| Principle | Result | Validation |
| --- | --- | --- |
| Separation of concerns | PASS | Repository, ArtifactService, WorkflowLoopEngine, QualityCheckService, Provider Adapter, StageExecutor, and ApplicationService have distinct responsibilities. |
| Single Responsibility | PASS | Persistence, artifact lifecycle, quality classification, workflow decisions, and provider calls are not collapsed into one module. |
| High cohesion / low coupling | PASS | Repository groups follow workflow evidence needs without exposing table-shaped generic repositories. |
| Information hiding | PASS | SQL, ORM sessions, cursors, query builders, and row dictionaries are hidden behind contracts and UoWs. |
| Dependency inversion | PASS | Workflow modules depend on repository contracts and service boundaries, not SQLite implementation details. |
| Interface segregation | PASS | StageEvidenceWriter is narrow; QualityCheckService receives no repository; Provider Adapters receive no persistence interface. |
| Composition over inheritance | PASS | The design composes repositories, services, adapters, and UoWs; no inheritance hierarchy is required for readiness. |
| Explicit state machines | PASS | Workflow stages, statuses, decisions, attempts, retry budgets, stale propagation, and readiness states are explicit. |
| Idempotent processing | PASS | Task duplicate suppression and stage reuse keys are separated and auditable. |
| Recoverability | PASS | Recovery uses committed evidence bundles and active pointers, not aggregate Page.status alone. |
| Traceability | PASS | Attempts, decisions, issue links, tool logs, artifacts, result versions, profile snapshots, and active pointer changes are persisted. |
| Scope control | PASS | DDL, ORM, API, frontend, real providers, prompt templates, full export, and P1/P2 features are excluded. |
| Testability | PASS | The first slice is expected to use temporary real SQLite app/project databases and workspace artifacts. |

## 11. Acceptability for FakeProvider Implementation

Result: PASS. The design is acceptable for FakeProvider single-Page backend vertical slice implementation.

Implementation may proceed if the next phase preserves these non-negotiable conditions:

- Use real temporary SQLite `app.db` and `project.db` tests, not in-memory-only fake persistence.
- Implement Project open identity/migration gating before exposing project repositories.
- Keep Provider Adapters repository-free and official-artifact-free.
- Keep provider/tool calls outside SQLite write transactions.
- Implement guarded acceptance as the only current-output selection boundary.
- Use active pointers, never latest timestamp, for current OCR, translation, cleaned image, and typeset image.
- Persist refusal, warning/blocking issue, attempt, tool log, decision, and decision-issue evidence for QualityIssue-bearing paths.
- Include restart/idempotency tests for crash after OCR acceptance, crash after artifact registration before acceptance, rerun unchanged stages, missing active artifact, and open blocking issue.

## 12. Rejected Validation Outcomes

| Rejected outcome | Reason |
| --- | --- |
| Require a design revision before implementation | No HARNESS scenario failed and no blocking UNCLEAR was found. |
| Claim complete MVP export readiness | This design validates readiness through `ready_for_export`; actual export records, ZIPs, manifests, and output artifacts remain follow-up work. |
| Treat deferred DDL/ORM/method names as blockers | The HARNESS and PLAN explicitly forbid implementation code and DDL in this phase. |
| Treat final design's own scenario replay as sufficient without rechecking | This report independently replayed each HARNESS scenario and boundary failure check. |

## 13. Open Questions After Validation

None block the FakeProvider single-Page persistence slice.

Non-blocking open questions remain as documented in `docs/design/persistence/final/open-questions.md`, especially exact repository methods/DTOs, SQL/ORM/migration details, heartbeat thresholds, recovery timeout values, artifact retention TTLs, export schema, provider/profile details, API/UI behavior, and P1/P2 entities.
