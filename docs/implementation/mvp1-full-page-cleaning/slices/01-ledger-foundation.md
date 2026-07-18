# Slice 1 — Full-page Cleaning Ledger Foundation

**Gate status: ACCEPTED_WITH_RECORDED_ENVIRONMENT_LIMITS.** The automatic
Slice 1 exit evidence is recorded in `01-ledger-foundation-GATE.md`. Full
integration remains `ENVIRONMENT_BLOCKED`, not PASS, because the available
Windows/UNC host lacks `cv2` and holds SQLite files during two existing delete
tests. Slice 2 is the next allowed Slice, but is not part of this commit.

## Goal

Persist and recover a page-scoped Cleaning run, immutable segment inventory,
immutable per-instance result facts, current final segment dispositions, and
one durable correction reservation. These facts must be queryable from
project.db without selecting artifacts by timestamp or inferring completion
from Page status.

## Allowed changes

- project migration/bootstrap and ProjectRepositories wiring;
- a dedicated full-page cleaning ledger repository and narrow UoW facade;
- focused ledger integration tests;
- this implementation-plan directory and this slice's report/gate.

## Explicit exclusions

No combined candidate/member tables, composition, page validator, issue
lifecycle integration, active pointer writes, real case execution, Cleaner,
Provider, UI/API, typesetting, export, or batch behavior.

`CLEANED_PASS` is forbidden in Slice 1. g002/s01 and g002/s02 are represented
only by `InstanceCleaningResult.state = validated | ready_for_composition`;
they have no final disposition until Slice 2 persists accepted combined-member,
page-validation, and acceptance facts. Slice 1 stale marking is named
`mark_unaccepted_cleaning_run_stale`, requires a null active cleaned pointer,
and otherwise returns `ACTIVE_POINTER_STALE_REPAIR_REQUIRES_SLICE_2` without
changing any pointer. Slice 2 owns guarded stale-pointer repair.

## Exit conditions

- v3 is additive, idempotent, preserves existing project identity/data, and
  blocks repository access on migration failure/checksum mismatch;
- run replay, inventory replay, result replay, disposition supersession, and
  correction replay are durable and queryable;
- a second automatic correction is explicitly rejected;
- stale marking preserves history and does not mutate active pointers;
- case-71 and case-72 can be expressed with complete unique inventories and
  explicit blockers only;
- focused migration/repository/UoW tests pass.
