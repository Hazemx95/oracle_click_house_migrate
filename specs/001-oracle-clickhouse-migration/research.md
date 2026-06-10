# Phase 0 Research: Oracle to ClickHouse Parallel Data Migration Engine

All technical choices below are derived directly from PLAN.md; there were no open NEEDS CLARIFICATION items in the spec. Each decision records what was chosen, why, and what was rejected.

## Decision: Web framework — FastAPI + uvicorn
- **Rationale**: PLAN.md §9 mandates FastAPI and `uvicorn[standard]`, with the run command `uvicorn app.main:app --host 0.0.0.0 --port 8000`. FastAPI gives async endpoints, easy JSON APIs for the GUI, and background-task support for non-blocking migrations.
- **Alternatives considered**: Flask/Django — rejected; not specified, heavier or less async-friendly for the polling/background-job model.

## Decision: Oracle driver — `oracledb` (thin mode), SELECT-only
- **Rationale**: `oracledb` is listed in PLAN.md dependencies and supports thin mode (no Oracle client install), bind variables, and `cursor.fetchmany(batch_size)` streaming required by the performance rule.
- **Safety**: A centralized read-only client is the single path to Oracle. A guard rejects any statement whose leading keyword is not `SELECT`/`WITH`, enforcing the forbidden-operation list (CREATE/ALTER/DROP/TRUNCATE/INSERT/UPDATE/DELETE/MERGE/EXEC/CALL).
- **Alternatives considered**: `cx_Oracle` — superseded by `oracledb`; SQLAlchemy ORM — unnecessary and risks non-SELECT emission.

## Decision: ClickHouse client — `clickhouse-connect`, target-DB confined
- **Rationale**: Listed in PLAN.md; supports HTTP (port 8123), efficient batch inserts, and DDL execution.
- **Safety**: All writes go through a wrapper that forces the database to `oracle_migration_hazem` and rejects any other database name before executing. Only `CREATE TABLE IF NOT EXISTS`, `INSERT`, and `SELECT` are used (no DROP/TRUNCATE unless explicitly enabled later).
- **Alternatives considered**: native TCP `clickhouse-driver` — not specified; HTTP via `clickhouse-connect` is sufficient and matches the default 8123 port.

## Decision: Memory-safe extraction/load — `fetchmany` + batch insert
- **Rationale**: PLAN.md §14 explicitly forbids `pandas.read_sql("SELECT * FROM huge_table")` and requires chunked fetch. Reading `MIGRATION_BATCH_SIZE` (default 100000) rows per chunk and inserting each chunk keeps memory bounded by batch size, not table size.
- **Alternatives considered**: full DataFrame load — rejected (violates memory-safety gate); server-side cursor streaming row-by-row — slower; batch chunking balances throughput and memory.

## Decision: Background jobs — in-memory job registry + background execution
- **Rationale**: PLAN.md §14 requires returning a `job_id` immediately and GUI polling via `GET /api/migrations/{job_id}/status`. A simple in-memory registry (dict keyed by job_id) with a background task satisfies Phases 6–8 without extra infrastructure.
- **Alternatives considered**: Celery/Redis queue — overkill for a single-instance internal tool; persistent DB-backed jobs — deferred to Phase 10 (audit table).

## Decision: Parallelism — thread pool over numeric/date ranges, hash fallback
- **Rationale**: PLAN.md §15 defines three modes. Numeric/date range splitting uses half-open intervals with an inclusive final upper bound to guarantee no overlap and no gaps; hash mode uses `MOD(ORA_HASH(col), :workers) = :id` only for non-null high-cardinality columns. Extraction is I/O-bound, so a worker pool (default 8, max 16) is appropriate; each worker batch-inserts independently.
- **Alternatives considered**: multiprocessing — heavier, complicates shared progress; asyncio-only — Oracle driver calls are blocking, so thread pool is simpler and safe.

## Decision: Type mapping — fixed Oracle→ClickHouse table with safe default
- **Rationale**: PLAN.md §13 specifies exact mappings; unsupported types fall back to `Nullable(String)` so migrations never crash on an unknown type. All columns are `Nullable(...)` to tolerate Oracle nullability.
- **Alternatives considered**: best-effort precise types for every Oracle type — deferred; the safe-default approach matches "first version" guidance.

## Decision: Target table engine/naming — MergeTree, `<schema>__<table>`
- **Rationale**: ClickHouse has no Oracle-style schemas; PLAN.md §7/§13 preserve the Oracle schema in the table name and use `MergeTree` with `ORDER BY <partition_column>` when present, else `ORDER BY tuple()`.
- **Alternatives considered**: separate ClickHouse databases per Oracle schema — violates the single fixed-target rule.

## Decision: Configuration — environment variables only via `.env` / `python-dotenv` + pydantic
- **Rationale**: PLAN.md §4 mandates env-only configuration, `.env.example` with placeholders, real `.env` git-ignored, and no secrets in code/Docker/README/PLAN. Pydantic settings centralize loading and validation; `CLICKHOUSE_DATABASE` defaults to `oracle_migration_hazem` and `CLICKHOUSE_ALLOW_CREATE_DATABASE` defaults to `false`.
- **Alternatives considered**: config files committed to repo — rejected (secrets risk); hardcoded defaults for hosts/passwords — rejected (violates secrets gate).

## Decision: Packaging — Dockerfile + docker-compose, single run command
- **Rationale**: PLAN.md §1/§9/§17 require `docker compose up -d --build`, app at `http://localhost:8000`, container name `oracle-clickhouse-migration-app`, env wired via env-file.
- **Alternatives considered**: bare-metal only — rejected; team-run requirement needs Compose.

## Open items
- None. All parameters (batch size 100000, default workers 8, max workers 16, ports, target DB) are fixed by PLAN.md.
