# Workflow State / Workflow Loop Detailed Design

This directory contains the Goal 1 design package for Workflow-State Core Design.

This design package defines how the MVP workflow progresses across stages, how retry/fallback/skip/warning/block decisions are made, how stale state propagates, and how recovery is performed after interruption or crash.

This is a design-only package. It must not include implementation code, SQL DDL, ORM mappings, API routes, UI components, or real Provider integration.