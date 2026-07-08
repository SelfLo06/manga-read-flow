## 1. Scope

This proposal covers the ArtifactService recovery and integrity contract for MVP-0:

- missing artifact detection;
- hash mismatch detection;
- `storage_state = missing` handling;
- orphan temp file treatment after crash;
- recovery evidence returned to StageExecutor / WorkflowLoopEngine;
- rebuildability classification as evidence, not a workflow decision.

It does not define directory layout, SQL DDL, ORM models, cleanup scheduler implementation, export manifest format, or real provider behavior.

## 2. Role Bias

Bias: maximize recovery correctness and auditability while preventing ArtifactService from becoming a hidden WorkflowLoopEngine.

Design posture:

- ArtifactService may say: "this file is absent", "hash does not match", "this artifact type is normally rebuildable", "this orphan temp file exists".
- ArtifactService must not say: "retry OCR", "block export", "rebuild typesetting now", "fallback provider", or "mark warning".

## 3. Assumptions

| Assumption | Rationale |
| --- | --- |
| `docs/HLD.md` is the preferred HLD baseline. | Project plan names it as the current architecture baseline. |
| `processing_artifacts.storage_state` vocabulary from data-model final is authoritative for MVP. | It already includes `present`, `metadata_only_cleaned`, `moved_to_trash`, `missing`, `deleted`. |
| Recovery rules are the tie-breaker for crash/orphan behavior. | They are newer and task-specific for workflow recovery. |
| Apparent tension is non-blocking: data model says recovery may scan temp/orphan files and register or clean; recovery-rules says MVP treats unregistered output as `abandoned_after_crash` unless normal validation is replayed. | Resolve by allowing scan/report/quarantine, but no active official promotion unless the normal validation + ArtifactService registration + QualityCheck + WorkflowLoopEngine acceptance path is explicitly replayed. |

## 4. Proposed Contract

Decisions:

| Decision | Contract | Rationale |
| --- | --- | --- |
| D1 | Artifact integrity check returns a structured `ArtifactIntegrityReport`. | WorkflowLoopEngine needs evidence without delegating decisions. |
| D2 | Missing path and hash mismatch both update artifact `storage_state` to `missing`, with an integrity reason. | Existing storage vocabulary already treats expected-but-invalid bytes as missing for recovery/export safety. |
| D3 | `metadata_only_cleaned` is not an error when the artifact bytes are intentionally cleaned and no active output depends on bytes. | Retention cleanup must not look like accidental loss. |
| D4 | Orphan temp files are never official artifacts by path alone. | Prevents crash residue from becoming accepted output without validation. |
| D5 | ArtifactService may attach a `rebuildability_hint`, but WorkflowLoopEngine decides rebuild/retry/warning/block. | Supports recovery-rules.md while preserving boundaries. |

Minimal service operations:

| Operation | Input | Output | Side effect |
| --- | --- | --- | --- |
| `validate_artifact(artifact_id, expected_use)` | Artifact id and expected use such as preview/export/recovery. | `ArtifactIntegrityReport`. | May update `storage_state` to `missing` or repair stale `present` metadata only when validation proves it. |
| `validate_artifacts(scope, expected_use)` | Project/Page/TextBlock scope and artifact ids selected by caller. | List of reports plus summary counts. | Same as per-artifact validation. |
| `scan_orphan_temps(attempt_id or task scope)` | Attempt/temp scope. | `OrphanTempReport`. | May quarantine/label temp files in temp space; does not register official artifacts unless caller invokes normal registration path. |
| `record_missing(artifact_id, reason)` | Artifact id and reason. | Updated artifact metadata snapshot. | Sets `storage_state = missing`; preserves path/hash/provenance. |
| `restore_validate(artifact_id)` | Artifact id after trash/restore/manual repair. | Integrity report. | May move `moved_to_trash` or `missing` back to `present` only after path and hash validation. |

## 5. Minimal Vocabulary / Fields

Storage state:

Use existing storage states:

| State | Integrity meaning |
| --- | --- |
| `present` | File exists at registered project-relative path and hash validates. |
| `metadata_only_cleaned` | Bytes intentionally removed by retention; metadata remains. Not valid for preview/export bytes. |
| `moved_to_trash` | File was intentionally moved under project trash. Not valid for normal workflow use until restored and hash-valid. |
| `missing` | Expected bytes are absent, inaccessible, or hash-invalid. |
| `deleted` | Permanently deleted by confirmed delete/retention; metadata may remain for audit. |

Integrity report:

| Field | Meaning |
| --- | --- |
| `artifact_id` | Existing artifact metadata id. |
| `artifact_type` | Example: original image, mask, crop, raw payload, cleaned image, typeset image, export output. |
| `source_stage` | Stage that produced or registered the artifact. |
| `expected_use` | `preview`, `export_check`, `recovery`, `reuse_check`, `cleanup`, or `restore`. |
| `expected_state` | Usually `present` for active preview/export/reuse. |
| `observed_state` | Current storage state after validation. |
| `integrity_status` | `valid`, `missing_path`, `hash_mismatch`, `metadata_only`, `trashed`, `deleted`, `inaccessible`, `unknown_error`. |
| `expected_hash` / `observed_hash` | Expected hash from metadata and observed hash when computable. |
| `byte_size_expected` / `byte_size_observed` | Optional mismatch evidence. |
| `relative_path` | Project-relative path only. |
| `active_reference` | Caller-supplied or repository-derived hint such as original/active_cleaned/active_typeset/export. |
| `rebuildability_hint` | `non_rebuildable`, `rebuildable_from_committed_inputs`, `retriable_provider_output`, `diagnostic_only`, `export_recreatable`, `unknown`. |
| `safe_to_cleanup_hint` | `yes`, `no`, or `unknown`; never a workflow decision. |
| `evidence_summary` | Sanitized, short audit message; no secrets. |

Orphan temp report:

| Field | Meaning |
| --- | --- |
| `attempt_id` / `task_id` | Scope where orphan was found. |
| `temp_path` | Temp or attempt-local path, not official path. |
| `size` / `observed_hash` | Evidence for audit/dedupe. |
| `suspected_stage` | Best-effort source stage from temp scope. |
| `classification` | `orphan_temp`, `partial_write`, `unregistered_provider_output`, `unknown_temp`. |
| `recommended_handling_hint` | `quarantine`, `eligible_temp_cleanup`, or `normal_validation_replay_required`. |

## 6. Normal Path

| Step | Actor | Contract |
| --- | --- | --- |
| 1 | StageExecutor | Receives provider/local output as temp file or in-memory payload. |
| 2 | StageExecutor -> ArtifactService | Requests official registration/promotion. |
| 3 | ArtifactService | Copies/moves into official project workspace path, computes hash, size, mime/dimensions, and registers metadata. |
| 4 | ArtifactService | Returns artifact id and `storage_state = present`. |
| 5 | QualityCheckService | Checks output quality using artifact ids/metadata as needed. |
| 6 | WorkflowLoopEngine | Decides continue/retry/warning/block and only then accepts active pointers/status updates through Repository. |
| 7 | Later recovery/export_check | Calls ArtifactService validation before treating active artifacts as export-effective. |

Normal path rule: an active pointer is necessary but not sufficient. Export-effective also requires artifact `present`, hash-valid, fresh dependency hashes, and no open blocking issue.

## 7. Failure / Edge Path

| Edge case | ArtifactService behavior | Report to WorkflowLoopEngine | What WorkflowLoopEngine may decide |
| --- | --- | --- | --- |
| Active original file missing | Mark original artifact `missing`; `rebuildability_hint = non_rebuildable`. | Missing original evidence. | Block or pause for user restore. |
| Active original hash mismatch | Mark `missing`; include expected/observed hash. | Integrity failure evidence. | Block; never overwrite original. |
| Active mask missing | Mark `missing`; hint depends on detection/geometry provenance. | Mask missing evidence. | Rebuild detection/mask, pause, or block. |
| Crop missing | Mark `missing` only if registered and expected; often `cache_rebuildable`. | Crop unavailable. | Rebuild crop or continue if committed OCRResult is enough. |
| Raw OCR/LLM payload cleaned | Keep `metadata_only_cleaned` if retention-cleaned. | Reduced diagnostic evidence. | Reuse committed result or retry if no result. |
| Failed-attempt payload missing | Mark `missing` if expected retained. | Diagnostic evidence degraded. | Usually keep workflow usable if active output does not depend on it. |
| Active cleaned image missing | Mark `missing`; hint `rebuildable_from_committed_inputs` only if caller supplies/ArtifactService can confirm provenance metadata. | Cleaning output absent. | Rebuild cleaning, warning if optional, pause, or block. |
| Active typeset image missing | Mark `missing`. | Export output dependency absent. | Rebuild typesetting if inputs fresh; otherwise block export readiness. |
| Export output missing | Mark `missing`. | Prior export bytes absent. | Does not change page readiness; export design may re-export. |
| Hash mismatch for active output | Treat as `missing`, not as valid altered file. | Tamper/drift evidence. | Rebuild or block; never silently accept. |
| File exists but DB registration failed | Leave non-official; produce orphan report if found. | `unregistered_provider_output`. | Attempt `abandoned_after_crash` unless normal validation replay is implemented. |
| DB artifact exists but file write incomplete | Mark `missing` or `hash_mismatch`. | Incomplete official artifact evidence. | Retry/rebuild/block by policy. |

## 8. Boundary Rules

ArtifactService may:

- generate official artifact paths;
- validate file existence, byte size, hash, and project-relative path safety;
- update `storage_state` for objective storage facts;
- report orphan temp files;
- quarantine temp files in temp/attempt scope;
- provide rebuildability and cleanup hints from artifact type, retention class, and provenance metadata;
- refuse unsafe path traversal or cross-project paths as artifact integrity errors.

ArtifactService must not:

- decide retry, fallback, skip, warning, pause, cancel, block, or ready status;
- call Provider Adapters;
- create `QualityIssue`;
- update active OCR/translation/cleaned/typeset pointers;
- treat temp files as official artifacts by location alone;
- parse raw provider output into accepted OCR/Translation results;
- store image bytes or large payloads in SQLite;
- overwrite original images;
- hide hash mismatches by recomputing metadata in place.

## 9. FakeProvider or FakeQuality Implications

FakeProvider/Fake tests should be able to force these integrity states without real tools:

| Fake mode | Setup | Expected artifact contract behavior |
| --- | --- | --- |
| `fake_missing_original` | Remove registered original file after import. | ArtifactService reports `missing_path`, `non_rebuildable`. |
| `fake_hash_mismatch_typeset` | Modify registered typeset file bytes after registration. | ArtifactService reports `hash_mismatch`, marks `missing`. |
| `fake_orphan_temp_after_crash` | Leave provider temp output without registration. | `scan_orphan_temps` reports `unregistered_provider_output`; no official artifact id. |
| `fake_cleaned_missing` | Delete active cleaned artifact. | Report missing with rebuildability hint if provenance exists. |
| `fake_payload_metadata_only` | Mark successful raw payload as retention-cleaned. | Validation returns `metadata_only`; not a failure unless bytes are required. |
| `fake_export_output_missing` | Delete prior export artifact. | Page readiness is not changed by ArtifactService; export design decides re-export. |

FakeQuality can convert ArtifactService reports into predictable issue candidates such as `artifact_missing`, `artifact_hash_mismatch`, `artifact_unregistered_output`, or stage-specific equivalents, but WorkflowLoopEngine still decides the outcome.

## 10. Recovery / Audit Impact

Recovery support:

This contract supports `recovery-rules.md` by making recovery evidence explicit:

| Recovery rule need | Artifact contract support |
| --- | --- |
| Load artifacts during startup reconciliation. | `validate_artifacts(scope, expected_use = recovery)`. |
| Reuse committed OCR/translation rows if raw payload missing. | Raw payload `metadata_only_cleaned` or `missing` is separate from committed result validity. |
| Reuse cleaned/typeset only when official artifact is `present`. | Integrity report proves `present` and hash-valid. |
| Missing original blocks recovery. | Original reports `non_rebuildable`. |
| Crash after file write before registration. | Orphan report identifies temp output but keeps attempt `abandoned_after_crash` for MVP. |
| Recovery decision must explain reuse/retry/fallback/pause/warning/block. | Artifact reports are durable decision inputs linked by artifact id/attempt id. |

Audit rules:

- Preserve original artifact metadata even when bytes are missing.
- Preserve expected hash after hash mismatch; do not replace it with observed hash.
- Preserve failed attempt metadata even if payload bytes are missing.
- Record integrity checks as recoverable evidence through ToolRunLog/WorkflowAttempt/WorkflowDecision references where the final design chooses the exact persistence location.
- Never include secrets in integrity summaries or orphan reports.

## 11. HARNESS Scenario Coverage

| Scenario | Coverage | Notes |
| --- | --- | --- |
| A01 Register original image | PASS | Original becomes official artifact; later validation treats missing/hash-invalid original as non-rebuildable. |
| A02 Promote temporary provider output | PASS | Temp output becomes official only through ArtifactService promotion and registration. |
| A03 Register failed attempt evidence | PASS | Failed/debug payloads can be registered with retention/safety flags and later validated. |
| A04 Missing active artifact | PASS | Missing/hash mismatch marks `storage_state = missing`; WorkflowLoopEngine receives report and decides. |
| A05 Artifact cleanup boundary | PASS | Active original/cleaned/typeset/export/failed evidence are protected by retention and active-reference hints; cleanup decisions remain separate. |
| S03 File produced but artifact registration fails | PASS | Temp output remains non-official; orphan report supports recovery without active promotion. |
| S04 QualityCheck blocking after artifact registration | PASS | Artifact may remain auditable; active/export-effective acceptance is not ArtifactService's decision. |
| F07 Fake missing artifact | PASS | Fake deletion/mutation can exercise `missing_path` and `hash_mismatch`. |
| Boundary: ArtifactService decides workflow | PASS | Explicitly forbidden. |

## 12. Rejected Alternatives

| Alternative | Rejected because |
| --- | --- |
| Auto-promote orphan temp files during recovery. | Too risky for MVP; bypasses normal validation, QualityCheck, and WorkflowLoopEngine acceptance. |
| Treat hash mismatch as a new valid artifact version. | Masks filesystem drift or tampering and can corrupt recovery/export decisions. |
| Delete artifact metadata when file is missing. | Breaks audit and prevents clear recovery explanations. |
| Make `missing` a QualityIssue only, not artifact state. | Loses storage source-of-truth and makes cleanup/recovery dependent on issue rows. |
| Let cleanup remove active cleaned/typeset artifacts if rebuildable. | Violates HLD/data-model retention rules and can surprise preview/export. |
| Let ArtifactService decide rebuild/block from rebuildability. | Violates WorkflowLoopEngine ownership. |
| Store orphan payloads in SQLite for safety. | Violates no image/large-payload BLOB invariant. |

## 13. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Rebuildability hint becomes de facto decision. | Boundary drift into ArtifactService. | Name it `hint`; require WorkflowDecision for any action. |
| Over-marking hash mismatch as `missing` loses distinction. | Debugging may need exact cause. | Keep `integrity_status = hash_mismatch` and expected/observed hash in report while storage state is `missing`. |
| Orphan temp cleanup removes useful debugging evidence. | Harder crash diagnosis. | Quarantine first for failed/interrupted attempts; retention policy decides later. |
| Metadata-only cleaned bytes needed unexpectedly. | Preview/export failure. | `expected_use` drives validation; metadata-only is invalid when bytes are required. |
| Manual filesystem repair is accepted unsafely. | Wrong file may be restored. | `restore_validate` requires path safety and hash match before `present`. |
| Cross-project path confusion. | Project isolation breach. | ArtifactService validates project-relative paths under the owning workspace. |

## 14. Open Questions

| Question | Blocking? | Notes |
| --- | --- | --- |
| Where exactly are integrity check events persisted: ToolRunLog, WorkflowAttempt artifact refs, WorkflowDecision rationale, or a lightweight maintenance log? | Non-blocking for contract. | Need persistence design to pick exact storage. |
| Should `artifact_hash_mismatch` be a distinct IssueType or an `artifact_missing` issue with error code `hash_mismatch`? | Non-blocking. | QualityCheck taxonomy should decide. |
| How long should quarantined orphan temp files be retained after crash? | Non-blocking. | Belongs to retention policy/profile defaults. |
| Can normal validation replay of orphan provider output be allowed in MVP-0, or should it be fully deferred? | Potentially blocking only if implementation wants orphan reuse. | Proposal recommends deferred; if allowed, it must use the same registration/check/decision path as normal execution. |
| Does `metadata_only_cleaned` apply to successful image derivatives, or only raw/provider payloads? | Non-blocking. | Current baseline protects active image outputs; exact retention classes can narrow this. |
