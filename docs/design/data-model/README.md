# Data Model Detailed Design

This directory contains the Data Model Detailed Design package.

Scope:
- Project / Batch / Page / TextBlock ownership model
- app.db / project.db data split
- OCR and translation result versioning
- Active pointer rules
- Artifact metadata and retention boundaries
- WorkflowAttempt, WorkflowDecision, ToolRunLog, and QualityIssue persistence needs
- ProcessingProfileSnapshot and export gate data support
- Soft delete / trash behavior and restart recovery data support

Primary final outputs:
- `final/data-model-dd-v0.1.md`
- `final/schema-outline.md`
- `final/state-data-impact.md`
- `final/erd.mmd`
- `final/open-questions.md`
- ADRs under `adr/`

This is a design-documentation package only.

No production code, SQL DDL, SQLAlchemy models, migrations, FastAPI routes, frontend implementation, real provider integrations, or real translation prompt templates belong here.
