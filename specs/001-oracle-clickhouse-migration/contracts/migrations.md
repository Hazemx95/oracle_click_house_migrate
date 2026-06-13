# Contract: Migration Endpoints

Introduced in Phase 6 (single-thread), extended in Phase 7 (parallel engine + parallel-mode selector), and Phase 8 (validation). Launch returns immediately with a `job_id`; the GUI polls status. Oracle read-only; ClickHouse writes only to `oracle_migration_hazem`.

## POST /api/migrations
Validates the selection, creates a job, starts background migration, returns immediately.

**Request**
```json
{
  "source_schema": "CM",
  "source_table": "COMPONENT",
  "target_table": "CM__COMPONENT",
  "partition_column": "ID",
  "partition_mode": "numeric",
  "parallel_mode": "auto",
  "workers": 8
}
```
- `partition_mode` (internal engine path) ∈ `single` | `numeric` | `date` | `hash` (Phase 6 supports `single`; Phases 7+ add the rest).
- `parallel_mode` (Phase 7, user-facing) ∈ `auto` | `numeric_range` | `date_range` | `hash`; default `auto`. Maps onto `partition_mode` after resolution: `numeric_range`→`numeric`, `date_range`→`date`, `hash`→`hash`; `auto` is resolved first (see resolution rules below).
- `workers`: 1..16; default 8; values above 16 are capped. When `workers == 1`, a parallel mode is allowed (single-thread) or warned — never a hard error solely for that reason.
- `partition_column` may be null for `single` / `auto` without a column.

**`parallel_mode` resolution & validation (Phase 7)** — performed **before** a job is created, using read-only Oracle column metadata (the client's claimed datatype is never trusted):
- `auto`: `NUMBER` column → `numeric_range`; `DATE`/`TIMESTAMP%` column → `date_range`; any other valid selected column → `hash`.
- `numeric_range` requires a `NUMBER` column; `date_range` requires a `DATE`/`TIMESTAMP%` column; `hash` requires a selected column (uses `ORA_HASH`).
- A mode that conflicts with the selected column's datatype, an unknown `parallel_mode` value, or `hash`/parallel `auto` with no usable column → **Response 400** (no job created).

**Response 202**
```json
{ "job_id": "f1c2…", "status": "PENDING" }
```

**Response 400** — invalid schema/table, bad target database (must be `oracle_migration_hazem`), unknown `parallel_mode`, or `parallel_mode` incompatible with the selected column's datatype.

## GET /api/migrations/{job_id}
Full job record.

**Response 200**
```json
{
  "job_id": "f1c2…",
  "source_schema": "CM",
  "source_table": "COMPONENT",
  "target_database": "oracle_migration_hazem",
  "target_table": "CM__COMPONENT",
  "partition_column": "ID",
  "partition_mode": "numeric",
  "requested_parallel_mode": "auto",
  "resolved_parallel_mode": "numeric_range",
  "workers": 8,
  "status": "RUNNING",
  "total_rows": 1000000,
  "processed_rows": 250000,
  "inserted_rows": 250000,
  "remaining_rows": 750000,
  "batches_completed": 5,
  "current_batch": 6,
  "progress_percent": 25.0,
  "rows_per_second": 7500,
  "elapsed_seconds": 33,
  "started_at": "2026-06-10T14:20:00Z",
  "finished_at": null,
  "duration_seconds": null,
  "error_message": null,
  "source_row_count": null,
  "target_row_count": null,
  "count_match": null,
  "validation_status": "PENDING"
}
```

## GET /api/migrations/{job_id}/status
Polling view returning **overall progress** + **per-worker progress** (Phase 7) + **validation fields** (Phase 8). The `workers` array is empty/omitted for single-thread (Phase 6) jobs; validation fields are `null`/`PENDING` until Phase 8 validation runs.

**Response 200**
```json
{
  "job_id": "f1c2…",
  "status": "RUNNING",
  "requested_parallel_mode": "auto",
  "resolved_parallel_mode": "numeric_range",
  "total_rows": 1000000,
  "processed_rows": 450000,
  "inserted_rows": 450000,
  "remaining_rows": 550000,
  "progress_percent": 45.0,
  "batches_completed": 9,
  "current_batch": 10,
  "rows_per_second": 7500,
  "elapsed_seconds": 60,
  "error_message": null,
  "workers": [
    {
      "worker_id": 1,
      "partition_mode": "numeric",
      "resolved_parallel_mode": "numeric_range",
      "partition_column": "ID",
      "range_start": 1,
      "range_end": 250000,
      "status": "RUNNING",
      "processed_rows": 120000,
      "inserted_rows": 120000,
      "batches_completed": 2,
      "rows_per_second": 3000,
      "error_message": null
    }
  ],
  "source_row_count": null,
  "target_row_count": null,
  "count_match": null,
  "validation_status": "PENDING"
}
```

**Overall progress fields**: `status`, `total_rows`, `processed_rows`, `inserted_rows`, `remaining_rows`, `progress_percent`, `batches_completed`, `current_batch`, `rows_per_second`, `elapsed_seconds`, `error_message`.
**Parallel-mode fields** (Phase 7): `requested_parallel_mode` ∈ `auto` | `numeric_range` | `date_range` | `hash`; `resolved_parallel_mode` ∈ `numeric_range` | `date_range` | `hash` (may be `single` for a single-worker run) — never `auto`.
**Per-worker fields** (Phase 7, + Phase 7 `resolved_parallel_mode`): `worker_id`, `partition_mode`, `resolved_parallel_mode`, `partition_column`, `range_start`, `range_end`, `status`, `processed_rows`, `inserted_rows`, `batches_completed`, `rows_per_second`, `error_message`.
**Validation fields** (Phase 8): `source_row_count`, `target_row_count`, `count_match`, `validation_status`.

## Job statuses
`PENDING` → `RUNNING` → `SUCCESS` | `FAILED` | `CANCELLED`. Any worker failure → `FAILED`.

## Validation fields (Phase 8)
After load: `source_row_count` (`SELECT COUNT(*) FROM <schema>.<table>`), `target_row_count` (`SELECT COUNT(*) FROM oracle_migration_hazem.<schema>__<table>`), `count_match` (bool), `validation_status` ∈ `PENDING` | `MATCH` | `MISMATCH`.

## POST /api/migrations/{job_id}/cancel  (Phase 10)
Requests cancellation; transitions a `RUNNING` job toward `CANCELLED`.
