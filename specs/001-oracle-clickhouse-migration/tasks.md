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

**Traceability to spec.md user stories**: Phase 2 → US2 (connectivity/safety); Phases 3–8 → US1 (single-table migration MVP); Phase 7 → US3 (parallel); Phase 8 → US4 (validation); Phase 9 → US5 (team run).

**Path convention**: repository root is `oracle_click_house_migrate/`; application code under `app/`, tests under `tests/`.

---

## Phase 0: Specification Initialization and Project Guardrails

**Goal**: Confirm spec/plan/constitution guardrails are in place before any code. No application code in this phase.

- [ ] T001 Verify spec, plan, and design docs exist: confirm `specs/001-oracle-clickhouse-migration/spec.md`, `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, and `contracts/` are present (list the directory; no edits).
- [ ] T002 Verify the project constitution exists and is v1.0.0 at `.specify/memory/constitution.md` (read and confirm the 7 principles; no edits).
- [ ] T003 Create a short guardrails summary section in `README.md` stub stating: Oracle read-only, ClickHouse target fixed to `oracle_migration_hazem`, env-only credentials, phase-by-phase delivery (placeholder file `README.md` at repo root).

**Acceptance criteria**: all design docs and constitution present; guardrails summarized. **Stop point**: do not start Phase 1 until guardrails are reviewed.

---

## Phase 1: Project Bootstrap and Docker Skeleton

**Goal**: Runnable FastAPI skeleton with home page + `/api/health`, locally and via Docker Compose; env example + gitignore; no hardcoded credentials.

- [ ] T004 [P] Create `requirements.txt` at repo root listing: `fastapi`, `uvicorn[standard]`, `python-dotenv`, `pydantic`, `jinja2`, `python-multipart`, `oracledb`, `clickhouse-connect`.
- [ ] T005 [P] Create `.gitignore` at repo root with: `.env`, `*.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, `.DS_Store`.
- [ ] T006 [P] Create `.env.example` at repo root with placeholder keys only (CLICKHOUSE_HOST/PORT/USER/PASS, `CLICKHOUSE_DATABASE=oracle_migration_hazem`, `CLICKHOUSE_ALLOW_CREATE_DATABASE=false`, P5_QA_ORACLE_* vars, `APP_HOST=0.0.0.0`, `APP_PORT=8000`, `MIGRATION_BATCH_SIZE=100000`, `MIGRATION_DEFAULT_WORKERS=8`). No real secrets.
- [ ] T007 [P] Create empty package markers: `app/__init__.py`, `app/api/__init__.py`, `app/db/__init__.py`, `app/services/__init__.py`.
- [ ] T008 Create `app/config.py` with a pydantic settings class that loads all env vars via `python-dotenv`; expose constant `TARGET_DATABASE = "oracle_migration_hazem"`; never embed secrets as defaults.
- [ ] T009 Create `app/api/health_routes.py` with an APIRouter exposing `GET /api/health` returning `{"status":"ok","service":"oracle-clickhouse-migration-engine"}`.
- [ ] T010 Create `app/main.py` with the FastAPI `app`, mount `app/static` at `/static`, configure Jinja2 templates dir `app/templates`, include the health router, and add `GET /` returning the rendered `index.html`.
- [ ] T011 [P] Create `app/templates/index.html` as a minimal GUI shell page (title + empty form container; dynamic behavior added in Phase 4).
- [ ] T012 [P] Create `app/static/style.css` with minimal base styling.
- [ ] T013 [P] Create `app/static/app.js` as an empty/placeholder script (behavior added in Phase 4).
- [ ] T014 [P] Create `Dockerfile` (python base image, install `requirements.txt`, run `uvicorn app.main:app --host 0.0.0.0 --port 8000`).
- [ ] T015 [P] Create `docker-compose.yml` defining service `app` with container name `oracle-clickhouse-migration-app`, `env_file: .env`, port mapping `8000:8000`, build context `.`.
- [ ] T016 [P] Create `tests/test_config.py` asserting `app.config` loads settings and that `TARGET_DATABASE == "oracle_migration_hazem"`.

**Acceptance criteria**: app starts locally and via Docker Compose; `/` serves the page; `/api/health` returns success; `.env` git-ignored; no hardcoded credentials. **Manual test**: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`; `curl http://localhost:8000/api/health`; `docker compose up -d --build`; `git check-ignore .env`. **Stop point**: confirm app starts before Phase 2.

---

## Phase 2: Database Connection Health Checks

**Goal**: Env-based Oracle + ClickHouse clients and health endpoints; confirm connectivity, Oracle metadata read, and target-DB presence (no auto-create).

- [ ] T017 Create `app/db/oracle_client.py`: connection factory using `oracledb` reading creds from `app/config.py`; a `run_select(sql, binds)` helper that rejects any non-`SELECT`/`WITH` statement (SELECT-only guard); never log credentials.
- [ ] T018 Add to `app/db/oracle_client.py` a `health()` function running `SELECT 1 FROM dual` and `SELECT COUNT(*) FROM all_tables`, returning connect + metadata-readable booleans.
- [ ] T019 Create `app/db/clickhouse_client.py`: `clickhouse-connect` client from `app/config.py`; helper `target_database_exists()` querying `system.databases WHERE name = 'oracle_migration_hazem'`; never auto-create unless `CLICKHOUSE_ALLOW_CREATE_DATABASE=true`; never log credentials.
- [ ] T020 Add to `app/db/clickhouse_client.py` a `health()` function running `SELECT 1` and the target-DB existence check, returning connect + target-exists booleans.
- [ ] T021 Update `app/config.py` to include `CLICKHOUSE_ALLOW_CREATE_DATABASE` (default `false`) and all Oracle/ClickHouse connection fields.
- [ ] T022 Update `app/api/health_routes.py`: add `GET /api/health/oracle` → `{"status","database":"oracle","can_connect","can_read_metadata"}` and `GET /api/health/clickhouse` → `{"status","database":"clickhouse","can_connect","target_database":"oracle_migration_hazem","target_database_exists"}`; return clear, credential-free errors on failure.

**Acceptance criteria**: both health checks succeed; errors clear; no credentials in logs; still runs in Docker. **Manual test**: `curl /api/health/oracle`; `curl /api/health/clickhouse`; `docker logs oracle-clickhouse-migration-app` shows no secrets. **Stop point**: both health checks green before Phase 3.

---

## Phase 3: Oracle Metadata Discovery APIs

**Goal**: Backend discovery of schemas, tables, columns, partition/hash candidates — bind variables, metadata-validated.

- [ ] T023 Create `app/services/metadata_service.py` with `list_schemas()` running `SELECT DISTINCT owner FROM all_tables ORDER BY owner` via the read-only client.
- [ ] T024 Add `list_tables(schema)` to `app/services/metadata_service.py` running `SELECT table_name FROM all_tables WHERE owner = :schema_name ORDER BY table_name` (bind variable).
- [ ] T025 Add `list_columns(schema, table)` to `app/services/metadata_service.py` selecting `column_name, data_type, data_length, data_precision, data_scale, nullable` from `all_tab_columns` (bind variables), ordered by `column_id`.
- [ ] T026 Add `list_partition_candidates(schema, table)` to `app/services/metadata_service.py` filtering `data_type IN ('NUMBER','DATE') OR data_type LIKE 'TIMESTAMP%'` (bind variables).
- [ ] T027 Add `schema_exists(schema)` and `table_exists(schema, table)` validation helpers to `app/services/metadata_service.py` (used to reject unknown inputs before any query that interpolates names).
- [ ] T028 Create `app/api/oracle_routes.py` with `GET /api/oracle/schemas`, `GET /api/oracle/tables?schema=`, `GET /api/oracle/columns?schema=&table=`, `GET /api/oracle/partition-columns?schema=&table=`; validate inputs via T027; return controlled errors for unknown schema/table.
- [ ] T029 Update `app/main.py` to include the oracle router from `app/api/oracle_routes.py`.

**Acceptance criteria**: all four endpoints return correct data; invalid schema/table → controlled error; injection-style input executes no dynamic SQL; Oracle read-only. **Manual test**: the four `curl` calls from `quickstart.md` plus `curl "…/api/oracle/tables?schema=CM%27--"` → controlled error. **Stop point**: metadata APIs work before Phase 4.

---

## Phase 4: GUI Dynamic Dropdowns

**Goal**: Interactive metadata-driven GUI; ClickHouse DB fixed and disabled.

- [ ] T030 Update `app/templates/index.html` to add all GUI fields: Oracle Source Schema (select), Oracle Source Table (select), Partition/Hash Column (select), Worker Threads (number, default 8), ClickHouse Schema Destination (text), ClickHouse Database (text, value `oracle_migration_hazem`, `disabled`), Target Table Name (text), Launch Migration Pipeline (button); plus health-status indicators.
- [ ] T031 Implement page-load logic in `app/static/app.js`: call `/api/health/oracle`, `/api/health/clickhouse`, and `/api/oracle/schemas`; render health and populate the schema dropdown.
- [ ] T032 Implement schema-change handler in `app/static/app.js`: on schema select, call `/api/oracle/tables?schema=…`, refresh the table dropdown, and auto-fill ClickHouse Schema Destination with the selected schema.
- [ ] T033 Implement table-change handler in `app/static/app.js`: on table select, call `/api/oracle/partition-columns?schema=…&table=…`, refresh the partition/hash dropdown, and auto-fill Target Table Name with the source table.
- [ ] T034 [P] Update `app/static/style.css` to style the form and health indicators.

**Acceptance criteria**: schemas load on open; schema change refreshes tables + auto-fills target schema; table change refreshes partition columns + auto-fills target table; CH database fixed/disabled. **Manual test**: browser + devtools confirm the three load calls; `curl -s http://localhost:8000/ | grep oracle_migration_hazem`. **Stop point**: GUI dynamic behavior works before Phase 5.

---

## Phase 5: ClickHouse DDL Generation

**Goal**: Type mapping, safe naming, DDL preview + create-if-not-exists confined to `oracle_migration_hazem`.

- [ ] T035 Create `app/services/ddl_mapper.py` with `map_oracle_type(col)` implementing the PLAN.md §13 mapping (NUMBER scale 0→`Nullable(Int64)`, NUMBER scale>0→`Nullable(Float64)`, VARCHAR2/NVARCHAR2/CHAR/NCHAR/CLOB→`Nullable(String)`, DATE→`Nullable(DateTime)`, TIMESTAMP%→`Nullable(DateTime64(6))`, FLOAT→`Nullable(Float64)`, BINARY_FLOAT→`Nullable(Float32)`, BINARY_DOUBLE→`Nullable(Float64)`, else→`Nullable(String)`).
- [ ] T036 Add `safe_target_name(schema, table)` to `app/services/ddl_mapper.py` producing `<schema>__<table>` and sanitizing/quoting identifiers.
- [ ] T037 Add `build_create_ddl(schema, table, columns, order_by)` to `app/services/ddl_mapper.py` generating `CREATE TABLE IF NOT EXISTS oracle_migration_hazem.<name> (...) ENGINE = MergeTree ORDER BY <col|tuple()>`; include a guard that the database is exactly `oracle_migration_hazem`.
- [ ] T038 Add `execute_ddl(ddl)` to `app/db/clickhouse_client.py` that runs only `CREATE TABLE IF NOT EXISTS` statements and rejects any target database other than `oracle_migration_hazem`.
- [ ] T039 Create `app/api/clickhouse_routes.py` with `POST /api/clickhouse/create-table-preview` (returns DDL, no execution) and `POST /api/clickhouse/create-table` (executes create-if-not-exists); reject non-target databases with a 400.
- [ ] T040 Update `app/main.py` to include the clickhouse router from `app/api/clickhouse_routes.py`.
- [ ] T041 [P] Create `tests/test_ddl_mapper.py` asserting each type mapping, the `<schema>__<table>` naming, unsupported-type fallback to `Nullable(String)`, and that a non-`oracle_migration_hazem` target is rejected.

**Acceptance criteria**: preview works; create works in target only; Oracle unmodified; unsupported types don't crash; dangerous target rejected. **Manual test**: preview + create `curl` calls; negative `curl` with `"target_database":"default"` rejected; `pytest tests/test_ddl_mapper.py`. **Stop point**: table creation works before Phase 6.

---

## Phase 6: Single-Thread Batch Migration

**Goal**: First working end-to-end memory-safe copy; background job + status polling.

- [ ] T042 Create `app/services/job_service.py` with an in-memory job registry: `create_job(...)`, `get_job(job_id)`, `update_job(job_id, **fields)`; job fields per `data-model.md` (job_id, source_schema, source_table, target_database, target_table, status, total_rows, processed_rows, started_at, finished_at, duration_seconds, error_message); status enum PENDING/RUNNING/SUCCESS/FAILED/CANCELLED.
- [ ] T043 Create `app/services/migration_service.py` with `run_single_thread(job_id, request)`: validate source schema/table via `metadata_service`, confirm target DB is `oracle_migration_hazem`, ensure target table via `ddl_mapper`/`clickhouse_client`.
- [ ] T044 Add the batch copy loop to `app/services/migration_service.py`: open an Oracle `SELECT *` cursor, read with `cursor.fetchmany(MIGRATION_BATCH_SIZE)`, batch-insert each chunk into ClickHouse, update `processed_rows` after each batch; never load the whole table.
- [ ] T045 Add status transitions + timing to `app/services/migration_service.py`: set RUNNING on start, SUCCESS on completion, FAILED with `error_message` on exception; record `started_at`/`finished_at`/`duration_seconds`.
- [ ] T046 Create `app/api/migration_routes.py` with `POST /api/migrations` (validate, create job, launch background task via FastAPI BackgroundTasks, return `job_id` immediately with 202), `GET /api/migrations/{job_id}` (full record), `GET /api/migrations/{job_id}/status` (lightweight progress).
- [ ] T047 Update `app/main.py` to include the migration router from `app/api/migration_routes.py`.
- [ ] T048 Update `app/static/app.js` to wire the Launch button to `POST /api/migrations` and poll `GET /api/migrations/{job_id}/status` to show progress.

**Acceptance criteria**: launch from GUI; job id immediate; data loads in batches; browser non-blocking; status updates; Oracle read-only; writes only to target. **Manual test**: the `POST /api/migrations` + status `curl` sequence from `quickstart.md`. **Stop point**: one full table copies successfully before Phase 7.

---

## Phase 7: Parallel Migration Engine

**Goal**: Parallel extraction via numeric-range, date-range, hash-fallback; default 8 workers, max 16.

- [ ] T049 Add `compute_numeric_ranges(min, max, workers)` to `app/services/migration_service.py`: half-open `[start, end)` slices with the final slice inclusive of max; no overlap, no gaps.
- [ ] T050 Add `compute_date_ranges(min_ts, max_ts, workers)` to `app/services/migration_service.py`: split the time span into worker ranges (final inclusive); no overlap, no gaps.
- [ ] T051 Add per-worker extraction to `app/services/migration_service.py`: numeric/date use bounded `SELECT * ... WHERE col >= :start AND col < :end` (bind vars) with `fetchmany` + batch insert; hash mode uses `WHERE MOD(ORA_HASH(col), :workers) = :id`.
- [ ] T052 Add a worker pool runner `run_parallel(job_id, request)` to `app/services/migration_service.py`: dispatch workers, aggregate `processed_rows`, and set job FAILED if any worker raises.
- [ ] T053 Update `app/config.py` / `app/services/migration_service.py` to read `MIGRATION_DEFAULT_WORKERS` (default 8) and clamp requested workers to a max of 16.
- [ ] T054 Update `app/api/migration_routes.py` to accept and validate `workers`, `partition_column`, and `partition_mode` (`single`|`numeric`|`date`|`hash`) and route to single vs parallel runner.
- [ ] T055 [P] Create `tests/test_range_split.py` asserting `compute_numeric_ranges` and `compute_date_ranges` produce contiguous, non-overlapping, fully-covering ranges for various worker counts.

**Acceptance criteria**: numeric/date/hash parallel work; worker failure → job FAILED; processed rows tracked; no duplicate/missing ranges. **Manual test**: parallel `POST /api/migrations` with `workers=8,partition_mode=numeric`; `pytest tests/test_range_split.py`. **Stop point**: parallel tested on small + medium tables before Phase 8.

---

## Phase 8: Validation, Counts, and Reconciliation

**Goal**: Capture + compare source/target counts; surface match/mismatch; Oracle untouched.

- [ ] T056 Add `count_source(schema, table)` to `app/services/migration_service.py` running read-only `SELECT COUNT(*) FROM <schema>.<table>`.
- [ ] T057 Add `count_target(target_table)` to `app/services/migration_service.py` running `SELECT COUNT(*) FROM oracle_migration_hazem.<target_table>`.
- [ ] T058 Extend job fields in `app/services/job_service.py` with `source_row_count`, `target_row_count`, `count_match`, `validation_status` (PENDING/MATCH/MISMATCH); compute after load completes.
- [ ] T059 Update `app/api/migration_routes.py` to include the validation fields in job responses.
- [ ] T060 Update `app/static/app.js` and `app/templates/index.html` to display source/target counts and a clear match/mismatch indicator.

**Acceptance criteria**: counts captured; match shown in GUI; mismatch clearly flagged; Oracle unmodified. **Manual test**: `curl /api/migrations/{job_id}` shows the four validation fields with `count_match=true` on a good run. **Stop point**: reconciliation works before Phase 9.

---

## Phase 9: Final Docker Compose and Team Run

**Goal**: Fresh-clone runnable with one command; complete README.

- [ ] T061 Finalize `Dockerfile` (pinned base image, clean layer for `requirements.txt`, correct uvicorn entrypoint) at repo root.
- [ ] T062 Finalize `docker-compose.yml` (container name `oracle-clickhouse-migration-app`, `env_file: .env`, `8000:8000`, restart policy) at repo root.
- [ ] T063 [P] Finalize `.env.example` at repo root: complete placeholder set, no real secrets.
- [ ] T064 Write `README.md` at repo root with all required sections: project overview, prerequisites, VPN requirement, `.env` setup, `docker compose up -d --build`, health-check commands, how to use the GUI, Oracle troubleshooting, ClickHouse troubleshooting, and Security notes (read-only Oracle, fixed target DB, env-only secrets).

**Acceptance criteria**: fresh clone + `.env` runs via compose; health + GUI + migration work; README clear. **Manual test**: `cp .env.example .env` (fill locally), `docker compose up -d --build`, health `curl`s, and `git status` confirms `.env` untracked; secret-scan grep over Dockerfile/compose/README is clean. **Stop point**: teammate can run unaided before Phase 10.

---

## Phase 10: Hardening and Production Readiness

**Goal**: Access protection, auditability, traceable failures, secret-free structured logs, cancel + confirmation.

- [ ] T065 Create `app/api/auth.py` and wire into `app/main.py`: basic GUI access protection (e.g., simple auth dependency); credentials sourced only from environment.
- [ ] T066 Add a persistent migration audit record in `app/services/job_service.py` (audit table created only inside `oracle_migration_hazem`, or an app-side durable store); never store secrets.
- [ ] T067 Add cancel support: `POST /api/migrations/{job_id}/cancel` in `app/api/migration_routes.py` transitioning a RUNNING job toward CANCELLED, plus cooperative cancellation in `app/services/migration_service.py`.
- [ ] T068 [P] Add retry policy, timeout settings, and a max row/table-size warning to `app/services/migration_service.py`.
- [ ] T069 [P] Create `app/services/report.py` for a downloadable migration report; add a route in `app/api/migration_routes.py`.
- [ ] T070 [P] Add structured JSON logging configuration (no secrets) in `app/main.py`/`app/config.py` and app-level rate limiting.
- [ ] T071 Add a pre-migration confirmation popup in `app/static/app.js` / `app/templates/index.html` before launching a job.
- [ ] T072 [P] Add a "Production deployment notes" section to `README.md` (auth, audit, logging, rate limits, deployment).

**Acceptance criteria**: GUI access-protected; migrations auditable; failures traceable; no secrets in logs; deployment notes documented. **Manual test**: `curl -i http://localhost:8000/` requires auth; `POST /api/migrations/{job_id}/cancel`; `docker logs … | grep -Ei "password|secret"` is clean. **Stop point**: final phase — project complete per PLAN.md §21.

---

## Dependencies & Execution Order

### Phase order (sequential — Constitution P-IV)

Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10. **Do not start a phase until the prior phase's acceptance criteria pass and its Stop point is satisfied.**

### Key cross-phase dependencies

- Phase 2 (clients) blocks Phases 3, 5, 6 (all need Oracle/ClickHouse access).
- Phase 3 (metadata) blocks Phase 4 (GUI populates from it) and Phase 5/6 (validation of names).
- Phase 5 (DDL) blocks Phase 6 (migration ensures target table).
- Phase 6 (single-thread) blocks Phase 7 (parallel only after single-thread is proven — P-V).
- Phase 7/6 blocks Phase 8 (validation runs after load).

### Within-phase parallel opportunities

- **Phase 1**: T004, T005, T006, T007, T011, T012, T013, T014, T015, T016 are `[P]` (distinct files). T008→T009→T010 are sequential (config → router → app wiring).
- **Phase 3**: T023–T027 edit the same `metadata_service.py` (sequential); T028 depends on them; T029 after T028.
- **Phase 5**: T041 `[P]` (test file) parallel with route wiring once mapper exists.
- **Phase 7**: T055 `[P]` (test file) parallel with engine code.

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

The MVP is the **single-table migration path (spec US1)** = Phases 0–6 plus Phase 8 validation. After Phase 6 you can migrate one table end to end through the GUI; Phase 8 adds the count check. Phases 7 (parallel), 9 (team packaging), and 10 (hardening) are incremental value on top.

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
