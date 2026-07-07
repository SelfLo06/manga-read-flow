# ADR 0004: Recovery Uses Committed Results First

## Status

Accepted for workflow-state v0.1.

## Context

Recovery could try to parse retained raw provider output after a crash, but doing so risks bypassing normal validation, artifact registration, active pointer selection, and QualityIssue creation.

## Decision

MVP recovery reuses committed result rows, active pointers, official artifacts, and matching dependency hashes first.

Raw provider output or orphan files are not promoted to accepted results by default. They may be used only if replayed through the normal validation, ArtifactService registration, QualityCheckService classification, WorkflowLoopEngine decision, and atomic acceptance path.

## Consequences

Recovery is conservative and easier to test. Some crashes may require retry even when raw output exists, but accepted workflow state remains explainable and safe.
