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

**Optional per-job runtime tuning (Phase 8.2.1)** — overrides config defaults **for this job only** (blank/omitted → config default; provided → override; never mutates `.env`). Validated **before** a job is created; invalid input → **Response 400**, no job created:
- `oracle_fetch_batch_size` (positive int) — Oracle fetch batch / cursor `arraysize`/`prefetchrows`.
- `clickhouse_insert_batch_size` (positive int) — starting ClickHouse insert chunk size (adaptive sizer may shrink it during the job).
- `max_concurrent_clickhouse_inserts` (positive int) — insert semaphore size; **must not exceed the safe configured ceiling**.
- `validation_mode` (`fast` | `strict` | `none`).
- `dynamic_chunks_per_worker` (positive int, optional).

**`parallel_mode` resolution & validation (Phase 7)** — performed **before** a job is created, using read-only Oracle column metadata (the client's claimed datatype is never trusted):
- `auto`: `NUMBER` column → `numeric_range`; `DATE`/`TIMESTAMP%` column → `date_range`; any other valid selected column → `hash`.
- `numeric_range` requires a `NUMBER` column; `date_range` requires a `DATE`/`TIMESTAMP%` column; `hash` requires a selected column (uses `ORA_HASH`).
- A mode that conflicts with the selected column's datatype, an unknown `parallel_mode` value, or `hash`/parallel `auto` with no usable column → **Response 400** (no job created).

**Response 202**
```json
{ "job_id": "f1c2…", "status": "PENDING" }
```

**Response 400** — invalid schema/table, bad target database (must be `oracle_migration_hazem`), unknown `parallel_mode`, `parallel_mode` incompatible with the selected column's datatype, or (Phase 8.2.1) invalid runtime tuning: a non-positive batch size, `max_concurrent_clickhouse_inserts` above the safe ceiling, a non-positive `dynamic_chunks_per_worker`, or a `validation_mode` outside `fast`/`strict`/`none`. No job is created on any of these.

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
  "validation_status": "NOT_STARTED",
  "validation_error_message": null
}
```

## GET /api/migrations/{job_id}/status
Polling view returning **overall progress** + **per-worker progress** (Phase 7) + **validation fields** (Phase 8). The `workers` array is empty/omitted for single-thread (Phase 6) jobs; validation fields are `null`/`NOT_STARTED` until Phase 8 validation runs.

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
  "validation_status": "NOT_STARTED",
  "validation_error_message": null
}
```

**Overall progress fields**: `status`, `total_rows`, `processed_rows`, `inserted_rows`, `remaining_rows`, `progress_percent`, `batches_completed`, `current_batch`, `rows_per_second`, `elapsed_seconds`, `error_message`.
**Parallel-mode fields** (Phase 7): `requested_parallel_mode` ∈ `auto` | `numeric_range` | `date_range` | `hash`; `resolved_parallel_mode` ∈ `numeric_range` | `date_range` | `hash` (may be `single` for a single-worker run) — never `auto`.
**Per-worker fields** (Phase 7, + Phase 7 `resolved_parallel_mode`): `worker_id`, `partition_mode`, `resolved_parallel_mode`, `partition_column`, `range_start`, `range_end`, `status`, `processed_rows`, `inserted_rows`, `batches_completed`, `rows_per_second`, `error_message`.
**Validation fields** (Phase 8): `source_row_count`, `target_row_count`, `count_match`, `validation_status`, `validation_error_message`.
**Diagnostics field** (Phase 8.1): `diagnostics` — performance timing breakdown, returned by **both** `GET /api/migrations/{job_id}` and `GET /api/migrations/{job_id}/status`. Contains no secrets and no raw row/LOB data.

## Diagnostics (Phase 8.1)
`diagnostics` is a per-step performance breakdown (seconds, monotonic clock) added to localize the slow path. The single-thread and parallel paths both populate it; the GUI renders it as a Diagnostics section.

```json
{
  "diagnostics": {
    "total_seconds": 1496.0,
    "ddl_seconds": 0.4,
    "source_count_seconds": 2.1,
    "range_discovery_seconds": 0.0,
    "query_execute_seconds": 1.2,
    "fetch_seconds": 740.0,
    "convert_seconds": 730.0,
    "insert_seconds": 18.0,
    "validation_seconds": 2.3,
    "batch_size": 100000,
    "batch_count": 1,
    "avg_rows_per_batch": 29792,
    "avg_seconds_per_batch": 1488.0,
    "warnings": [
      "Heavy LOB columns detected (CLOB/BLOB) — per-LOB reads likely dominate fetch time",
      "Table below MIGRATION_PARALLEL_MIN_ROWS — running single-thread (workers=1)"
    ],
    "per_worker": [
      {
        "worker_id": 0,
        "query_execute_seconds": 0.3,
        "fetch_seconds": 92.0,
        "convert_seconds": 91.0,
        "insert_seconds": 2.2,
        "batch_count": 1,
        "avg_seconds_per_batch": 185.0
      }
    ]
  }
}
```

Fields: `total_seconds`, `ddl_seconds`, `source_count_seconds`, `range_discovery_seconds` (0 for single/hash), `query_execute_seconds`, `fetch_seconds`, `convert_seconds` (includes LOB `.read()` cost), `insert_seconds`, `validation_seconds`, `batch_size`, `batch_count`, `avg_rows_per_batch`, `avg_seconds_per_batch`, `warnings` (heavy columns, non-indexed range column, small-table single-worker downgrade), and `per_worker` (parallel mode) with each worker's `query_execute_seconds`/`fetch_seconds`/`convert_seconds`/`insert_seconds`/`batch_count`/`avg_seconds_per_batch`. The example values above illustrate the suspected LOB-fetch bottleneck behind the ~19 rows/s baseline.

## Effective settings & stability diagnostics (Phase 8.2.1)
Both `GET /api/migrations/{job_id}` and `GET /api/migrations/{job_id}/status` additionally return:
- `effective_settings` — the per-job runtime tuning actually in force after merging GUI overrides over config defaults; each field records its source (`override` | `default`): `oracle_fetch_batch_size`, `clickhouse_insert_batch_size`, `max_concurrent_clickhouse_inserts`, `validation_mode`, `dynamic_chunks_per_worker`.
- Inside `diagnostics`: `effective_clickhouse_timeouts` (`connect_timeout`, `send_receive_timeout`, insert timeout where supported, `compress`), `clickhouse_insert_batch_size_initial`, `clickhouse_insert_batch_size_current` (adaptive), `insert_target_seconds`, `insert_slow_seconds`, `slow_insert_count`, and `dynamic_chunk_count`.

```json
{
  "effective_settings": {
    "oracle_fetch_batch_size": {"value": 50000, "source": "override"},
    "clickhouse_insert_batch_size": {"value": 10000, "source": "override"},
    "max_concurrent_clickhouse_inserts": {"value": 2, "source": "default"},
    "validation_mode": {"value": "fast", "source": "default"},
    "dynamic_chunks_per_worker": {"value": 64, "source": "override"}
  },
  "diagnostics": {
    "effective_clickhouse_timeouts": {"connect_timeout": 15, "send_receive_timeout": 900, "insert_timeout": 900, "compress": true},
    "clickhouse_insert_batch_size_initial": 10000,
    "clickhouse_insert_batch_size_current": 5000,
    "insert_target_seconds": 30,
    "insert_slow_seconds": 45,
    "slow_insert_count": 3,
    "dynamic_chunk_count": 256
  }
}
```
GUI overrides apply to that one job only and never mutate `.env`. The fail-fast insert-timeout behavior (worker `FAILED` → job `FAILED` → other workers stop at a safe boundary → validation skipped → target treated as incomplete, with the exact GUI message) is unchanged from Phase 8.2.

## Job statuses
`PENDING` → `RUNNING` → `SUCCESS` | `FAILED` | `CANCELLED`. Any worker failure → `FAILED`.

## Validation fields (Phase 8)
After load: `source_row_count` (`SELECT COUNT(*) FROM <schema>.<table>`), `target_row_count` (`SELECT COUNT(*) FROM oracle_migration_hazem.<schema>__<table>`), `count_match` (bool or null when validation could not compare counts), `validation_status` ∈ `NOT_STARTED` | `RUNNING` | `SUCCESS` | `FAILED`, and `validation_error_message` (null unless validation fails). A count mismatch marks the job `FAILED`; a count-query infrastructure failure after the load completes leaves the job `SUCCESS` while setting `validation_status="FAILED"` and `count_match=null`.

## POST /api/migrations/{job_id}/cancel  (Phase 10)
Requests cancellation; transitions a `RUNNING` job toward `CANCELLED`.
