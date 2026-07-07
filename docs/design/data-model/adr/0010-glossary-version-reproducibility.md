# ADR 0010: GlossaryVersion Reproducibility

## Status

Accepted.

## Context

Translation quality depends on Project glossary state. Glossary terms can change after translations are generated.

## Decision

Every semantic glossary change creates a `GlossaryVersion` with version number and terms hash. Every `TranslationResult` records `glossary_version_id`, `glossary_version_number`, and `glossary_terms_hash`. Optional `snapshot_artifact_id` can store a full snapshot for strict/debug reproducibility.

## Rationale

Version/hash is the minimum P0 provenance needed for stale checks and cache keys. Full snapshots are useful but may be retained by policy instead of required for every MVP run.

## Rejected alternatives

- Store only current glossary terms: old translations become inexplicable.
- Require full snapshot for every version in all profiles: more storage and migration cost than MVP requires.
- Global shared glossary by default: violates Project isolation.

## Consequences

- Old TranslationResults keep old glossary version after edits.
- Glossary edits can mark affected translations stale by policy.
- Strict/debug profiles may retain snapshot artifacts.

## Validation

Supports glossary edit after translation, translation cache keys, old result provenance, and project-local glossary isolation.
