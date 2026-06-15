---
description: "Phase-based task list for Oracle to ClickHouse Parallel Data Migration Engine"
---

# Tasks: Oracle to ClickHouse Parallel Data Migration Engine

**Input**: Design documents from `specs/001-oracle-clickhouse-migration/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `.specify/memory/constitution.md`

## How to use this file

- Tasks are grouped by **implementation phase** (Phase 0 → Phase 10), matching `plan.md` and `PLAN.md`.
- Each task is small, has a unique ID (`T001`…), and names the **exact file path** to create or modify.
- `[P]` = may run in parallel with other `[P]` tasks in the same phase (different files, no ordering dependency).
- **Do not start a phase until the previous phase's acceptance criteria pass** (Constitution P-IV). Each phase ends with a Stop point.
- **Constitution gates apply to every phase** (v1.0.0): Oracle SELECT-only (P-I); ClickHouse writes only to `oracle_migration_hazem` (P-II); credentials env-only, never hardcoded (P-III); no secrets in logs, bind variables, metadata-validated names (P-VII); memory-safe `fetchmany` + batch insert (P-V).

**Scope — initial full load only (Phases 4–10).** Launch / Replicate performs a full-table **replace**: `DROP TABLE IF EXISTS` → `CREATE TABLE` (from the Oracle→ClickHouse type map) → full `fetchmany` extraction → ClickHouse batch insert. Re-running the same source schema/table drops and recreates the target and reloads in full, so the target holds **only the latest full-load result** (never appended duplicate copies). `DROP TABLE`/`CREATE TABLE` are the explicitly authorized rerun operations and stay confined to `oracle_migration_hazem`. **Out of scope (no tasks):** CDC, incremental load, watermark/last-loaded-value tracking, deduplication, append-only duplicate behavior, merge/upsert, staging tables, skip-existing-row logic — these are owned by another team. **Reusability:** all business logic lives in framework-agnostic service modules (`app/services/*`, `app/db/*`) with no FastAPI imports, so a future Flask app can import them directly; FastAPI route handlers stay thin wrappers.

**Traceability to spec.md user stories**: Phase 2 → US2 (connectivity/safety); Phases 3–8 → US1 (single-table full-load migration MVP); Phase 7 → US3 (parallel engine **+ Parallel Mode selector**); Phase 8 → US4 (validation); Phase 9 → US5 (team run).

**Path convention**: repository root is `oracle_click_house_migrate/`; application code under `app/`, tests under `tests/`.

---

## Phase 0: Specification Initialization and Project Guardrails

**Goal**: Confirm spec/plan/constitution guardrails are in place before any code. No application code in this phase.

- [X] T001 Verify spec, plan, and design docs exist: confirm `specs/001-oracle-clickhouse-migration/spec.md`, `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, and `contracts/` are present (list the directory; no edits).
- [X] T002 Verify the project constitution exists and is v1.0.0 at `.specify/memory/constitution.md` (read and confirm the 7 principles; no edits).
- [X] T003 Create a short guardrails summary section in `README.md` stub stating: Oracle read-only, ClickHouse target fixed to `oracle_migration_hazem`, env-only credentials, phase-by-phase delivery (placeholder file `README.md` at repo root).

**Acceptance criteria**: all design docs and constitution present; guardrails summarized. **Stop point**: do not start Phase 1 until guardrails are reviewed.

---

## Phase 1: Project Bootstrap and Docker Skeleton

**Goal**: Runnable FastAPI skeleton with home page + `/api/health`, locally and via Docker Compose; env example + gitignore; no hardcoded credentials.

- [X] T004 [P] Create `requirements.txt` at repo root listing: `fastapi`, `uvicorn[standard]`, `python-dotenv`, `pydantic`, `jinja2`, `python-multipart`, `oracledb`, `clickhouse-connect`.
- [X] T005 [P] Create `.gitignore` at repo root with: `.env`, `*.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, `.DS_Store`.
- [X] T006 [P] Create `.env.example` at repo root with placeholder keys only (CLICKHOUSE_HOST/PORT/USER/PASS, `CLICKHOUSE_DATABASE=oracle_migration_hazem`, `CLICKHOUSE_ALLOW_CREATE_DATABASE=false`, P5_QA_ORACLE_* vars, `APP_HOST=0.0.0.0`, `APP_PORT=8000`, `MIGRATION_BATCH_SIZE=100000`, `MIGRATION_DEFAULT_WORKERS=8`). No real secrets.
- [X] T007 [P] Create empty package markers: `app/__init__.py`, `app/api/__init__.py`, `app/db/__init__.py`, `app/services/__init__.py`.
- [X] T008 Create `app/config.py` with a pydantic settings class that loads all env vars via `python-dotenv`; expose constant `TARGET_DATABASE = "oracle_migration_hazem"`; never embed secrets as defaults.
- [X] T009 Create `app/api/health_routes.py` with an APIRouter exposing `GET /api/health` returning `{"status":"ok","service":"oracle-clickhouse-migration-engine"}`.
- [X] T010 Create `app/main.py` with the FastAPI `app`, mount `app/static` at `/static`, configure Jinja2 templates dir `app/templates`, include the health router, and add `GET /` returning the rendered `index.html`.
- [X] T011 [P] Create `app/templates/index.html` as a minimal GUI shell page (title + empty form container; dynamic behavior added in Phase 4).
- [X] T012 [P] Create `app/static/style.css` with minimal base styling.
- [X] T013 [P] Create `app/static/app.js` as an empty/placeholder script (behavior added in Phase 4).
- [X] T014 [P] Create `Dockerfile` (python base image, install `requirements.txt`, run `uvicorn app.main:app --host 0.0.0.0 --port 8000`).
- [X] T015 [P] Create `docker-compose.yml` defining service `app` with container name `oracle-clickhouse-migration-app`, `env_file: .env`, port mapping `8000:8000`, build context `.`.
- [X] T016 [P] Create `tests/test_config.py` asserting `app.config` loads settings and that `TARGET_DATABASE == "oracle_migration_hazem"`.

**Acceptance criteria**: app starts locally and via Docker Compose; `/` serves the page; `/api/health` returns success; `.env` git-ignored; no hardcoded credentials. **Manual test**: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`; `curl http://localhost:8000/api/health`; `docker compose up -d --build`; `git check-ignore .env`. **Stop point**: confirm app starts before Phase 2.

---

## Phase 2: Database Connection Health Checks

**Goal**: Env-based Oracle + ClickHouse clients and health endpoints; confirm connectivity, Oracle metadata read, and target-DB presence (no auto-create).

- [X] T017 Create `app/db/oracle_client.py`: connection factory using `oracledb` reading creds from `app/config.py`; a `run_select(sql, binds)` helper that rejects any non-`SELECT`/`WITH` statement (SELECT-only guard); never log credentials.
- [X] T018 Add to `app/db/oracle_client.py` a `health()` function running `SELECT 1 FROM dual` and `SELECT COUNT(*) FROM all_tables`, returning connect + metadata-readable booleans.
- [X] T019 Create `app/db/clickhouse_client.py`: `clickhouse-connect` client from `app/config.py`; helper `target_database_exists()` querying `system.databases WHERE name = 'oracle_migration_hazem'`; never auto-create unless `CLICKHOUSE_ALLOW_CREATE_DATABASE=true`; never log credentials.
- [X] T020 Add to `app/db/clickhouse_client.py` a `health()` function running `SELECT 1` and the target-DB existence check, returning connect + target-exists booleans.
- [X] T021 Update `app/config.py` to include `CLICKHOUSE_ALLOW_CREATE_DATABASE` (default `false`) and all Oracle/ClickHouse connection fields.
- [X] T022 Update `app/api/health_routes.py`: add `GET /api/health/oracle` → `{"status","database":"oracle","can_connect","can_read_metadata"}` and `GET /api/health/clickhouse` → `{"status","database":"clickhouse","can_connect","target_database":"oracle_migration_hazem","target_database_exists"}`; return clear, credential-free errors on failure.

**Acceptance criteria**: both health checks succeed; errors clear; no credentials in logs; still runs in Docker. **Manual test**: `curl /api/health/oracle`; `curl /api/health/clickhouse`; `docker logs oracle-clickhouse-migration-app` shows no secrets. **Stop point**: both health checks green before Phase 3.

---

## Phase 3: Oracle Metadata Discovery APIs

**Goal**: Backend discovery of schemas, tables, columns, partition/hash candidates — bind variables, metadata-validated.

- [X] T023 Create `app/services/metadata_service.py` with `list_schemas()` running `SELECT DISTINCT owner FROM all_tables ORDER BY owner` via the read-only client.
- [X] T024 Add `list_tables(schema)` to `app/services/metadata_service.py` running `SELECT table_name FROM all_tables WHERE owner = :schema_name ORDER BY table_name` (bind variable).
- [X] T025 Add `list_columns(schema, table)` to `app/services/metadata_service.py` selecting `column_name, data_type, data_length, data_precision, data_scale, nullable` from `all_tab_columns` (bind variables), ordered by `column_id`.
- [X] T026 Add `list_partition_candidates(schema, table)` to `app/services/metadata_service.py` filtering `data_type IN ('NUMBER','DATE') OR data_type LIKE 'TIMESTAMP%'` (bind variables).
- [X] T027 Add `schema_exists(schema)` and `table_exists(schema, table)` validation helpers to `app/services/metadata_service.py` (used to reject unknown inputs before any query that interpolates names).
- [X] T028 Create `app/api/oracle_routes.py` with `GET /api/oracle/schemas`, `GET /api/oracle/tables?schema=`, `GET /api/oracle/columns?schema=&table=`, `GET /api/oracle/partition-columns?schema=&table=`; validate inputs via T027; return controlled errors for unknown schema/table.
- [X] T029 Update `app/main.py` to include the oracle router from `app/api/oracle_routes.py`.

**Acceptance criteria**: all four endpoints return correct data; invalid schema/table → controlled error; injection-style input executes no dynamic SQL; Oracle read-only. **Manual test**: the four `curl` calls from `quickstart.md` plus `curl "…/api/oracle/tables?schema=CM%27--"` → controlled error. **Stop point**: metadata APIs work before Phase 4.

---

## Phase 4: GUI Dynamic Dropdowns

**Goal**: Interactive metadata-driven GUI; ClickHouse DB fixed and disabled.

- [X] T030 Update `app/templates/index.html` to add all GUI fields: Oracle Source Schema (select), Oracle Source Table (select), Partition/Hash Column (select), Worker Threads (number, default 8), ClickHouse Schema Destination (text), ClickHouse Database (text, value `oracle_migration_hazem`, `disabled`), Target Table Name (text), and a **Launch / Replicate (Full Load)** button. Add helper text near the button stating that launching performs an initial **full load**: it drops and recreates the target table, then loads the entire Oracle table (no append, no incremental). Include health-status indicators.
- [X] T031 Implement page-load logic in `app/static/app.js`: call `/api/health/oracle`, `/api/health/clickhouse`, and `/api/oracle/schemas`; render health and populate the schema dropdown.
- [X] T032 Implement schema-change handler in `app/static/app.js`: on schema select, call `/api/oracle/tables?schema=…`, refresh the table dropdown, and auto-fill ClickHouse Schema Destination with the selected schema.
- [X] T033 Implement table-change handler in `app/static/app.js`: on table select, call `/api/oracle/partition-columns?schema=…&table=…`, refresh the partition/hash dropdown, and auto-fill Target Table Name with the source table.
- [X] T033a Implement the Launch / Replicate button state in `app/static/app.js`: enable only when source schema, source table, and target table are set; on click, show a confirmation that the target table `oracle_migration_hazem.<schema>__<table>` will be **dropped and fully reloaded** before the POST (actual POST/polling wired in Phase 6).
- [X] T034 [P] Update `app/static/style.css` to style the form, health indicators, and the Launch / Replicate button.

**Acceptance criteria**: schemas load on open; schema change refreshes tables + auto-fills target schema; table change refreshes partition columns + auto-fills target table; CH database fixed/disabled; the Launch / Replicate button communicates full-load replace semantics. **Manual test**: browser + devtools confirm the three load calls; `curl -s http://localhost:8000/ | grep oracle_migration_hazem`; confirm button helper text mentions drop + full reload. **Stop point**: GUI dynamic behavior works before Phase 5.

---

## Phase 5: ClickHouse DDL Generation **(Critical DDL & Type-Mapping Gate)**

**Goal**: The critical gate before any data movement — a correct, framework-agnostic Oracle→ClickHouse type mapper, safe identifier quoting with unsafe-identifier rejection, target-DB enforcement, and a **drop-and-recreate** DDL pair (`DROP TABLE IF EXISTS` + `CREATE TABLE`, no `IF NOT EXISTS`) confined to `oracle_migration_hazem`; preview (with warnings) + execute. `app/services/ddl_mapper.py` MUST contain **no FastAPI imports** so a future Flask app can import it directly.

- [X] T035 Extend `app/services/metadata_service.py` `list_columns(schema, table)` to also select `char_length` and `char_used` from `all_tab_columns` (alongside the existing `column_name, data_type, data_length, data_precision, data_scale, nullable`), and pass them through `GET /api/oracle/columns` so the mapper receives the full metadata set. (Minimal, additive change required by the mapper.)
- [X] T036 Create `app/services/ddl_mapper.py` with `map_oracle_type(col)` implementing the **authoritative refined mapping** over the metadata fields (`data_type`, `data_precision`, `data_scale`, `nullable`, `char_length`, `char_used`): `NUMBER(p,0) p<=18`→`Nullable(Int64)`; `NUMBER(p,0) 18<p<=76`→`Nullable(Decimal(p,0))`; `NUMBER(p,s) s>0 and p<=76`→`Nullable(Decimal(p,s))`; `NUMBER` unknown precision/scale→`Nullable(Float64)`; `FLOAT`→`Nullable(Float64)`; `BINARY_FLOAT`→`Nullable(Float32)`; `BINARY_DOUBLE`→`Nullable(Float64)`; `VARCHAR2`/`NVARCHAR2`/`CHAR`/`NCHAR`/`CLOB`/`NCLOB`→`Nullable(String)`; `DATE`→`Nullable(DateTime)`; `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE`/`TIMESTAMP WITH LOCAL TIME ZONE`→`Nullable(DateTime64(6))`; `RAW`/`BLOB`→`Nullable(String)`. **No FastAPI imports.**
- [X] T037 Add unsupported-type handling to `app/services/ddl_mapper.py`: any unrecognized Oracle type falls back to `Nullable(String)` **and** appends a structured warning (`{column, oracle_type, mapped_to}`); the mapper never raises on an unknown type. Provide `map_columns(columns) -> (column_defs, warnings)` that maps a full column list and collects all warnings.
- [X] T038 Add `quote_identifier(name)` to `app/services/ddl_mapper.py`: backtick-quote every ClickHouse identifier (database/table/column) and **reject unsafe identifiers** (empty, containing backticks, control chars, or other unsafe characters) by raising a clear `ValueError` — no raw/odd identifier may reach the DDL.
- [X] T039 Add `safe_target_name(schema, table)` to `app/services/ddl_mapper.py` producing `<source_schema>__<source_table>` and quoting it via `quote_identifier` (rejecting unsafe parts).
- [X] T040 Add a target-database guard `assert_target_database(db)` to `app/services/ddl_mapper.py` that enforces `db == "oracle_migration_hazem"` and rejects any other value (used by both the DDL builders and `execute_ddl`).
- [X] T041 Add `build_drop_ddl(schema, table)` and `build_create_ddl(schema, table, columns, order_by)` to `app/services/ddl_mapper.py`: drop emits `DROP TABLE IF EXISTS oracle_migration_hazem.<name>`; create emits `CREATE TABLE oracle_migration_hazem.<name> (...) ENGINE = MergeTree ORDER BY <order_by>` with **no `IF NOT EXISTS`**. ORDER BY logic: use `ORDER BY <col>` only when the chosen order column is supported and **non-nullable**, otherwise `ORDER BY tuple()` (never order by a Nullable column). Both builders call `assert_target_database`.
- [X] T042 Add `build_recreate_ddl(schema, table, columns, order_by)` to `app/services/ddl_mapper.py` returning the ordered pair `[drop_ddl, create_ddl]` (plus warnings), used by both the preview endpoint and the migration engine so drop-then-create is generated in one place.
- [X] T043 Add `execute_ddl(ddl)` to `app/db/clickhouse_client.py` that runs only `DROP TABLE IF EXISTS` or `CREATE TABLE` statements and rejects any target database other than `oracle_migration_hazem` (guard applies to both statement kinds).
- [X] T044 Create `app/api/clickhouse_routes.py` (**thin handlers only**) with `POST /api/clickhouse/create-table-preview` (returns `drop_ddl`, `create_ddl`, and the `warnings` list, no execution) and `POST /api/clickhouse/create-table` (executes DROP then CREATE, yielding a fresh empty table even on re-run, returns `warnings`); reject non-target databases with a 400. Handlers delegate all logic to `ddl_mapper`/`clickhouse_client`.
- [X] T045 Update `app/main.py` to include the clickhouse router from `app/api/clickhouse_routes.py`.
- [X] T046 [P] Create `tests/test_ddl_mapper.py` with comprehensive assertions: `NUMBER(p,0) p<=18`→`Nullable(Int64)`; `NUMBER(p,0) 18<p<=76`→`Nullable(Decimal(p,0))`; `NUMBER(p,s) s>0 p<=76`→`Nullable(Decimal(p,s))`; `NUMBER` unknown→`Nullable(Float64)`; `FLOAT`→`Nullable(Float64)`; `BINARY_FLOAT`→`Nullable(Float32)`; `BINARY_DOUBLE`→`Nullable(Float64)`; `VARCHAR2`/`NVARCHAR2`/`CHAR`/`NCHAR`/`CLOB`/`NCLOB`→`Nullable(String)`; `DATE`→`Nullable(DateTime)`; all TIMESTAMP variants→`Nullable(DateTime64(6))`; `RAW`/`BLOB`→`Nullable(String)`; unsupported type→`Nullable(String)` **with a warning emitted**; nullable vs non-nullable column handling (and ORDER BY refusing a Nullable column); unsafe identifiers rejected by `quote_identifier`; the `<schema>__<table>` naming; the generated DDL is a DROP-then-CREATE pair (CREATE has no `IF NOT EXISTS`); and a non-`oracle_migration_hazem` target rejected for both DROP and CREATE.

**Acceptance criteria**: every mapping branch (incl. Decimal boundaries, TIMESTAMP-with-zone, RAW/BLOB, NCLOB) is covered by tests; preview shows the drop+create pair and any warnings; executing it produces a fresh empty table even on a second run; both DROP and CREATE act only in `oracle_migration_hazem`; Oracle unmodified; unsupported types fall back to `Nullable(String)` + warning and don't crash; unsafe identifiers rejected; `ddl_mapper.py` imports no FastAPI; dangerous target rejected for both statements. **Manual test**: preview + create `curl` calls; run create twice and confirm no error and no leftover rows; negative `curl` with `"target_database":"default"` rejected; `grep -rn "fastapi" app/services/ddl_mapper.py` returns nothing; `pytest tests/test_ddl_mapper.py`. **Stop point**: drop-and-recreate table creation works on first run and re-run before Phase 6.

---

## Phase 6: Single-Thread Batch Migration **(Performance + Live Progress)**

**Goal**: First working end-to-end **initial full load** (drop → create → full extract → full insert), memory-safe and batched, single-threaded; background job returning `job_id` immediately; live progress polling. Engine is framework-agnostic (**no FastAPI imports**) so Flask can call it directly.

- [X] T047 Create `app/services/job_service.py` with an in-memory job registry: `create_job(...)`, `get_job(job_id)`, `update_job(job_id, **fields)`; job fields per `data-model.md` — identity/config (job_id, source_schema, source_table, target_database, target_table, status) **plus the full progress set**: `total_rows`, `processed_rows`, `inserted_rows`, `remaining_rows`, `batches_completed`, `current_batch`, `progress_percent`, `rows_per_second`, `elapsed_seconds`, `started_at`, `finished_at`, `duration_seconds`, `error_message`; status enum PENDING/RUNNING/SUCCESS/FAILED/CANCELLED. **No FastAPI imports.**
- [X] T048 Create `app/services/migration_service.py` with a framework-agnostic entry point `launch_initial_load(request, job_id)` (plain function/dataclass args, **no FastAPI types**): validate source schema/table via `metadata_service`, confirm target DB is `oracle_migration_hazem`, then **drop and recreate** the target table via `ddl_mapper.build_recreate_ddl` + `clickhouse_client.execute_ddl` (DROP IF EXISTS then CREATE) so each launch starts from a fresh empty table. Capture `total_rows` (source `SELECT COUNT(*)`) for progress math.
- [X] T049 Add the full-extraction batch copy loop to `app/services/migration_service.py` following the **mandatory performance rules**: open a read-only Oracle `SELECT <explicit columns>` cursor over the entire source table; set `cursor.arraysize` and `cursor.prefetchrows` (tuned to the batch size); read with `cursor.fetchmany(MIGRATION_BATCH_SIZE)`; batch-insert each chunk into ClickHouse with **explicit column names in a stable column order** (the order returned by the column metadata query, identical on SELECT and INSERT). **Never** use `pandas.read_sql`, **never** `cursor.fetchall()`, **never** row-by-row inserts; never filter by watermark/last-loaded value (full load every run).
- [X] T050 Add live progress tracking to `app/services/migration_service.py`, updated after every batch: `processed_rows`, `inserted_rows`, `remaining_rows` (= `total_rows - processed_rows`), `batches_completed`, `current_batch`, `elapsed_seconds`, `rows_per_second` (processed/elapsed), and `progress_percent` (processed/total × 100).
- [X] T051 Add status transitions + timing to `app/services/migration_service.py`: set RUNNING on start, SUCCESS on completion, FAILED with `error_message` on exception; record `started_at`/`finished_at`/`duration_seconds`.
- [X] T052 Add a re-run/idempotency guarantee to `app/services/migration_service.py`: because the table is dropped and recreated before load, re-launching the same source schema/table yields the **latest-only** result (e.g. 100 source rows → 100 target rows on every run, never doubled). No append, dedup, merge, upsert, staging swap, or skip-existing logic.
- [X] T053 Create `app/api/migration_routes.py` as **thin handlers only**: `POST /api/migrations` (validate input shape, create job, hand off to `migration_service.launch_initial_load` via FastAPI BackgroundTasks, **return `job_id` immediately with 202**), `GET /api/migrations/{job_id}` (full record), `GET /api/migrations/{job_id}/status` (returns the live overall-progress fields: status, total/processed/inserted/remaining rows, progress_percent, batches_completed, current_batch, rows_per_second, elapsed_seconds, error_message). No migration/DDL/DB logic in this file — only request parsing and service calls.
- [X] T054 Update `app/main.py` to include the migration router from `app/api/migration_routes.py`.
- [X] T055 Update `app/static/app.js` to wire the Launch / Replicate button to `POST /api/migrations` (after the drop+reload confirmation from T033a), then **poll `GET /api/migrations/{job_id}/status` every 1–3 seconds** and **stop polling when status is SUCCESS, FAILED, or CANCELLED**.
- [X] T056 Build the **live overall-progress UI** in `app/templates/index.html` + `app/static/app.js`: an overall progress bar (0–100% from `progress_percent`), job status text, processed/total rows, inserted rows, remaining rows, elapsed time, rows per second, current batch number, and an error message area shown on FAILED.

**Acceptance criteria**: launch from GUI; job id immediate; target table is dropped and recreated before load; full data loads in batches (no `read_sql`/`fetchall`/row-by-row; explicit stable column order); the live UI shows progress bar, status, total/processed/inserted/remaining rows, elapsed time, rows/sec, current batch, and error-on-failure; polling stops on terminal status; **re-running the same table yields the same row count, not a doubled count**; Oracle read-only; writes only to target; `migration_service.py`/`job_service.py` contain no FastAPI imports. **Manual test**: the `POST /api/migrations` + status `curl` sequence from `quickstart.md`; re-POST the same table and confirm target count is unchanged; `grep -rn "fastapi" app/services/` returns nothing. **Stop point**: one full table copies successfully AND a second run leaves the target row count unchanged, before Phase 7.

---

## Phase 7: Parallel Migration Engine **(Per-Worker Progress + Parallel Mode Selector)**

**Goal**: Faster **full load** via parallel extraction (numeric-range, date-range, hash-fallback); default 8 workers, max 16; latest-only replace preserved; per-worker + overall progress tracked and shown in the GUI. Expose the technique through a user-facing **Parallel Mode** dropdown (`Auto`/`Numeric Range`/`Date Range`/`Hash`): the backend honors a concrete mode (validated against the selected column's Oracle datatype) or resolves `Auto` from that datatype, stores `requested_parallel_mode`/`resolved_parallel_mode` on the job, and surfaces both in `/status` and the GUI (overall + per-worker).

**Kept guarantees (unchanged):** initial full load only; single drop/create per job; workers only INSERT into the fresh table; no CDC/incremental/watermark/staging/append; Oracle read-only; ClickHouse writes only to `oracle_migration_hazem`; service layer importable from Flask (no FastAPI imports); routes stay thin. The resolved user-facing mode maps onto the existing internal `partition_mode` (`numeric_range`→`numeric`, `date_range`→`date`, `hash`→`hash`).

### Parallel engine (sequential — same files)

- [X] T057 Refactor `app/services/migration_service.py` so the **drop + create runs exactly once per job** (before any worker is dispatched); workers only `INSERT` into the freshly created target and never re-drop or re-create it mid-job. Both single-thread and parallel paths share this one-time recreate step.
- [X] T058 Add `compute_numeric_ranges(min, max, workers)` to `app/services/migration_service.py`: half-open `[start, end)` slices with the final slice inclusive of max; no overlap, no gaps (union = full table).
- [X] T059 Add `compute_date_ranges(min_ts, max_ts, workers)` to `app/services/migration_service.py`: split the time span into worker ranges (final inclusive); no overlap, no gaps (union = full table).
- [X] T060 Add per-worker extraction to `app/services/migration_service.py` following the same performance rules as Phase 6 (`arraysize`/`prefetchrows`, `fetchmany`, batch insert, explicit/stable column order): numeric/date use bounded `SELECT <cols> ... WHERE col >= :start AND col < :end` (bind vars); hash mode uses `WHERE MOD(ORA_HASH(col), :workers) = :id`. Each partition covers part of the full table exactly once — no skip-existing, no dedup.
- [X] T061 Add a **per-worker progress registry** to `app/services/job_service.py` (a `workers` list on the job), each entry tracking: `worker_id`, `partition_mode`, `partition_column`, `range_start`, `range_end`, `status`, `processed_rows`, `inserted_rows`, `batches_completed`, `rows_per_second`, `error_message`; aggregate workers' `processed_rows`/`inserted_rows` into the job totals and recompute overall `progress_percent`/`rows_per_second`.
- [X] T062 Add a worker pool runner `run_parallel(job_id, request)` to `app/services/migration_service.py`: dispatch workers (after the one-time recreate from T057), update each worker's progress entry, aggregate into job totals, and set job FAILED (surfacing that worker's `error_message`) if any worker raises. No FastAPI imports.
- [X] T063 Update `app/config.py` / `app/services/migration_service.py` to read `MIGRATION_DEFAULT_WORKERS` (default 8) and clamp requested workers to a max of 16.
- [X] T064 Update `app/api/migration_routes.py` (thin) to accept and validate `workers`, `partition_column`, and `partition_mode` (`single`|`numeric`|`date`|`hash`), route to the single vs parallel runner, and make `GET /api/migrations/{job_id}/status` return the **`workers` array** (per-worker fields) alongside the overall progress.
- [X] T065 Add a **per-worker progress table/cards** to `app/templates/index.html` + `app/static/app.js`: render one row/card per worker (worker_id, partition_mode, partition_column, range_start–range_end, status, processed_rows, inserted_rows, batches_completed, rows_per_second, error_message), updated from the `workers` array on each poll, alongside the overall progress bar.
- [X] T066 [P] Create `tests/test_range_split.py` asserting `compute_numeric_ranges` and `compute_date_ranges` produce contiguous, non-overlapping, fully-covering ranges for various worker counts.

### Parallel Mode selector (additive — reuses the engine above)

> Reuses the Phase 7 engine unchanged: the resolved user-facing mode maps onto the existing internal `partition_mode` (`numeric_range`→`numeric`, `date_range`→`date`, `hash`→`hash`). These tasks add the user-facing selector, Auto resolution, datatype validation, and requested/resolved tracking on top of the engine tasks above (T057–T066).

- [X] T086 Add a pure resolver+validator `resolve_parallel_mode(parallel_mode, partition_column, column_metadata, workers)` to `app/services/migration_service.py` (no FastAPI imports): accepts `parallel_mode` ∈ `auto`|`numeric_range`|`date_range`|`hash`; reads the selected column's datatype from Oracle column metadata (`all_tab_columns`, read-only — never trusted from the client); returns the concrete resolved mode (`numeric_range`|`date_range`|`hash`, or `single` when `workers == 1`) or raises a controlled validation error. **Auto** resolution: `NUMBER`→`numeric_range`, `DATE`/`TIMESTAMP%`→`date_range`, any other valid selected column→`hash`. Map the resolved mode onto the existing internal `partition_mode` and feed the Phase 7 engine (T057–T066).
- [X] T087 In `resolve_parallel_mode` (T086) enforce explicit-mode datatype validation, raising a clear error (naming the chosen mode, the column, and its datatype) **before** any job is created: `numeric_range` requires a `NUMBER` column; `date_range` requires a `DATE`/`TIMESTAMP%` column; `hash` requires a selected column (any supported partition-candidate type) and **may override Auto even for NUMBER/DATE columns**; `auto` with no usable column (and `workers > 1`) returns a clear "a partition/hash column is required for parallel execution" error. An unknown `parallel_mode` value is rejected.
- [X] T088 Add the `workers == 1` rule to `app/services/migration_service.py`: a parallel mode selected with a single worker is **allowed** (runs the proven single-thread path, `resolved_parallel_mode` reported as `single`) and is never a hard error solely for that reason; surface a warning that parallel mode only takes effect when `workers > 1`. Keep the existing clamp of requested workers to max 16 (T063).
- [X] T089 Extend the job record in `app/services/job_service.py` to store and expose `requested_parallel_mode` (exactly what the client sent; default `auto`) and `resolved_parallel_mode` (from T086); include both in `get_job` and `get_status` output, and add `resolved_parallel_mode` to each per-worker entry in the `workers` list (T061).
- [X] T090 Update `app/api/migration_routes.py` (thin only): add `parallel_mode: str = "auto"` to the `MigrationRequest` model; pass it to the service which calls `resolve_parallel_mode` **before** creating/launching the job (a validation error → controlled `400`, no job created); ensure `GET /api/migrations/{job_id}` and `GET /api/migrations/{job_id}/status` return `requested_parallel_mode` and `resolved_parallel_mode`, and that each item in the `workers` array includes the resolved mode. No business logic in this file.
- [X] T091 Add the **Parallel Mode** `<select>` to `app/templates/index.html` near the Partition/Hash Column and Worker Threads fields, with options `Auto`/`Numeric Range`/`Date Range`/`Hash` (default `Auto`, values `auto`/`numeric_range`/`date_range`/`hash`) and per-mode helper text: Auto chooses the mode from the column datatype; Numeric Range requires a NUMBER column; Date Range requires a DATE/TIMESTAMP column; Hash uses `ORA_HASH` and requires a selected column (and may force Hash even for NUMBER/DATE columns).
- [X] T092 Update `app/static/app.js`: include `parallel_mode` from the dropdown in the `POST /api/migrations` body; after launch display `requested_parallel_mode` and `resolved_parallel_mode` in the overall status area; render `resolved_parallel_mode` on each worker progress card/row; surface backend validation errors (datatype mismatch, missing column, unknown mode) and the single-worker warning.
- [X] T093 [P] Create `tests/test_parallel_mode.py` (pure-function tests over `resolve_parallel_mode`, no HTTP) covering every required case: auto + NUMBER → `numeric_range`; auto + DATE/TIMESTAMP → `date_range`; auto + VARCHAR2 (other valid column) → `hash`; explicit `numeric_range` rejects DATE and VARCHAR columns; explicit `date_range` rejects NUMBER and VARCHAR columns; explicit `hash` accepts a NUMBER column; explicit `hash` accepts a DATE column (if supported by the implementation); `hash` requires a selected column (missing column → clear error); auto with no resolvable mode returns a clear error; `workers == 1` is allowed (resolves to `single`); `workers > 16` is capped (or rejected) per config. Add a status-shape assertion that `requested_parallel_mode`, `resolved_parallel_mode`, and the `workers` array are present in the `/status` payload.

**Acceptance criteria (engine + selector)**: numeric/date/hash parallel work; target dropped+created exactly once per job (not per worker); worker failure → job FAILED with the worker error surfaced; per-worker and aggregate processed/inserted rows tracked; `/status` returns the `workers` array; the GUI shows per-worker cards plus the overall bar; no duplicate/missing ranges; re-running the same table still yields latest-only counts. **Parallel Mode dropdown** visible near Partition/Hash Column + Worker Threads with per-mode helper text; `POST /api/migrations` accepts `parallel_mode` (omitting → `auto`); Auto resolves by datatype (NUMBER→numeric_range, DATE/TIMESTAMP→date_range, else→hash); a mode conflicting with the column datatype (or `hash`/parallel `auto` with no usable column) returns a clear pre-launch `400` and creates no job; `requested_parallel_mode`/`resolved_parallel_mode` returned by `/status` and shown in the GUI (overall + per-worker); `workers=1` with a parallel mode is allowed/warned, never a hard error; workers above max still clamp to 16; Oracle read-only; writes only to `oracle_migration_hazem`; `grep -rn "fastapi" app/services/` still returns nothing. **Manual test**: parallel `POST /api/migrations` with `workers=8,parallel_mode=numeric_range`; poll `/status` and confirm a populated `workers` array with the resolved mode; `parallel_mode=auto` on a NUMBER column → `resolved_parallel_mode=numeric_range`; `parallel_mode=date_range` on a NUMBER column → `400`, no job; `parallel_mode=hash` with `partition_column=null` → `400`; re-run and confirm count unchanged; `pytest tests/test_range_split.py tests/test_parallel_mode.py`. **Stop point**: engine (numeric/date/hash) + selector (dropdown, Auto resolution, datatype validation, requested/resolved display, per-worker + overall progress) all tested on small + medium tables before Phase 8.

---

## Phase 8: Validation, Counts, and Reconciliation

**Goal**: Capture + compare source/target counts; surface match/mismatch in the job, the `/status` response, and the GUI; Oracle untouched.

- [X] T067 Add `count_source(schema, table)` to `app/services/migration_service.py` running read-only `SELECT COUNT(*) FROM <schema>.<table>`.
- [X] T068 Add `count_target(target_table)` to `app/services/migration_service.py` running `SELECT COUNT(*) FROM oracle_migration_hazem.<target_table>`.
- [X] T069 Extend job fields in `app/services/job_service.py` with `source_row_count`, `target_row_count`, `count_match`, `validation_status` (`NOT_STARTED`/`RUNNING`/`SUCCESS`/`FAILED`), and `validation_error_message`; compute after load completes. Because this is a full-load replace into a freshly created table, `count_match` is **exact equality** (target == source); any inequality is a hard validation failure.
- [X] T070 Update `app/api/migration_routes.py` (thin) to include the validation fields in **both** the full job record and `GET /api/migrations/{job_id}/status` (so a single poll returns overall progress + per-worker progress + validation).
- [X] T071 Update `app/static/app.js` and `app/templates/index.html` to display source/target counts and a clear match/mismatch indicator.

**Acceptance criteria**: counts captured; exact match shown in GUI; mismatch clearly flagged; `/status` returns the validation fields; re-running the same table reports the same source/target counts (no drift from duplication); Oracle unmodified. **Manual test**: `curl /api/migrations/{job_id}/status` shows the four validation fields with `count_match=true` on a good run; a second run reports identical counts. **Stop point**: reconciliation works before Phase 9.

---

## Phase 8.1: Performance Diagnostics and Migration Speed Optimization

**Goal**: Localize where migration time is actually spent (baseline ~29,792 rows / ~1496 s ≈ 19 rows/s in both single-thread and parallel mode) and apply bounded, behavior-preserving tuning. **Brownfield/additive** — these tasks only **add** diagnostics + safe tuning to the already-completed Phases 6–8 engine; they MUST NOT change business behavior (initial full load only; one drop + one create per job; full Oracle load; Oracle read-only; ClickHouse writes only to `oracle_migration_hazem`). The job diagnostics field is named `performance_diagnostics` (this refines the `diagnostics` block described in `plan.md`/`data-model.md`).

> **Diagnosis-first**: with `MIGRATION_BATCH_SIZE=100000` vs ~29,792 rows the load is a single batch/insert, so batch granularity is not the cause — the cost is per-cell/per-round-trip. Prime suspect is per-LOB locator reads in `migration_service._normalize_cell` (`.read()` per CLOB/BLOB/NCLOB cell) over a remote/VPN link; secondary is repeated fresh Oracle connections (COUNT, MIN/MAX, validation, per worker). Instrument first, then tune.

### Configuration (`app/config.py`)

- [X] T094 Add Phase 8.1 settings to `app/config.py` `Settings` + `get_settings()`: keep existing `migration_batch_size` (default 100000); add `oracle_arraysize`, `oracle_prefetchrows`, `clickhouse_insert_batch_size` (each reading its env var `ORACLE_ARRAYSIZE` / `ORACLE_PREFETCHROWS` / `CLICKHOUSE_INSERT_BATCH_SIZE` and **defaulting to `migration_batch_size`** when unset), and `migration_parallel_min_rows` (env `MIGRATION_PARALLEL_MIN_ROWS`, default 100000).
- [X] T095 Add positive-integer validation in `app/config.py` for `migration_batch_size`, `oracle_arraysize`, `oracle_prefetchrows`, `clickhouse_insert_batch_size`, and `migration_parallel_min_rows`: reject non-positive/non-integer values with a clear error (no secrets), so misconfiguration fails fast at settings load.

### Job diagnostics state (`app/services/job_service.py`)

- [X] T096 Add a `performance_diagnostics` dict to each job in `app/services/job_service.py` `create_job()` with timing fields initialized to 0.0: `ddl_duration_seconds`, `oracle_count_duration_seconds`, `range_discovery_duration_seconds`, `oracle_execute_duration_seconds`, `oracle_fetch_duration_seconds`, `row_conversion_duration_seconds`, `clickhouse_insert_duration_seconds`, `validation_duration_seconds`, `total_duration_seconds`; plus batch metrics `batch_size`, `batches_completed`, `average_rows_per_batch`, `average_seconds_per_batch`; and a `per_worker` list for parallel timings. Include it in `get_job`/`get_status`/`_public_job` output. No secrets stored.
- [X] T097 Add a `warnings` list field to each job in `app/services/job_service.py` (`create_job` + output in `get_job`/`get_status`), and a helper `add_warning(job_id, message)` that appends a credential-free message; expose `warnings` in both endpoints' payloads.

### Oracle read-only metadata helpers (`app/services/metadata_service.py`)

- [X] T098 [P] Add a read-only `detect_heavy_columns(schema, table)` helper to `app/services/metadata_service.py` that queries `all_tab_columns` (bind variables, SELECT-only) and returns the columns whose `data_type` is `CLOB`, `BLOB`, `NCLOB`, `LONG`, or `RAW`, plus very large `VARCHAR2`/`NVARCHAR2` (e.g. `char_length`/`data_length` above a threshold). Oracle stays read-only.
- [X] T099 [P] Add a read-only `is_column_indexed(schema, table, column)` helper to `app/services/metadata_service.py` that checks whether the column appears in `ALL_IND_COLUMNS` (`SELECT ... FROM all_ind_columns WHERE table_owner=:s AND table_name=:t AND column_name=:c`, bind variables, SELECT-only) and returns a boolean. **Never create an index; never modify Oracle.**

### Step instrumentation (`app/services/migration_service.py`)

- [X] T100 Instrument the single-thread/`_copy_batches` path in `app/services/migration_service.py` with `time.perf_counter`: time DDL drop+create (`ddl_duration_seconds`), source `COUNT` (`oracle_count_duration_seconds`), MIN/MAX discovery (`range_discovery_duration_seconds`), **Oracle `cursor.execute` separately from `fetchmany`** (`oracle_execute_duration_seconds` vs `oracle_fetch_duration_seconds`), **Python row conversion/`_normalize_batch` separately** (`row_conversion_duration_seconds`), and **ClickHouse insert separately** (`clickhouse_insert_duration_seconds`); accumulate into the job's `performance_diagnostics` and set `batch_size`, `batches_completed`, `average_rows_per_batch`, `average_seconds_per_batch`. Apply `oracle_arraysize`/`oracle_prefetchrows` to the cursor and `clickhouse_insert_batch_size` to insert chunking (from T094). No FastAPI imports.
- [X] T101 Add per-worker timing in `run_parallel`/`_run_worker` (`app/services/migration_service.py`): record each worker's execute/fetch/convert/insert seconds and batch counts into the job's `performance_diagnostics.per_worker` list, and **aggregate** worker timings into the overall `performance_diagnostics` totals (sum durations, recompute `batches_completed`/`average_*`). Reuse the same timing helper as T100.
- [X] T102 Update error handling in `app/services/migration_service.py` (`_safe_error_message` callers / worker + job failure paths) so failures include the **step name** (e.g. `oracle_fetch`, `clickhouse_insert`) while still redacting credentials via the existing secret-scrubbing; record `validation_duration_seconds` around `run_validation` and `total_duration_seconds` for the whole job. Keep the module free of FastAPI imports.
- [X] T103 In `app/services/migration_service.py`, before/at launch call `detect_heavy_columns` (T098) and, for range modes, `is_column_indexed` (T099); append warnings to the job (T097): a heavy-LOB warning ("Heavy LOB columns detected (…) — per-LOB reads may dominate fetch time") when heavy columns exist, and a non-indexed-range warning ("Range mode on a non-indexed column may be slow") when a numeric/date range mode targets an unindexed column. Warnings only — no behavior change, no Oracle modification.

### Safe tuning (`app/services/migration_service.py`)

- [X] T104 Add the small-table guard to `app/services/migration_service.py` (`_build_request`/`resolve_parallel_mode` path): when `total_rows < migration_parallel_min_rows` **and** the user did not explicitly force a parallel mode (i.e. `parallel_mode == "auto"`), run with `workers = 1` and add the warning "Small table detected; single-thread mode may be faster than parallel mode." An explicit `workers > 1` / explicit parallel mode is **still honored** (warning shown, never blocked).
- [X] T105 Refine `compute_numeric_ranges` in `app/services/migration_service.py` so that for `NUMBER` scale-0 (integer) partition columns the split boundaries are **integers** (no decimal boundaries for integer ID columns), while preserving the existing half-open ranges with a final inclusive range and full coverage with no gaps/overlap. (Pass column scale through from the resolver/metadata.)

### ClickHouse batch insert verification (`app/db/clickhouse_client.py` / `app/services/migration_service.py`)

- [X] T106 Verify and keep `app/db/clickhouse_client.insert_rows` as a **true batch insert** (single `client.insert(table, data, column_names, database)` per chunk — never row-by-row), preserving explicit column names in stable metadata order; ensure the caller in `_copy_batches` records rows-per-insert-batch and seconds-per-insert-batch into `performance_diagnostics` (feeds T100/T101). Document the confirmation in a brief code comment.

### API (`app/api/migration_routes.py` — thin wrappers)

- [X] T107 Ensure `GET /api/migrations/{job_id}` and `GET /api/migrations/{job_id}/status` in `app/api/migration_routes.py` return `performance_diagnostics` (overall + `per_worker`) and `warnings`. No business logic added in the route file.

### GUI (`app/templates/index.html` + `app/static/app.js`)

- [X] T108 Add a **Performance Diagnostics** section to `app/templates/index.html` and render it in `app/static/app.js` on each status poll: show total duration, Oracle count time, Oracle execute time, Oracle fetch time, row conversion time, ClickHouse insert time, validation time, batch size, average rows per batch, average seconds per batch, and the `warnings` list; in the per-worker table show per-worker timing when `performance_diagnostics.per_worker` is available.

### Tests (`tests/`)

- [X] T109 [P] Add a test to `tests/test_job_service.py` asserting a created job exposes the `performance_diagnostics` field with all timing keys (`ddl_duration_seconds`, `oracle_count_duration_seconds`, `range_discovery_duration_seconds`, `oracle_execute_duration_seconds`, `oracle_fetch_duration_seconds`, `row_conversion_duration_seconds`, `clickhouse_insert_duration_seconds`, `validation_duration_seconds`, `total_duration_seconds`) and batch-metric keys (`batch_size`, `batches_completed`, `average_rows_per_batch`, `average_seconds_per_batch`) present in `get_job`/`get_status` output.
- [X] T110 [P] Add a test to `tests/test_job_service.py` asserting the job exposes a `warnings` list (default empty) and that `add_warning` appends to it and surfaces in `get_status`.
- [X] T111 [P] Add a test to `tests/test_migration_service.py` for the small-table rule (T104): `total_rows < migration_parallel_min_rows` with `parallel_mode="auto"` resolves to `workers = 1` with the small-table warning; an explicit `workers > 1` / explicit parallel mode is preserved (warning present, not blocked).
- [X] T112 [P] Add a test to `tests/test_migration_service.py` for integer numeric range boundaries (T105): a `NUMBER` scale-0 column yields integer (non-decimal) boundaries, half-open ranges with a final inclusive range, and full coverage with no gaps/overlap.
- [X] T113 [P] Add a test (e.g. `tests/test_service_layer_framework_agnostic.py`) asserting `grep`-style that `app/services/*.py` and `app/db/*.py` contain no `import fastapi` / `from fastapi` (service modules stay framework-agnostic and Flask-importable).
- [X] T114 [P] Add a test to `tests/test_clickhouse_connection.py` asserting `clickhouse_client.insert_rows` performs a single batch `insert(...)` call for a multi-row batch (e.g. via a fake/mock client capturing one call with all rows) — i.e. it is batch-oriented, not row-by-row.

**Acceptance criteria**: both GET endpoints return `performance_diagnostics` (overall + per-worker) and `warnings`; the GUI shows the timing breakdown + warnings; logs identify the slow step without printing secrets; heavy-LOB and non-indexed-range warnings appear when applicable (no index created, Oracle never modified); small-table auto-downgrade to `workers=1` works (explicit parallel still honored); NUMBER scale-0 ranges use integer boundaries; ClickHouse insert stays a true batch insert; migration + validation still pass and re-runs stay latest-only; `grep -rn "fastapi" app/services/ app/db/` returns nothing. **Manual test**: run a migration, `curl /api/migrations/{job_id}/status | python -m json.tool` shows the diagnostics block + warnings; `docker logs … | grep -Ei "password|secret"` is clean; `pytest tests/test_migration_service.py tests/test_job_service.py tests/test_clickhouse_connection.py`. **Stop point**: timing breakdown localizes the slow step (API + GUI + logs) and bounded optimizations are in place before Phase 8.2.

---

## Phase 8.2: ClickHouse Insert Timeout, Backpressure, and Validation Optimization

**Goal**: Prevent ClickHouse HTTP insert timeouts on huge tables via env-driven client timeouts/compression, an insert-backpressure semaphore (independent of Oracle worker count), safer insert batching, fail-fast insert-timeout handling, default-off opt-in retry, and `fast`/`strict`/`none` validation — without changing business behavior. Additive on Phases 6–8.1; do not rewrite existing migration logic. (Maps PLAN.md §16.2 / plan.md "Phase 8.2".)

**Keep business behavior**: initial full load only; drop+create target once per job; full-load Oracle rows; validate Oracle count vs ClickHouse count; no CDC/incremental/watermark/staging/append/dedup; Oracle read-only; ClickHouse writes only to `oracle_migration_hazem`; services stay framework-agnostic; routes stay thin.

### Configuration (`app/config.py` + `.env.example`)

- [X] T115 Add Phase 8.2 settings to `app/config.py` `Settings` + `get_settings()` (each read from its env var, never hardcoded in service logic): `clickhouse_connect_timeout_seconds` (`CLICKHOUSE_CONNECT_TIMEOUT_SECONDS`, default 15), `clickhouse_send_receive_timeout_seconds` (`CLICKHOUSE_SEND_RECEIVE_TIMEOUT_SECONDS`, default 900), `clickhouse_insert_timeout_seconds` (`CLICKHOUSE_INSERT_TIMEOUT_SECONDS`, default 900), `clickhouse_compress` (`CLICKHOUSE_COMPRESS`, default true), `clickhouse_max_concurrent_inserts` (`CLICKHOUSE_MAX_CONCURRENT_INSERTS`, default 2), `clickhouse_insert_retry_attempts` (`CLICKHOUSE_INSERT_RETRY_ATTEMPTS`, default 0, may be zero), `clickhouse_insert_retry_backoff_seconds` (`CLICKHOUSE_INSERT_RETRY_BACKOFF_SECONDS`, default 2), `migration_max_workers` (`MIGRATION_MAX_WORKERS`, default 8), `validation_mode` (`VALIDATION_MODE`, default `fast`), `validation_timeout_seconds` (`VALIDATION_TIMEOUT_SECONDS`, default 600). Change `clickhouse_insert_batch_size` default to **25000** (still env-overridable via `CLICKHOUSE_INSERT_BATCH_SIZE`; supersedes the Phase 8.1 `= MIGRATION_BATCH_SIZE` default) and change `migration_default_workers` default to **4**. `MIGRATION_BATCH_SIZE` stays the Oracle fetch size.
- [X] T116 Add config validation in `app/config.py`: positive-integer checks (allowing `0` only for `clickhouse_insert_retry_attempts`) for all new numeric settings; reject `migration_max_workers > 16` (absolute hard cap reachable only when explicitly configured up to 16); validate `validation_mode ∈ {fast, strict, none}` and reject any other value with a clear, secret-free error so misconfiguration fails fast at settings load.
- [X] T117 [P] Add the Phase 8.2 variables with safe defaults (no secrets) to `.env.example` at repo root: `CLICKHOUSE_CONNECT_TIMEOUT_SECONDS=15`, `CLICKHOUSE_SEND_RECEIVE_TIMEOUT_SECONDS=900`, `CLICKHOUSE_INSERT_TIMEOUT_SECONDS=900`, `CLICKHOUSE_COMPRESS=true`, `CLICKHOUSE_MAX_CONCURRENT_INSERTS=2`, `CLICKHOUSE_INSERT_BATCH_SIZE=25000`, `CLICKHOUSE_INSERT_RETRY_ATTEMPTS=0`, `CLICKHOUSE_INSERT_RETRY_BACKOFF_SECONDS=2`, `MIGRATION_DEFAULT_WORKERS=4`, `MIGRATION_MAX_WORKERS=8`, `VALIDATION_MODE=fast`, `VALIDATION_TIMEOUT_SECONDS=600`.

### ClickHouse client (`app/db/clickhouse_client.py`)

- [X] T118 Update `get_client(...)` in `app/db/clickhouse_client.py` to pass `connect_timeout` (from `clickhouse_connect_timeout_seconds`) and `send_receive_timeout` (from `clickhouse_send_receive_timeout_seconds`) and `compress` (from `clickhouse_compress`) into `clickhouse_connect.get_client(...)`, **capability-guarded** (use `inspect`/`try` so older `clickhouse-connect` versions that lack a kwarg do not break). Never log credentials.
- [X] T119 In `app/db/clickhouse_client.insert_rows`, apply the per-insert timeout via `clickhouse_insert_timeout_seconds` as a query/insert setting **only when the installed driver supports it** (otherwise ignore, no crash); keep the existing target-database guard so all writes stay confined to `oracle_migration_hazem`; add a `ClickHouseInsertTimeoutError` class plus an `is_transient_connection_error(exc)` predicate that classifies HTTP "Connection aborted"/`TimeoutError`/timeout exceptions; raise `ClickHouseInsertTimeoutError` (with a credential-redacted message via `_safe_error_message`) on insert timeout so callers can fail-fast vs. opt-in retry.

### Insert backpressure + batching (`app/services/migration_service.py`)

- [X] T120 Add a process/job-wide `threading.BoundedSemaphore(settings.clickhouse_max_concurrent_inserts)` shared by all workers and pass it into the insert path; acquire it **immediately before** each `clickhouse_client.insert_rows` call and **release it in a `finally`** so a failed/timed-out insert never leaves it locked. Keep this semaphore **independent of the Oracle `ThreadPoolExecutor` worker count** (e.g. `workers=8`, max concurrent inserts `=2`). Measure the time spent blocked acquiring it and accumulate `insert_wait_seconds` into the job diagnostics (overall + per-worker). No FastAPI imports.
- [X] T121 In `_copy_batches` (`app/services/migration_service.py`) keep the Oracle fetch sized by `migration_batch_size`, split each fetched batch into `clickhouse_insert_batch_size` chunks via the existing `_chunk_rows`, and insert each chunk with **one true `client.insert` batch call** (never row-by-row). Track `clickhouse_insert_batch_size`, rows-per-insert-chunk, and seconds-per-insert-chunk into the diagnostics (extends T100/T106 instrumentation). Do not change extraction or DDL behavior.

### Timeout failure handling + retry (`app/services/migration_service.py` + `app/services/job_service.py`)

- [X] T122 Add a cooperative cancellation `threading.Event` per job (stored/threaded into the run) in `app/services/migration_service.py`. On a `ClickHouseInsertTimeoutError` (from T119): mark the worker `FAILED`, set the cancellation event, mark the **job `FAILED`**, and have every other worker check the event at the **next safe batch boundary** (before the next `fetchmany`/insert) in `_copy_batches`/`_run_worker` and stop cleanly. Single-thread path fails the job the same way. The event must also be honored by the single-thread loop.
- [X] T123 On insert-timeout failure, store a credential-free **insert-failure record** on the job via `app/services/job_service.py`: `failed_worker_id`, `failed_batch_number`, `range_start`, `range_end`, `inserted_rows before failure`, `exception_class`, and a redacted `exception_message`; set the job `error_message` so the GUI can render the exact text: `"ClickHouse insert timed out. Target table may be incomplete. Re-run after reducing batch size or worker concurrency."`
- [X] T124 Gate `run_validation` in `app/services/migration_service.py` so it is **not started** when the job failed due to an insert timeout (target treated as incomplete) — i.e. `run_initial_load` only calls validation on the success path.
- [X] T125 Implement opt-in retry in the insert path (`app/services/migration_service.py`): when `clickhouse_insert_retry_attempts > 0`, retry **only** errors for which `is_transient_connection_error` is true (T119), using exponential backoff seeded by `clickhouse_insert_retry_backoff_seconds`; never retry by default (`=0`). Count each retry into `clickhouse_insert_retries` and, when retries are enabled, append a diagnostics warning that "retrying an insert timeout can duplicate rows if ClickHouse already received the batch; full job restart (drop+recreate) is the safe recovery." Track `clickhouse_insert_timeout_count` and `clickhouse_insert_error_count`.

### Worker tuning (`app/services/migration_service.py`)

- [X] T126 Update `clamp_worker_count` in `app/services/migration_service.py` to clamp to `settings.migration_max_workers` (default 8) with the absolute ceiling `16` (reachable only when `MIGRATION_MAX_WORKERS` is explicitly configured up to 16), default unspecified workers to `migration_default_workers` (4), and emit a warning (via `add_warning`) when the requested worker count exceeds the safe max instead of silently inflating. Do not auto-increase workers to mask timeouts. Keep the Phase 8.1 small-table single-thread rule (T104) intact.

### Validation modes (`app/services/migration_service.py` + `app/services/job_service.py`)

- [X] T127 Add `ValidationStatus.SKIPPED` and `ValidationStatus.TIMEOUT` to the `ValidationStatus` enum in `app/services/job_service.py`.
- [X] T128 Implement `VALIDATION_MODE` in `run_validation` (`app/services/migration_service.py`): **fast** — reuse the Oracle source count captured at job start (the `total_rows` already computed in `run_initial_load`, passed through to validation) and run only the ClickHouse target `COUNT(*)`, comparing start-count vs target-count; **strict** — re-run Oracle `COUNT(*)` and ClickHouse `COUNT(*)` post-load and compare; **none** — skip counting and set `validation_status=SKIPPED` (job stays `SUCCESS`, `count_match=null`). Enforce `validation_timeout_seconds`: on overrun set `validation_status=TIMEOUT` with a clear message **without hiding a successful insert** (load stays `SUCCESS`). Validation runs only `SELECT COUNT(*)` and never modifies Oracle or ClickHouse. Record `validation_mode` and validation timing into the diagnostics.

### Job diagnostics state (`app/services/job_service.py`)

- [X] T129 Extend the job `performance_diagnostics` block (init in `create_job`, surfaced in `get_job`/`get_status`/`_public_job`) with the Phase 8.2 fields, all credential-free: `clickhouse_insert_batch_size`, `max_concurrent_clickhouse_inserts`, `insert_wait_seconds`, `clickhouse_insert_timeout_count`, `clickhouse_insert_retries`, `clickhouse_insert_error_count`, `validation_mode`, `validation_timeout_seconds`, plus the insert-failure record (T123). Track both the Oracle fetch batch size and the ClickHouse insert batch size side by side.

### API (`app/api/migration_routes.py` — thin wrappers)

- [X] T130 Ensure `GET /api/migrations/{job_id}` and `GET /api/migrations/{job_id}/status` in `app/api/migration_routes.py` return the new diagnostics fields (`clickhouse_insert_batch_size`, `max_concurrent_clickhouse_inserts`, `insert_wait_seconds`, `clickhouse_insert_timeout_count`, `clickhouse_insert_retries`, `clickhouse_insert_error_count`, `validation_mode`, `validation_timeout_seconds`), the existing `validation_status` and `warnings`, and the insert-failure record. No business logic added in the route file.

### GUI (`app/templates/index.html` + `app/static/app.js`)

- [X] T131 Add a **ClickHouse Insert Tuning** section to `app/templates/index.html` and render it in `app/static/app.js` on each status poll, showing: insert batch size, max concurrent ClickHouse inserts, insert wait time, insert timeout count, retry count, validation mode, and validation timeout. Keep the existing progress bar, per-worker table, Performance Diagnostics, and validation displays.
- [X] T132 In `app/static/app.js`/`app/templates/index.html`, on an insert-timeout failure show the exact message `"ClickHouse insert timed out. Target table may be incomplete. Re-run after reducing batch size or worker concurrency."` plus a suggested-action list (reduce `CLICKHOUSE_INSERT_BATCH_SIZE`; reduce `CLICKHOUSE_MAX_CONCURRENT_INSERTS`; reduce worker count; increase ClickHouse timeout only after reducing pressure). Add the helper text near Worker Threads: "For huge tables, start with 4 workers and 25k insert batch size. Increase only after checking diagnostics." and show a recommended worker count / warning when the requested workers exceed the safe max.

### Tests (`tests/`)

- [X] T133 [P] Add tests to `tests/test_config.py`: Phase 8.2 defaults parse correctly (timeouts 15/900/900, `CLICKHOUSE_COMPRESS=true`, `CLICKHOUSE_MAX_CONCURRENT_INSERTS=2`, `CLICKHOUSE_INSERT_BATCH_SIZE=25000`, retry 0/backoff 2, workers 4/max 8, `VALIDATION_MODE=fast`, `VALIDATION_TIMEOUT_SECONDS=600`); and invalid values are rejected (non-positive integers, `migration_max_workers > 16`, `VALIDATION_MODE=bogus`).
- [X] T134 [P] Add a test to `tests/test_clickhouse_connection.py` asserting the ClickHouse client receives the configured `connect_timeout` / `send_receive_timeout` / `compress` (capture kwargs via a fake `clickhouse_connect.get_client`), tolerating capability-guarded omission on older drivers.
- [X] T135 [P] Add a test to `tests/test_migration_service.py` asserting the insert semaphore limits concurrency to `clickhouse_max_concurrent_inserts` (observed max concurrent inserts ≤ configured value) while more Oracle workers run, and that the semaphore is released after a failing insert.
- [X] T136 [P] Add a test to `tests/test_migration_service.py` asserting a `ClickHouseInsertTimeoutError` marks the worker and the job `FAILED`, stores the insert-failure record, and that validation is **not** run.
- [X] T137 [P] Add a test to `tests/test_migration_service.py` asserting the cancellation event set on one worker's insert timeout stops other workers at the next safe batch boundary.
- [X] T138 [P] Add tests to `tests/test_migration_service.py` for validation modes: **fast** reuses the start-of-job Oracle count and does **not** re-run Oracle `COUNT(*)`; **strict** re-runs Oracle `COUNT(*)`; **none** skips counting and sets `validation_status=SKIPPED`.
- [X] T139 [P] Extend `tests/test_service_layer_framework_agnostic.py` to confirm `app/services/*.py` and `app/db/*.py` still contain no `import fastapi` / `from fastapi` after Phase 8.2.
- [X] T140 [P] Add a test asserting Phase 8.2 ClickHouse writes stay restricted to `oracle_migration_hazem` (insert/count/DDL helpers reject any other target database), guarding the new timeout/retry/semaphore paths.

**Acceptance criteria**: config parses all new settings and rejects invalid ones (`VALIDATION_MODE`, over-cap workers, bad integers); the client uses configured connect/send-receive/compress (and insert timeout where supported); the insert semaphore bounds concurrent inserts while Oracle worker concurrency stays independent and is always released; an insert timeout fails the worker+job, signals other workers to stop at a safe boundary, skips validation, stores the failure record, and surfaces the exact GUI message; retries are off by default and, when enabled, cover only transient connection errors with exponential backoff and a duplicate-risk warning; `fast`/`strict`/`none` validation behave as specified within `VALIDATION_TIMEOUT_SECONDS` and never modify Oracle/ClickHouse; both GET endpoints + GUI show all new diagnostics, the validation mode, and a recommended/warned worker count; services stay FastAPI-free and writes stay confined to `oracle_migration_hazem`. **Manual test**: `CLICKHOUSE_MAX_CONCURRENT_INSERTS=2` parallel `POST /api/migrations` with `workers=8`; `curl /api/migrations/{job_id}/status | python -m json.tool` shows `clickhouse_insert_*`, `max_concurrent_clickhouse_inserts`, `insert_wait_seconds`, `validation_mode`, `validation_timeout_seconds`; `VALIDATION_MODE=none` job reports `validation_status=SKIPPED`; `docker logs … | grep -Ei "password|secret"` is clean; `pytest tests/test_config.py tests/test_clickhouse_connection.py tests/test_migration_service.py tests/test_job_service.py tests/test_service_layer_framework_agnostic.py`. **Stop point**: timeouts configurable, semaphore bounds concurrency, insert timeout fails fast (no validation, clear message, stored failure record), retries off by default, the three validation modes work within their timeout, and the new diagnostics appear in the status API and GUI — before Phase 9.

---

## Phase 9: Final Docker Compose and Team Run

**Goal**: Fresh-clone runnable with one command; complete README.

- [ ] T072 Finalize `Dockerfile` (pinned base image, clean layer for `requirements.txt`, correct uvicorn entrypoint) at repo root.
- [ ] T073 Finalize `docker-compose.yml` (container name `oracle-clickhouse-migration-app`, `env_file: .env`, `8000:8000`, restart policy) at repo root.
- [ ] T074 [P] Finalize `.env.example` at repo root: complete placeholder set, no real secrets.
- [ ] T075 Write `README.md` at repo root with all required sections: project overview, prerequisites, VPN requirement, `.env` setup, `docker compose up -d --build`, health-check commands, how to use the GUI, Oracle troubleshooting, ClickHouse troubleshooting, and Security notes (read-only Oracle, fixed target DB, env-only secrets).
- [ ] T076 [P] Add an **"Initial full load only"** section to `README.md` documenting: each Launch / Replicate drops and recreates the target then reloads the full Oracle table (latest-only, no append/incremental); and the explicit out-of-scope list (CDC, incremental, watermark, dedup, merge/upsert, staging swap, skip-existing) with a note that CDC/incremental are owned by another team.
- [ ] T077 [P] Add a **"Flask integration"** section to `README.md` showing the service layer is framework-agnostic and importable, with the example `from app.services.migration_service import launch_initial_load` and `from app.services.metadata_service import get_oracle_tables`, and a note that FastAPI route files are thin wrappers containing no business logic.

**Acceptance criteria**: fresh clone + `.env` runs via compose; health + GUI + full-load migration work (re-run stays latest-only); README clear and documents both the full-load-only scope and the Flask integration path. **Manual test**: `cp .env.example .env` (fill locally), `docker compose up -d --build`, health `curl`s, and `git status` confirms `.env` untracked; secret-scan grep over Dockerfile/compose/README is clean; README contains the `launch_initial_load` import example. **Stop point**: teammate can run unaided before Phase 10.

---

## Phase 10: Hardening and Production Readiness

**Goal**: Access protection, auditability, traceable failures, secret-free structured logs, cancel + confirmation.

- [ ] T078 Create `app/api/auth.py` and wire into `app/main.py`: basic GUI access protection (e.g., simple auth dependency); credentials sourced only from environment.
- [ ] T079 Add a persistent migration audit record in `app/services/job_service.py` (audit table created only inside `oracle_migration_hazem`, or an app-side durable store); each record captures the full-load drop+create+reload (source/target, row counts, status, timings); never store secrets.
- [ ] T080 Add cancel support: `POST /api/migrations/{job_id}/cancel` in `app/api/migration_routes.py` transitioning a RUNNING job toward CANCELLED, plus cooperative cancellation in `app/services/migration_service.py`.
- [ ] T081 [P] Add retry policy, timeout settings, and a max row/table-size warning to `app/services/migration_service.py`.
- [ ] T082 [P] Create `app/services/report.py` for a downloadable migration report; add a route in `app/api/migration_routes.py`.
- [ ] T083 [P] Add structured JSON logging configuration (no secrets) in `app/main.py`/`app/config.py` and app-level rate limiting.
- [ ] T084 Add a pre-migration confirmation popup in `app/static/app.js` / `app/templates/index.html` before launching a job that explicitly warns the target table will be **dropped and fully reloaded** (destructive full-load replace) and names the target `oracle_migration_hazem.<schema>__<table>`.
- [ ] T085 [P] Add a "Production deployment notes" section to `README.md` (auth, audit, logging, rate limits, deployment).

**Acceptance criteria**: GUI access-protected; migrations auditable; failures traceable; no secrets in logs; deployment notes documented. **Manual test**: `curl -i http://localhost:8000/` requires auth; `POST /api/migrations/{job_id}/cancel`; `docker logs … | grep -Ei "password|secret"` is clean. **Stop point**: final phase — project complete per PLAN.md §21.

---

## Dependencies & Execution Order

### Phase order (sequential — Constitution P-IV)

Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 8.1 → 8.2 → 9 → 10. **Do not start a phase until the prior phase's acceptance criteria pass and its Stop point is satisfied.**

### Key cross-phase dependencies

- Phase 2 (clients) blocks Phases 3, 5, 6 (all need Oracle/ClickHouse access).
- Phase 3 (metadata) blocks Phase 4 (GUI populates from it) and Phase 5/6 (validation of names).
- Phase 5 (DDL drop+create) blocks Phase 6 (full-load engine drops and recreates the target via `build_recreate_ddl`); T035 (metadata `char_length`/`char_used`) precedes the mapper (T036).
- Phase 6 (single-thread full load) blocks Phase 7 (parallel only after single-thread is proven — P-V); Phase 7 reuses the one-time recreate step (T057).
- Within Phase 7, the Parallel Mode selector tasks (T086–T093) are additive on the engine tasks (T057–T066): the resolver maps the resolved mode onto the engine's `partition_mode`, so T057–T066 land before (or alongside) T086–T093.
- Phase 7 (engine + selector) and Phase 6 precede Phase 8 (validation runs after load).
- Phase 8.1 (T094–T114) is **additive on Phases 6–8**: config (T094–T095) and job state (T096–T097) come first; metadata helpers (T098–T099) are independent; instrumentation (T100–T102) precedes warning emission (T103) and the GUI (T108); tuning (T104–T105) and the insert check (T106) are independent of instrumentation; API (T107) after job state; tests (T109–T114) follow their targets.
- Phase 8.2 (T115–T140) is **additive on Phases 6–8.1** and must not rewrite migration logic: config (T115–T117) comes first; the ClickHouse client changes (T118–T119) gate the backpressure/batching (T120–T121), failure handling + retry (T122–T125), and worker tuning (T126); validation modes (T127–T128) depend on the client/diagnostics; the diagnostics state (T129) precedes the API (T130) and GUI (T131–T132); tests (T133–T140) follow their targets. T119 (`ClickHouseInsertTimeoutError` + transient predicate) is a prerequisite for T122/T125/T136.

### Within-phase parallel opportunities

- **Phase 1**: T004, T005, T006, T007, T011, T012, T013, T014, T015, T016 are `[P]` (distinct files). T008→T009→T010 are sequential (config → router → app wiring).
- **Phase 3**: T023–T027 edit the same `metadata_service.py` (sequential); T028 depends on them; T029 after T028.
- **Phase 5**: T035 (metadata) first; T036–T042 edit the same `ddl_mapper.py` (sequential); T043–T045 wire client/route/app; T046 `[P]` (test file) parallel once the mapper exists.
- **Phase 6**: T047–T052 edit `job_service.py`/`migration_service.py` (sequential); routes (T053), app wiring (T054), and JS/GUI (T055, T056) follow.
- **Phase 7 (engine)**: T057–T063 edit `migration_service.py`/`job_service.py` (sequential); T064 (route) and T065 (GUI) follow; T066 `[P]` (test file) parallel with engine code.
- **Phase 7 (selector)**: T086–T088 edit `migration_service.py` (sequential), T089 edits `job_service.py`; T090 (route) follows; T091 (HTML) and T092 (JS) follow; T093 `[P]` (new test file) parallel with the resolver once T086–T088 exist.
- **Phase 8.1**: T098, T099 `[P]` (independent metadata helpers); T109–T114 `[P]` (distinct test files/cases). T094→T095 (config), T096→T097 (job state), and T100→T101→T102→T103 (instrumentation then warnings) are sequential (same files).
- **Phase 8.2**: T117 `[P]` (`.env.example`); T133–T140 `[P]` (distinct test files/cases). T115→T116 (config) and T118→T119 (client) are sequential (same files); T120→T121→T122→T123→T124→T125→T126 and T127→T128→T129 edit `migration_service.py`/`job_service.py` (sequential); T130 (route) and T131–T132 (GUI) follow.
- **Phase 9**: T076, T077 `[P]` (same README, append-only sections) after T075.

---

## Parallel Example: Phase 1 bootstrap

```bash
# These create distinct files and can be done together:
T004 requirements.txt
T005 .gitignore
T006 .env.example
T014 Dockerfile
T015 docker-compose.yml
T016 tests/test_config.py
```

---

## Implementation Strategy

### MVP scope

The MVP is the **single-table initial-full-load path (spec US1)** = Phases 0–6 plus Phase 8 validation. After Phase 6 you can full-load one table end to end through the GUI (drop → create → full extract → full insert, latest-only on re-run); Phase 8 adds the exact count check. Phases 7 (parallel), 9 (team packaging), and 10 (hardening) are incremental value on top.

### Incremental delivery

1. Phases 0–1 → app boots (local + Docker).
2. Phase 2 → connectivity proven.
3. Phases 3–4 → discovery + GUI.
4. Phase 5 → target tables.
5. Phase 6 → **MVP: first real migration**.
6. Phase 7 → speed for large tables.
7. Phase 8 → trust (reconciliation).
8. Phase 8.1 → diagnostics + bounded speed tuning.
9. Phase 8.2 → ClickHouse insert timeout resilience (backpressure, fail-fast, validation modes).
10. Phase 9 → team run.
11. Phase 10 → production hardening.

---

## Notes

- `[P]` = different files, no ordering dependency within the phase.
- Every task names an exact file path and is small enough to implement and test in isolation.
- Honor the per-phase Stop points; verify acceptance criteria (and the Constitution gates in `plan.md`) before advancing.
- Tests included only where the plan names a specific test file (`tests/test_config.py`, `tests/test_ddl_mapper.py`, `tests/test_range_split.py`); no broader TDD was requested.
