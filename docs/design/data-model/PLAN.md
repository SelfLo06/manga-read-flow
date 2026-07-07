You are the orchestrator for the data model detailed design loop.

This task is design-documentation only. Do not implement code, migrations, SQL DDL, ORM models, API handlers, frontend code, prompt templates, or provider integrations.

## Goal

Run the full data model detailed design loop:

1. Preflight validation
2. Five independent proposal agents
3. Cross-review agent
4. Limited revision loop if blocking issues exist
5. Synthesizer agent
6. Harness validation
7. ADR generation
8. Final report

## Required Inputs

Before starting, inspect the current branch and working tree.

Read:

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/design/data-model/GOAL.md`
- `docs/design/data-model/HARNESS.md`

If `GOAL.md` or `HARNESS.md` is missing or empty, stop and report the blocker.

If `docs/SRS-v1.0.md` or `docs/HLD.md` is missing, stop and report the blocker.

Do not modify unrelated files.

Do not push, pull, rebase, create remote branches, upgrade dependencies, or modify package/dependency files.

## Execution Mode

Prefer true parallel execution for proposal agents.

If true parallel execution is not supported by the current Codex client, run the five proposal agents sequentially while preserving independence.

Independence rule:

- During Phase 1, each proposal agent must read the required input documents independently.
- During Phase 1, proposal agents must not read or depend on other proposal files.
- If running sequentially, do not let later proposal agents inspect earlier proposal files.

Commit rule:

- Commits are explicitly allowed for this documentation design loop.
- Commit only after the relevant file or phase is complete.
- Before each commit, inspect `git status --short`.
- Before staging a file, inspect `git diff -- <target-file>`.
- Stage only the intended file or files.
- Do not commit unrelated changes.
- Do not push.
- Do not commit `.codex/`, `.claude/`, `.idea/`, logs, caches, build outputs, local config, secrets, or temporary files.

If the working tree already contains unrelated user changes before starting, stop and report them instead of overwriting or mixing with them.

## Required Directory Structure

Ensure these directories exist:

- `docs/design/data-model/proposals/`
- `docs/design/data-model/reviews/`
- `docs/design/data-model/final/`
- `docs/design/data-model/adr/`

Create only these required directories if missing.

Do not create unrelated files.

---

# Phase 0: Preflight Validation

Create:

`docs/design/data-model/reviews/00-preflight.md`

The preflight report must include:

1. Current branch
2. Initial `git status --short`
3. Required file presence check
4. Whether `GOAL.md` and `HARNESS.md` are non-empty
5. Conflicts found between SRS and HLD, if any
6. Data model risks before proposal generation
7. Questions that must be answered before proposal agents start
8. Whether Phase 1 may proceed

If Phase 1 may not proceed, stop after writing the preflight report.

Commit message:

`docs: add data model preflight report`

---

# Phase 1: Independent Proposal Agents

Open these five agents.

If true parallel execution is not available, run them sequentially but preserve independence.

## 1. Domain Model Agent

Output:

`docs/design/data-model/proposals/01-domain-model-agent.md`

Focus:

- Domain boundaries
- Entity responsibility
- Aggregate-like ownership
- Result versioning
- Active result selection
- Glossary ownership
- Stale relationships

## 2. Persistence Agent

Output:

`docs/design/data-model/proposals/02-persistence-agent.md`

Focus:

- app.db vs project.db placement
- Indexes
- Uniqueness constraints
- Migration readiness
- Soft delete
- Schema evolution
- Project isolation
- Avoiding cross-database foreign keys

## 3. Workflow-State Agent

Output:

`docs/design/data-model/proposals/03-workflow-state-agent.md`

Focus:

- ProcessingTask
- WorkflowAttempt
- WorkflowDecision
- Stage status
- Restart recovery
- Partial retry
- Stale propagation
- Idempotency keys
- Crash recovery

## 4. Artifact-Quality Agent

Output:

`docs/design/data-model/proposals/04-artifact-quality-agent.md`

Focus:

- ProcessingArtifact
- QualityIssue
- ToolRunLog
- Provider refusal records
- Failed payload retention
- Debug artifacts
- File cleanup
- Export blocking
- Artifact lifecycle ownership

## 5. API/ORM Readiness Agent

Output:

`docs/design/data-model/proposals/05-api-orm-readiness-agent.md`

Focus:

- SQLAlchemy mapping readiness
- Pydantic DTO readiness
- FastAPI endpoint readiness
- Transaction boundaries
- Repository boundaries
- Query patterns
- Avoiding cyclic dependencies
- Avoiding over-designed models

Do not design the full API or ORM implementation.

## Proposal Structure

Each proposal must follow this exact structure:

1. Scope
2. Role Bias
3. Assumptions
4. Proposed entities
5. P0 / P1 / P2 classification
6. app.db vs project.db placement
7. Key fields
8. Relationships
9. Versioning rules
10. Active pointer rules
11. State and stale rules
12. Artifact relationships
13. Idempotency and cache keys
14. Deletion and retention policy
15. Migration concerns
16. Risks
17. Rejected alternatives
18. Decisions intentionally left to later rounds
19. Validation against all scenarios in `HARNESS.md`
20. Open questions

Each proposal must explicitly discuss:

- Project / Batch / Page / TextBlock
- OCRResult
- TranslationResult
- GlossaryTerm / GlossaryVersion
- ProcessingTask
- WorkflowAttempt / WorkflowDecision
- QualityIssue
- ProcessingArtifact
- ToolRunLog
- ExportRecord
- ProcessingProfile

## Proposal Hard Rules

- Do not implement code.
- Do not create migrations.
- Do not write SQL DDL.
- Do not edit final design files.
- Do not edit ADR files in this round.
- Do not modify proposal files owned by other agents.
- Do not invent features outside SRS/HLD.
- If a decision is unclear, list it as an open question.
- If SRS and HLD conflict, report the conflict in the relevant proposal instead of silently choosing.
- Provider adapters must not own persistence, artifact lifecycle, retry/fallback decisions, or quality issue attribution.
- No image BLOBs in SQLite.
- Original images must never be overwritten.
- API keys must not be stored in project.db.
- Logs and proposal examples must not include secrets.

## Phase 1 Commit Discipline

After each proposal file is completed:

1. Inspect `git status --short`.
2. Inspect `git diff -- <that proposal file>`.
3. Stage only that proposal file.
4. Commit it.
5. Use these commit messages:

- `docs: add domain model data proposal`
- `docs: add persistence data proposal`
- `docs: add workflow state data proposal`
- `docs: add artifact quality data proposal`
- `docs: add api orm readiness data proposal`

Do not stage or commit any other files.

---

# Phase 2: Cross-Review Agent

After all five proposal files exist and are committed, run the reviewer agent.

The reviewer must read:

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/design/data-model/GOAL.md`
- `docs/design/data-model/HARNESS.md`
- all files under `docs/design/data-model/proposals/`

Create:

`docs/design/data-model/reviews/01-cross-review.md`

The review must include:

1. Summary of each proposal
2. Conflicts between proposals
3. Missing entities
4. Missing relationships
5. Violated invariants
6. Unsupported scenarios
7. Over-designed parts
8. Under-designed parts
9. Migration risks
10. ORM risks
11. Artifact lifecycle risks
12. Recovery risks
13. Duplicated source-of-truth risks
14. Recommended final decisions
15. ADR candidates
16. Blocking issues
17. Non-blocking issues
18. Open questions that block final synthesis
19. Open questions that do not block final synthesis

Commit message:

`docs: add data model cross review`

---

# Phase 3: Limited Revision Loop

If the cross-review identifies blocking issues, run at most two revision rounds.

Rules:

- Revise only the affected proposal files.
- Do not edit final files.
- Do not edit ADR files.
- Do not edit unrelated files.
- Each revised proposal must add a `Revision Notes` section at the top.
- The revised proposal must explain what changed and which review issue it addresses.
- Do not silently remove open questions.
- If a blocking issue cannot be resolved without user input, record it in `docs/design/data-model/final/open-questions.md` later during synthesis.

After each revised proposal:

1. Inspect `git status --short`.
2. Inspect `git diff -- <revised proposal file>`.
3. Stage only that proposal file.
4. Commit it with:

`docs: revise <agent-name> data proposal`

After revisions, update the cross-review or create:

`docs/design/data-model/reviews/01-cross-review-revision-notes.md`

Commit message:

`docs: add data proposal revision review`

If there are still blocking issues after two revision rounds, stop and report them.

---

# Phase 4: Synthesizer Agent

If synthesis may proceed, run the synthesizer agent.

The synthesizer must read:

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/design/data-model/GOAL.md`
- `docs/design/data-model/HARNESS.md`
- all proposal files
- all review files

The synthesizer may edit only:

- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/erd.mmd`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/data-model/final/open-questions.md`
- `docs/design/data-model/adr/*.md`

Do not implement code.

The final design must include:

1. Design goals
2. Source documents
3. app.db/project.db split
4. Full entity list
5. P0 / P1 / P2 entity classification
6. Entity responsibility table
7. Relationship table
8. Key fields per entity
9. Index and uniqueness recommendations
10. Versioning rules
11. Active pointer rules
12. Stale propagation rules
13. Artifact lifecycle
14. WorkflowAttempt and WorkflowDecision model
15. QualityIssue model
16. ToolRunLog model
17. Export model
18. ProcessingProfile model
19. Soft delete rules
20. Migration strategy
21. Idempotency strategy
22. Scenario replay
23. ADR list
24. Open questions
25. Rejected alternatives
26. Risks and mitigations
27. Decisions deferred to later detailed design stages

The ERD file must be Mermaid-compatible.

The schema outline must not be full SQL DDL. It should be implementation-ready but still design-level.

The state-data impact document must explain how OCR edit, translation edit, provider refusal, cleaning skip, typesetting overflow, crash recovery, and export blocking are represented in data.

Commit all Phase 4 final and ADR files together.

Commit message:

`docs: add data model detailed design`

---

# Phase 5: Harness Validation Agent

After synthesis, run the harness validation agent.

The harness validation agent must read:

- `docs/design/data-model/HARNESS.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/erd.mmd`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/data-model/final/open-questions.md`
- `docs/design/data-model/adr/*.md`

Create:

`docs/design/data-model/reviews/02-harness-validation.md`

The validation report must include:

1. Invariant checklist with PASS / FAIL / UNCLEAR
2. Scenario replay results with PASS / FAIL / UNCLEAR
3. Missing fields
4. Ambiguous ownership
5. Duplicated source-of-truth risks
6. Recovery gaps
7. Idempotency gaps
8. Artifact lifecycle gaps
9. Export blocking gaps
10. Whether final design is acceptable for MVP backend skeleton design

If any hard invariant fails, do not modify final files automatically. Report the failure.

Commit message:

`docs: add data model harness validation`

---

# Final Report

At the end, report:

1. Current branch
2. Final `git status --short`
3. Commits created
4. Files changed
5. Proposal files created
6. Review files created
7. Final design files created
8. ADR files created
9. Blocking issues, if any
10. Non-blocking open questions
11. Whether the data model design loop is complete
12. Recommended next step

Do not push.