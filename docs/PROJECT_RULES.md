# Project Rules

## Purpose

This project builds the Oracle to ClickHouse Parallel Data Migration Engine as a
Python FastAPI web application. The application will let an engineer discover
Oracle schemas and tables, select a source table, and migrate data into a fixed
ClickHouse database through a GUI.

## Phase Discipline

- Implementation MUST proceed phase by phase.
- Phase 0 creates documentation and guardrails only.
- Application source code MUST NOT be created or changed in Phase 0.
- Phase 1 or later work MUST NOT start until Phase 0 guardrails are reviewed.
- Each future phase MUST have scope, files, acceptance criteria, manual test commands, and a stop point.

## Global Guardrails

- Oracle is a read-only source.
- ClickHouse writes are restricted to `oracle_migration_hazem` only.
- Credentials and configuration are environment-based only.
- Real `.env` files must not be committed.
- Large-table migration must use bounded batches, not full-table memory loads.
- User-provided schema, table, and column names must be validated before use.

## Planned Repository Shape

Future implementation phases may create these paths:

```text
app/
app/api/
app/db/
app/services/
app/templates/
app/static/
tests/
```

Phase 0 does not create those application paths.

## Required Dependency Set For Later Phases

Future Phase 1 dependency documentation must include:

- `fastapi`
- `uvicorn[standard]`
- `python-dotenv`
- `pydantic`
- `jinja2`
- `python-multipart`
- `oracledb`
- `clickhouse-connect`
