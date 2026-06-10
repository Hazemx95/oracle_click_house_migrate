<!--
Sync Impact Report
Version change: none -> 1.0.0
Modified principles: initial adoption of seven project principles
Added sections: Core Principles; Operational Constraints; Phase Workflow; Governance
Removed sections: none
Templates requiring updates: no changes required; generated plan/spec/tasks already align
Follow-up TODOs: none
-->

# Oracle to ClickHouse Migration Engine Constitution

## Core Principles

### I. Oracle Read-Only (NON-NEGOTIABLE)
Oracle is a source system only. The application MUST issue only read statements
against Oracle, limited to `SELECT` or read-only `WITH` queries. It MUST NOT
create, alter, drop, truncate, insert, update, delete, merge, execute procedures,
call jobs, or otherwise modify any Oracle schema, table, data, trigger,
procedure, or job.

### II. ClickHouse Target Restricted (NON-NEGOTIABLE)
All ClickHouse writes MUST target exactly `oracle_migration_hazem`. Operations
targeting any other ClickHouse database MUST be rejected before execution. The
only allowed target operations in the normal migration flow are
`CREATE TABLE IF NOT EXISTS`, `INSERT INTO`, and `SELECT`. Destructive rerun
operations such as `TRUNCATE TABLE` or `DROP TABLE` MUST NOT be implemented
unless explicitly approved in a later phase and still confined to the target
database.

### III. Environment-Based Credentials (NON-NEGOTIABLE)
All configuration and credentials MUST come from environment variables. Real
credentials MUST NOT be hardcoded in source code, Dockerfile, Docker Compose,
README, PLAN.md, tests, generated docs, or any committed file. The repository may
include only placeholder examples such as `.env.example`; the real `.env` MUST
remain ignored by Git and excluded from Docker build context.

### IV. Phase-Based Implementation
Implementation MUST proceed one phase at a time. A later phase MUST NOT begin
until the current phase has documented scope, completed acceptance criteria,
manual test commands, and an explicit stop point. Each phase MUST preserve all
non-negotiable guardrails from this constitution.

### V. Memory-Safe Large-Table Migration
Any phase that copies Oracle data MUST use bounded batch extraction and batch
loading. The application MUST NOT load a full Oracle table into memory. Parallel
migration MUST be introduced only after the single-thread batch path is proven,
and worker ranges MUST avoid duplicate or missing rows.

### VI. Dynamic Metadata-Driven GUI
The GUI MUST use Oracle metadata to populate schemas, tables, and candidate
columns dynamically. The ClickHouse database field MUST be fixed and non-editable
as `oracle_migration_hazem`. The GUI MUST NOT hardcode source schemas or tables.

### VII. Security And Safety First (NON-NEGOTIABLE)
The application MUST avoid secret leakage in responses, logs, docs, and errors.
Schema, table, and column names MUST be validated against metadata before use.
Oracle parameter values MUST use bind variables. Raw user input MUST NOT be
concatenated into SQL.

## Operational Constraints

- Runtime platform: Python FastAPI web application, run locally or through Docker Compose.
- Oracle source access is read-only and metadata-driven.
- ClickHouse target database is fixed to `oracle_migration_hazem`.
- Configuration is environment-only; `.env.example` contains placeholders only.
- The real `.env` and local artifacts MUST be ignored by Git and Docker context.
- Application source files MUST NOT be created during Phase 0.

## Phase Workflow

Every future phase MUST define and satisfy:

- Scope and explicit non-scope.
- Files to create or update.
- Acceptance criteria.
- Manual test commands.
- Constitution gate checks.
- Stop point before any later phase begins.

## Governance

This constitution supersedes conflicting project practices. Amendments require a
documented rationale, an updated version, and a review of generated specs, plans,
tasks, and guardrail documents. Versioning follows semantic versioning: MAJOR for
incompatible governance changes, MINOR for new principles or expanded mandatory
guidance, and PATCH for clarifications. Every implementation review MUST verify
compliance with the non-negotiable principles.

**Version**: 1.0.0 | **Ratified**: 2026-06-10 | **Last Amended**: 2026-06-10
