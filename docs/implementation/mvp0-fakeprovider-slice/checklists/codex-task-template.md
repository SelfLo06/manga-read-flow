# Codex Implementation Task

## Goal

State the specific slice goal in one paragraph. Include the target validation command and the expected persisted evidence.

## Source documents

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/HLD-v0.2.md`
- `docs/PROJECT-PLAN.md`
- Relevant final design documents under `docs/design/**/final/`
- `docs/implementation/mvp0-fakeprovider-slice/GOAL.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`
- The specific slice file under `docs/implementation/mvp0-fakeprovider-slice/slices/`

## Allowed files

List exact files or directories for the slice. Keep the list narrow and include the test file for the validation command.

## Forbidden files

Always include:

- `docs/design/**/final/**`
- frontend, Web UI, and Next.js files unless the slice explicitly allows them
- FastAPI route/API files unless the slice explicitly allows them
- real provider integrations
- real prompt templates
- export output, ZIP, manifest, or `ExportRecord`
- secrets, local config, logs, caches, build outputs, `.codex/`, `.claude/`, `.idea/`, or generated scratch files

## Required behavior

Describe:

- persisted evidence expected;
- architecture boundaries that must hold;
- normal path;
- failure path;
- boundary conditions;
- restart/recovery or idempotency expectations when relevant.

## Validation command

```bash
pytest <slice-specific-test-target>
```

If the command cannot run, stop and report why. Do not fabricate results.

## Acceptance criteria

List concrete assertions. Include both behavior and boundary assertions.

## Stop conditions

Stop and report before editing further if any of these occur:

- unrelated dirty working tree exists;
- the slice needs a real provider;
- the slice needs UI, API routes, or export output;
- the slice needs to modify previous final design docs;
- an architecture boundary would be broken;
- the validation command is unavailable or failing for an unrelated reason;
- the implementation requires secrets, local config, logs, caches, build outputs, or generated scratch files.

## Commit rule

Do not commit unless the user explicitly allows commits for the implementation task.

If commits are allowed:

1. Inspect `git status --short`.
2. Inspect `git diff -- <target-files>`.
3. Stage only files allowed for this slice.
4. Commit once with a precise message.
5. Do not push.

## Final report format

Report:

1. Current branch.
2. Final `git status --short`.
3. Files changed.
4. Decisions made.
5. Validation command and result.
6. Boundary risks.
7. Scope risks.
8. Unresolved questions.
