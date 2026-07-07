# ADR 0005: FakeProvider Deterministic Modes and Artifact Boundary

## Status

Accepted.

## Context

The next milestone must validate execution contracts without real OCR, LLM, cleaning, or typesetting tools. A fake path that bypasses ProviderResult, ArtifactService, QualityCheckService, or WorkflowLoopEngine would not prove the architecture.

## Decision

FakeProvider must implement the same Provider Adapter contract as real providers. Fake modes are deterministic and durable/test-visible through profile snapshot or task test config copied into sanitized attempt/tool metadata.

File-producing fake stages write temp files only. ArtifactService must promote all official artifacts. Missing active artifact is a harness/ArtifactService setup, not a provider mode that mutates official files.

Required fake modes include happy path, OCR fail once, OCR empty, invalid translation JSON, translation refusal, partial translation, provider unavailable, cleaning skip, typesetting overflow, temp artifact missing before promotion, and missing active artifact setup.

## Consequences

- Retry, refusal, invalid output, partial output, skip, overflow, and missing artifact paths are testable without real tools.
- Fake tests remain deterministic and replayable after crash/retry.
- Artifact promotion and integrity checks are validated for real.

## Rejected alternatives

| Alternative | Reason rejected |
| --- | --- |
| FakeProvider writes official artifacts or DB rows. | Bypasses the boundaries under test. |
| Random fake failures. | Makes retry/recovery tests flaky. |
| Hidden global fake modes only. | Not durable enough for audit/recovery. |
| Real provider integrations for Goal 2. | Hides contract defects and expands scope. |
