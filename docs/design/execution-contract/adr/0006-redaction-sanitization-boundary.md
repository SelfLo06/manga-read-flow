# ADR 0006: Redaction and Sanitization Boundary

## Status

Accepted.

## Context

Provider errors, raw requests/responses, debug summaries, ToolRunLogs, QualityIssues, and WorkflowDecisions can contain OCR text, translations, original-image references, provider responses, and potentially secrets. The system must not store API keys, tokens, credentials, or secret headers in project.db, logs, artifacts, issues, or decisions.

## Decision

A central sanitization step is required before any provider payload, provider error, diagnostic summary, message param, ToolRunLog, QualityIssue draft, WorkflowDecision rationale, or debug artifact is persisted.

Boundary rules:

- ProviderConfig and snapshots may carry `secret_ref` only, never raw secrets.
- StageExecutor invokes sanitization before ToolRunLog and before requesting retained raw payload artifact registration.
- ArtifactService treats sanitization as a precondition for raw/debug payload registration and may reject uncertain payloads.
- QualityCheckService uses sanitized evidence only.
- User-facing refusal messages must not include bypass, jailbreak, prompt rewrite, obfuscation, or policy evasion guidance.

Exact helper/module name and API are deferred to config/security design.

## Consequences

- Failed/refusal evidence can be retained by default without normalizing secret leakage.
- Debug artifacts remain sensitive but bounded by safety flags and retention policy.
- Provider refusal remains explainable without exposing raw provider internals or unsafe guidance.

## Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| Let each provider adapter invent redaction behavior. | Inconsistent and hard to test. |
| Retain raw failed payloads without sanitization. | Secret/privacy risk. |
| Store raw provider refusal text as user message. | May expose sensitive or unsafe provider text. |
| Hash secret-looking values into user-visible text. | Still leaks stable secret fingerprints and is unnecessary. |
