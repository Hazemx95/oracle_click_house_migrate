<!--
SYNC IMPACT REPORT
==================
Version change: (template / unversioned) → 1.0.0
Bump rationale: Initial ratification of a fully populated constitution from the
  template placeholders. MAJOR baseline established.

Modified principles:
  - [PRINCIPLE_1_NAME] → I. Oracle Source Is Read-Only (NON-NEGOTIABLE)
  - [PRINCIPLE_2_NAME] → II. ClickHouse Target Is Restricted (NON-NEGOTIABLE)
  - [PRINCIPLE_3_NAME] → III. Environment-Based Credentials & Configuration (NON-NEGOTIABLE)
  - [PRINCIPLE_4_NAME] → IV. Phase-Based Implementation
  - [PRINCIPLE_5_NAME] → V. Memory-Safe Large-Table Migration
  - (added) VI. Dynamic, Metadata-Driven GUI
  - (added) VII. Security & Safety First (NON-NEGOTIABLE)

Added sections:
  - Additional Constraints & Standards
  - Development Workflow & Quality Gates
  - Expanded Governance (amendment, versioning, compliance review)

Removed sections: none (all template placeholders resolved)

Templates requiring updates:
  - .specify/templates/plan-template.md ✅ aligned (Constitution Check gate is
    generic and now resolves against these 7 principles; no edit required)
  - .specify/templates/spec-template.md ✅ aligned (no mandatory section conflicts)
  - .specify/templates/tasks-template.md ✅ aligned (phase/safety task types covered)
  - .specify/templates/checklist-template.md ✅ aligned (no change needed)

Follow-up TODOs: none. RATIFICATION_DATE set to 2026-06-10 (initial project adoption).
-->

# Oracle to ClickHouse Parallel Data Migration Engine Constitution

This constitution defines mandatory, project-wide rules. **All future specifications,
plans, tasks, generated code, reviews, and implementation phases MUST comply with every
principle below.** Any artifact or change that conflicts with this document is invalid
until either the artifact is corrected or this constitution is formally amended.

## Core Principles

### I. Oracle Source Is Read-Only (NON-NEGOTIABLE)

The Oracle database is a strictly read-only source. The application MUST only ever issue
`SELECT` statements against Oracle (including metadata views and source tables).

The application MUST NEVER execute `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `INSERT`,
`UPDATE`, `DELETE`, `MERGE`, `EXEC`, or `CALL` against Oracle, and MUST NEVER modify any
Oracle schema, table, data, index, trigger, procedure, sequence, or job.

All Oracle access MUST flow through a single centralized read-only client that rejects any
statement whose effective operation is not a read. **Rationale**: The source is a shared,
production-adjacent system; a single accidental write could corrupt upstream data, so the
read-only guarantee is enforced in code, not merely by convention.

### II. ClickHouse Target Is Restricted (NON-NEGOTIABLE)

The application MUST write only to the ClickHouse database `oracle_migration_hazem`.

The application MUST NEVER create, modify, truncate, drop, or insert into any other
ClickHouse database. Inside `oracle_migration_hazem`, only `CREATE TABLE IF NOT EXISTS`,
`INSERT INTO`, and `SELECT` are permitted. Destructive rerun operations (`TRUNCATE TABLE`,
`DROP TABLE`) MUST NOT be implemented unless a future amendment or explicitly approved
requirement authorizes them, and even then only inside `oracle_migration_hazem`.

The target database name MUST be validated before any write; any value other than
`oracle_migration_hazem` MUST be rejected. **Rationale**: Confining all writes to one
database makes the blast radius of the tool auditable and reversible.

### III. Environment-Based Credentials & Configuration (NON-NEGOTIABLE)

All credentials and connection configuration MUST come from environment variables (loaded
from `.env` at runtime).

Real credentials MUST NEVER be hardcoded in source code, `Dockerfile`, `docker-compose.yml`,
`README`, `PLAN.md`, tests, or any other committed file. The real `.env` file MUST be
ignored by Git; only `.env.example` containing placeholder values MAY be committed.
**Rationale**: Secrets in version control are effectively permanent leaks; environment-only
configuration keeps credentials out of history and out of shared artifacts.

### IV. Phase-Based Implementation

The project MUST be implemented phase by phase, never as a single bundle.

Each phase MUST define: scope, files to create/update, acceptance criteria, manual test
commands, and a clear stop point. Implementation MUST NOT advance to the next phase until
the current phase's acceptance criteria pass and the stop point is satisfied. **Rationale**:
Incremental, independently verifiable slices keep the migration engine safe to build and
easy to validate against the safety principles at every step.

### V. Memory-Safe Large-Table Migration

Migration MUST be memory-safe and MUST scale to large tables.

The application MUST NEVER load a full Oracle table into memory (e.g.,
`pandas.read_sql("SELECT * FROM huge_table")` is forbidden). It MUST extract using cursor
`fetchmany(batch_size)` or equivalent chunking and load using ClickHouse batch inserts.
Parallel migration MUST NOT be introduced until single-thread batch migration is working
and verified. When parallel migration is added, worker count MUST be configurable with a
safe maximum (default 8, maximum 16), and numeric/date range partitioning MUST produce no
duplicate or missing rows. **Rationale**: Bounded memory use and proven single-thread
correctness are prerequisites for trustworthy high-volume migration.

### VI. Dynamic, Metadata-Driven GUI

GUI behavior MUST be dynamic and driven by live database metadata.

Oracle schemas MUST be loaded from Oracle metadata; the table list MUST refresh
automatically when the source schema changes; the target schema MUST auto-fill from the
selected source schema; and the ClickHouse database field MUST be fixed and non-editable as
`oracle_migration_hazem`. **Rationale**: Metadata-driven selection prevents stale or invalid
choices and keeps the user within the safe, supported migration paths.

### VII. Security & Safety First (NON-NEGOTIABLE)

Security and safety take precedence over convenience and features.

The application MUST NOT log passwords or other secrets. Schema, table, and column names
MUST be validated against database metadata before use. Unsafe user input MUST NEVER be
concatenated directly into SQL; bind variables MUST be used for parameterized Oracle queries
where applicable. Errors surfaced to users and logs MUST be clear yet free of credentials.
**Rationale**: A migration tool sits between two sensitive systems; injection and secret
leakage are the highest-impact failure modes and must be designed out.

## Additional Constraints & Standards

- **Stack**: Python web application using FastAPI/uvicorn, served at the configured host
  and port (default `0.0.0.0:8000`), deployable via `docker compose up -d --build`.
- **Fixed target**: ClickHouse database is always `oracle_migration_hazem`. Target table
  naming MUST use `<schema>__<table>` to avoid collisions within the single database.
- **Defaults**: Batch size and worker defaults come from environment
  (`MIGRATION_BATCH_SIZE`, `MIGRATION_DEFAULT_WORKERS`); the target database is never
  auto-created unless explicitly enabled (`CLICKHOUSE_ALLOW_CREATE_DATABASE=false` by
  default).
- **Job lifecycle**: Migrations run as background jobs that return a job id immediately and
  expose pollable status (`PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`).
- **Validation**: Post-migration row-count reconciliation MUST be available and MUST NOT
  modify Oracle.

## Development Workflow & Quality Gates

- **Constitution Check**: Every `/speckit-plan` MUST evaluate its design against these
  principles before and after design. Violations MUST be resolved or explicitly justified in
  the plan's Complexity Tracking; an unjustified violation blocks the plan.
- **Per-phase gates**: A phase is "done" only when its acceptance criteria and manual test
  commands pass and the four NON-NEGOTIABLE principles (I, II, III, VII) hold.
- **Review focus**: Reviews MUST explicitly confirm: no non-SELECT Oracle statements; no
  writes outside `oracle_migration_hazem`; no hardcoded secrets; no secret logging; bind
  variables and metadata validation in place; memory-safe extraction.
- **Secret scanning**: Before commit, contributors MUST verify `.env` is ignored and that
  no real credentials appear in code, Docker files, docs, or tests.

## Governance

This constitution supersedes other practices and conventions within the project. When any
plan, task, spec, or code conflicts with it, this document wins.

- **Amendments**: Changes MUST be proposed as an edit to this file with a clear rationale,
  reviewed and approved by the project owner, and accompanied by a Sync Impact Report and
  updates to any dependent templates/docs.
- **Versioning policy** (semantic):
  - **MAJOR**: Backward-incompatible governance changes or removal/redefinition of a
    principle.
  - **MINOR**: A new principle/section is added or existing guidance is materially expanded.
  - **PATCH**: Clarifications, wording, or non-semantic refinements.
- **Compliance review**: Compliance is checked at every phase stop point and at every plan
  Constitution Check. The NON-NEGOTIABLE principles (I, II, III, VII) admit no exceptions;
  they cannot be waived via Complexity Tracking.

**Version**: 1.0.0 | **Ratified**: 2026-06-10 | **Last Amended**: 2026-06-10
