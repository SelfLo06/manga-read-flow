# ArtifactService Contract v0.1

## 1. Scope

ArtifactService owns official file artifact lifecycle for MVP-0:

- original image registration;
- temp-to-official promotion;
- path generation, hashing, media metadata, storage state, retention, and safety flags;
- failed/refusal/debug evidence artifact registration;
- missing/hash mismatch detection;
- cleanup/trash boundary.

ArtifactService does not own provider execution, quality classification, workflow retry/fallback/warning/block/readiness decisions, result versioning, or active pointer acceptance.

## 2. Official artifact definition

An official artifact is a committed `processing_artifact` metadata record for bytes promoted or written by ArtifactService under the owning Project workspace.

A usable official artifact additionally requires:

- `storage_state = present`;
- registered project-relative path;
- file exists at that path;
- hash validates against recorded hash;
- required dependency hashes are fresh when used by workflow/export.

A file without an artifact row is an orphan/non-official file. A registered artifact without an active pointer is official but unselected. It is audit/reuse evidence only, not export-effective.

## 3. Minimal operations

| Operation | Input | Output | Does not do |
| --- | --- | --- | --- |
| Register original | User/upload source file, Project/Batch/Page scope, original filename metadata. | Official `original_image` artifact metadata. | Overwrite original bytes or mark Page ready. |
| Promote temp output | Temp ref, scope, artifact intent, stage, attempt/tool refs, safety/retention intent. | Registration result with artifact id/metadata or failure evidence. | Trust provider path/hash, update active pointer, decide workflow outcome. |
| Register failed/debug evidence | Sanitized temp file/payload, failure/refusal scope, safety/retention intent. | Official evidence artifact or registration failure. | Store secrets or create QualityIssue. |
| Validate artifact | Artifact id plus expected use. | Integrity report; may update objective storage state. | Decide rebuild/retry/warning/block. |
| Cleanup/trash | Scope, retention policy, active-reference evidence. | Cleanup/trash result. | Remove protected active artifacts or decide workflow readiness. |

Repository / DAO is the only SQLite writer. ArtifactService uses repository APIs for artifact metadata and storage state updates.

## 4. Artifact type vocabulary

| Artifact type | Required for MVP-0 | Typical retention | Notes |
| --- | --- | --- | --- |
| `original_image` | Yes | `permanent_original` | Never overwritten; required root input. |
| `mask_image` | Yes when materialized | `active_result` while active | Detection/cleaning mask. |
| `ocr_input_crop` | Yes when materialized | `cache_rebuildable` | Rebuildable from original plus geometry/config. |
| `provider_raw_request` | Policy-dependent | `failed_attempt_payload`, `successful_payload`, or `debug` | Must be sanitized before registration. |
| `provider_raw_response` | Failed/refused/invalid evidence when safe | `failed_attempt_payload` by default | Raw failed/refusal payload evidence. |
| `cleaned_image` | Yes when cleaning output accepted | `active_result` while active | Page-level cleaned output. |
| `typeset_image` | Yes when typesetting output accepted | `active_result` while active | Final page preview/export source. |
| `typeset_preview_image` | Yes when overflow preview produced | `failed_attempt_payload` or `successful_payload` | Kept separate so overflow preview is not mistaken for accepted output. |
| `export_output` | Export design | `export_output` | Export history, not workflow readiness source. |
| `issue_snapshot` | Optional | `successful_payload` or `debug` | Deferred unless export/reporting design needs it. |
| `debug_bundle` | Optional | `debug` | Opt-in diagnostics only. |

`temp`, `orphan`, `staging`, and `quarantine` are not official artifact types.

## 5. Storage state vocabulary

| State | Meaning | Usable as bytes |
| --- | --- | --- |
| `present` | File exists and hash validates. | Yes. |
| `metadata_only_cleaned` | Bytes intentionally removed by retention; metadata/provenance remains. | No. |
| `moved_to_trash` | File moved under Project trash by soft delete. | No, until restored and hash-valid. |
| `missing` | Expected file absent, inaccessible, or hash-invalid. | No. |
| `deleted` | Permanently removed by explicit delete or retention cleanup. | No. |

`orphan` is a recovery classification for files without committed artifact metadata, not a storage state.

## 6. Retention and safety vocabulary

Retention classes:

| Class | Default rule |
| --- | --- |
| `permanent_original` | Keep until explicit permanent Project/Page deletion. |
| `active_result` | Keep while referenced by active page/textblock/export pointers or required active masks. |
| `failed_attempt_payload` | Retain by default after sanitization. |
| `successful_payload` | Eligible for cleanup when committed results/artifacts explain recovery. |
| `debug` | Retain only when debug policy enables it. |
| `cache_rebuildable` | Eligible for cleanup after grace period if reconstructable from protected inputs. |
| `export_output` | Keep until export deletion or Project deletion. |
| `trash_pending_delete` | Moved/marked during soft delete before permanent purge. |

Safety flags:

```text
is_debug
may_contain_original_image
may_contain_ocr_text
may_contain_translation
may_contain_provider_response
contains_secret_redacted
```

Callers declare possible contents. ArtifactService may preserve or strengthen safety flags, never weaken them. If sanitization is uncertain, retain only sanitized metadata or reject raw payload registration.

## 7. Temp-to-official promotion rule

Promotion sequence:

1. StageExecutor receives a provider/local temp ref under the attempt temp root.
2. StageExecutor calls ArtifactService with scope, artifact intent, source stage, attempt/tool refs, retention intent, and safety flags.
3. ArtifactService validates:
   - path is inside the allowed attempt temp root;
   - path traversal and cross-project paths are rejected;
   - file exists and is readable;
   - file type/media expectations are safe enough for the requested artifact type;
   - provider did not choose an official workspace path.
4. ArtifactService copies/writes bytes into a Project-owned staging/final area chosen by ArtifactService.
5. ArtifactService computes hash, byte size, media/mime, and dimensions where relevant from actual bytes.
6. ArtifactService persists artifact metadata through Repository with `storage_state = present`.
7. ArtifactService returns artifact id and metadata.

Promotion results:

| Case | Result |
| --- | --- |
| File write/copy succeeds but metadata commit fails | File is orphan/non-official. Cleanup/quarantine may be attempted; recovery does not treat it as official. |
| Metadata commit succeeds but active pointer update does not | Artifact is official but unselected. It is not export-effective. |
| Quality later blocks output | Artifact remains audit evidence; active/export-effective acceptance is withheld unless WorkflowLoopEngine later accepts a valid path. |

## 8. Original image rule

Original import uses ArtifactService registration. The original image:

- is registered as `artifact_type = original_image`;
- uses `retention_class = permanent_original`;
- records hash, size, media, dimensions when available, and project-relative path;
- is selected by `Page.original_artifact_id` only after successful registration and workflow/import acceptance;
- is never overwritten by detection, OCR, cleaning, typesetting, or export.

If original bytes are missing or hash-invalid, ArtifactService marks the artifact `missing`; WorkflowLoopEngine must block or pause for user restore because the original is not rebuildable.

## 9. Missing artifact detection rule

ArtifactService validation returns an `ArtifactIntegrityReport`.

| Field | Meaning |
| --- | --- |
| `artifact_id` | Existing artifact metadata id. |
| `artifact_type` | Registered type. |
| `expected_use` | `preview`, `export_check`, `recovery`, `reuse_check`, `cleanup`, or `restore`. |
| `observed_state` | Current state after validation. |
| `integrity_status` | `valid`, `missing_path`, `hash_mismatch`, `metadata_only`, `trashed`, `deleted`, `inaccessible`, or `unknown_error`. |
| `expected_hash` / `observed_hash` | Expected and observed hash when computable. |
| `relative_path` | Project-relative path only. |
| `active_reference` | Caller/repository hint such as original, active cleaned, active typeset. |
| `rebuildability_hint` | `non_rebuildable`, `rebuildable_from_committed_inputs`, `retriable_provider_output`, `diagnostic_only`, `export_recreatable`, or `unknown`. |
| `evidence_summary` | Sanitized short summary. |

Missing path and hash mismatch both set `storage_state = missing`, preserving expected hash/path/provenance. The report keeps the exact integrity reason so debugging is not lost.

WorkflowLoopEngine decides rebuild, retry, warning, pause, or block. ArtifactService must not make that decision.

## 10. Registration failure evidence

Artifact registration failure is not provider failure unless the provider supplied an invalid temp ref. StageExecutor reports it as stage evidence:

```text
artifact_registration_failed
```

QualityCheckService may classify the failure as `issue_type = artifact_unavailable`. WorkflowLoopEngine decides retry, upstream retry, pause, or block.

## 11. Cleanup boundary

Cleanup may remove only bytes that are eligible under retention policy and safe at the moment of cleanup.

Before deleting bytes, cleanup must re-check:

- Project scope.
- Current active pointers.
- Retention class.
- Storage state.
- Open issues or attempts that require the artifact as failed/refusal evidence.
- Whether artifact is original, active mask, active cleaned image, active typeset image, export output, or retained failed-attempt payload.

Cleanup must not remove:

- original images except explicit permanent delete;
- active cleaned/typeset/mask artifacts;
- export outputs except export deletion/project deletion policy;
- retained failed/refusal/invalid-output evidence needed for audit;
- files outside the owning Project workspace.

Cleanup does not decide workflow readiness. If cleanup causes or discovers missing active bytes, ArtifactService reports storage state and WorkflowLoopEngine decides next action.

## 12. Recovery and orphan rule

Recovery trusts committed domain rows, active pointers, official artifacts, hashes, ToolRunLogs, WorkflowAttempts, QualityIssues, and WorkflowDecisions.

Files without artifact rows are orphan/non-official. MVP-0 may scan/report/quarantine orphan temp files, but must not promote them to active outputs unless the normal path is replayed:

```text
ArtifactService registration
-> QualityCheckService classification
-> WorkflowLoopEngine acceptance decision
-> Repository active pointer/status transaction
```

Parsing raw provider output into accepted results during recovery is deferred unless this full replay path is implemented.
