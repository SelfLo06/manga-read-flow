# ADR 0003: Artifact Metadata Lifecycle

## Status

Accepted.

## Context

The workflow creates original images, masks, crops, raw tool payloads, cleaned images, typeset images, exports, and debug artifacts. Image BLOBs must not enter SQLite, and original images must never be overwritten.

## Decision

Use `ProcessingArtifact` as the metadata source of truth for filesystem artifacts. Store project-relative path, hash, type, ownership scope, retention class, safety/debug flags, and storage state.

Storage states are:

- `present`
- `metadata_only_cleaned`
- `moved_to_trash`
- `missing`
- `deleted`

## Rationale

Central artifact metadata lets ArtifactService enforce path safety, hashing, retention, cleanup, trash/restore, and missing-file repair without scattering file paths across domain rows.

## Rejected alternatives

- Store image BLOBs in SQLite: violates invariant and hurts local file workflows.
- Store direct authoritative paths on Page/Result rows: weak retention and provenance.
- Let providers choose final artifact paths: violates architecture boundaries.

## Consequences

- Domain rows store artifact ids for active inputs/outputs.
- Cleanup can remove successful raw payload bytes while retaining metadata.
- Failed attempt artifacts are retained by default.

## Validation

Supports original immutability, failed LLM payload retention, successful payload cleanup, soft delete/trash, and export output traceability.
