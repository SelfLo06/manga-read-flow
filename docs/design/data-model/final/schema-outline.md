# Schema Outline v0.1

This outline is implementation-ready design guidance. It is not SQL DDL and intentionally contains no table-creation statements.

## app.db

### projects

Field groups:

- Identity: `project_id`, `name`.
- Location: `workspace_project_path`, `project_db_path`.
- Defaults: `default_source_language`, `default_target_language`, `default_processing_profile_id`.
- Lifecycle: `status`, `deleted_at`, `trash_path`, `permanent_delete_after`.
- Timestamps: `created_at`, `updated_at`, `last_opened_at`, `last_processed_at`.

Indexes and uniqueness:

- Unique `project_id`.
- Unique active normalized `workspace_project_path`.
- Index `status, updated_at`.
- Index `deleted_at`.

Notes:

- Names do not need global uniqueness.
- `project_db_path` is used to open the Project's project.db, then ProjectMetadata must be verified.

### provider_configs

Field groups:

- Identity: `provider_config_id`, `provider_name`, `provider_type`.
- Capability: `capabilities_json`, `default_model_id`, `license_note`, `is_local`, `requires_gpu`.
- Secret reference: `secret_ref`.
- Lifecycle: `enabled`, timestamps.

Indexes and uniqueness:

- Unique `provider_config_id`.
- Index `provider_type, enabled`.

Notes:

- Do not store raw API keys here as project data.
- Do not copy secrets into project.db snapshots, logs, or artifacts.

### processing_profiles

Field groups:

- Identity: `profile_id`, `name`, `version`, `scope`, `is_builtin`.
- Policy: provider refs, retry budgets, quality strictness, fallback policy, warning export policy, auto-skip policy.
- Retention: failed payload, successful payload, debug artifact policy.
- Lifecycle: `disabled_at`, timestamps.

Indexes and uniqueness:

- Unique `profile_id`.
- Unique active `scope, name`.
- Index `is_builtin, name`.

Notes:

- These rows are mutable templates.
- Historical runs use project-local `processing_profile_snapshots`.

### global_settings

Field groups:

- `setting_key`, `setting_value`, `setting_schema_version`, timestamps.

Notes:

- Non-secret settings only.

### schema_migrations

Field groups:

- `migration_id`, `applied_at`, `checksum`, `description`.

## project.db

### project_metadata

Field groups:

- `project_id`, `project_schema_version`, `workspace_identity`, `created_at`, `last_opened_at`.

Notes:

- Must match app.db Project registry before Project data is used.

### batches

Field groups:

- Identity: `batch_id`, `project_id`, `name`.
- Languages: `source_language`, `target_language`.
- Progress: `page_count`, `status`, `quality_summary_json`, `last_processed_at`.
- Lifecycle: `deleted_at`, timestamps.

Indexes and uniqueness:

- Unique `batch_id`.
- Optional unique active `project_id, name`.
- Index `project_id, status`.
- Index `project_id, deleted_at`.

### pages

Field groups:

- Identity/order: `page_id`, `project_id`, `batch_id`, `page_index`, `original_filename`.
- Artifact pointers: `original_artifact_id`, `active_cleaned_artifact_id`, `active_typeset_artifact_id`.
- State: `status`, `quality_flags_json`, `translation_context_hash`, `translation_context_stale`, `has_stale_blocks`.
- Lifecycle: `deleted_at`, timestamps.

Indexes and uniqueness:

- Unique `page_id`.
- Unique active `batch_id, page_index`.
- Index `batch_id, status`.
- Index `project_id, status`.

Notes:

- Do not store authoritative image paths here. Store artifact IDs.

### text_blocks

Field groups:

- Identity/order: `text_block_id`, `project_id`, `batch_id`, `page_id`, `reading_order`.
- Geometry: `bbox_x`, `bbox_y`, `bbox_width`, `bbox_height`, `polygon_json`, `geometry_revision`, `geometry_hash`, `source_direction`.
- Detection: `detection_provider`, `detection_model_id`, `detection_confidence`, `detection_quality_flags_json`.
- Active pointers: `active_mask_artifact_id`, `active_ocr_result_id`, `active_translation_result_id`, `locked_translation_result_id`.
- Stage statuses: `detection_status`, `ocr_status`, `translation_status`, `translation_check_status`, `cleaning_status`, `typesetting_status`, `review_status`.
- Flags: `is_skipped`, `skip_reason`, `is_manual_adjusted`.
- Lifecycle: `deleted_at`, timestamps.

Indexes and uniqueness:

- Unique `text_block_id`.
- Unique active `page_id, reading_order` when reading_order is assigned.
- Index `page_id, is_skipped`.
- Index `page_id` plus each stage status used by recovery.
- Index active result pointers.

Notes:

- P0 geometry lives here. `GeometryRevision` is P1.
- Active result pointers are the source of truth. No independent active flags on result tables.

### ocr_results

Field groups:

- Identity/version: `ocr_result_id`, `project_id`, `text_block_id`, `version_number`, `parent_ocr_result_id`.
- Content: `source_text`, `source_text_hash`.
- Quality: `ocr_confidence`, `ocr_quality_flag`, `quality_flags_json`.
- Provider/provenance: `provider`, `model_id`, `tool_version`, `workflow_attempt_id`, `tool_run_id`, `source_type`, `is_user_edited`.
- Artifacts/cache: `input_artifact_id`, `raw_output_artifact_id`, `input_hash`, `config_hash`, `geometry_hash`.
- Timestamps: `created_at`.

Indexes and uniqueness:

- Unique `ocr_result_id`.
- Unique `text_block_id, version_number`.
- Index `text_block_id, created_at`.
- Index `source_text_hash`.
- Cache lookup index on `text_block_id, input_hash, config_hash, provider, model_id, tool_version`.

Notes:

- Immutable semantic content.
- Invalid provider output may not create OCRResult.

### translation_results

Field groups:

- Identity/version: `translation_result_id`, `project_id`, `text_block_id`, `version_number`, `parent_translation_result_id`.
- Source: `source_ocr_result_id`, `source_text_hash`.
- Content: `translation_text`, `translation_text_hash`, `used_terms_json`.
- Provider/prompt: `provider`, `model_id`, `prompt_template_version`, `generation_config_hash`.
- Context/glossary: `glossary_version_id`, `glossary_version_number`, `glossary_terms_hash`, `context_hash`, `page_translation_group_key`.
- Quality: `confidence`, `needs_review`, `quality_flags_json`, `error_code`.
- Provenance: `workflow_attempt_id`, `tool_run_id`, `source_type`, `is_user_edited`.
- Timestamps: `created_at`.

Indexes and uniqueness:

- Unique `translation_result_id`.
- Unique `text_block_id, version_number`.
- Index `source_ocr_result_id`.
- Index `glossary_version_id`.
- Cache lookup index on `source_text_hash, context_hash, glossary_version_id, provider, model_id, prompt_template_version, generation_config_hash`.

Notes:

- Must link to `source_ocr_result_id` and `source_text_hash`.
- Page-level translation creates one attempt/log and per-block result rows for valid outputs.

### glossary_terms

Field groups:

- Identity/content: `term_id`, `project_id`, `source_text`, `target_text`, `term_type`, `reading`, `aliases_json`.
- Behavior: `case_sensitive`, `priority`, `status`.
- Provenance: `created_from_text_block_id`, `created_by_user`, `note`.
- Lifecycle: `deleted_at`, timestamps.

Indexes and uniqueness:

- Unique `term_id`.
- Index `project_id, source_text, status`.
- Optional uniqueness for active normalized `project_id, source_text, target_text, term_type`.

### glossary_versions

Field groups:

- Identity/version: `glossary_version_id`, `project_id`, `version_number`.
- Snapshot identity: `terms_hash`, `term_count`, optional `snapshot_artifact_id`.
- Reason: `created_reason`, `created_at`.

Indexes and uniqueness:

- Unique `glossary_version_id`.
- Unique `project_id, version_number`.
- Optional unique `project_id, terms_hash` for no-op version reuse.

### processing_profile_snapshots

Field groups:

- Identity: `profile_snapshot_id`, `project_id`.
- Source: `source_profile_id`, `source_profile_version`, `name`.
- Snapshot: `snapshot_schema_version`, `settings_json`, `settings_hash`.
- Timestamp: `created_at`.

Indexes and uniqueness:

- Unique `profile_snapshot_id`.
- Index `project_id, settings_hash`.

Notes:

- Immutable.
- Contains provider references and sanitized identity, not raw secrets.

### processing_tasks

Field groups:

- Identity: `task_id`, `project_id`.
- Target: `target_type`, `target_id`, common `batch_id`, `page_id`, `text_block_id`.
- Intent: `task_type`, `requested_stages`, `resume_policy`, `requested_by`.
- Policy: `profile_snapshot_id`, `idempotency_key`.
- State: `status`, `current_stage`, `progress_json`, `last_workflow_decision_id`, `last_attempt_id`.
- Control: `pause_requested_at`, `cancel_requested_at`.
- Recovery: `heartbeat_at`, `started_at`, `finished_at`, timestamps.

Indexes and uniqueness:

- Unique `task_id`.
- Unique active `idempotency_key` where duplicate suppression is required.
- Index `project_id, status, heartbeat_at`.
- Index `target_type, target_id, status`.

### workflow_attempts

Field groups:

- Identity/order: `attempt_id`, `project_id`, `task_id`, `stage`, `target_type`, `target_id`, `attempt_number`.
- Scope: common `batch_id`, `page_id`, `text_block_id`.
- Provider: `provider_name`, `provider_version`, `model_id`, `tool_version`.
- Inputs: `input_hash`, `config_hash`, `context_hash`, `profile_snapshot_id`, `profile_hash`.
- Outcome: `status`, `error_code`, `error_class`, `sanitized_error_message`.
- Retry: `retry_budget_before`, `retry_budget_after`.
- Artifacts: `input_artifact_id`, `output_artifact_id`, `raw_request_artifact_id`, `raw_response_artifact_id`.
- Timing: `started_at`, `finished_at`.

Indexes and uniqueness:

- Unique `attempt_id`.
- Unique `task_id, stage, target_type, target_id, attempt_number`.
- Index `task_id, stage, status`.
- Index `target_type, target_id, stage, status`.

### workflow_decisions

Field groups:

- Identity: `decision_id`, `project_id`, `task_id`, optional `attempt_id`.
- Target/scope: `stage`, `target_type`, `target_id`, common `batch_id`, `page_id`, `text_block_id`.
- Decision: `decision_type`, `reason_code`, `rationale_summary`, `next_stage`, `fallback_provider`.
- Retry/profile: `retry_budget_before`, `retry_budget_after`, `profile_snapshot_id`.
- Timestamp: `created_at`.

Indexes and uniqueness:

- Unique `decision_id`.
- Index `task_id, created_at`.
- Index `attempt_id`.
- Index `target_type, target_id, stage`.

### workflow_decision_issues

Field groups:

- `decision_id`, `quality_issue_id`, `relation_type`, `created_at`.

Indexes and uniqueness:

- Unique `decision_id, quality_issue_id, relation_type`.
- Index `quality_issue_id`.

Notes:

- This relation is preferred over a JSON list as the source of truth.

### quality_issues

Field groups:

- Identity/scope: `quality_issue_id`, `project_id`, common `batch_id`, `page_id`, `text_block_id`.
- Target: `target_type`, `target_id`.
- Classification: `discovered_stage`, `root_stage`, `issue_type`, `error_code`.
- Gate: `severity`, `is_blocking`, `status`.
- Message: `message_key`, `sanitized_message`, `suggested_action`.
- Provenance: `workflow_attempt_id`, `workflow_decision_id`, `tool_run_id`, `artifact_id`, `applies_to_result_id`.
- Stale/dedupe: `input_hash`, `config_hash`, `superseded_by_issue_id`.
- Resolution: `resolved_at`, `resolved_by`, `resolution_reason`.
- Timestamps: `created_at`, `updated_at`.

Indexes and uniqueness:

- Unique `quality_issue_id`.
- Index `project_id, is_blocking, status`.
- Index `batch_id, is_blocking, status`.
- Index `page_id, is_blocking, status`.
- Index `text_block_id, status`.
- Optional dedupe index on `target_type, target_id, issue_type, root_stage, discovered_stage, status`.

### processing_artifacts

Field groups:

- Identity/scope: `artifact_id`, `project_id`, common `batch_id`, `page_id`, `text_block_id`.
- Owner: `owner_type`, `owner_id`.
- Classification: `artifact_type`, `source_stage`, `media_type`.
- Location/integrity: `relative_path`, `file_hash`, `hash_algorithm`, `byte_size`, `mime_type`, `width`, `height`.
- Provenance: `workflow_attempt_id`, `tool_run_id`, `source_artifact_id`.
- Retention: `retention_class`, `storage_state`, `cleanup_eligible_at`, `cleaned_at`, `deleted_at`.
- Safety: `is_debug`, `may_contain_original_image`, `may_contain_ocr_text`, `may_contain_translation`, `may_contain_provider_response`, `contains_secret_redacted`.
- Timestamps: `created_at`, `updated_at`.

Indexes and uniqueness:

- Unique `artifact_id`.
- Unique active `project_id, relative_path` while storage state is `present` or `moved_to_trash`.
- Index `project_id, artifact_type`.
- Index `owner_type, owner_id, artifact_type`.
- Index `page_id, artifact_type`.
- Index `text_block_id, artifact_type`.
- Index `file_hash, artifact_type`.
- Index `project_id, retention_class, storage_state, cleanup_eligible_at`.

Notes:

- Storage states: `present`, `metadata_only_cleaned`, `moved_to_trash`, `missing`, `deleted`.
- Domain rows use artifact IDs, not paths.

### tool_run_logs

Field groups:

- Identity/scope: `tool_run_id`, `project_id`, `task_id`, `attempt_id`, common `batch_id`, `page_id`, `text_block_id`.
- Tool: `stage`, `tool_name`, `tool_version`, `provider_name`, `model_id`.
- Inputs/artifacts: `input_hash`, `config_hash`, `input_artifact_id`, `output_artifact_id`, `raw_request_artifact_id`, `raw_response_artifact_id`.
- Outcome: `status`, `error_code`, `error_class`, `is_provider_refusal`, `sanitized_error_message`, `user_message`.
- Usage/timing: optional token/cost fields, `started_at`, `finished_at`, `duration_ms`.
- Safety: `sanitization_version`.

Indexes and uniqueness:

- Unique `tool_run_id`.
- Index `attempt_id`.
- Index `project_id, stage, status, started_at`.
- Index common scope fields for trace UI.

Notes:

- No secrets.
- Raw payload bytes, if retained, are ProcessingArtifacts.

### export_records

Field groups:

- Identity/scope: `export_id`, `project_id`, `target_type`, `target_id`, common `batch_id`, `page_id`.
- Request: `export_type`, `format`, `requested_by`, `profile_snapshot_id`, `profile_hash`.
- Precheck: `precheck_status`, `blocking_issue_count`, `warning_issue_count`, `issue_snapshot_hash`, `issue_snapshot_artifact_id`.
- Outcome: `status`, `allowed_with_warnings`, `rejected_reason`, `error_code`.
- Artifacts: `output_artifact_id`, `manifest_artifact_id`.
- Timestamps: `requested_at`, `started_at`, `finished_at`.

Indexes and uniqueness:

- Unique `export_id`.
- Index `project_id, target_type, target_id, created_at`.
- Index `batch_id, created_at`.
- Index `page_id, created_at`.
- Index `status`.

Notes:

- Blocked exports are retained for explainability and may have no output artifact.

### schema_migrations

Field groups:

- `migration_id`, `applied_at`, `checksum`, `description`.
