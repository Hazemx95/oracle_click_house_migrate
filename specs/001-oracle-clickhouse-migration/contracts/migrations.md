# Contract: Migration Endpoints

Introduced in Phase 6 (single-thread), extended in Phase 7 (parallel) and Phase 8 (validation). Launch returns immediately with a `job_id`; the GUI polls status. Oracle read-only; ClickHouse writes only to `oracle_migration_hazem`.

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
  "workers": 8
}
```
- `partition_mode` ∈ `single` | `numeric` | `date` | `hash` (Phase 6 supports `single`; Phases 7+ add the rest).
- `workers`: 1..16; default 8; values above 16 are capped.
- `partition_column` may be null for `single`.

**Response 202**
```json
{ "job_id": "f1c2…", "status": "PENDING" }
```

**Response 400** — invalid schema/table or bad target database (must be `oracle_migration_hazem`).

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
  "workers": 8,
  "status": "RUNNING",
  "total_rows": 1000000,
  "processed_rows": 250000,
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
Lightweight progress view for polling.

**Response 200**
```json
{ "job_id": "f1c2…", "status": "RUNNING", "total_rows": 1000000, "processed_rows": 250000 }
```

## Job statuses
`PENDING` → `RUNNING` → `SUCCESS` | `FAILED` | `CANCELLED`. Any worker failure → `FAILED`.

## Validation fields (Phase 8)
After load: `source_row_count` (`SELECT COUNT(*) FROM <schema>.<table>`), `target_row_count` (`SELECT COUNT(*) FROM oracle_migration_hazem.<schema>__<table>`), `count_match` (bool), `validation_status` ∈ `PENDING` | `MATCH` | `MISMATCH`.

## POST /api/migrations/{job_id}/cancel  (Phase 10)
Requests cancellation; transitions a `RUNNING` job toward `CANCELLED`.
