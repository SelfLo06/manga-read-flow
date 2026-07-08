# MVP-0 FakeProvider Slice Open Questions

Only implementation-planning questions that affect the next Codex tasks are listed here.

## 1. Blocking questions

None.

The plan is ready to generate implementation tasks because all required slices have validation targets, file boundaries, acceptance criteria, and stop conditions.

## 2. Non-blocking questions for Slice 01

- Exact backend package path: the plan recommends `src/manga_read_flow/**` unless a future implementation task discovers an existing backend package.
- Exact migration runner shape: the plan requires independent app/project ledgers and readiness checks, but does not require Alembic or a custom production migration framework for MVP-0.
- Exact Project id format: UUIDv7, ULID, integer/public id, or another stable id can be chosen during implementation if tests keep Project isolation explicit.
- Exact Project workspace identity marker format.

## 3. Non-blocking questions for Slice 02

- Exact repository method names and DTO field names.
- Exact SQLite access implementation: raw `sqlite3`, SQLAlchemy Core, or another minimal approach. The repository boundary is fixed; the concrete implementation is deferred.
- Exact optimistic concurrency representation for expected-state guard failures.
- Exact fixture/helper names for app/project Unit of Work tests.

## 4. Non-blocking questions for Slice 03

- Exact artifact directory layout under a Project workspace.
- Exact filename collision strategy for duplicate original filenames.
- Exact hash algorithm constant. The designs imply stable hash metadata; implementation can choose a standard such as SHA-256.
- Exact tiny fake image fixture.
- Whether dimensions are extracted in Slice 03 or deferred until a provider/image helper exists.

## 5. Non-blocking questions for Slices 04-06

- Exact FakeProvider mode selector location: ProcessingProfileSnapshot settings, test task config, or both.
- Exact minimal ProviderResult DTO field names.
- Exact issue type/error code spellings for invalid translation, partial translation, provider refusal, cleaning skip, and typesetting overflow.
- Exact user-facing message keys and suggested action keys. Backend tests can assert stable codes before final UI copy exists.

## 6. Non-blocking questions for Slice 07

- Exact fake provider call-count instrumentation for idempotency tests.
- Exact crash simulation helper: exception injection, manual transaction split, or test-only hook.
- Exact policy for official unselected artifact cleanup after the recovery test. Cleanup scheduling is not required for MVP-0.
- Exact crash retry ceiling defaults in the FakeProvider ProcessingProfileSnapshot.

## 7. Resolved input conflict

`GOAL.md` lists Slice 02 as import/artifact and Slice 03 as repository/UoW, while `PLAN.md` and the task prompt require Slice 02 repository/UoW and Slice 03 ArtifactService/import.

Resolution:

- Use the `PLAN.md` and task-prompt order.
- This is non-blocking because the required output paths and slice sections are explicit in `PLAN.md`.
