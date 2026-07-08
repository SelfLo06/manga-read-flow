# MVP-0 FakeProvider Implementation Readiness Checklist

Use this checklist before starting each implementation slice. Mark each item as `PASS`, `FAIL`, or `N/A` and link or name the evidence.

| Area | Check | Result | Evidence / notes |
| --- | --- | --- | --- |
| Project foundation | `app.db` initialization, `project.db` initialization, ProjectMetadata verification, and independent migration ledgers are planned before workflow code. | PASS / FAIL / N/A | |
| Repository boundary | Repository / DAO is the only SQLite access entry; callers do not receive SQL, cursors, sessions, or generic table gateways. | PASS / FAIL / N/A | |
| Unit of Work boundary | Provider calls, file scans, and long file-producing operations do not run inside SQLite write transactions. | PASS / FAIL / N/A | |
| ArtifactService import | Original image import uses ArtifactService, project-relative artifact paths, hash/metadata registration, and Page original pointer commit. | PASS / FAIL / N/A | |
| FakeProvider modes | FakeProvider has deterministic success, invalid output, partial translation, refusal, cleaning skip, and typesetting overflow modes. | PASS / FAIL / N/A | |
| StageExecutor boundary | StageExecutor records tool evidence only through `StageEvidenceWriter` and does not update active pointers, issues, decisions, or retry budget. | PASS / FAIL / N/A | |
| WorkflowLoop happy path | One Project / one Batch / one Page can reach `ready_for_export` through fake detection, OCR, translation, cleaning, typesetting, and `export_check`. | PASS / FAIL / N/A | |
| QualityIssue paths | Invalid/partial translation, provider refusal, cleaning skip, and typesetting overflow create visible issue evidence through WorkflowLoopEngine acceptance. | PASS / FAIL / N/A | |
| Readiness gate | Open blocking issues prevent pure `ready_for_export`; warning readiness is explicit and profile-controlled. | PASS / FAIL / N/A | |
| Idempotency | Unchanged rerun can reuse OCR, translation, cleaned, and typeset outputs with auditable reuse attempts or decisions. | PASS / FAIL / N/A | |
| Recovery | Crash after OCR acceptance, registered-but-unselected artifact, and missing active artifact scenarios are planned and testable. | PASS / FAIL / N/A | |
| Forbidden scope | No UI/API routes, real providers, real prompt templates, export output, ZIP, manifest, `ExportRecord`, batch-scale workflow, or P1/P2 features are required. | PASS / FAIL / N/A | |
| Commit hygiene | Branch and `git status --short` are inspected; only intended files are staged; no secrets, logs, caches, build outputs, or AI runtime files are committed. | PASS / FAIL / N/A | |

Readiness rule:

- All non-`N/A` rows must be `PASS` before claiming an implementation slice is ready.
- Any `FAIL` must name the blocking file, boundary, or validation command.
- `N/A` is allowed only when a row is outside the current slice and is already covered by an earlier or later slice.
