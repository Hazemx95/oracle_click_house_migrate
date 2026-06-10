# Oracle to ClickHouse Parallel Data Migration Engine

This repository is implemented phase by phase. Phase 1 provides only the base
FastAPI application skeleton, a home page, a service health endpoint, Docker
bootstrap files, and environment placeholders.

## Guardrails Summary

- Oracle is read-only. Only `SELECT` statements may be issued against Oracle.
- ClickHouse writes are restricted to `oracle_migration_hazem` only.
- Credentials and runtime configuration must come from environment variables only.
- Real `.env` files must not be committed; use `.env.example` placeholders only.
- Every future phase must define acceptance criteria, manual test commands, and a stop point.

## Current Phase

Phase 1: Project Bootstrap and Docker Skeleton.

Implemented in this phase:

- `GET /` renders a static GUI shell.
- `GET /api/health` returns service liveness.
- Local run via uvicorn.
- Docker Compose run configuration.
- Placeholder-only `.env.example`.

Not implemented in this phase:

- Oracle connection.
- ClickHouse connection.
- Metadata APIs.
- Migration logic.
- Parallel workers.

## Local Run

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/api/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "oracle-clickhouse-migration-engine"
}
```

## Docker Run

Create a local `.env` from `.env.example`, fill values locally, and do not commit it.

```bash
docker compose up -d --build
curl http://localhost:8000/api/health
```

## Phase 0 Documents

- `docs/PROJECT_RULES.md`
- `docs/SECURITY_RULES.md`
- `docs/PHASE_EXECUTION_GUIDE.md`
- `docs/ENVIRONMENT_RULES.md`
- `docs/ACCEPTANCE_CRITERIA.md`
