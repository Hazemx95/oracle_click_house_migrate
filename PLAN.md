# PLAN.md — Phase-Based Spec Kit Plan for Oracle to ClickHouse Migration Engine

## 1. Project Name

**Oracle to ClickHouse Parallel Data Migration Engine**

---

## 2. Main Goal

Build a Python web application that allows users to migrate selected Oracle tables into ClickHouse through a GUI.

The application must support:

* Oracle source schema discovery.
* Oracle source table discovery based on selected schema.
* Automatic target schema/table population.
* Fixed ClickHouse target database.
* High-performance batch loading.
* Future parallel migration support.
* Dockerized deployment using Docker Compose.
* Environment-based configuration using `.env`.

This project must be implemented **phase by phase**. Do not implement everything in one bundle.

---

## 3. Critical Safety Rules

### 3.1 Oracle Source Safety

Oracle is a **read-only source**.

The application must never modify Oracle.

Allowed Oracle operations:

```sql
SELECT
```

Forbidden Oracle operations:

```sql
CREATE
ALTER
DROP
TRUNCATE
INSERT
UPDATE
DELETE
MERGE
EXEC
CALL
```

The application must not change any Oracle source schema, table, data, trigger, procedure, or job.

---

### 3.2 ClickHouse Target Safety

All data must be loaded only into this ClickHouse database:

```text
oracle_migration_hazem
```

The application must not create, drop, truncate, insert, or modify data in any other ClickHouse database.

Allowed ClickHouse operations only inside `oracle_migration_hazem`:

```sql
CREATE TABLE IF NOT EXISTS
INSERT INTO
SELECT
```

Optional controlled rerun operations inside `oracle_migration_hazem` only:

```sql
TRUNCATE TABLE
DROP TABLE
```

These optional operations must not be implemented unless explicitly required later.

---

## 4. Environment Configuration

All configuration must come from environment variables.

Do not hardcode credentials inside:

* Python source code.
* Dockerfile.
* Docker Compose.
* README.
* PLAN.md.
* Git repository.

Create `.env.example` only.

The real `.env` file must be ignored by Git.

### 4.1 Required Environment Variables

```env
CLICKHOUSE_HOST=
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=
CLICKHOUSE_PASS=
CLICKHOUSE_DATABASE=oracle_migration_hazem

P5_QA_ORACLE_USER=
P5_QA_ORACLE_PASSWORD=
P5_QA_ORACLE_HOST=
P5_QA_ORACLE_PORT=1521
P5_QA_ORACLE_SERVICE_NAME=
P5_QA_ORACLE_DSN=

APP_HOST=0.0.0.0
APP_PORT=8000
MIGRATION_BATCH_SIZE=100000
MIGRATION_DEFAULT_WORKERS=8
```

### 4.2 `.env.example`

```env
CLICKHOUSE_HOST=10.199.104.156
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASS=
CLICKHOUSE_DATABASE=oracle_migration_hazem

P5_QA_ORACLE_USER=admin
P5_QA_ORACLE_PASSWORD=replace_with_real_password
P5_QA_ORACLE_HOST=p5-ora-quality.cdyue4j7h7u5.us-east-1.rds.amazonaws.com
P5_QA_ORACLE_PORT=1521
P5_QA_ORACLE_SERVICE_NAME=quality
P5_QA_ORACLE_DSN=p5-ora-quality.cdyue4j7h7u5.us-east-1.rds.amazonaws.com:1521/quality

APP_HOST=0.0.0.0
APP_PORT=8000
MIGRATION_BATCH_SIZE=100000
MIGRATION_DEFAULT_WORKERS=8
```

### 4.3 `.gitignore`

```gitignore
.env
*.env
.venv/
__pycache__/
.pytest_cache/
*.pyc
.DS_Store
```

---

## 5. Target User Flow

The GUI must follow this flow:

```text
User opens application
        ↓
Application checks Oracle and ClickHouse health
        ↓
User selects Oracle source schema
        ↓
Application automatically loads tables for selected schema
        ↓
Application automatically fills target schema with same source schema
        ↓
User selects Oracle source table
        ↓
Application loads candidate partition/hash columns
        ↓
ClickHouse database is fixed as oracle_migration_hazem
        ↓
User optionally changes target table name
        ↓
User chooses worker thread count
        ↓
User clicks Launch Migration Pipeline
        ↓
Application creates migration job
        ↓
Background process migrates data
        ↓
GUI shows status and progress
```

---

## 6. Required GUI Fields

The GUI must include:

| Field                         | Type                  | Behavior                                  |
| ----------------------------- | --------------------- | ----------------------------------------- |
| Oracle Source Schema          | Dropdown              | Loaded dynamically from Oracle            |
| Oracle Source Table           | Dropdown              | Loaded dynamically after schema selection |
| Partition/Hash Column         | Dropdown              | Loaded dynamically after table selection  |
| Worker Threads                | Number input          | Default `8`                               |
| ClickHouse Schema Destination | Text input            | Auto-filled from selected Oracle schema   |
| ClickHouse Database           | Static/disabled input | Always `oracle_migration_hazem`           |
| Target Table Name             | Text input            | Default same as source table              |
| Launch Migration Pipeline     | Button                | Starts migration job                      |

---

## 7. Final ClickHouse Naming Rule

ClickHouse has a fixed database:

```text
oracle_migration_hazem
```

Because ClickHouse does not use Oracle-style schemas inside a database, preserve Oracle schema in the table name.

Recommended final table name:

```text
<oracle_schema>__<oracle_table>
```

Example:

```text
Oracle source:
CM.COMPONENT

ClickHouse target:
oracle_migration_hazem.CM__COMPONENT
```

If user provides custom target table name, still protect against collision by using:

```text
<target_schema>__<target_table>
```

---

# 8. Spec Kit Execution Strategy

## Important Rule

Do not implement this project as one large bundle.

Use one complete specification, but implement in phases.

Recommended flow:

```text
/specify
    ↓
/plan
    ↓
/tasks
    ↓
Implement Phase 1 only
    ↓
Test Phase 1
    ↓
Implement Phase 2 only
    ↓
Test Phase 2
    ↓
Continue phase by phase
```

Each phase must have:

* Scope.
* Files to create/update.
* Acceptance criteria.
* Manual test commands.
* Clear stop point.

Do not move to the next phase until the current phase is tested successfully.

---

# 9. Phase 1 — Project Bootstrap and Docker Skeleton

## Goal

Create the base project structure and make sure the application can start locally and through Docker Compose.

## Scope

Implement only:

* Project folder structure.
* FastAPI application skeleton.
* Basic home page.
* `.env.example`.
* `.gitignore`.
* `requirements.txt`.
* `Dockerfile`.
* `docker-compose.yml`.

Do not implement Oracle connection yet.

Do not implement ClickHouse connection yet.

Do not implement migration logic yet.

## Recommended Project Structure

```text
oracle-clickhouse-migration/
│
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
│   ├── main.py
│   ├── config.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── oracle_client.py
│   │   ├── clickhouse_client.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health_routes.py
│   │   ├── oracle_routes.py
│   │   ├── migration_routes.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── metadata_service.py
│   │   ├── ddl_mapper.py
│   │   ├── migration_service.py
│   │   ├── job_service.py
│   │
│   ├── templates/
│   │   ├── index.html
│   │
│   ├── static/
│   │   ├── app.js
│   │   ├── style.css
│
├── tests/
│   ├── test_config.py
```

## Required Dependencies

```text
fastapi
uvicorn[standard]
python-dotenv
pydantic
jinja2
python-multipart
oracledb
clickhouse-connect
```

## Required Basic Endpoint

```http
GET /
```

Should return the basic GUI page.

```http
GET /api/health
```

Should return:

```json
{
  "status": "ok",
  "service": "oracle-clickhouse-migration-engine"
}
```

## Dockerfile Requirement

The application must run using:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Docker Compose Requirement

The app must start with:

```bash
docker compose up -d --build
```

The app must be available at:

```text
http://localhost:8000
```

## Acceptance Criteria

Phase 1 is complete only when:

* App starts locally.
* App starts through Docker Compose.
* Browser opens the home page.
* `/api/health` returns success.
* `.env` is ignored by Git.
* No credentials are hardcoded.

## Manual Test Commands

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
curl http://localhost:8000/api/health
```

```bash
docker compose up -d --build
```

```bash
curl http://localhost:8000/api/health
```

## Stop Point

Stop after Phase 1. Do not continue until the user confirms the app starts successfully.

---

# 10. Phase 2 — Database Connection Health Checks

## Goal

Verify that the application can connect to Oracle and ClickHouse from the same environment where the app runs.

## Scope

Implement:

* Oracle connection client.
* ClickHouse connection client.
* Environment-based configuration.
* Oracle health endpoint.
* ClickHouse health endpoint.

Do not implement GUI dropdowns yet.

Do not implement migration yet.

## Required Endpoints

```http
GET /api/health/oracle
GET /api/health/clickhouse
```

## Oracle Health Check

Oracle test query:

```sql
SELECT 1 FROM dual
```

Oracle metadata test:

```sql
SELECT COUNT(*) FROM all_tables
```

Expected response:

```json
{
  "status": "success",
  "database": "oracle",
  "can_connect": true,
  "can_read_metadata": true
}
```

## ClickHouse Health Check

ClickHouse test query:

```sql
SELECT 1
```

ClickHouse target database validation:

```sql
SELECT name
FROM system.databases
WHERE name = 'oracle_migration_hazem'
```

Expected response:

```json
{
  "status": "success",
  "database": "clickhouse",
  "can_connect": true,
  "target_database": "oracle_migration_hazem",
  "target_database_exists": true
}
```

## Important Rule

If target database does not exist, do not automatically create it in this phase unless explicitly configured.

Default behavior:

```env
CLICKHOUSE_ALLOW_CREATE_DATABASE=false
```

## Acceptance Criteria

Phase 2 is complete only when:

* Oracle health check succeeds.
* ClickHouse health check succeeds.
* Health errors are clear.
* No credentials are printed in logs.
* App still runs in Docker Compose.

## Manual Test Commands

```bash
curl http://localhost:8000/api/health/oracle
```

```bash
curl http://localhost:8000/api/health/clickhouse
```

Also test from Docker:

```bash
docker compose up -d --build
docker logs oracle-clickhouse-migration-app
```

## Stop Point

Stop after Phase 2. Do not continue until Oracle and ClickHouse health checks are successful.

---

# 11. Phase 3 — Oracle Metadata Discovery APIs

## Goal

Allow the backend to dynamically discover Oracle schemas, tables, columns, and partition/hash candidates.

## Scope

Implement metadata APIs only.

Do not implement full GUI behavior yet.

Do not implement migration yet.

## Required Endpoints

```http
GET /api/oracle/schemas
GET /api/oracle/tables?schema=<schema>
GET /api/oracle/columns?schema=<schema>&table=<table>
GET /api/oracle/partition-columns?schema=<schema>&table=<table>
```

## Query: List Oracle Schemas

```sql
SELECT DISTINCT owner
FROM all_tables
ORDER BY owner
```

## Query: List Tables by Schema

```sql
SELECT table_name
FROM all_tables
WHERE owner = :schema_name
ORDER BY table_name
```

## Query: List Columns

```sql
SELECT
    column_name,
    data_type,
    data_length,
    data_precision,
    data_scale,
    nullable
FROM all_tab_columns
WHERE owner = :schema_name
  AND table_name = :table_name
ORDER BY column_id
```

## Query: Candidate Partition/Hash Columns

```sql
SELECT
    column_name,
    data_type,
    data_precision,
    data_scale,
    nullable
FROM all_tab_columns
WHERE owner = :schema_name
  AND table_name = :table_name
  AND (
        data_type IN ('NUMBER', 'DATE')
        OR data_type LIKE 'TIMESTAMP%'
      )
ORDER BY column_id
```

## Security Requirement

Schema and table values must be validated from Oracle metadata.

Do not allow raw user input to be directly concatenated into SQL.

Use bind variables.

## Acceptance Criteria

Phase 3 is complete only when:

* `/api/oracle/schemas` returns visible schemas.
* `/api/oracle/tables?schema=...` returns tables for selected schema.
* `/api/oracle/columns?schema=...&table=...` returns columns.
* `/api/oracle/partition-columns?...` returns candidate columns.
* Invalid schema/table returns controlled error.
* Oracle source remains read-only.

## Manual Test Commands

```bash
curl http://localhost:8000/api/oracle/schemas
```

```bash
curl "http://localhost:8000/api/oracle/tables?schema=CM"
```

```bash
curl "http://localhost:8000/api/oracle/columns?schema=CM&table=CROSS_REP_TYPE"
```

## Stop Point

Stop after Phase 3. Do not continue until metadata APIs work correctly.


---
## Initial Full Load and Flask Integration Requirement

This project implements initial full load only.

CDC, incremental loading, watermark logic, deduplication, merge/upsert, append-only duplicate loading, and staging-table logic are not part of this project.

CDC and incremental logic will be handled by another team.

### Required Initial Load Behavior

When the user clicks Launch / Replicate, the application must:

1. Read Oracle metadata.
2. Drop the target ClickHouse table if it already exists.
3. Create a new empty ClickHouse target table using Oracle-to-ClickHouse data type mapping.
4. Extract all rows from Oracle using batch/chunked reads.
5. Insert all rows into ClickHouse using batch inserts.
6. Track job status, processed rows, and errors.

### Repeated Execution Behavior

If the same Oracle schema/table is launched again:

1. Drop the existing ClickHouse target table.
2. Recreate the target table.
3. Load the full Oracle source table again.

The final ClickHouse table must contain only the latest full load result.

The application must not append duplicate full copies.

Example:

First run:

* Oracle table has 100 rows.
* ClickHouse target table is created and loaded with 100 rows.

Second run:

* Existing ClickHouse target table is dropped.
* Target table is recreated.
* Oracle table is fully loaded again.
* Final ClickHouse target table has 100 rows, not 200 rows.

### Out of Scope

The application must not implement:

* CDC
* Incremental loading
* Watermark filtering
* Deduplication
* Merge/upsert
* Staging table replacement
* Append-only duplicate loading
* Skip-existing-row logic

### Oracle Safety

Oracle remains read-only.

The application can only execute SELECT statements against Oracle.

### ClickHouse Safety

ClickHouse write operations are allowed only inside:

`oracle_migration_hazem`

Allowed ClickHouse operations for this project:

* DROP TABLE IF EXISTS inside `oracle_migration_hazem`
* CREATE TABLE inside `oracle_migration_hazem`
* INSERT INTO inside `oracle_migration_hazem`
* SELECT inside `oracle_migration_hazem`

Target table format:

`oracle_migration_hazem.<source_schema>__<source_table>`

Example:

`oracle_migration_hazem.CM__COMPONENT`

### Flask Integration Requirement

The migration code must be easy to integrate into an existing Flask application.

Business logic must be reusable and must not be tightly coupled to FastAPI.

The real logic must live in service modules:

* `app/services/metadata_service.py`
* `app/services/ddl_mapper.py`
* `app/services/migration_service.py`
* `app/services/job_service.py`
* `app/db/oracle_client.py`
* `app/db/clickhouse_client.py`

FastAPI route files must only call service-layer functions.

The future Flask app should be able to import the service layer directly.

Example future Flask usage:

```python
from app.services.migration_service import launch_initial_load
from app.services.metadata_service import get_oracle_tables
```
---


# 12. Phase 4 — GUI Dynamic Dropdowns

## Goal

Build the interactive GUI behavior.

## Scope

Implement frontend behavior only using the already completed metadata APIs.

Do not implement migration yet.

## Required Behavior

When page loads:

* Call `/api/health/oracle`.
* Call `/api/health/clickhouse`.
* Call `/api/oracle/schemas`.

When user selects Oracle source schema:

* Call `/api/oracle/tables?schema=<schema>`.
* Refresh Oracle source table dropdown.
* Auto-fill ClickHouse schema destination with the selected schema.

When user selects Oracle source table:

* Call `/api/oracle/partition-columns?schema=<schema>&table=<table>`.
* Refresh partition/hash column dropdown.
* Auto-fill target table name with the selected source table.

ClickHouse database field must be fixed and disabled:

```text
oracle_migration_hazem
```

## Acceptance Criteria

Phase 4 is complete only when:

* GUI loads schemas dynamically.
* Changing source schema refreshes tables.
* Changing source schema auto-fills target schema.
* Changing source table refreshes partition/hash columns.
* Changing source table auto-fills target table.
* ClickHouse database is fixed to `oracle_migration_hazem`.

## Stop Point

Stop after Phase 4. Do not continue until GUI dynamic behavior works.

---

# 13. Phase 5 — ClickHouse DDL Generation

## Goal

Generate and execute ClickHouse `CREATE TABLE IF NOT EXISTS` based on Oracle table metadata.

## Scope

Implement:

* Oracle-to-ClickHouse type mapping.
* Safe target table naming.
* ClickHouse DDL generation.
* Target database enforcement.

Do not implement full data migration yet.

## Target Naming

Use:

```text
<source_schema>__<source_table>
```

Example:

```text
CM__COMPONENT
```

Final ClickHouse path:

```text
oracle_migration_hazem.CM__COMPONENT
```

## Required Type Mapping

| Oracle Type      | ClickHouse Type         |
| ---------------- | ----------------------- |
| NUMBER scale 0   | Nullable(Int64)         |
| NUMBER scale > 0 | Nullable(Float64)       |
| VARCHAR2         | Nullable(String)        |
| NVARCHAR2        | Nullable(String)        |
| CHAR             | Nullable(String)        |
| NCHAR            | Nullable(String)        |
| CLOB             | Nullable(String)        |
| DATE             | Nullable(DateTime)      |
| TIMESTAMP        | Nullable(DateTime64(6)) |
| FLOAT            | Nullable(Float64)       |
| BINARY_FLOAT     | Nullable(Float32)       |
| BINARY_DOUBLE    | Nullable(Float64)       |

Use safe default:

```text
Nullable(String)
```

for unsupported types in the first version.

## Recommended ClickHouse Engine

If partition/hash/order column exists:

```sql
ENGINE = MergeTree
ORDER BY <partition_column>
```

Otherwise:

```sql
ENGINE = MergeTree
ORDER BY tuple()
```

## Required Endpoint

```http
POST /api/clickhouse/create-table-preview
```

Returns generated DDL without executing.

```http
POST /api/clickhouse/create-table
```

Executes `CREATE TABLE IF NOT EXISTS`.

## Acceptance Criteria

Phase 5 is complete only when:

* DDL preview works.
* Create table works.
* Table is created only in `oracle_migration_hazem`.
* Oracle is not modified.
* Unsupported Oracle types do not crash app.
* Dangerous target database values are rejected.

## Stop Point

Stop after Phase 5. Do not continue until table creation works.

---

# 14. Phase 6 — Single-Thread Batch Migration

## Goal

Implement the first working Oracle-to-ClickHouse data copy using safe batch loading.

## Scope

Implement single-thread migration only.

Do not implement parallel workers yet.

## Required Behavior

When user launches migration:

1. Validate source schema/table from Oracle metadata.
2. Validate target database is `oracle_migration_hazem`.
3. Create target ClickHouse table if not exists.
4. Read Oracle rows using `fetchmany(batch_size)`.
5. Insert rows into ClickHouse using batch insert.
6. Track total rows and processed rows.
7. Return job ID immediately.
8. GUI polls job status.

## Required Endpoints

```http
POST /api/migrations
GET /api/migrations/{job_id}
GET /api/migrations/{job_id}/status
```

## Job Statuses

```text
PENDING
RUNNING
SUCCESS
FAILED
CANCELLED
```

## Job Metadata

Track:

```text
job_id
source_schema
source_table
target_database
target_table
status
total_rows
processed_rows
started_at
finished_at
duration_seconds
error_message
```

## Performance Rule

Never do this:

```python
df = pandas.read_sql("SELECT * FROM huge_table", conn)
```

Use streaming/chunked fetch:

```python
cursor.fetchmany(batch_size)
```

## Acceptance Criteria

Phase 6 is complete only when:

* User can launch migration from GUI.
* App returns job ID immediately.
* Data loads into ClickHouse table.
* Migration works in batches.
* Browser does not wait for full migration.
* Job status updates.
* Oracle source is read-only.
* ClickHouse writes only to `oracle_migration_hazem`.

## Stop Point

Stop after Phase 6. Do not continue until one full table can be copied successfully.

---

# 15. Phase 7 — Parallel Migration Engine

## Goal

Improve performance for large Oracle tables using parallel extraction and batch loading.

## Scope

Implement parallel migration after single-thread migration is stable.

## Supported Modes

### 15.1 Numeric Range Mode

For numeric partition column:

```sql
SELECT MIN(<column>), MAX(<column>)
FROM <schema>.<table>
```

Split min/max into worker ranges.

Each worker extracts:

```sql
SELECT *
FROM <schema>.<table>
WHERE <column> >= :start_value
  AND <column> < :end_value
```

Final worker uses:

```sql
WHERE <column> >= :start_value
  AND <column> <= :end_value
```

### 15.2 Date Range Mode

For date/timestamp column:

* Get min/max date.
* Split into time ranges.
* Each worker extracts one range.

### 15.3 Hash Mode

Fallback option:

```sql
SELECT *
FROM <schema>.<table>
WHERE MOD(ORA_HASH(<column>), :worker_count) = :worker_id
```

Use hash mode only when column is non-null and high-cardinality.

## Required Rules

* Worker count must be configurable.
* Default worker count is `8`.
* Worker count must have a safe maximum.
* Recommended maximum: `16`.
* Each worker must batch insert into ClickHouse.
* Each worker must update progress.
* If any worker fails, job status becomes `FAILED`.

## Acceptance Criteria

Phase 7 is complete only when:

* Numeric parallel migration works.
* Date parallel migration works if date column exists.
* Hash mode works as fallback.
* Worker failures are handled.
* Total processed rows are tracked.
* No duplicate or missing ranges for numeric/date mode.

## Stop Point

Stop after Phase 7. Do not continue until parallel migration is tested on small and medium tables.

---

# 16. Phase 8 — Validation, Counts, and Reconciliation

## Goal

Validate that Oracle and ClickHouse row counts match after migration.

## Scope

Implement post-migration validation.

## Required Validation

Oracle count:

```sql
SELECT COUNT(*)
FROM <schema>.<table>
```

ClickHouse count:

```sql
SELECT COUNT(*)
FROM oracle_migration_hazem.<schema>__<table>
```

Store validation result in job metadata.

## Required Status Fields

```text
source_row_count
target_row_count
count_match
validation_status
```

## Acceptance Criteria

Phase 8 is complete only when:

* Source count is captured.
* Target count is captured.
* Count match is shown in GUI.
* Validation failure is clearly displayed.
* Validation does not modify Oracle.

## Stop Point

Stop after Phase 8. Do not continue until reconciliation works.

---

# 17. Phase 9 — Final Docker Compose and Team Run

## Goal

Make the project easy for team members or manager to run.

## Scope

Finalize:

* Dockerfile.
* Docker Compose.
* README.
* `.env.example`.
* Logs.
* Troubleshooting.

## Required Run Command

```bash
docker compose up -d --build
```

## Required Access URL

```text
http://localhost:8000
```

## Required README Sections

* Project overview.
* Prerequisites.
* VPN requirement.
* `.env` setup.
* Docker Compose run command.
* Health check commands.
* How to use GUI.
* Troubleshooting Oracle connection.
* Troubleshooting ClickHouse connection.
* Security notes.

## Acceptance Criteria

Phase 9 is complete only when:

* Fresh clone works with `.env`.
* Docker Compose starts app.
* Health checks work.
* GUI works.
* Migration works.
* README is clear for another engineer.

---

# 18. Phase 10 — Hardening and Production Readiness

## Goal

Prepare for controlled production/UAT usage.

## Scope

Add production-quality safety and observability.

## Recommended Improvements

* Add authentication for GUI.
* Add role-based permissions.
* Add migration audit table.
* Add retry policy.
* Add timeout settings.
* Add maximum row/table size warning.
* Add cancel job option.
* Add downloadable migration report.
* Add structured JSON logging.
* Add app-level rate limiting.
* Add confirmation popup before migration starts.

## Acceptance Criteria

Phase 10 is complete only when:

* App has basic access protection.
* Migration operations are auditable.
* Failures are traceable.
* No secrets appear in logs.
* Production deployment notes are documented.

---

# 19. Spec Kit Prompt to Use

Use this prompt with Spec Kit.

```text
/specify

Build a Python FastAPI web application called Oracle to ClickHouse Parallel Data Migration Engine.

The application must allow users to select an Oracle source schema, dynamically load all tables for that schema, select a source table, automatically fill the target schema and target table, and migrate data into a fixed ClickHouse database named oracle_migration_hazem.

The source Oracle database is read-only. The application must never modify Oracle. It can only execute SELECT statements against Oracle metadata and source tables.

The ClickHouse target database is fixed to oracle_migration_hazem. The application must not create or modify any other ClickHouse database.

The application must use environment variables from .env for Oracle and ClickHouse configuration. Credentials must not be hardcoded in code, Dockerfile, README, or PLAN.md.

The GUI must include Oracle Source Schema, Oracle Source Table, Partition/Hash Column, Worker Threads, ClickHouse Schema Destination, ClickHouse Database fixed to oracle_migration_hazem, Target Table Name, and Launch Migration Pipeline button.

Implementation must be phase-based. Do not implement the full system in one bundle. Create phases with acceptance criteria and stop points. The required phase order is:

1. Project Bootstrap and Docker Skeleton
2. Database Connection Health Checks
3. Oracle Metadata Discovery APIs
4. GUI Dynamic Dropdowns
5. ClickHouse DDL Generation
6. Single-Thread Batch Migration
7. Parallel Migration Engine
8. Validation, Counts, and Reconciliation
9. Final Docker Compose and Team Run
10. Hardening and Production Readiness

The migration must support large tables by using Oracle fetchmany batch extraction and ClickHouse batch inserts. It must not load huge Oracle tables fully into memory. Parallel migration should be added only after single-thread migration is working.

Create a detailed implementation plan and tasks for this project.
```

---

# 20. Implementation Instruction After `/tasks`

After Spec Kit creates the tasks, use this command style:

```text
Implement Phase 1 only. Do not implement Phase 2 or any later phase. Stop after Phase 1 acceptance criteria are complete.
```

After testing Phase 1 successfully:

```text
Implement Phase 2 only. Do not implement Phase 3 or any later phase. Stop after Phase 2 acceptance criteria are complete.
```

Continue with the same pattern for all phases.

---

# 21. Final Definition of Done

The full project is complete when:

* App runs locally.
* App runs with Docker Compose.
* Oracle health check works.
* ClickHouse health check works.
* Oracle schemas load dynamically.
* Oracle tables load dynamically after schema selection.
* Target schema auto-fills from source schema.
* Target table auto-fills from source table.
* ClickHouse database is fixed to `oracle_migration_hazem`.
* Target ClickHouse table is created safely.
* Data migrates in batches.
* Large tables do not load fully into memory.
* Parallel migration works after single-thread migration.
* Row count validation works.
* Oracle source remains read-only.
* ClickHouse writes only into `oracle_migration_hazem`.
* Credentials are fully environment-based.
* Docker Compose allows team run.
* README explains how to run and troubleshoot.
