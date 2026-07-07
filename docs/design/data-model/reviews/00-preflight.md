# Data Model Detailed Design Preflight

## 1. Current Branch

`main`

## 2. Initial `git status --short`

Captured before creating phase output directories or files:

```text
 M .gitignore
?? docs/design/data-model/DECISION_LOG.md
?? docs/design/data-model/GOAL.md
?? docs/design/data-model/HARNESS.md
```

Pre-existing changes are treated as user-owned. This design loop must not stage or commit `.gitignore`, `DECISION_LOG.md`, `GOAL.md`, or `HARNESS.md` unless explicitly requested later. Phase commits must stage only the phase output file or files.

## 3. Required File Presence Check

| Required input | Present | Notes |
| --- | --- | --- |
| `AGENTS.md` | Yes | Repository instruction file read. |
| `docs/SRS-v1.0.md` | Yes | Tracked source document. |
| `docs/HLD.md` | Yes | Tracked source document. |
| `docs/design/data-model/GOAL.md` | Yes | Present but untracked at preflight time. |
| `docs/design/data-model/HARNESS.md` | Yes | Present but untracked at preflight time. |

Required output directories were ensured:

- `docs/design/data-model/proposals/`
- `docs/design/data-model/reviews/`
- `docs/design/data-model/final/`
- `docs/design/data-model/adr/`

## 4. Non-Empty Input Check

| File | Size / line evidence | Non-empty |
| --- | ---: | --- |
| `docs/design/data-model/GOAL.md` | 4,880 bytes / 136 lines | Yes |
| `docs/design/data-model/HARNESS.md` | 4,424 bytes / 126 lines | Yes |

## 5. Conflicts Found Between SRS and HLD

No hard conflict blocks proposal generation. The following design tensions must be resolved or recorded by proposals and synthesis:

| Topic | SRS position | HLD position | Preflight handling |
| --- | --- | --- | --- |
| State vocabulary | SRS lists Batch/Page states such as `completed`, `partially_failed`, `failed`, `exported`. | HLD adds workflow-loop states such as `auto_checking`, `auto_retrying`, `ready_for_export`, `ready_for_export_with_warnings`, and `blocked`. | Prefer HLD for state architecture; keep SRS states as requirement vocabulary where useful. |
| Data fields vs detailed model | SRS includes candidate field lists for core tables. | HLD adds explicit loop, artifact, profile, decision, and quality ownership requirements. | Treat SRS field lists as minimum requirement signals, not final schema. |
| Export with blocking issues | SRS requires export and manifest support but does not fully specify blocking semantics. | HLD requires unresolved blocking issues to reject normal export; warning export depends on `ProcessingProfile`. | Prefer HLD export gate semantics. |
| Provider refusal handling | SRS lists provider refusal error codes and fallback/manual paths. | HLD assigns refusal decision-making to `WorkflowLoopEngine`, not Provider Adapter. | Preserve SRS error codes and HLD ownership boundary. |

## 6. Data Model Risks Before Proposal Generation

- Active OCR/translation can become a duplicated source of truth if both result rows and parent pointers independently claim current state without consistency rules.
- Page-level translation calls but TextBlock-level storage require clear `WorkflowAttempt`, `ToolRunLog`, and artifact ownership so one LLM call can map to many `TranslationResult` rows.
- `app.db` / `project.db` separation must avoid cross-database foreign keys while still supporting project discovery, soft delete, and workspace paths.
- Restart recovery cannot rely only on coarse Page or Batch status; it must combine task, stage status, attempts, decisions, artifacts, and active result pointers.
- Stale propagation after OCR edits, translation edits, geometry edits, and glossary edits must be explicit enough to avoid accidental reuse of obsolete downstream results.
- Artifact retention must preserve failed payloads by default while allowing successful large raw payload cleanup without losing traceability.
- Debug artifacts and logs may contain source images, OCR text, translations, provider responses, or request metadata; retention and secret-scrubbing rules must be explicit.
- Provider refusal records must be represented without letting Provider Adapters own persistence, fallback, retry, skip, or blocked decisions.
- Soft deletion must cover database rows and filesystem artifacts without breaking restore before permanent deletion.
- Export blocking requires an unambiguous query over unresolved blocking `QualityIssue` records and any accepted-warning policy from `ProcessingProfile`.

## 7. Questions Before Proposal Agents Start

No question blocks Phase 1. Proposal agents should explicitly discuss these unresolved items:

- Whether active result selection should use parent pointers, per-result active flags, or both with a strict consistency rule.
- Whether `ProcessingProfile` should be stored globally in `app.db`, copied/snapshotted into each `project.db`, or represented as a global template plus per-task snapshot.
- How much normalized structure is needed for `QualityIssue` and `WorkflowDecision` in MVP versus JSON metadata fields.
- Whether `ToolRunLog` and `WorkflowAttempt` should be one-to-one, one-to-many, or stage-dependent.
- How to represent Page-level translation attempt artifacts while preserving TextBlock-level result versions.
- How to model permanent deletion readiness for filesystem artifacts without over-designing a retention worker.

## 8. Phase 1 May Proceed

Phase 1 may proceed.

Proceeding rationale:

- Required authoritative documents are present and non-empty.
- No SRS/HLD conflict blocks independent proposal generation.
- The pre-existing dirty worktree was already reported before this preflight; the active goal was resumed afterward.
- Commit discipline can keep user-owned changes isolated by staging only generated phase output files.

Phase 1 guardrails:

- Proposal agents must read only the authoritative inputs and must not read other proposal files during Phase 1.
- Proposal agents must not edit final design or ADR files.
- Commits must stage only the completed proposal file.
- `.gitignore`, `DECISION_LOG.md`, `GOAL.md`, and `HARNESS.md` must remain unstaged unless the user explicitly asks otherwise.
