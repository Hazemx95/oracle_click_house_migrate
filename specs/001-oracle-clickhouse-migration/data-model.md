# Phase 1 Data Model: Oracle to ClickHouse Parallel Data Migration Engine

This describes the conceptual entities the application manipulates. Source-side entities are read-only Oracle metadata; target-side entities live in ClickHouse `oracle_migration_hazem`; job entities live in the app's in-memory registry (Phases 6–8) and optionally a persistent audit table (Phase 10).

## OracleSchema (read-only, discovered)
Represents a distinct Oracle owner that has tables.
- `owner` (string) — schema/owner name. **Identity.**
- **Source**: `SELECT DISTINCT owner FROM all_tables ORDER BY owner`.
- **Validation**: a user-supplied schema must exist in this set before use.

## OracleTable (read-only, discovered)
A table within a schema; the unit selected for migration.
- `owner` (string) — parent schema.
- `table_name` (string). **Identity** = (`owner`, `table_name`).
- **Source**: `SELECT table_name FROM all_tables WHERE owner = :schema_name ORDER BY table_name`.
- **Validation**: must exist for the given owner before any column/DDL/migration operation.

## OracleColumn (read-only, discovered)
A column of a source table, used for DDL generation and partition-candidate detection.
- `column_name` (string)
- `data_type` (string) — e.g., NUMBER, VARCHAR2, DATE, TIMESTAMP(6)
- `data_length` (int, nullable)
- `data_precision` (int, nullable)
- `data_scale` (int, nullable)
- `nullable` (string Y/N)
- `char_length` (int, nullable) — character length for char-semantics types (added Phase 5)
- `char_used` (string, nullable) — `B` (byte) or `C` (char) semantics (added Phase 5)
- **Source**: `all_tab_columns` ordered by `column_id`.
- **Derived**: maps to a ClickHouse type via the type-mapping rules (incl. NUMBER precision/scale → Int64/Decimal/Float64); see `contracts/clickhouse-ddl.md`. Unsupported types fall back to `Nullable(String)` with a warning.

## PartitionCandidate (derived view of OracleColumn)
Columns eligible to drive parallelism / target ordering.
- Same fields as OracleColumn (subset).
- **Rule**: `data_type IN ('NUMBER','DATE') OR data_type LIKE 'TIMESTAMP%'`.
- **Mode mapping**: NUMBER → numeric range; DATE/TIMESTAMP% → date range; any non-null high-cardinality column → hash fallback.
- **Parallel-mode resolution (Phase 7)**: the column's `data_type` is the authoritative input for resolving/validating `parallel_mode`. `auto` resolves NUMBER→`numeric_range`, DATE/TIMESTAMP%→`date_range`, otherwise `hash`. An explicit `numeric_range` requires a NUMBER column, `date_range` requires a DATE/TIMESTAMP% column, and `hash` requires a selected column; a mismatch is a pre-launch validation error. Datatype is always read from Oracle metadata, never trusted from the client.

## TargetTable (ClickHouse, created)
The destination table in `oracle_migration_hazem`.
- `database` (string) — **always** `oracle_migration_hazem` (fixed/validated).
- `name` (string) — `<source_schema>__<source_table>` by default, or `<target_schema>__<target_table>` when customized.
- `columns` — derived from OracleColumn list via type mapping; all `Nullable(...)`.
- `engine` — `MergeTree`.
- `order_by` — chosen partition/order column, or `tuple()` when none.
- **Validation**: database must equal `oracle_migration_hazem`; reject any other value. **Created via a DROP-then-CREATE pair** (`DROP TABLE IF EXISTS` then `CREATE TABLE`) — never `CREATE TABLE IF NOT EXISTS` — so every launch starts from a fresh empty target (initial full load only, latest-only).

## MigrationJob (app state)
A unit of background migration work.
- `job_id` (string/UUID) — **Identity.**
- `source_schema` (string)
- `source_table` (string)
- `target_database` (string, = `oracle_migration_hazem`)
- `target_table` (string)
- `partition_column` (string, nullable)
- `partition_mode` (enum: `single` | `numeric` | `date` | `hash`) — internal engine path that drives Phase 7 extraction.
- `requested_parallel_mode` (enum, Phase 7: `auto` | `numeric_range` | `date_range` | `hash`) — exactly what the client sent on `POST /api/migrations`; defaults to `auto` when omitted.
- `resolved_parallel_mode` (enum, Phase 7: `numeric_range` | `date_range` | `hash`, or `single` for a single-worker run) — the concrete mode the engine runs after Auto resolution + datatype validation; never `auto`. Maps onto `partition_mode` (`numeric_range`→`numeric`, `date_range`→`date`, `hash`→`hash`).
- `workers` (int, default 8, 1..16)
- `status` (enum: `PENDING` | `RUNNING` | `SUCCESS` | `FAILED` | `CANCELLED`)
- `total_rows` (int, nullable)
- `processed_rows` (int)
- `inserted_rows` (int) — rows confirmed inserted into ClickHouse
- `remaining_rows` (int, nullable) — `total_rows - processed_rows`
- `batches_completed` (int)
- `current_batch` (int)
- `progress_percent` (number) — 0..100
- `rows_per_second` (number) — throughput
- `elapsed_seconds` (number)
- `started_at` (timestamp, nullable)
- `finished_at` (timestamp, nullable)
- `duration_seconds` (number, nullable)
- `error_message` (string, nullable)
- Per-worker progress (Phase 7): `workers` — list of Worker progress entries (see Worker below)
- Validation fields (Phase 8): `source_row_count`, `target_row_count`, `count_match` (bool or null), `validation_status` (enum: `NOT_STARTED` | `RUNNING` | `SUCCESS` | `FAILED`), `validation_error_message` (string, nullable)
- Diagnostics (Phase 8.1): `diagnostics` — performance timing breakdown for the job (see Diagnostics below)

## Diagnostics (embedded in MigrationJob, Phase 8.1)
Per-step performance instrumentation; all durations in seconds measured with a monotonic clock. Added to localize the slow path before optimizing. Contains no secrets and no raw row/LOB data.
- `total_seconds` (number) — total job duration (mirrors `duration_seconds`).
- `ddl_seconds` (number) — DROP + CREATE target table.
- `source_count_seconds` (number) — Oracle source `COUNT(*)`.
- `range_discovery_seconds` (number) — Oracle `MIN/MAX` discovery (range modes; 0 for single/hash).
- `query_execute_seconds` (number) — Oracle `cursor.execute` of the extraction SELECT (summed across batches/workers).
- `fetch_seconds` (number) — Oracle `fetchmany` time (summed).
- `convert_seconds` (number) — Python row conversion / normalization time (summed), including any LOB `.read()` cost.
- `insert_seconds` (number) — ClickHouse batch insert time (summed).
- `validation_seconds` (number) — post-load count reconciliation time.
- `batch_size` (int) — effective batch size used.
- `batch_count` (int) — number of batches across the job.
- `avg_rows_per_batch` (number) — total processed rows / `batch_count`.
- `avg_seconds_per_batch` (number) — sum of batch durations / `batch_count`.
- `warnings` (list of string) — heavy columns present (CLOB/NCLOB/BLOB/LONG/RAW); non-indexed range column; small-table single-worker downgrade; etc.
- `per_worker` (list, parallel mode) — each entry: `worker_id`, `query_execute_seconds`, `fetch_seconds`, `convert_seconds`, `insert_seconds`, `batch_count`, `avg_seconds_per_batch`.

### State transitions
```
PENDING ──launch──▶ RUNNING ──all rows loaded & counts match──▶ SUCCESS
   │                   │
   │                   ├── any worker error / load error ─────▶ FAILED
   │                   └── cancel requested (Phase 10) ───────▶ CANCELLED
   └── invalid selection at creation ─────────────────────────▶ (rejected, no job)
```
Validation runs after load completes (Phase 8); `validation_status` becomes `SUCCESS` when counts match or `FAILED` when counts mismatch or validation cannot run. A count mismatch marks the job `FAILED`; a count-query infrastructure failure after load completion leaves the job `SUCCESS`, sets `count_match` to null, and stores the failure in `validation_error_message`.

## Worker (transient, Phase 7)
A parallel extraction+load unit operating on one slice. Each entry is surfaced in `GET /api/migrations/{job_id}/status` under `workers` and rendered as a per-worker card/row in the GUI.
- `worker_id` (int, 0..workers-1)
- `partition_mode` (enum: `numeric` | `date` | `hash`)
- `resolved_parallel_mode` (enum, Phase 7: `numeric_range` | `date_range` | `hash`) — the resolved user-facing mode, shown on each worker card/row in the GUI.
- `partition_column` (string, nullable)
- `range_start` / `range_end` — slice bounds: numeric `[start, end)` (final inclusive), date `[start, end)` (final inclusive), or null for hash bucket `MOD(ORA_HASH(col), workers) = worker_id`.
- `status` (enum: `PENDING` | `RUNNING` | `SUCCESS` | `FAILED`)
- `processed_rows` (int) — contributes to the job's aggregate `processed_rows`.
- `inserted_rows` (int)
- `batches_completed` (int)
- `rows_per_second` (number)
- `error_message` (string, nullable)
- `timings` (object, Phase 8.1) — this worker's `query_execute_seconds`, `fetch_seconds`, `convert_seconds`, `insert_seconds`, `batch_count`, `avg_seconds_per_batch`.
- **Rule**: any worker failure marks the parent job `FAILED` and surfaces that worker's `error_message`.

## ValidationResult (embedded in MigrationJob, Phase 8)
- `source_row_count` (int) — `SELECT COUNT(*) FROM <schema>.<table>` (read-only).
- `target_row_count` (int) — `SELECT COUNT(*) FROM oracle_migration_hazem.<schema>__<table>`.
- `count_match` (bool, nullable) — `source_row_count == target_row_count`, or null when validation could not compare counts.
- `validation_status` (enum) — see above.
- `validation_error_message` (string, nullable) — clear validation failure message without credentials.

## AuditRecord (persistent, Phase 10 — optional)
Durable record of each migration for traceability.
- Mirrors MigrationJob terminal fields plus actor/initiator and timestamps.
- Stored in `oracle_migration_hazem` (e.g., a `_migration_audit` table) or app-side store; never contains credentials.
