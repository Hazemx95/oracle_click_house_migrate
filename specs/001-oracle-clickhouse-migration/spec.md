# Feature Specification: Oracle to ClickHouse Parallel Data Migration Engine

**Feature Branch**: `001-oracle-clickhouse-migration`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Read PLAN.md and create a complete product specification for the project: Oracle to ClickHouse Parallel Data Migration Engine. Phase-based, with a Phase 0 for guardrails. Oracle read-only, ClickHouse writes restricted to oracle_migration_hazem, credentials from environment only, GUI dynamic schema/table discovery and batch migration."

## Overview *(mandatory)*

A web-based migration tool that lets an engineer copy selected tables from a read-only Oracle source database into a single, fixed ClickHouse target database (`oracle_migration_hazem`). Through a graphical interface, the user discovers Oracle schemas and tables dynamically, picks what to migrate, chooses how the work is parallelized, launches the migration as a background job, and watches progress and row-count validation until completion.

The product is delivered **phase by phase**. Each phase has its own scope, acceptance criteria, and a hard stop point; later phases are not started until the current phase is verified. A foundational **Phase 0** establishes the project guardrails (safety rules, environment rules, folder expectations, and acceptance gates) that every later phase must honor.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Discover and migrate a single table (Priority: P1)

An engineer opens the application, the app confirms both databases are reachable, the engineer selects an Oracle source schema, the matching tables load automatically, they pick a table, the target schema and target table name auto-fill, the ClickHouse database is fixed to `oracle_migration_hazem`, and they launch a migration that copies the table's data into ClickHouse in batches while the browser stays responsive.

**Why this priority**: This is the core promise of the product — moving one table from Oracle to ClickHouse safely through a GUI. Without it, nothing else matters. It is the MVP.

**Independent Test**: Open the app, select a known schema and table, launch the migration, and confirm the target ClickHouse table is created in `oracle_migration_hazem` and populated with the source rows, with the job returning immediately and progress visible.

**Acceptance Scenarios**:

1. **Given** the app is open and both databases are healthy, **When** the engineer selects an Oracle schema, **Then** the source table dropdown is populated with that schema's tables and the target schema field auto-fills with the same schema name.
2. **Given** a source table is selected, **When** the selection completes, **Then** the partition/hash column dropdown is populated with candidate columns and the target table name auto-fills with the source table name.
3. **Given** valid selections, **When** the engineer clicks "Launch Migration Pipeline", **Then** a migration job is created, a job identifier is returned immediately, and the browser does not block while data is copied.
4. **Given** a running job, **When** the engineer views status, **Then** total rows, processed rows, and current status (PENDING/RUNNING/SUCCESS/FAILED) are shown and updated.
5. **Given** a completed job, **When** the target table is inspected, **Then** it exists only inside `oracle_migration_hazem` and contains the migrated data, and Oracle is unchanged.

### User Story 2 - Verify connectivity and target safety before migrating (Priority: P1)

Before any migration, the engineer needs confidence that the app can reach Oracle (read-only) and ClickHouse, and that the fixed target database exists, so that failures are diagnosed up front rather than mid-migration.

**Why this priority**: Connectivity and the fixed-target guarantee are prerequisites for any safe migration; they protect the source and confine all writes. This is a foundational slice that delivers value even before full migration exists.

**Independent Test**: Trigger the health checks and confirm Oracle reports connectable + metadata-readable and ClickHouse reports connectable + target database present, with clear errors when either is misconfigured and no credentials leaked in output or logs.

**Acceptance Scenarios**:

1. **Given** valid Oracle settings, **When** the Oracle health check runs, **Then** it reports the connection succeeded and metadata is readable.
2. **Given** valid ClickHouse settings, **When** the ClickHouse health check runs, **Then** it reports the connection succeeded and whether the `oracle_migration_hazem` target database exists.
3. **Given** a misconfigured or unreachable database, **When** a health check runs, **Then** a clear, actionable error is returned and no credentials appear in the response or logs.

### User Story 3 - Parallel migration for large tables (Priority: P2)

For large tables, the engineer chooses a worker-thread count and a partition/hash column so the extraction and load run in parallel, completing significantly faster than a single-threaded copy.

**Why this priority**: Performance for large tables is a key differentiator, but it depends on a stable single-thread migration first, so it is the next slice after the MVP.

**Independent Test**: Run a parallel migration on a medium table using a numeric, a date, and a hash partitioning strategy, and confirm the target row count matches the source with no duplicated or missing ranges.

**Acceptance Scenarios**:

1. **Given** a numeric partition column, **When** a parallel migration runs, **Then** the value range is split across workers with no overlapping or missing rows and the target count matches the source.
2. **Given** a date/timestamp column, **When** a parallel migration runs, **Then** the time range is split across workers and the target count matches the source.
3. **Given** no suitable range column, **When** hash mode is selected, **Then** rows are distributed across workers by a hash of the chosen column and the target count matches the source.
4. **Given** any worker fails, **When** the job is evaluated, **Then** the overall job status becomes FAILED and the failure is reported.

### User Story 4 - Validate the migration (Priority: P2)

After a migration, the engineer needs assurance the copy is complete, so the app compares source and target row counts and reports whether they match.

**Why this priority**: Reconciliation turns "data moved" into "data verified," which is essential for trust but follows the actual migration capability.

**Independent Test**: Run a migration, then view the job result and confirm source count, target count, and a clear match/mismatch indicator are displayed without modifying Oracle.

**Acceptance Scenarios**:

1. **Given** a finished migration, **When** validation runs, **Then** the source row count and target row count are captured and stored with the job.
2. **Given** captured counts, **When** the result is shown, **Then** a clear "counts match" or "counts do not match" indicator is displayed.
3. **Given** validation runs, **When** it queries Oracle, **Then** only read operations are used and Oracle is unchanged.

### User Story 5 - Run the project as a team member (Priority: P3)

A teammate or manager clones the repository, supplies their own environment file, and starts the whole application with a single command, reaching the GUI in a browser.

**Why this priority**: Easy, reproducible team deployment matters for adoption but is a packaging concern that follows working functionality.

**Independent Test**: From a fresh clone with a valid environment file, start the app with one command and confirm the GUI loads, health checks pass, and a migration can be run end to end following the README.

**Acceptance Scenarios**:

1. **Given** a fresh clone and a valid environment file, **When** the single start command is run, **Then** the application starts and the GUI is reachable in a browser.
2. **Given** the running app, **When** a teammate follows the README, **Then** they can run health checks and complete a migration without additional guidance.

### Edge Cases

- What happens when the selected Oracle schema or table no longer exists or is not visible to the configured account? → A controlled error is returned; the source is never modified.
- How does the system handle an Oracle column type that has no defined mapping? → It falls back to a safe text representation rather than failing the migration.
- What happens when the fixed ClickHouse target database does not exist? → The app reports it as missing and does not auto-create it unless explicitly configured to do so.
- What happens if a user-supplied target table name would collide with another? → The naming rule (`<schema>__<table>`) is applied to keep targets distinct within the single database.
- What happens when a very large table is selected? → Data is streamed in batches; the full table is never loaded into memory at once.
- How does the system handle a request that attempts any write to Oracle or any non-`oracle_migration_hazem` ClickHouse database? → The operation is rejected by guardrails.
- What happens when a chosen hash column is nullable or low-cardinality? → Hash mode is only used when the column is non-null and high-cardinality; otherwise it is not offered/used.
- What happens when a worker count above the safe maximum is requested? → It is capped at the safe maximum.

## Requirements *(mandatory)*

### Functional Requirements

#### Safety & Guardrails (Phase 0 foundation, enforced in all phases)

- **FR-001**: The system MUST treat the Oracle source as strictly read-only and MUST only ever issue `SELECT` statements against it.
- **FR-002**: The system MUST NOT issue any Oracle statement that creates, alters, drops, truncates, inserts, updates, deletes, merges, or executes procedures/jobs, and MUST NOT modify any Oracle schema, table, data, trigger, procedure, or job.
- **FR-003**: The system MUST restrict all ClickHouse writes to the single target database `oracle_migration_hazem` and MUST reject operations targeting any other ClickHouse database.
- **FR-004**: Inside `oracle_migration_hazem`, the system MUST limit itself to `CREATE TABLE IF NOT EXISTS`, `INSERT INTO`, and `SELECT`; any rerun-oriented destructive operations (drop/truncate) MUST NOT be implemented unless explicitly required later.
- **FR-005**: The system MUST load all configuration and credentials exclusively from environment variables and MUST NOT hardcode credentials in source code, Dockerfile, Docker Compose, README, PLAN, or any committed file.
- **FR-006**: The repository MUST provide an example environment file with placeholder values only, and MUST ensure the real environment file and other secrets/artifacts are excluded from version control.
- **FR-007**: The system MUST NOT print or log credentials in any output, response, or log line.
- **FR-008**: The system MUST validate user-provided schema and table names against Oracle metadata and MUST use bind variables rather than concatenating raw user input into SQL.
- **FR-009**: The system MUST reject dangerous or unexpected target-database values and confirm the target is exactly `oracle_migration_hazem` before any write.

#### Discovery & GUI

- **FR-010**: The system MUST expose a GUI home page reachable in a browser when the application is running.
- **FR-011**: On load, the GUI MUST report Oracle and ClickHouse health and MUST populate the Oracle source schema list dynamically from Oracle metadata.
- **FR-012**: When a source schema is selected, the system MUST load that schema's tables dynamically and MUST auto-fill the ClickHouse schema destination field with the selected schema name.
- **FR-013**: When a source table is selected, the system MUST load candidate partition/hash columns dynamically and MUST auto-fill the target table name with the source table name.
- **FR-014**: The GUI MUST present the ClickHouse database as a fixed, non-editable value of `oracle_migration_hazem`.
- **FR-015**: The GUI MUST provide a worker-thread count input defaulting to 8, an editable target table name, and a control to launch the migration pipeline.
- **FR-016**: The system MUST provide the ability to discover, for a given schema and table, its columns with their types and nullability, and to identify candidate partition/hash columns (numeric, date, and timestamp types).

#### Target Modeling (DDL Generation)

- **FR-017**: The system MUST derive the target ClickHouse table name as `<source_schema>__<source_table>` (and `<target_schema>__<target_table>` when the user customizes the target), to avoid collisions within the single database.
- **FR-018**: The system MUST map Oracle column types to ClickHouse types using the defined mapping (e.g., integer-scale NUMBER → nullable 64-bit integer, scaled NUMBER/FLOAT → nullable float, character/text/CLOB → nullable string, DATE → nullable date-time, TIMESTAMP → nullable high-precision date-time, binary float/double → nullable float variants) and MUST fall back to a safe nullable string for unmapped types without crashing.
- **FR-019**: The system MUST generate target tables using an append-friendly columnar engine, ordering by the chosen partition/hash column when present and by an empty key otherwise.
- **FR-020**: The system MUST allow previewing the generated target table definition without executing it, and MUST be able to create the target table with create-if-not-exists semantics inside `oracle_migration_hazem` only.

#### Migration Execution

- **FR-021**: When a migration is launched, the system MUST validate the source schema/table against Oracle metadata, confirm the target database, create the target table if needed, then copy data.
- **FR-022**: The system MUST extract Oracle rows in batches (chunked fetch) and insert into ClickHouse in batches, and MUST NOT load an entire source table into memory at once.
- **FR-023**: The system MUST run migrations as background jobs, returning a job identifier immediately so the browser does not wait for completion, and MUST let the GUI poll job status.
- **FR-024**: The system MUST track per-job metadata: job id, source schema, source table, target database, target table, status, total rows, processed rows, start time, finish time, duration, and error message.
- **FR-025**: The system MUST represent job lifecycle using the statuses PENDING, RUNNING, SUCCESS, FAILED, and CANCELLED.

#### Parallelism

- **FR-026**: The system MUST support parallel migration with a configurable worker count, defaulting to 8 and capped at a safe maximum of 16.
- **FR-027**: The system MUST support numeric-range partitioning (split min/max into non-overlapping worker ranges, with the final range inclusive of the maximum) so that no rows are duplicated or missed.
- **FR-028**: The system MUST support date/timestamp-range partitioning by splitting the min/max time span across workers.
- **FR-029**: The system MUST support a hash-based fallback distribution, used only when the chosen column is non-null and high-cardinality.
- **FR-030**: Each worker MUST batch-insert into ClickHouse and update progress, and if any worker fails the overall job status MUST become FAILED.

#### Validation

- **FR-031**: After migration, the system MUST capture the Oracle source row count and the ClickHouse target row count and store them with the job.
- **FR-032**: The system MUST compute and display whether source and target counts match, clearly indicating validation success or failure, without modifying Oracle.

#### Packaging & Operability

- **FR-033**: The system MUST be startable both locally and via a single containerized compose command, and MUST expose a health endpoint indicating service availability.
- **FR-034**: The repository MUST include documentation covering project overview, prerequisites (including any network/VPN requirement), environment setup, the run command, health-check usage, GUI usage, troubleshooting for both databases, and security notes.

#### Hardening (later phase)

- **FR-035**: The system SHOULD, in a later hardening phase, add access protection for the GUI, an auditable record of migration operations, traceable failures, structured logging without secrets, job cancellation, and a confirmation step before starting a migration.

### Key Entities *(include if feature involves data)*

- **Oracle Source Schema**: A named owner in the Oracle source whose tables can be discovered; read-only.
- **Oracle Source Table**: A table within a source schema, described by its columns, types, and nullability; the unit selected for migration.
- **Partition/Hash Column**: A candidate column (numeric, date, or timestamp; or a high-cardinality non-null column for hashing) used to split work across parallel workers and/or order the target table.
- **Target Table**: The ClickHouse table created inside `oracle_migration_hazem`, named `<schema>__<table>`, modeled from the source columns via the type mapping.
- **Migration Job**: A background unit of work with an id, source/target identifiers, status, total/processed rows, timing, error message, and validation counts.
- **Worker**: A unit of parallel extraction+load operating on one slice (numeric range, date range, or hash bucket) of the source table.
- **Validation Result**: The captured source and target counts plus the match indicator and validation status for a job.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An engineer can go from opening the app to launching a migration of a chosen table in under 2 minutes, using only dynamically discovered schemas and tables.
- **SC-002**: 100% of migrations write data exclusively into the `oracle_migration_hazem` target database and make zero changes to the Oracle source (verified by source being byte-for-byte unchanged).
- **SC-003**: After any completed migration, source and target row counts are reported, and a successful migration shows a 100% count match.
- **SC-004**: Launching a migration returns control to the user immediately (job id within a few seconds) regardless of table size, and the browser never blocks on data transfer.
- **SC-005**: Migrating a large table completes without the application loading the full table into memory (memory use stays bounded by batch size, not table size).
- **SC-006**: Parallel migration on a medium table is measurably faster than single-thread migration on the same table while still achieving an exact row-count match.
- **SC-007**: Zero credentials appear in source code, committed configuration, documentation, application responses, or logs (verified by inspection/search).
- **SC-008**: A teammate can take a fresh clone, supply an environment file, and reach a working GUI with passing health checks using a single start command.
- **SC-009**: Invalid schema/table selections and unmapped column types produce controlled, clear errors instead of crashes.

## Phased Delivery Plan *(mandatory — implementation is phase-based)*

Implementation proceeds one phase at a time. Each phase has a scope, acceptance criteria, and a hard stop point; the next phase does not begin until the current phase is verified.

### Phase 0 — Specification Initialization and Project Guardrails

**Goal**: Establish the rules, safety constraints, environment rules, folder expectations, and acceptance gates that govern every later phase.

**Scope**:
- Document the Oracle read-only rule and the explicit forbidden-operations list.
- Document the ClickHouse write restriction to `oracle_migration_hazem` and the allowed-operations list.
- Define environment-variable-only configuration and the rule that no credentials appear in code, Dockerfile, Docker Compose, README, PLAN, or version control.
- Define the example environment file (placeholders only) and the version-control ignore rules for secrets and local artifacts.
- Define expected project folder structure and required dependencies at a high level.
- Define the cross-cutting acceptance criteria that every phase must satisfy (read-only source, confined target, no secret leakage, batch/streaming for large tables, controlled errors).

**Acceptance Criteria**:
- Guardrail rules are written and unambiguous.
- Example environment file and ignore rules are defined; the real environment file is excluded from version control.
- Folder expectations and dependency list are documented.
- The safety acceptance gates that apply to all phases are explicitly listed.

**Stop Point**: Do not begin Phase 1 until guardrails are documented and agreed.

### Phase 1 — Project Bootstrap and Skeleton
**Goal**: A runnable application skeleton with a home page and a service health endpoint, runnable locally and via the single compose command, with example environment file and ignore rules in place and no hardcoded credentials. No database or migration logic yet. **Stop** until the app starts and the health endpoint succeeds.

### Phase 2 — Database Connection Health Checks
**Goal**: Environment-based Oracle and ClickHouse clients plus health checks confirming connectivity, Oracle metadata readability, and presence of the `oracle_migration_hazem` target (without auto-creating it by default). No GUI dropdowns or migration yet. **Stop** until both health checks succeed with no secrets in logs.

### Phase 3 — Oracle Metadata Discovery
**Goal**: Backend discovery of Oracle schemas, tables, columns, and candidate partition/hash columns, with validated inputs and bind variables, source remaining read-only. No full GUI behavior or migration yet. **Stop** until discovery works and invalid inputs return controlled errors.

### Phase 4 — GUI Dynamic Dropdowns
**Goal**: Interactive GUI using the discovery capability: load schemas on open, refresh tables and auto-fill target schema on schema selection, refresh partition/hash columns and auto-fill target table on table selection, with the ClickHouse database fixed and disabled. No migration yet. **Stop** until dynamic GUI behavior works.

### Phase 5 — ClickHouse Target Modeling (DDL Generation)
**Goal**: Oracle-to-ClickHouse type mapping, safe target naming, DDL preview, and create-if-not-exists table creation confined to `oracle_migration_hazem`, with unmapped types handled safely and dangerous target values rejected. No full data migration yet. **Stop** until preview and table creation work.

### Phase 6 — Single-Thread Batch Migration
**Goal**: First working end-to-end copy: validate selections, ensure target table, stream rows from Oracle in batches, batch-insert into ClickHouse, track totals/progress, return a job id immediately, and let the GUI poll status. No parallel workers yet. **Stop** until one full table copies successfully without blocking the browser.

### Phase 7 — Parallel Migration Engine
**Goal**: Parallel extraction and load via numeric-range, date-range, and hash-fallback modes with a configurable worker count (default 8, max 16), per-worker progress, and job-level failure handling, with no duplicated or missing rows for range modes. **Stop** until parallel migration is verified on small and medium tables.

### Phase 8 — Validation, Counts, and Reconciliation
**Goal**: Capture source and target row counts after migration, compute and display a match indicator, store results with the job, without modifying Oracle. **Stop** until reconciliation works.

### Phase 9 — Final Packaging and Team Run
**Goal**: Finalize containerized run, documentation, example environment file, logs, and troubleshooting so a fresh clone runs end to end with a single command and a clear README. **Stop** when a teammate can run it unaided.

### Phase 10 — Hardening and Production Readiness
**Goal**: Add GUI access protection, migration audit trail, retry/timeout settings, size warnings, job cancellation, downloadable report, structured secret-free logging, rate limiting, and a pre-migration confirmation step. **Stop** when access protection, auditability, traceable failures, and no-secret logging are in place.

## Assumptions

- The configured Oracle account has read access to the metadata views needed for schema/table/column discovery and to the source tables selected for migration.
- The fixed ClickHouse target database `oracle_migration_hazem` either already exists or its creation is handled outside the default app behavior; the app does not auto-create it unless explicitly configured.
- Default operational parameters follow PLAN.md: batch size of 100000 rows, default worker count of 8, and a maximum worker count of 16.
- ClickHouse has no Oracle-style nested schemas, so the Oracle schema is preserved inside the target table name using the `<schema>__<table>` convention.
- Network access to both databases is available from wherever the app runs (a VPN or equivalent may be required) and is a prerequisite, not something the app provisions.
- A single shared target database is intentional; cross-database writes are out of scope and explicitly disallowed.
- Authentication, audit, and other production hardening are intentionally deferred to the final phase and are not part of the MVP.
- The specification is derived solely from PLAN.md; any capability not described there is out of scope for this spec.
