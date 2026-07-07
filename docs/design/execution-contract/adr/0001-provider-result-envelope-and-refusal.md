# ADR 0001: ProviderResult Envelope and First-Class Refusal

## Status

Accepted.

## Context

Provider Adapters must call tools and return structured evidence without accessing SQLite, registering official artifacts, creating QualityIssues, or deciding retry/fallback/skip/warning/block. The proposal set used several envelope shapes and sometimes mixed generic error classes with stage-specific codes.

Provider refusal must not collapse into generic failure because the system must not retry with policy-evasion behavior.

## Decision

Use one canonical `ProviderResult` envelope:

```text
outcome = success | partial_success | failure | refusal | invalid_output
```

Nest standardized error fields under `ProviderResult.error`:

- `kind`;
- stage-specific `code`;
- `is_provider_refusal`;
- optional advisory `retry_hint`;
- sanitized message;
- safe provider error ref;
- optional raw temp ref after sanitization.

Provider refusal uses `outcome = refusal`, `kind = provider_refusal`, and `is_provider_refusal = true`. QualityCheckService classifies it as `issue_type = provider_refusal` with `root_stage = provider_policy`.

## Consequences

- StageExecutor can normalize all provider results through one path.
- QualityCheckService receives enough refusal evidence without provider-created issues.
- WorkflowLoopEngine can decide fallback/manual/warning/skip/pause/block from explicit refusal evidence.
- Same-provider retry after refusal cannot be implemented as a hidden provider behavior.

## Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| Separate unrelated envelopes per provider type. | Makes StageExecutor branching and failure handling inconsistent. |
| Error-only envelope with `ok = false` as the main shape. | Does not handle partial success and success/refusal symmetry cleanly. |
| Treat refusal as generic `failure`. | Loses compliance semantics and risks evasion-like retries. |
| Provider returns `should_retry` or `should_fallback`. | Violates WorkflowLoopEngine ownership. |
