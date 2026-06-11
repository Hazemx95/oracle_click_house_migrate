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

**Traceability to spec.md user stories**: Phase 2 → US2 (connectivity/safety); Phases 3–8 → US1 (single-table full-load migration MVP); Phase 7 → US3 (parallel); Phase 8 → US4 (validation); Phase 9 → US5 (team run).

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

## Phase 5: ClickHouse DDL Generation

**Goal**: Type mapping, safe naming, and a **drop-and-recreate** DDL pair (`DROP TABLE IF EXISTS` + `CREATE TABLE`) confined to `oracle_migration_hazem`; preview + execute. No `IF NOT EXISTS` create — the full-load model replaces the table each run. Service-layer DDL functions are pure and FastAPI-free (Flask-reusable).

- [ ] T035 Create `app/services/ddl_mapper.py` with `map_oracle_type(col)` implementing the PLAN.md §13 mapping (NUMBER scale 0→`Nullable(Int64)`, NUMBER scale>0→`Nullable(Float64)`, VARCHAR2/NVARCHAR2/CHAR/NCHAR/CLOB→`Nullable(String)`, DATE→`Nullable(DateTime)`, TIMESTAMP%→`Nullable(DateTime64(6))`, FLOAT→`Nullable(Float64)`, BINARY_FLOAT→`Nullable(Float32)`, BINARY_DOUBLE→`Nullable(Float64)`, else→`Nullable(String)`). No FastAPI imports.
- [ ] T036 Add `safe_target_name(schema, table)` to `app/services/ddl_mapper.py` producing `<schema>__<table>` and sanitizing/quoting identifiers.
- [ ] T037 Add `build_drop_ddl(schema, table)` and `build_create_ddl(schema, table, columns, order_by)` to `app/services/ddl_mapper.py`: the drop builder emits `DROP TABLE IF EXISTS oracle_migration_hazem.<name>`; the create builder emits `CREATE TABLE oracle_migration_hazem.<name> (...) ENGINE = MergeTree ORDER BY <col|tuple()>` (no `IF NOT EXISTS`). Both include a guard that the database is exactly `oracle_migration_hazem`.
- [ ] T037a Add `build_recreate_ddl(schema, table, columns, order_by)` to `app/services/ddl_mapper.py` returning the ordered pair `[drop_ddl, create_ddl]` used by both the preview endpoint and the migration engine, so drop-then-create is generated in one place.
- [ ] T038 Add `execute_ddl(ddl)` to `app/db/clickhouse_client.py` that runs only `DROP TABLE IF EXISTS` or `CREATE TABLE` statements and rejects any target database other than `oracle_migration_hazem` (guard applies to both statement kinds).
- [ ] T039 Create `app/api/clickhouse_routes.py` (thin handlers only) with `POST /api/clickhouse/create-table-preview` (returns the DROP + CREATE pair as text, no execution) and `POST /api/clickhouse/create-table` (executes DROP then CREATE, yielding a fresh empty table even on re-run); reject non-target databases with a 400. Handlers delegate all logic to `ddl_mapper`/`clickhouse_client`.
- [ ] T040 Update `app/main.py` to include the clickhouse router from `app/api/clickhouse_routes.py`.
- [ ] T041 [P] Create `tests/test_ddl_mapper.py` asserting each type mapping, the `<schema>__<table>` naming, unsupported-type fallback to `Nullable(String)`, that the generated DDL is a DROP-then-CREATE pair (CREATE has no `IF NOT EXISTS`), and that a non-`oracle_migration_hazem` target is rejected for both DROP and CREATE.

**Acceptance criteria**: preview shows the drop+create pair; executing it produces a fresh empty table even on a second run; both DROP and CREATE act only in `oracle_migration_hazem`; Oracle unmodified; unsupported types don't crash; dangerous target rejected for both statements. **Manual test**: preview + create `curl` calls; run create twice and confirm no error and no leftover rows; negative `curl` with `"target_database":"default"` rejected; `pytest tests/test_ddl_mapper.py`. **Stop point**: drop-and-recreate table creation works on first run and re-run before Phase 6.

---

## Phase 6: Single-Thread Batch Migration

**Goal**: First working end-to-end **initial full load** (drop → create → full extract → full insert), memory-safe, single-threaded; background job + status polling. Engine is framework-agnostic so Flask can call it directly.

- [ ] T042 Create `app/services/job_service.py` with an in-memory job registry: `create_job(...)`, `get_job(job_id)`, `update_job(job_id, **fields)`; job fields per `data-model.md` (job_id, source_schema, source_table, target_database, target_table, status, total_rows, processed_rows, started_at, finished_at, duration_seconds, error_message); status enum PENDING/RUNNING/SUCCESS/FAILED/CANCELLED. No FastAPI imports.
- [ ] T043 Create `app/services/migration_service.py` with a framework-agnostic entry point `launch_initial_load(request, job_id)` (plain function/dataclass args, **no FastAPI types**): validate source schema/table via `metadata_service`, confirm target DB is `oracle_migration_hazem`, then **drop and recreate** the target table via `ddl_mapper.build_recreate_ddl` + `clickhouse_client.execute_ddl` (DROP IF EXISTS then CREATE) so each launch starts from a fresh empty table.
- [ ] T044 Add the full-extraction batch copy loop to `app/services/migration_service.py`: open an Oracle read-only `SELECT *` cursor over the entire source table, read with `cursor.fetchmany(MIGRATION_BATCH_SIZE)`, batch-insert each chunk into ClickHouse, update `processed_rows` after each batch; never load the whole table into memory; never filter by watermark/last-loaded value (full load every run).
- [ ] T045 Add status transitions + timing to `app/services/migration_service.py`: set RUNNING on start, SUCCESS on completion, FAILED with `error_message` on exception; record `started_at`/`finished_at`/`duration_seconds`.
- [ ] T045a Add a re-run/idempotency guarantee to `app/services/migration_service.py`: because the table is dropped and recreated before load, re-launching the same source schema/table yields the **latest-only** result (e.g. 100 source rows → 100 target rows on every run, never doubled). No append, dedup, merge, upsert, staging swap, or skip-existing logic.
- [ ] T046 Create `app/api/migration_routes.py` as **thin handlers only**: `POST /api/migrations` (validate input shape, create job, hand off to `migration_service.launch_initial_load` via FastAPI BackgroundTasks, return `job_id` immediately with 202), `GET /api/migrations/{job_id}` (full record), `GET /api/migrations/{job_id}/status` (lightweight progress). No migration/DDL/DB logic in this file — only request parsing and service calls.
- [ ] T047 Update `app/main.py` to include the migration router from `app/api/migration_routes.py`.
- [ ] T048 Update `app/static/app.js` to wire the Launch / Replicate button to `POST /api/migrations` (after the drop+reload confirmation from T033a) and poll `GET /api/migrations/{job_id}/status` to show progress.

**Acceptance criteria**: launch from GUI; job id immediate; target table is dropped and recreated before load; full data loads in batches; browser non-blocking; status updates; **re-running the same table yields the same row count, not a doubled count**; Oracle read-only; writes only to target; `migration_service.py`/`job_service.py` contain no FastAPI imports. **Manual test**: the `POST /api/migrations` + status `curl` sequence from `quickstart.md`; then re-POST the same table and confirm target count is unchanged; `grep -rn "fastapi" app/services/` returns nothing. **Stop point**: one full table copies successfully AND a second run leaves the target row count unchanged, before Phase 7.

---

## Phase 7: Parallel Migration Engine

**Goal**: Faster **full load** via parallel extraction (numeric-range, date-range, hash-fallback); default 8 workers, max 16; latest-only replace preserved.

- [ ] T048a Refactor `app/services/migration_service.py` so the **drop + create runs exactly once per job** (before any worker is dispatched); workers only `INSERT` into the freshly created target and never re-drop or re-create it mid-job. Both single-thread and parallel paths share this one-time recreate step.
- [ ] T049 Add `compute_numeric_ranges(min, max, workers)` to `app/services/migration_service.py`: half-open `[start, end)` slices with the final slice inclusive of max; no overlap, no gaps (union = full table).
- [ ] T050 Add `compute_date_ranges(min_ts, max_ts, workers)` to `app/services/migration_service.py`: split the time span into worker ranges (final inclusive); no overlap, no gaps (union = full table).
- [ ] T051 Add per-worker extraction to `app/services/migration_service.py`: numeric/date use bounded `SELECT * ... WHERE col >= :start AND col < :end` (bind vars) with `fetchmany` + batch insert; hash mode uses `WHERE MOD(ORA_HASH(col), :workers) = :id`. Each partition covers part of the full table exactly once — no skip-existing, no dedup.
- [ ] T052 Add a worker pool runner `run_parallel(job_id, request)` to `app/services/migration_service.py`: dispatch workers (after the one-time recreate from T048a), aggregate `processed_rows`, and set job FAILED if any worker raises. No FastAPI imports.
- [ ] T053 Update `app/config.py` / `app/services/migration_service.py` to read `MIGRATION_DEFAULT_WORKERS` (default 8) and clamp requested workers to a max of 16.
- [ ] T054 Update `app/api/migration_routes.py` (thin) to accept and validate `workers`, `partition_column`, and `partition_mode` (`single`|`numeric`|`date`|`hash`) and route to the single vs parallel runner in the service layer.
- [ ] T055 [P] Create `tests/test_range_split.py` asserting `compute_numeric_ranges` and `compute_date_ranges` produce contiguous, non-overlapping, fully-covering ranges for various worker counts.

**Acceptance criteria**: numeric/date/hash parallel work; target dropped+created exactly once per job (not per worker); worker failure → job FAILED; processed rows tracked; no duplicate/missing ranges; re-running the same table still yields latest-only counts. **Manual test**: parallel `POST /api/migrations` with `workers=8,partition_mode=numeric`; re-run and confirm count unchanged; `pytest tests/test_range_split.py`. **Stop point**: parallel tested on small + medium tables before Phase 8.

---

## Phase 8: Validation, Counts, and Reconciliation

**Goal**: Capture + compare source/target counts; surface match/mismatch; Oracle untouched.

- [ ] T056 Add `count_source(schema, table)` to `app/services/migration_service.py` running read-only `SELECT COUNT(*) FROM <schema>.<table>`.
- [ ] T057 Add `count_target(target_table)` to `app/services/migration_service.py` running `SELECT COUNT(*) FROM oracle_migration_hazem.<target_table>`.
- [ ] T058 Extend job fields in `app/services/job_service.py` with `source_row_count`, `target_row_count`, `count_match`, `validation_status` (PENDING/MATCH/MISMATCH); compute after load completes. Because this is a full-load replace into a freshly created table, `count_match` is **exact equality** (target == source); any inequality is a hard MISMATCH.
- [ ] T059 Update `app/api/migration_routes.py` (thin) to include the validation fields in job responses.
- [ ] T060 Update `app/static/app.js` and `app/templates/index.html` to display source/target counts and a clear match/mismatch indicator.

**Acceptance criteria**: counts captured; exact match shown in GUI; mismatch clearly flagged; re-running the same table reports the same source/target counts (no drift from duplication); Oracle unmodified. **Manual test**: `curl /api/migrations/{job_id}` shows the four validation fields with `count_match=true` on a good run; a second run reports identical counts. **Stop point**: reconciliation works before Phase 9.

---

## Phase 9: Final Docker Compose and Team Run

**Goal**: Fresh-clone runnable with one command; complete README.

- [ ] T061 Finalize `Dockerfile` (pinned base image, clean layer for `requirements.txt`, correct uvicorn entrypoint) at repo root.
- [ ] T062 Finalize `docker-compose.yml` (container name `oracle-clickhouse-migration-app`, `env_file: .env`, `8000:8000`, restart policy) at repo root.
- [ ] T063 [P] Finalize `.env.example` at repo root: complete placeholder set, no real secrets.
- [ ] T064 Write `README.md` at repo root with all required sections: project overview, prerequisites, VPN requirement, `.env` setup, `docker compose up -d --build`, health-check commands, how to use the GUI, Oracle troubleshooting, ClickHouse troubleshooting, and Security notes (read-only Oracle, fixed target DB, env-only secrets).
- [ ] T064a Add a **"Initial full load only"** section to `README.md` documenting: each Launch / Replicate drops and recreates the target then reloads the full Oracle table (latest-only, no append/incremental); and the explicit out-of-scope list (CDC, incremental, watermark, dedup, merge/upsert, staging swap, skip-existing) with a note that CDC/incremental are owned by another team.
- [ ] T064b Add a **"Flask integration"** section to `README.md` showing the service layer is framework-agnostic and importable, with the example `from app.services.migration_service import launch_initial_load` and `from app.services.metadata_service import get_oracle_tables`, and a note that FastAPI route files are thin wrappers containing no business logic.

**Acceptance criteria**: fresh clone + `.env` runs via compose; health + GUI + full-load migration work (re-run stays latest-only); README clear and documents both the full-load-only scope and the Flask integration path. **Manual test**: `cp .env.example .env` (fill locally), `docker compose up -d --build`, health `curl`s, and `git status` confirms `.env` untracked; secret-scan grep over Dockerfile/compose/README is clean; README contains the `launch_initial_load` import example. **Stop point**: teammate can run unaided before Phase 10.

---

## Phase 10: Hardening and Production Readiness

**Goal**: Access protection, auditability, traceable failures, secret-free structured logs, cancel + confirmation.

- [ ] T065 Create `app/api/auth.py` and wire into `app/main.py`: basic GUI access protection (e.g., simple auth dependency); credentials sourced only from environment.
- [ ] T066 Add a persistent migration audit record in `app/services/job_service.py` (audit table created only inside `oracle_migration_hazem`, or an app-side durable store); each record captures the full-load drop+create+reload (source/target, row counts, status, timings); never store secrets.
- [ ] T067 Add cancel support: `POST /api/migrations/{job_id}/cancel` in `app/api/migration_routes.py` transitioning a RUNNING job toward CANCELLED, plus cooperative cancellation in `app/services/migration_service.py`.
- [ ] T068 [P] Add retry policy, timeout settings, and a max row/table-size warning to `app/services/migration_service.py`.
- [ ] T069 [P] Create `app/services/report.py` for a downloadable migration report; add a route in `app/api/migration_routes.py`.
- [ ] T070 [P] Add structured JSON logging configuration (no secrets) in `app/main.py`/`app/config.py` and app-level rate limiting.
- [ ] T071 Add a pre-migration confirmation popup in `app/static/app.js` / `app/templates/index.html` before launching a job that explicitly warns the target table will be **dropped and fully reloaded** (destructive full-load replace) and names the target `oracle_migration_hazem.<schema>__<table>`.
- [ ] T072 [P] Add a "Production deployment notes" section to `README.md` (auth, audit, logging, rate limits, deployment).

**Acceptance criteria**: GUI access-protected; migrations auditable; failures traceable; no secrets in logs; deployment notes documented. **Manual test**: `curl -i http://localhost:8000/` requires auth; `POST /api/migrations/{job_id}/cancel`; `docker logs … | grep -Ei "password|secret"` is clean. **Stop point**: final phase — project complete per PLAN.md §21.

---

## Dependencies & Execution Order

### Phase order (sequential — Constitution P-IV)

Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10. **Do not start a phase until the prior phase's acceptance criteria pass and its Stop point is satisfied.**

### Key cross-phase dependencies

- Phase 2 (clients) blocks Phases 3, 5, 6 (all need Oracle/ClickHouse access).
- Phase 3 (metadata) blocks Phase 4 (GUI populates from it) and Phase 5/6 (validation of names).
- Phase 5 (DDL drop+create) blocks Phase 6 (full-load engine drops and recreates the target via `build_recreate_ddl`).
- Phase 6 (single-thread full load) blocks Phase 7 (parallel only after single-thread is proven — P-V); Phase 7 reuses the one-time recreate step (T048a).
- Phase 7/6 blocks Phase 8 (validation runs after load).

### Within-phase parallel opportunities

- **Phase 1**: T004, T005, T006, T007, T011, T012, T013, T014, T015, T016 are `[P]` (distinct files). T008→T009→T010 are sequential (config → router → app wiring).
- **Phase 3**: T023–T027 edit the same `metadata_service.py` (sequential); T028 depends on them; T029 after T028.
- **Phase 5**: T035–T037a edit the same `ddl_mapper.py` (sequential); T041 `[P]` (test file) parallel with route wiring once mapper exists.
- **Phase 6**: T042–T045a mostly edit `migration_service.py`/`job_service.py` (sequential); routes (T046) and JS (T048) follow.
- **Phase 7**: T048a–T053 edit `migration_service.py` (sequential); T055 `[P]` (test file) parallel with engine code.
- **Phase 9**: T064a, T064b `[P]` (same README, append-only sections) after T064.

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
8. Phase 9 → team run.
9. Phase 10 → production hardening.

---

## Notes

- `[P]` = different files, no ordering dependency within the phase.
- Every task names an exact file path and is small enough to implement and test in isolation.
- Honor the per-phase Stop points; verify acceptance criteria (and the Constitution gates in `plan.md`) before advancing.
- Tests included only where the plan names a specific test file (`tests/test_config.py`, `tests/test_ddl_mapper.py`, `tests/test_range_split.py`); no broader TDD was requested.
