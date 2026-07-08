# MVP-0 FakeProvider Single-Page Backend Slice

This directory contains the implementation planning package for Goal 4.

Scope:

* Plan the minimal backend implementation slices for one Project, one Batch, one Page, and deterministic FakeProvider workflow.
* Use real temporary SQLite files and filesystem artifacts.
* Prove persistence, workflow, artifact, issue, decision, recovery, and idempotency boundaries before real provider integration.
* Stop at `ready_for_export`.

Out of scope:

* Production implementation in this planning step.
* Full Web UI.
* FastAPI route design.
* Real OCR, translation, cleaning, or typesetting provider integration.
* Real translation prompt templates.
* Actual export output, ZIP, manifest, and ExportRecord implementation.
* Batch-scale workflow.
* P1/P2 features.

This package should produce implementation-ready slices, validation commands, file boundaries, commit strategy, and Codex task prompts.