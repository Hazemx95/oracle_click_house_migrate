# Implementation Plan: Oracle to ClickHouse Parallel Data Migration Engine

**Branch**: `001-oracle-clickhouse-migration` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-oracle-clickhouse-migration/spec.md` and source plan `PLAN.md`

## Summary

A Python FastAPI web application that lets an engineer migrate selected Oracle tables into a single fixed ClickHouse database (`oracle_migration_hazem`) through a browser GUI. The app dynamically discovers Oracle schemas/tables/columns, generates ClickHouse table definitions from Oracle metadata, and copies data using memory-bounded batch extraction and batch inserts, first single-threaded and then in parallel. Oracle is strictly read-only; ClickHouse writes are confined to the one target database; all credentials come from environment variables only.

**Scope — initial full load only (Phases 4–10).** When the user clicks **Launch / Replicate**, the app performs a full-table **replace**: drop the target ClickHouse table if it exists, create a fresh empty target table from the Oracle→ClickHouse type mapping, extract the full Oracle source table via batch reads, and batch-insert every row. Re-launching the same source schema/table drops and recreates the target and reloads in full, so the target always holds **only the latest full-load result** (never appended duplicate copies). This project does **not** implement CDC, incremental loading, watermark logic, deduplication, merge/upsert, staging-table replacement, append-only duplicate loading, or skip-existing-row logic — CDC and incremental logic are owned by another team. `DROP TABLE` is hereby explicitly authorized (per Constitution Principle II's "later phase" clause) and remains confined to `oracle_migration_hazem`. Business logic lives in framework-agnostic service modules (`app/services/*`, `app/db/*`) so the engine can be imported directly into an existing Flask app; FastAPI route files are thin wrappers only.

The work is delivered **phase by phase** (Phase 0 through Phase 10). Each phase has a goal, scope, files, the code that must exist when it ends, acceptance criteria, manual test commands, and a hard stop point. No phase begins until the prior phase is verified.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, uvicorn[standard], python-dotenv, pydantic, jinja2, python-multipart, oracledb (Oracle driver, thin mode), clickhouse-connect

**Storage**: Source = Oracle (read-only, accessed via `all_tables`/`all_tab_columns` metadata and `SELECT` on source tables). Target = ClickHouse database `oracle_migration_hazem` (MergeTree tables). Job state = in-process store (in-memory registry) in Phases 6–8; optional persistent audit table in Phase 10.

**Testing**: pytest (unit for config/type-mapping/range-splitting; manual `curl`/browser checks per phase as defined in PLAN.md)

**Target Platform**: Linux server / container; reachable at `http://localhost:8000`; run via local uvicorn and via `docker compose up -d --build`

**Project Type**: Web service with server-rendered GUI (single FastAPI app serving JSON APIs + Jinja2 template + static JS/CSS)

**Performance Goals**: Memory bounded by `MIGRATION_BATCH_SIZE` (default 100000 rows) regardless of table size; job id returned within a few seconds of launch; parallel mode (default 8, max 16 workers) measurably faster than single-thread on medium tables

**Constraints**: Oracle is read-only (SELECT only); ClickHouse writes only to `oracle_migration_hazem`; credentials from environment variables only, never hardcoded or logged; bind variables for all parameterized Oracle queries; no full-table reads into memory

**Scale/Scope**: Single-instance internal tool for engineers; one migration job per table; handles small/medium/large tables via batching and parallel range/hash extraction

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against the project constitution v1.0.0 (`.specify/memory/constitution.md`). All seven principles are satisfied by this design:

- **I. Oracle read-only (NON-NEGOTIABLE)**: PASS — all Oracle access routes through one read-only client issuing only `SELECT`; a guard rejects any non-read statement.
- **II. ClickHouse target restricted (NON-NEGOTIABLE)**: PASS — every write goes through a wrapper that forces/validates database `oracle_migration_hazem` and rejects any other. The full-load engine uses `DROP TABLE IF EXISTS`, `CREATE TABLE`, `INSERT INTO`, and `SELECT`, all confined to `oracle_migration_hazem`. `DROP TABLE`/`CREATE TABLE` (drop-and-recreate replace) is the explicitly authorized rerun behavior this plan introduces under Principle II's "later phase" clause; it is never executed against any other database.
- **III. Environment-based credentials (NON-NEGOTIABLE)**: PASS — config via `.env`/pydantic, `.env.example` placeholders only, `.gitignore` excludes `.env`, no secrets in code/Docker/README/tests.
- **IV. Phase-based implementation**: PASS — Phases 0–10 each carry scope, files, acceptance criteria, manual test commands, and a stop point.
- **V. Memory-safe large-table migration**: PASS — chunked `fetchmany` + ClickHouse batch inserts; parallel mode (Phase 7) added only after single-thread (Phase 6); workers default 8, max 16; range modes guarantee no duplicate/missing rows.
- **VI. Dynamic, metadata-driven GUI**: PASS — schemas/tables/columns loaded from Oracle metadata; target schema auto-fills; ClickHouse DB fixed/disabled (Phase 4).
- **VII. Security & safety first (NON-NEGOTIABLE)**: PASS — no secret logging; schema/table/column validated against metadata; bind variables for Oracle queries; no raw input concatenated into SQL.

No violations to justify; Complexity Tracking is not required. This gate is re-checked after Phase 1 design (artifacts produced: research.md, data-model.md, contracts/, quickstart.md) and remains PASS.

## Project Structure

### Documentation (this feature)

```text
specs/001-oracle-clickhouse-migration/
├── plan.md              # This file (/speckit-plan output)
├── spec.md              # Feature specification (/speckit-specify output)
├── research.md          # Phase 0 research (this command)
├── data-model.md        # Phase 1 design (this command)
├── quickstart.md        # Phase 1 validation guide (this command)
├── contracts/           # Phase 1 API contracts (this command)
│   ├── health.md
│   ├── oracle-metadata.md
│   ├── clickhouse-ddl.md
│   └── migrations.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
oracle_click_house_migrate/
├── PLAN.md
├── README.md
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, router registration, template/static mount
│   ├── config.py                # Env-based settings (pydantic), fixed target DB constant
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── oracle_client.py     # Read-only Oracle connection + SELECT-only guard
│   │   └── clickhouse_client.py # ClickHouse connection + target-DB confinement guard
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health_routes.py     # /api/health, /api/health/oracle, /api/health/clickhouse
│   │   ├── oracle_routes.py     # /api/oracle/schemas|tables|columns|partition-columns
│   │   ├── clickhouse_routes.py # /api/clickhouse/create-table-preview|create-table
│   │   └── migration_routes.py  # /api/migrations ...
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── metadata_service.py  # Oracle discovery queries (bind vars), validation
│   │   ├── ddl_mapper.py        # Oracle→ClickHouse type map, target naming, DDL builder
│   │   ├── migration_service.py # Single-thread + parallel migration engine
│   │   └── job_service.py       # Job registry, status, progress, validation results
│   │
│   ├── templates/
│   │   └── index.html           # GUI page
│   │
│   └── static/
│       ├── app.js               # Dynamic dropdown behavior, launch + polling
│       └── style.css
│
└── tests/
    ├── test_config.py
    ├── test_ddl_mapper.py       # type mapping + naming (added Phase 5)
    ├── test_range_split.py      # numeric/date range splitting (added Phase 7)
    └── test_parallel_mode.py    # parallel-mode resolver/validator (added Phase 7)
```

**Structure Decision**: Single FastAPI web-service project exactly as laid out in PLAN.md §9. JSON APIs under `/api/*`, GUI served from `/` via Jinja2 with static assets. One added module `app/api/clickhouse_routes.py` (PLAN.md lists DDL endpoints but no dedicated route file; kept separate from `migration_routes.py` for clarity). Job state lives in `job_service.py` as an in-memory registry through Phase 8; an optional persistent audit table is introduced in Phase 10.

---

## Phased Implementation Plan

> **Constitution gate — applies to EVERY phase (project constitution v1.0.0).** Before a phase's stop point is satisfied, all of the following MUST hold, in addition to that phase's own acceptance criteria:
> - **P-I Oracle read-only (NON-NEGOTIABLE)**: only `SELECT` reaches Oracle; no `CREATE/ALTER/DROP/TRUNCATE/INSERT/UPDATE/DELETE/MERGE/EXEC/CALL`.
> - **P-II ClickHouse confined (NON-NEGOTIABLE)**: every write targets only `oracle_migration_hazem`; any other database is rejected.
> - **P-III Env-only credentials (NON-NEGOTIABLE)**: configuration/credentials come only from `.env`/environment; never hardcoded in code, `Dockerfile`, `docker-compose.yml`, `README`, `PLAN.md`, or tests; real `.env` git-ignored; only `.env.example` committed.
> - **P-VII Security & safety (NON-NEGOTIABLE)**: no secrets in logs; schema/table/column names validated against metadata; bind variables used; no raw user input concatenated into SQL.
> - **P-IV Phase discipline**: do not advance until this phase's acceptance criteria pass and its stop point is met.
> - **P-V Memory safety**: any code touching source data uses chunked `fetchmany` + batch insert; no full-table load; parallel only after single-thread is proven.
>
> Each phase below restates the principles most at risk in that phase under **Constitution gate**; the full list above still applies even where not repeated. The NON-NEGOTIABLE principles (I, II, III, VII) admit no exceptions and cannot be waived via Complexity Tracking.

### Phase 0 — Specification Initialization and Project Guardrails

**Goal**: Lock in the rules, safety constraints, environment rules, folder expectations, and acceptance gates that govern all later phases — before any application code exists.

**Scope**:
- Confirm spec + plan + guardrails are written and agreed.
- Define forbidden Oracle operations and allowed ClickHouse operations explicitly.
- Define environment-variable-only configuration policy and the example-env / git-ignore policy.
- Define the target folder structure and dependency list.
- Define the global acceptance gates reused by every phase.

**Files to create or update**:
- `specs/001-oracle-clickhouse-migration/spec.md` (exists)
- `specs/001-oracle-clickhouse-migration/plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/*` (this command)
- No application source files yet.

**Code that must exist after the phase**: None. This phase produces documentation/guardrails only.

**Acceptance criteria**:
- Oracle read-only rule and forbidden-operation list documented.
- ClickHouse write-confinement rule and allowed-operation list documented.
- Environment rules, `.env.example` policy, and `.gitignore` policy documented.
- Folder expectations and dependency list documented.
- Global safety gates listed and referenced by later phases.

**Constitution gate**: P-I/P-II/P-III/P-VII are documented as binding guardrails here; this phase establishes them. No source code, so no runtime checks yet.

**Manual test commands**:
```bash
ls specs/001-oracle-clickhouse-migration/
test -f specs/001-oracle-clickhouse-migration/plan.md && echo "plan present"
test -f .specify/memory/constitution.md && echo "constitution present"
```

**Stop point**: Do not start Phase 1 until guardrails are reviewed and agreed.

---

### Phase 1 — Project Bootstrap and Docker Skeleton

**Goal**: A runnable FastAPI skeleton with a home page and a health endpoint, runnable locally and via Docker Compose, with env example + gitignore in place and no hardcoded credentials.

**Scope** (implement only): folder structure, FastAPI skeleton, basic home page, `.env.example`, `.gitignore`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`. No Oracle/ClickHouse connection, no migration logic.

**Files to create or update**:
- `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `.gitignore`, `README.md` (stub)
- `app/__init__.py`, `app/main.py`, `app/config.py`
- `app/api/__init__.py`, `app/api/health_routes.py`
- `app/templates/index.html`, `app/static/app.js`, `app/static/style.css`
- `app/db/__init__.py`, `app/services/__init__.py` (empty packages)
- `tests/test_config.py`

**Code that must exist after the phase**:
- `app.main:app` FastAPI instance mounting templates + static and including the health router.
- `GET /` returns the GUI page (static shell is fine).
- `GET /api/health` returns `{"status":"ok","service":"oracle-clickhouse-migration-engine"}`.
- `app/config.py` reads settings from environment via `python-dotenv`/pydantic, exposes the fixed `CLICKHOUSE_DATABASE=oracle_migration_hazem` constant; no secrets in code.
- `.env.example` with placeholder values; `.gitignore` excluding `.env`/`*.env`/`.venv/`/`__pycache__/` etc.

**Acceptance criteria**: App starts locally; app starts via Docker Compose; browser opens home page; `/api/health` returns success; `.env` is git-ignored; no credentials hardcoded.

**Constitution gate (P-III, P-VII)**: `.env` is git-ignored; only `.env.example` (placeholders) is committed; no real credentials appear in code, `Dockerfile`, `docker-compose.yml`, `README`, or tests; startup logs print no secrets.

**Manual test commands**:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/api/health
docker compose up -d --build
curl http://localhost:8000/api/health
git check-ignore .env   # should print .env
grep -rEi "password|passwd|secret" app/ Dockerfile docker-compose.yml README.md   # expect no real values
```

**Stop point**: Stop after Phase 1 until the user confirms the app starts successfully.

---

### Phase 2 — Database Connection Health Checks

**Goal**: Confirm the app can connect to Oracle (read-only) and ClickHouse from its runtime environment and that the fixed target database exists.

**Scope**: Oracle client, ClickHouse client, env-based config for both, Oracle health endpoint, ClickHouse health endpoint. No GUI dropdowns, no migration.

**Files to create or update**:
- `app/db/oracle_client.py` — connection factory using `oracledb`; helper that runs `SELECT 1 FROM dual` and `SELECT COUNT(*) FROM all_tables`; SELECT-only guard.
- `app/db/clickhouse_client.py` — `clickhouse-connect` client; `SELECT 1`; target-DB existence query against `system.databases`.
- `app/config.py` — add Oracle + ClickHouse settings, `CLICKHOUSE_ALLOW_CREATE_DATABASE=false` default.
- `app/api/health_routes.py` — add `/api/health/oracle`, `/api/health/clickhouse`.
- `app/main.py` — ensure health router wired.

**Code that must exist after the phase**:
- `GET /api/health/oracle` → `{"status":"success","database":"oracle","can_connect":true,"can_read_metadata":true}` (or a clear error).
- `GET /api/health/clickhouse` → `{"status":"success","database":"clickhouse","can_connect":true,"target_database":"oracle_migration_hazem","target_database_exists":true|false}`.
- Reusable connection helpers used by later phases; errors are structured and credential-free.
- Target database is **not** auto-created (unless `CLICKHOUSE_ALLOW_CREATE_DATABASE=true`).

**Acceptance criteria**: Oracle health succeeds; ClickHouse health succeeds; errors are clear; no credentials printed in logs; app still runs in Docker Compose.

**Constitution gate (P-I, P-II, P-III, P-VII)**: Oracle health uses only `SELECT` (`SELECT 1 FROM dual`, `SELECT COUNT(*) FROM all_tables`); ClickHouse check only reads `system.databases` and never auto-creates the target unless `CLICKHOUSE_ALLOW_CREATE_DATABASE=true`; both clients read credentials only from environment; health responses and `docker logs` contain no credentials.

**Manual test commands**:
```bash
curl http://localhost:8000/api/health/oracle
curl http://localhost:8000/api/health/clickhouse
docker compose up -d --build
docker logs oracle-clickhouse-migration-app    # confirm NO credentials/secrets in output
```

**Stop point**: Stop after Phase 2 until both health checks succeed.

---

### Phase 3 — Oracle Metadata Discovery APIs

**Goal**: Backend can dynamically discover Oracle schemas, tables, columns, and candidate partition/hash columns using bind variables.

**Scope**: Metadata APIs only. No full GUI behavior, no migration.

**Files to create or update**:
- `app/services/metadata_service.py` — discovery queries (schemas, tables-by-schema, columns, partition-candidate columns) using bind variables; validation helpers (`schema_exists`, `table_exists`).
- `app/api/oracle_routes.py` — the four GET endpoints.
- `app/main.py` — include oracle router.

**Code that must exist after the phase**:
- `GET /api/oracle/schemas` → distinct owners from `all_tables`.
- `GET /api/oracle/tables?schema=<schema>` → tables for that owner (bind var).
- `GET /api/oracle/columns?schema=<schema>&table=<table>` → column name/type/length/precision/scale/nullable.
- `GET /api/oracle/partition-columns?schema=<schema>&table=<table>` → NUMBER/DATE/TIMESTAMP% candidates.
- Validation rejects schema/table not present in metadata with a controlled error (no raw concatenation into SQL).

**Acceptance criteria**: all four endpoints return correct data; invalid schema/table returns controlled error; Oracle remains read-only.

**Constitution gate (P-I, P-VII)**: all discovery queries are `SELECT` against `all_tables`/`all_tab_columns` only; `schema`/`table` are validated against metadata before use and passed as bind variables — never concatenated into SQL; an injection-style value (e.g. `CM'--`) returns a controlled error and executes no dynamic SQL.

**Manual test commands**:
```bash
curl http://localhost:8000/api/oracle/schemas
curl "http://localhost:8000/api/oracle/tables?schema=CM"
curl "http://localhost:8000/api/oracle/columns?schema=CM&table=COMPONENT"
curl "http://localhost:8000/api/oracle/partition-columns?schema=CM&table=COMPONENT"
curl "http://localhost:8000/api/oracle/tables?schema=CM%27--"   # injection attempt → controlled error, no SQL executed
```

**Stop point**: Stop after Phase 3 until metadata APIs work correctly.

---

### Phase 4 — GUI Dynamic Dropdowns

**Goal**: Interactive GUI behavior built on the metadata APIs.

**Scope**: Frontend behavior only (using completed APIs). The Launch/Replicate button is wired in Phase 6; this phase only renders it. No migration logic.

**Files to create or update**:
- `app/templates/index.html` — all GUI fields from PLAN.md §6 (source schema, source table, partition/hash column, worker threads default 8, CH schema destination, CH database fixed+disabled, target table name, **Launch / Replicate** button). The button label and adjacent helper text MUST make the full-load **replace** semantics explicit (e.g. "Launching drops and recreates the target table, then loads the full Oracle table").
- `app/static/app.js` — load health + schemas on page load; on schema change load tables + auto-fill target schema; on table change load partition columns + auto-fill target table; keep CH database fixed/disabled.
- `app/static/style.css` — basic styling and health indicators.

**Code that must exist after the phase**:
- On load: calls `/api/health/oracle`, `/api/health/clickhouse`, `/api/oracle/schemas`.
- On schema select: calls `/api/oracle/tables?schema=...`, refreshes table dropdown, auto-fills CH schema destination.
- On table select: calls `/api/oracle/partition-columns?...`, refreshes column dropdown, auto-fills target table name.
- ClickHouse database field fixed and disabled to `oracle_migration_hazem`.
- The Launch/Replicate control is present and clearly communicates that launching performs a destructive full-load replace of the target table (no append, no incremental).

**Acceptance criteria**: GUI loads schemas dynamically; changing source schema refreshes tables and auto-fills target schema; changing source table refreshes partition/hash columns and auto-fills target table; CH database is fixed to `oracle_migration_hazem`; the Launch/Replicate button communicates full-load replace semantics.

**Constitution gate (P-VI, P-I)**: every dropdown is populated from live Oracle metadata (no hardcoded lists); the ClickHouse database field is rendered fixed and `disabled` to `oracle_migration_hazem` and cannot be edited; GUI issues only read/discovery calls (no writes in this phase).

**Manual test commands**:
```bash
curl http://localhost:8000/            # returns GUI shell
# In a browser + devtools, confirm on open: GET /api/health/oracle, /api/health/clickhouse, /api/oracle/schemas fire
# Confirm the ClickHouse Database input is disabled and shows oracle_migration_hazem
curl -s http://localhost:8000/ | grep -i "oracle_migration_hazem"   # fixed DB present in markup
```

**Stop point**: Stop after Phase 4 until GUI dynamic behavior works.

---

### Phase 5 — ClickHouse DDL Generation **(Critical DDL & Type-Mapping Gate)**

**Goal**: Generate and execute a **drop-and-recreate** target DDL pair (`DROP TABLE IF EXISTS` then `CREATE TABLE`) in `oracle_migration_hazem` from Oracle metadata, so each launch starts from a fresh empty target. No idempotent `IF NOT EXISTS` create — the full-load model requires the table to be replaced, not preserved. This phase is the **critical gate**: data migration (Phase 6+) must not begin until the type mapping, identifier quoting, and drop+create generation are proven correct here.

**Scope**: Type mapping, safe target naming, safe identifier quoting, drop+create DDL generation, target-DB enforcement, unsupported-type fallback with warnings. No data migration yet.

**Framework-agnostic requirement (hard gate)**: `app/services/ddl_mapper.py` MUST contain **no FastAPI imports** and no dependency on FastAPI request/response objects — only pure functions over plain Python structures (column metadata dicts/dataclasses → DDL strings/warnings). A future Flask app must be able to `from app.services.ddl_mapper import ...` directly. The route layer (`app/api/clickhouse_routes.py`) is a thin wrapper that only adapts HTTP ↔ service calls.

**Files to create or update**:
- `app/services/ddl_mapper.py` — Oracle→ClickHouse type map (table below), safe-name builder `<schema>__<table>`, **safe ClickHouse identifier quoting** (backtick-quote every identifier; reject/escape backticks and control chars), engine selection (`ORDER BY <col>` or `ORDER BY tuple()`), **DROP and CREATE** DDL string builders, target-DB guard (enforce `oracle_migration_hazem`), unsupported-type fallback that returns a structured warning list. Pure functions, **no FastAPI imports**, importable by a future Flask app.
- `app/api/clickhouse_routes.py` — `POST /api/clickhouse/create-table-preview` (returns the DROP + CREATE statements **and any type-mapping warnings**), `POST /api/clickhouse/create-table` (executes DROP then CREATE). Thin wrapper only.
- `app/db/clickhouse_client.py` — `execute_ddl` confined to target DB; rejects any statement whose target is not `oracle_migration_hazem`.
- `app/main.py` — include clickhouse router.
- `tests/test_ddl_mapper.py` — **comprehensive** unit tests for every mapping branch (NUMBER precision/scale boundaries, FLOAT/BINARY_FLOAT/BINARY_DOUBLE, char types incl. NCLOB, DATE, TIMESTAMP variants, RAW/BLOB), unsupported-type fallback + warning emission, identifier quoting/injection safety, naming, and that the generated DDL is a DROP-then-CREATE pair (no `IF NOT EXISTS` on CREATE).

**Oracle metadata fields consumed** (from `ALL_TAB_COLUMNS`): `column_name`, `data_type`, `data_length`, `data_precision`, `data_scale`, `nullable`, `char_length`, `char_used`. (`char_length`/`char_used` are added in this phase to disambiguate char-semantics columns; the Phase 3 columns endpoint is extended to also return them if not already present.)

**Required Oracle → ClickHouse mapping** (authoritative for this project):

| Oracle type | Condition | ClickHouse type |
| --- | --- | --- |
| `NUMBER(p,0)` | `p <= 18` | `Nullable(Int64)` |
| `NUMBER(p,0)` | `18 < p <= 76` | `Nullable(Decimal(p,0))` |
| `NUMBER(p,s)` | `s > 0` and `p <= 76` | `Nullable(Decimal(p,s))` |
| `NUMBER` | unknown precision/scale | `Nullable(Float64)` |
| `FLOAT` | — | `Nullable(Float64)` |
| `BINARY_FLOAT` | — | `Nullable(Float32)` |
| `BINARY_DOUBLE` | — | `Nullable(Float64)` |
| `VARCHAR2` / `NVARCHAR2` / `CHAR` / `NCHAR` / `CLOB` / `NCLOB` | — | `Nullable(String)` |
| `DATE` | — | `Nullable(DateTime)` |
| `TIMESTAMP` / `TIMESTAMP WITH TIME ZONE` / `TIMESTAMP WITH LOCAL TIME ZONE` | — | `Nullable(DateTime64(6))` |
| `RAW` / `BLOB` | — | `Nullable(String)` |
| any other / unsupported | — | `Nullable(String)` **+ warning** |

**Code that must exist after the phase**:
- The mapping above implemented exactly, including the `NUMBER` precision/scale boundaries (`p <= 18` → Int64; `Decimal(p,0)` for `18 < p <= 76`; `Decimal(p,s)` for `s > 0`; `Float64` when precision/scale are null/unknown), TIMESTAMP-with-zone variants, and RAW/BLOB → `Nullable(String)`.
- Unsupported Oracle types **do not crash**: they fall back to `Nullable(String)` and the mapper returns a warning entry (column name + original Oracle type) that the preview endpoint surfaces.
- All ClickHouse identifiers (database, table, column names) are **safely quoted** so a hostile/odd identifier cannot inject DDL.
- Preview endpoint returns DDL text (both `DROP TABLE IF EXISTS oracle_migration_hazem.<schema>__<table>` and the `CREATE TABLE` statement) plus the warnings list, **without executing**.
- Create endpoint executes, in order: `DROP TABLE IF EXISTS oracle_migration_hazem.<schema>__<table>` then `CREATE TABLE oracle_migration_hazem.<schema>__<table> (...) ENGINE = MergeTree ORDER BY ...` — yielding a fresh empty table even when one already existed.
- Target-database enforcement: any value other than `oracle_migration_hazem` is rejected for **both** DROP and CREATE.

**Acceptance criteria**: DDL preview shows the drop+create pair and any mapping warnings; executing it produces a fresh empty table even on re-run; both DROP and CREATE act only in `oracle_migration_hazem`; Oracle not modified; every mapping branch (incl. Decimal boundaries, TIMESTAMP-with-zone, RAW/BLOB, NCLOB) is covered by `tests/test_ddl_mapper.py`; unsupported types fall back to `Nullable(String)` with a warning and do not crash; identifiers are safely quoted; `ddl_mapper.py` imports no FastAPI; dangerous target values rejected for both DROP and CREATE.

**Constitution gate (P-II, P-I, P-VII)**: the only ClickHouse statements executed are `DROP TABLE IF EXISTS` and `CREATE TABLE` inside `oracle_migration_hazem` (the explicitly authorized rerun behavior); the target-DB guard rejects any other database value on **both** statements; Oracle is touched only for read-only column metadata; identifiers are sanitized/quoted so DDL cannot be injected.

**Manual test commands**:
```bash
curl -X POST http://localhost:8000/api/clickhouse/create-table-preview \
  -H 'Content-Type: application/json' \
  -d '{"schema":"CM","table":"COMPONENT","target_table":"CM__COMPONENT","order_by":null}'   # returns DROP + CREATE

curl -X POST http://localhost:8000/api/clickhouse/create-table \
  -H 'Content-Type: application/json' \
  -d '{"schema":"CM","table":"COMPONENT","target_table":"CM__COMPONENT","order_by":null}'

# re-run: table is dropped and recreated empty (no error, no leftover rows from a prior create)
curl -X POST http://localhost:8000/api/clickhouse/create-table \
  -H 'Content-Type: application/json' \
  -d '{"schema":"CM","table":"COMPONENT","target_table":"CM__COMPONENT","order_by":null}'

# negative: a different target database MUST be rejected for both DROP and CREATE
curl -X POST http://localhost:8000/api/clickhouse/create-table \
  -H 'Content-Type: application/json' \
  -d '{"schema":"CM","table":"COMPONENT","target_table":"CM__COMPONENT","target_database":"default"}'   # expect rejection
pytest tests/test_ddl_mapper.py
```

**Stop point**: Stop after Phase 5 until drop-and-recreate table creation works on both first run and re-run.

---

### Phase 6 — Single-Thread Batch Migration

**Goal**: First working end-to-end **initial full load** (drop → create → full extract → full insert) using memory-safe batch loading, single-threaded.

**Scope**: Single-thread full-load replace only. No parallel workers. No CDC, incremental, watermark, dedup, merge/upsert, staging swap, append, or skip-existing logic.

**Files to create or update**:
- `app/services/job_service.py` — in-memory job registry; create/get/update; status + **full progress fields** (see below). Framework-agnostic, no FastAPI imports.
- `app/services/migration_service.py` — single-thread full-load pipeline exposing a framework-agnostic entry point (e.g. `launch_initial_load(...)`): (1) validate source schema/table against Oracle metadata; (2) confirm target DB is `oracle_migration_hazem`; (3) **DROP** target table if it exists then **CREATE** it fresh (via `ddl_mapper`); (4) batch read loop over the full Oracle source; (5) batch insert each chunk with explicit column names in a stable order; (6) progress tracking. Run in background. **No FastAPI imports / no coupling to FastAPI request/response types** so a Flask app can call it directly.
- `app/api/migration_routes.py` — thin wrappers only: `POST /api/migrations`, `GET /api/migrations/{job_id}`, `GET /api/migrations/{job_id}/status`.
- `app/static/app.js` + `app/templates/index.html` — wire Launch/Replicate button to POST and poll `/status`; render the **live progress UI** (see below); surface that each launch replaces the target.
- `app/main.py` — include migration router; use FastAPI BackgroundTasks/async worker.

**Performance rules (mandatory — memory-safe, batched, never row-by-row)**:
- **Never** use `pandas.read_sql` for full-table migration.
- **Never** use `cursor.fetchall()` for huge tables.
- **Never** insert row-by-row into ClickHouse.
- Set `cursor.arraysize` and `cursor.prefetchrows` to tune Oracle round-trips.
- Extract with `cursor.fetchmany(MIGRATION_BATCH_SIZE)` in a loop.
- Insert into ClickHouse with **batch inserts**, using **explicit column names** and a **stable column order** (the order returned by the column metadata query) for both the SELECT projection and the INSERT.

**Progress fields tracked on the job** (in `job_service.py`): `job_id`, `source_schema`, `source_table`, `target_database`, `target_table`, `status`, `total_rows`, `processed_rows`, `inserted_rows`, `remaining_rows`, `batches_completed`, `current_batch`, `progress_percent`, `rows_per_second`, `elapsed_seconds`, `started_at`, `finished_at`, `duration_seconds`, `error_message`.

**Code that must exist after the phase**:
- `POST /api/migrations` validates selection, creates a job, kicks off the background full load, returns `job_id` immediately.
- The pipeline drops the existing target table, recreates it empty, then loads the **entire** Oracle source. Re-launching the same source schema/table drops+recreates and reloads in full, so the target ends with **only the latest full-load result** (e.g. 100 source rows → 100 target rows on every run, never 200). The engine never appends a second full copy and performs no row-skipping/merge.
- Migration reads via `cursor.fetchmany(MIGRATION_BATCH_SIZE)` (with `arraysize`/`prefetchrows` set) and batch-inserts into ClickHouse with explicit, stable column ordering — never `read_sql`/`fetchall` of the whole table, never row-by-row insert.
- Job statuses PENDING→RUNNING→SUCCESS/FAILED/CANCELLED; the job tracks every progress field listed above and updates them as batches complete.
- `GET /api/migrations/{job_id}` returns the full job record; `GET /api/migrations/{job_id}/status` returns the live overall-progress view: `status`, `total_rows`, `processed_rows`, `inserted_rows`, `remaining_rows`, `progress_percent`, `batches_completed`, `current_batch`, `rows_per_second`, `elapsed_seconds`, `error_message` (a `workers` array is added in Phase 7; validation fields in Phase 8). See `contracts/migrations.md`.

**Live migration progress UI (single-thread)**: the GUI must show, after launch and while polling `/status`: an **overall progress bar (0–100%)**, **job status** (PENDING/RUNNING/SUCCESS/FAILED/CANCELLED), **total rows**, **processed rows**, **inserted rows**, **remaining rows**, **elapsed time**, **rows per second**, **current batch number**, and an **error message** when the job fails.

**Acceptance criteria**: launch from GUI; job id returned immediately; target table is dropped and recreated before load; full data loads in batches (no `read_sql`/`fetchall`/row-by-row); the live progress UI shows overall progress bar, status, total/processed/inserted/remaining rows, elapsed time, rows/sec, current batch, and error-on-failure; browser doesn't block; job status updates; **re-running the same table yields the same row count, not a doubled count**; Oracle read-only; CH writes only to `oracle_migration_hazem`.

**Constitution gate (P-V, P-I, P-II, P-VII)**: extraction uses `cursor.fetchmany(MIGRATION_BATCH_SIZE)` with tuned `arraysize`/`prefetchrows` (no full-table read, no `pandas.read_sql`, no `fetchall`, no row-by-row insert); Oracle issues only `SELECT`; only `DROP TABLE IF EXISTS`/`CREATE TABLE`/`INSERT` run, and only against `oracle_migration_hazem`; source schema/table re-validated against metadata before launch; `migration_service.py`/`job_service.py` import no FastAPI; no secrets in job records or logs.

**Manual test commands**:
```bash
JOB=$(curl -s -X POST http://localhost:8000/api/migrations \
  -H 'Content-Type: application/json' \
  -d '{"source_schema":"CM","source_table":"COMPONENT","target_table":"CM__COMPONENT","workers":1,"partition_column":null}' | python -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
curl http://localhost:8000/api/migrations/$JOB
curl http://localhost:8000/api/migrations/$JOB/status
# Re-launch the SAME table and confirm the target row count is unchanged (latest-only, no append/duplication)
```

**Stop point**: Stop after Phase 6 until one full table copies successfully AND a second run of the same table leaves the target row count unchanged.

---

### Phase 7 — Parallel Migration Engine **(with Parallel Mode Selector)**

**Goal**: Faster **initial full load** for large tables via parallel extraction + batch load, preserving the latest-only replace guarantee. Expose the parallel technique to the user via a **Parallel Mode** dropdown (`Auto` / `Numeric Range` / `Date Range` / `Hash`): the backend either honors a concrete mode (validated against the selected column's Oracle datatype) or, in `Auto`, resolves the best mode from that datatype; the job records both the requested and resolved mode and surfaces them in the API and GUI.

**Scope**: Parallel migration after single-thread (Phase 6) is stable. Engine modes: numeric range, date range, hash fallback, plus `auto` resolution. User-selectable **Parallel Mode** with pre-launch datatype validation, requested/resolved tracking, and per-worker + overall progress aggregation. Still full-load replace only — no CDC/incremental/dedup/merge/append. The service layer stays framework-agnostic (no FastAPI imports); routes stay thin wrappers.

**Files to create or update**:
- `app/services/migration_service.py` — keep the drop+create as a **single step performed once** before any worker starts; then add a worker pool that loads partitions of the **full** source: numeric-range splitting (`MIN/MAX`, half-open ranges, final range inclusive), date-range splitting, hash mode (`MOD(ORA_HASH(col), :workers) = :id`); aggregate per-worker progress into the overall job progress; mark job FAILED if any worker fails. Each worker observes the same performance rules as Phase 6 (`arraysize`/`prefetchrows`, `fetchmany`, batch insert, explicit/stable column order). Ranges partition the whole table exactly once (union = full table, no overlap). **Add a pure resolver/validator** `resolve_parallel_mode(parallel_mode, partition_column, column_metadata, workers)` that performs Auto resolution + explicit-mode datatype validation (reading the column datatype from read-only Oracle metadata, never from the client) and returns the concrete resolved mode (or raises a controlled validation error); map the resolved mode onto the internal `partition_mode` (`numeric_range`→`numeric`, `date_range`→`date`, `hash`→`hash`). **No FastAPI imports** — importable from Flask.
- `app/services/job_service.py` — add a per-worker progress registry on the job (see fields below); aggregate workers' `processed_rows`/`inserted_rows` into the job totals and recompute `progress_percent`/`rows_per_second`; **persist `requested_parallel_mode` and `resolved_parallel_mode` on the job** (in `get_job`/`get_status` output) and carry `resolved_parallel_mode` onto each worker entry.
- `app/config.py` — `MIGRATION_DEFAULT_WORKERS=8`, enforce max 16.
- `app/api/migration_routes.py` — thin wrapper: add `parallel_mode: str = "auto"` to the `MigrationRequest` model; accept and validate `workers` and partition column; call `resolve_parallel_mode` **before** creating/launching the job (a validation error → controlled `400`, no job created); `/status` now also returns the `workers` array plus `requested_parallel_mode`/`resolved_parallel_mode`. No business logic in this file.
- `app/templates/index.html` — add the **Parallel Mode** `<select>` (`Auto` / `Numeric Range` / `Date Range` / `Hash`, default `Auto`) near **Partition/Hash Column** and **Worker Threads**, with per-mode helper text; render a **per-worker progress table/cards** alongside the overall progress bar.
- `app/static/app.js` — send `parallel_mode` in the `POST /api/migrations` body; after launch display `requested_parallel_mode`/`resolved_parallel_mode`; render the resolved mode on each worker card/row; render per-worker progress from the `workers` array on each poll; surface validation errors (datatype mismatch, missing column, unknown mode) and the single-worker warning.
- `tests/test_range_split.py` — unit tests proving no overlap/no gaps for numeric and date splits.
- `tests/test_parallel_mode.py` — pure-function tests over `resolve_parallel_mode`: Auto→numeric_range for NUMBER, Auto→date_range for DATE/TIMESTAMP, Auto→hash otherwise; explicit-mode datatype mismatches rejected; hash requires a column; `workers == 1` single-thread allowance/warning; requested workers above max clamp to 16.

**Parallel Mode field model & terminology**:
- `parallel_mode` (user-facing API field) ∈ `auto` | `numeric_range` | `date_range` | `hash`; defaults to `auto` when omitted.
- `requested_parallel_mode` = exactly what the client sent.
- `resolved_parallel_mode` = the concrete mode the engine runs ∈ `numeric_range` | `date_range` | `hash` (never `auto`); may be reported as `single` for a single-worker run.
- These map onto the engine's internal `partition_mode`: `numeric_range`→`numeric`, `date_range`→`date`, `hash`→`hash`.

**Auto resolution rules** (from the selected partition/hash column's Oracle datatype):
- `NUMBER` column → `numeric_range`.
- `DATE` or `TIMESTAMP%` column → `date_range`.
- Any other valid, selected column → `hash` (uses `ORA_HASH`).
- No usable column with `auto` and `workers > 1` → clear validation error that a partition/hash column is required for parallel execution.

**Explicit-mode validation rules** (return a clear `400` **before** launching — no job created on failure; datatype read from `all_tab_columns`, never trusted from the client):
- `numeric_range` requires a `NUMBER` column.
- `date_range` requires a `DATE` or `TIMESTAMP%` column.
- `hash` requires a selected column (any supported partition-candidate type); uses `ORA_HASH(<column>)` and **may be used even for NUMBER or DATE columns** to override Auto when numeric/date range distribution is poor.
- A mode that does not match the selected column's datatype (e.g. `date_range` on a `NUMBER` column) is rejected with a message naming the chosen mode, the column, and its datatype. An unknown `parallel_mode` value is rejected.

**Worker-count rule** (`workers == 1`): single-thread behavior is allowed even when a parallel mode is selected — the backend runs the proven Phase 6 single-thread path (reporting `resolved_parallel_mode` as `single`) or clearly warns that the selected mode only takes effect when `workers > 1`. Never an error solely because a parallel mode was chosen with one worker. Worker count stays capped at 16.

**Per-worker progress fields** (tracked per worker, returned in `/status`): `worker_id`, `partition_mode`, `resolved_parallel_mode`, `partition_column`, `range_start`, `range_end`, `status`, `processed_rows`, `inserted_rows`, `batches_completed`, `rows_per_second`, `error_message`.

**Code that must exist after the phase**:
- Target table is dropped and recreated **exactly once** per job (before workers fan out); workers only `INSERT` into that fresh target — never re-drop or re-create mid-job.
- `POST /api/migrations` accepts `parallel_mode` (omitting → `auto`); `resolve_parallel_mode(...)` applies the Auto rules + explicit-mode datatype validation using read-only Oracle metadata and returns the concrete resolved mode, free of FastAPI coupling.
- Mode selection feeds the existing engine: numeric range when resolved to numeric; date range when resolved to date; hash otherwise.
- Per-worker bounded SQL using bind variables; each worker batch-inserts and updates its own progress (the fields above), which aggregates into the overall job progress.
- The job (and each worker entry) carries `requested_parallel_mode` and `resolved_parallel_mode`; `GET /api/migrations/{job_id}` and `GET /api/migrations/{job_id}/status` return both, plus the overall job progress (Phase 6 fields) and a `workers` array (per-worker fields above). See `contracts/migrations.md`.
- The GUI shows the Parallel Mode dropdown with helper text, displays the resolved mode after launch, and shows one row/card per worker (worker_id, mode, column, range, status, processed/inserted rows, batches, rows/sec, error) in addition to the overall progress bar.
- Worker count configurable, default 8, capped at 16; any worker failure → job FAILED (and that worker's `error_message` is surfaced). A single-worker launch with a parallel mode is allowed/warned, never a hard error.

**Acceptance criteria**: numeric parallel works; date parallel works when date column exists; hash mode works as fallback and as an explicit override for NUMBER/DATE columns; the Parallel Mode dropdown is visible near Partition/Hash Column and Worker Threads with per-mode helper text; `POST /api/migrations` accepts `parallel_mode` (default `auto`); Auto resolves by datatype (NUMBER→numeric_range, DATE/TIMESTAMP→date_range, else→hash); a mode conflicting with the column datatype (or `hash`/parallel `auto` with no usable column) returns a clear pre-launch `400` and creates no job; `requested_parallel_mode`/`resolved_parallel_mode` appear in `/status` and the GUI (overall + per-worker cards); `workers == 1` with a parallel mode is allowed/warned, never a hard error; worker failures handled and surfaced per worker; total processed/inserted rows tracked and aggregated; the GUI renders per-worker progress cards plus the overall bar; no duplicate/missing ranges for numeric/date; re-running the same table still yields latest-only counts (single drop+create per job, not per worker).

**Constitution gate (P-V, P-VI, P-I, P-II, P-VII)**: parallel mode is enabled only after single-thread (Phase 6) is proven; each worker still uses tuned `arraysize`/`prefetchrows` + chunked `fetchmany` + batch insert (no full-range load into memory, no `fetchall`, no row-by-row); per-worker `SELECT` bounds use bind variables; worker count is clamped to max 16; the datatype used to resolve/validate the Parallel Mode is read from live Oracle metadata (P-VI) — the client's claimed datatype is never trusted; mismatched mode/column combinations and unknown `parallel_mode` values are rejected with controlled errors and no dynamic SQL from raw input (P-VII); the only ClickHouse statements are one `DROP`/`CREATE` pair plus `INSERT`s, all in `oracle_migration_hazem`; row-count reconciliation (Phase 8) confirms no duplicate/missing rows.

**Manual test commands**:
```bash
# Numeric parallel run
curl -X POST http://localhost:8000/api/migrations \
  -H 'Content-Type: application/json' \
  -d '{"source_schema":"CM","source_table":"COMPONENT","target_table":"CM__COMPONENT","workers":8,"partition_column":"ID","parallel_mode":"numeric_range"}'

# Auto on a NUMBER column → resolves to numeric_range
curl -s -X POST http://localhost:8000/api/migrations \
  -H 'Content-Type: application/json' \
  -d '{"source_schema":"CM","source_table":"COMPONENT","target_table":"CM__COMPONENT","workers":8,"partition_column":"ID","parallel_mode":"auto"}'

# Explicit date_range on a NUMBER column → controlled 400, no job created
curl -i -X POST http://localhost:8000/api/migrations \
  -H 'Content-Type: application/json' \
  -d '{"source_schema":"CM","source_table":"COMPONENT","target_table":"CM__COMPONENT","workers":8,"partition_column":"ID","parallel_mode":"date_range"}'

# Hash without a selected column → controlled 400 (column required)
curl -i -X POST http://localhost:8000/api/migrations \
  -H 'Content-Type: application/json' \
  -d '{"source_schema":"CM","source_table":"COMPONENT","target_table":"CM__COMPONENT","workers":8,"partition_column":null,"parallel_mode":"hash"}'

# Status returns requested/resolved mode + per-worker resolved mode
curl -s http://localhost:8000/api/migrations/$JOB/status
pytest tests/test_range_split.py tests/test_parallel_mode.py
```

**Stop point**: Stop after Phase 7 until parallel migration — including Parallel Mode selection, Auto resolution, datatype validation, requested/resolved display, and per-worker + overall progress — is tested on small and medium tables. Then continue Phase 8 (Validation, Counts, and Reconciliation).

---

### Phase 8 — Validation, Counts, and Reconciliation

**Goal**: Confirm Oracle and ClickHouse row counts match after migration.

**Scope**: Post-migration validation only.

**Files to create or update**:
- `app/services/migration_service.py` (or `job_service.py`) — after load, run Oracle `COUNT(*)` and ClickHouse `COUNT(*)`, compute match.
- Job metadata — add `source_row_count`, `target_row_count`, `count_match`, `validation_status`.
- `app/api/migration_routes.py` — expose validation fields in the full job record **and in `GET /api/migrations/{job_id}/status`** (so a single poll returns overall progress + per-worker progress + validation). See `contracts/migrations.md`.
- `app/static/app.js` / `index.html` — show counts and match/mismatch.

**Code that must exist after the phase**:
- Oracle count: `SELECT COUNT(*) FROM <schema>.<table>` (read-only).
- ClickHouse count: `SELECT COUNT(*) FROM oracle_migration_hazem.<schema>__<table>`.
- Because this is a full-load replace into a freshly created table, `count_match` is exact equality (target == source); any inequality is a hard validation failure. Counts + match stored in job and shown in GUI; mismatch clearly flagged.
- `GET /api/migrations/{job_id}/status` now returns the validation fields (`source_row_count`, `target_row_count`, `count_match`, `validation_status`) in addition to overall progress and the `workers` array.

**Acceptance criteria**: source count captured; target count captured; exact count match shown in GUI; validation failure clearly displayed; re-running the same table reports the same source/target counts (no drift from duplication); validation does not modify Oracle.

**Constitution gate (P-I, P-II)**: validation uses only `SELECT COUNT(*)` — read-only on Oracle and read-only on `oracle_migration_hazem`; no other database is queried for writes; no Oracle modification of any kind.

**Manual test commands**:
```bash
curl http://localhost:8000/api/migrations/$JOB        # includes source_row_count, target_row_count, count_match, validation_status
```

**Stop point**: Stop after Phase 8 until reconciliation works.

---

### Phase 9 — Final Docker Compose and Team Run

**Goal**: Make the project easy for a teammate/manager to run from a fresh clone.

**Scope**: Finalize Dockerfile, Docker Compose, README, `.env.example`, logs, troubleshooting.

**Files to create or update**:
- `Dockerfile`, `docker-compose.yml` (container name `oracle-clickhouse-migration-app`, port 8000, env-file wiring).
- `README.md` — overview, prerequisites, VPN requirement, `.env` setup, compose run command, health-check commands, GUI usage, Oracle troubleshooting, ClickHouse troubleshooting, security notes. **Must also document**: (a) this engine performs **initial full load only** — every launch drops and recreates the target and reloads in full (latest-only, no append/incremental); (b) what is explicitly out of scope (CDC, incremental, watermark, dedup, merge/upsert, staging swap, skip-existing) and that CDC/incremental are owned by another team; (c) a **Flask integration** section showing the service layer is framework-agnostic and importable, e.g. `from app.services.migration_service import launch_initial_load` and `from app.services.metadata_service import get_oracle_tables`.
- `.env.example` — final, placeholders only.

**Code that must exist after the phase**: No new app logic required; packaging + docs finalized. Service modules (`app/services/*`, `app/db/*`) remain free of FastAPI imports so they can be reused from Flask. App reachable at `http://localhost:8000` after `docker compose up -d --build`.

**Acceptance criteria**: fresh clone works with `.env`; compose starts app; health checks work; GUI works; full-load migration works (and re-run stays latest-only); README clear for another engineer and documents the full-load-only scope and Flask integration path.

**Constitution gate (P-III, P-VII)**: only `.env.example` (placeholders) is committed; the real `.env` stays git-ignored; `Dockerfile`/`docker-compose.yml`/`README` contain no real credentials; README "Security notes" restate the read-only-Oracle and fixed-target rules.

**Manual test commands**:
```bash
cp .env.example .env   # fill in real secrets locally (never committed)
docker compose up -d --build
curl http://localhost:8000/api/health
curl http://localhost:8000/api/health/oracle
curl http://localhost:8000/api/health/clickhouse
git status --porcelain | grep -E "(^|/)\.env$" && echo "ERROR: .env tracked" || echo ".env not tracked"
grep -rEi "password|passwd|secret" Dockerfile docker-compose.yml README.md   # expect no real values
```

**Stop point**: Stop after Phase 9 once a teammate can run it unaided.

---

### Phase 10 — Hardening and Production Readiness

**Goal**: Prepare for controlled production/UAT use.

**Scope**: Add production-quality safety + observability.

**Files to create or update**:
- `app/main.py` / new `app/api/auth.py` — GUI access protection + (optional) role-based permissions.
- `app/services/job_service.py` — persistent migration audit table; cancel-job support; retry policy; timeout settings; max row/table size warning.
- `app/services/report.py` — downloadable migration report.
- Logging config — structured JSON logging without secrets; app-level rate limiting; pre-migration confirmation popup in GUI that explicitly warns the launch will **drop and recreate** the target table (destructive full-load replace).

**Code that must exist after the phase**:
- Basic access protection on the GUI; auditable migration records (each recording the full-load drop+create+reload); traceable failures; secret-free structured logs; cancel + destructive-replace confirmation; deployment notes in README.

**Acceptance criteria**: app has basic access protection; migration operations auditable; failures traceable; no secrets in logs; the pre-migration confirmation states the target will be dropped and reloaded; production deployment notes documented.

**Constitution gate (P-VII, P-II, P-III)**: structured logs are verified secret-free; if a migration audit table is added it lives only in `oracle_migration_hazem`; the authorized full-load operations (`DROP TABLE IF EXISTS`/`CREATE TABLE`/`INSERT`/`SELECT`) remain confined to `oracle_migration_hazem` and no other destructive operation (e.g. `TRUNCATE`, or DROP/CREATE against any other database) is introduced; auth credentials/secrets come only from environment.

**Manual test commands**:
```bash
curl -i http://localhost:8000/            # protected resources require auth
curl -X POST http://localhost:8000/api/migrations/$JOB/cancel
docker logs oracle-clickhouse-migration-app | grep -Ei "password|passwd|secret" && echo "ERROR: secret in logs" || echo "logs clean"
```

**Stop point**: Final phase — project complete per PLAN.md §21 Definition of Done.

## Complexity Tracking

No constitution violations to justify; this section is intentionally empty.
