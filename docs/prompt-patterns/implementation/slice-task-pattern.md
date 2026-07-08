# Implementation Slice Task Pattern

This is a lightweight reusable pattern for MVP-0 implementation slice tasks.

It is based on the Slice 01-07 documents under `docs/implementation/mvp0-fakeprovider-slice/slices/`. It must not broaden a slice beyond its slice document.

## Use For

- MVP-0 backend implementation slices
- Small vertical implementation tasks with clear file boundaries
- Codex tasks that must end with tests, command output, and diff review

Do not use it to generate a new product roadmap, detailed design baseline, or real Codex prompt unless a specific slice is being prepared for execution.

## Goal

State the exact slice objective in one or two paragraphs.

Include:

- what this slice proves;
- why it comes now;
- what it deliberately does not implement;
- the product stage it supports.

## Source Documents

List only documents needed for the slice.

Typical sources:

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- relevant final detailed designs;
- relevant MVP-0 implementation package files;
- the exact slice document.

Avoid adding broad source lists that encourage the agent to re-open settled design decisions.

## Allowed Files

List exact files or directories the implementation may change.

Keep the list narrow enough that the diff can be reviewed quickly. Include tests and fixtures explicitly.

## Forbidden Files

List files and categories the implementation must not touch.

Typical forbidden areas:

- unrelated source code;
- UI/API/frontend files unless the slice is about them;
- real providers when the slice uses FakeProvider;
- export output, ZIP, manifest, or `ExportRecord` unless the slice is about export;
- `docs/design/**/final/**`;
- secrets, logs, caches, build outputs, local config, and AI runtime files.

## Implementation Boundaries

State the architectural rules the slice must preserve.

Examples:

- Repository / DAO is the only SQLite access entry.
- Provider adapters must not access SQLite.
- Provider adapters must not register official artifacts.
- StageExecutor must not update active pointers or create WorkflowDecision.
- ArtifactService must not decide retry, fallback, warning, block, or readiness.
- WorkflowLoopEngine owns workflow decisions.
- Active output selection must not use timestamps or Page.status alone.

## Validation Command

Provide one focused command, usually a pytest target:

```bash
pytest tests/integration/test_<slice_name>.py
```

If multiple commands are required, explain why. Prefer focused integration tests over broad full-suite runs during early slice work.

## Expected Output

Describe the observable result after implementation:

- files or modules that should exist;
- behavior that should pass;
- evidence persisted or exposed;
- failure paths covered;
- what remains intentionally absent.

## Commit Rule

Default rule:

```text
Do not commit unless explicitly allowed.
```

If commits are allowed, require one focused slice commit after validation passes. Stage only files allowed for the slice.

## Stop Conditions

Stop and report when:

- unrelated dirty working tree exists;
- the slice requires forbidden files;
- the slice needs a broader design decision;
- validation cannot run for an unrelated reason;
- implementing the slice would require UI, API, real providers, export output, or batch-scale behavior outside the slice;
- an architecture invariant would be violated.

## Final Report Requirements

The final report should include:

- files changed;
- what was implemented;
- tests or commands run;
- pass/fail result;
- what was skipped and why;
- risks that remain;
- confirmation that forbidden files and final design baselines were not changed.

Do not claim success if validation was not performed.

## Harness Principles For Implementation Tasks

- The real harness for implementation is not the prompt text; it is validation by tests, commands, diffs, file boundaries, and reviewable evidence.
- Each implementation task should make Codex report what it changed, what it ran, what passed, what was skipped, and where risk remains.
- Prefer pytest and focused integration tests over a new custom harness runtime.
- Do not build a custom agent loop or Superpowers-like framework for this project.
- Add repo-side scripts or checkers only after repeated failures justify them.

## Minimal Reusable Skeleton

```text
Goal:
Implement <slice id and name>.

This slice proves <specific behavior>. It does not implement <explicit non-goals>.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- <relevant final design docs>
- <exact slice document>

Allowed files:
- <narrow source paths>
- <test file>
- <fixtures if needed>

Forbidden files:
- <unrelated product areas>
- docs/design/**/final/**
- secrets, logs, caches, build outputs, local config, AI runtime files

Implementation boundaries:
- <architecture invariant 1>
- <architecture invariant 2>
- <slice-specific boundary>

Validation command:
pytest <focused test target>

Expected output:
- <observable success>
- <failure path coverage>
- <intentionally absent scope>

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- <forbidden dependency or scope expansion appears>
- Validation command is unavailable or failing for unrelated reasons.

Final report:
- files changed
- implementation summary
- validation run and result
- skipped validation, if any
- risks
- confirmation that no forbidden files or final design baselines changed
```

## Scope Guard

This pattern is only a shell for turning an existing slice document into a real task prompt.

It must not add capabilities beyond the slice document. If the slice document says "ready_for_export only," the generated prompt must not ask for actual export output. If the slice document says FakeProvider only, the generated prompt must not ask for real provider integration.
