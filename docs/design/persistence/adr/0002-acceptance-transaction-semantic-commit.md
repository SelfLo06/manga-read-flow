# ADR 0002: Acceptance Transaction as Semantic Commit Point

Status: Accepted

## Context

Stage execution produces provider outputs, tool logs, artifacts, quality findings, and workflow decisions. Registered artifacts may exist before the workflow decides whether they should become current output. Crashes can occur between provider call, artifact registration, and active pointer update.

## Decision

Workflow acceptance is the semantic commit point.

The acceptance transaction must commit accepted result rows or selected artifact pointers, active pointer updates, QualityIssue lifecycle changes, WorkflowDecision, WorkflowDecisionIssue links, retry budget after, task progress, and stage statuses together.

Provider calls happen outside SQLite write transactions. Artifact registration may commit separately, but registered artifacts remain unselected evidence until acceptance.

Acceptance must guard expected active pointer ids, relevant dependency hashes, and stage statuses.

## Rationale

This prevents partial current-state drift. It also gives recovery a clear rule: committed acceptance is current state; unaccepted official artifacts are evidence/reuse candidates only.

## Rejected Alternatives

- One long transaction around provider calls.
- Artifact registration automatically updating active pointers.
- Selecting newest result/artifact by timestamp.
- Persisting provider output as current before quality/workflow acceptance.

## Consequences

- Acceptance operations are more complex than CRUD.
- Concurrency conflicts must abort and reload evidence.
- Crash recovery can be conservative and explainable.
