# Quickstart & Phase Validation Guide

This guide validates the engine end to end and per phase. It assumes a populated local `.env` (copied from `.env.example`) and network access to Oracle and ClickHouse (VPN may be required). Implementation details live in `plan.md`, `data-model.md`, and `contracts/`.

## Prerequisites
- Python 3.11+ (for local run) or Docker + Docker Compose (for containerized run).
- A real `.env` file (never committed). Start from the template:
  ```bash
  cp .env.example .env
  # edit .env to add real Oracle/ClickHouse credentials
  git check-ignore .env   # must print .env
  ```
- Network reachability to the Oracle host and the ClickHouse host.

## Run locally
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Run with Docker Compose
```bash
docker compose up -d --build
# app available at http://localhost:8000
docker logs oracle-clickhouse-migration-app
```

## Per-phase validation

### Phase 1 — bootstrap
```bash
curl http://localhost:8000/api/health        # {"status":"ok","service":"oracle-clickhouse-migration-engine"}
# open http://localhost:8000 in a browser → GUI shell renders
git check-ignore .env                         # prints .env
```

### Phase 2 — health checks
```bash
curl http://localhost:8000/api/health/oracle      # can_connect + can_read_metadata true
curl http://localhost:8000/api/health/clickhouse  # target_database_exists true (no auto-create)
# confirm: docker logs show NO credentials
```

### Phase 3 — metadata discovery
```bash
curl http://localhost:8000/api/oracle/schemas
curl "http://localhost:8000/api/oracle/tables?schema=CM"
curl "http://localhost:8000/api/oracle/columns?schema=CM&table=COMPONENT"
curl "http://localhost:8000/api/oracle/partition-columns?schema=CM&table=COMPONENT"
curl "http://localhost:8000/api/oracle/tables?schema=DOES_NOT_EXIST"   # controlled error
```

### Phase 4 — GUI dropdowns
- Open the GUI; confirm schemas load on open and health indicators show.
- Select a schema → table dropdown refreshes; ClickHouse schema destination auto-fills.
- Select a table → partition/hash column dropdown refreshes; target table name auto-fills.
- Confirm the ClickHouse database field is fixed and disabled to `oracle_migration_hazem`.

### Phase 5 — DDL generation
```bash
curl -X POST http://localhost:8000/api/clickhouse/create-table-preview \
  -H 'Content-Type: application/json' \
  -d '{"schema":"CM","table":"COMPONENT","target_table":"CM__COMPONENT","order_by":null}'
curl -X POST http://localhost:8000/api/clickhouse/create-table \
  -H 'Content-Type: application/json' \
  -d '{"schema":"CM","table":"COMPONENT","target_table":"CM__COMPONENT","order_by":null}'
# negative: a non-oracle_migration_hazem target must be rejected
pytest tests/test_ddl_mapper.py
```

### Phase 6 — single-thread migration
```bash
JOB=$(curl -s -X POST http://localhost:8000/api/migrations \
  -H 'Content-Type: application/json' \
  -d '{"source_schema":"CM","source_table":"COMPONENT","target_table":"CM__COMPONENT","workers":1,"partition_mode":"single","partition_column":null}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
echo "job: $JOB"          # returned immediately
curl http://localhost:8000/api/migrations/$JOB/status   # processed_rows climbs
```

### Phase 7 — parallel migration
```bash
curl -X POST http://localhost:8000/api/migrations \
  -H 'Content-Type: application/json' \
  -d '{"source_schema":"CM","source_table":"COMPONENT","target_table":"CM__COMPONENT","workers":8,"partition_mode":"numeric","partition_column":"ID"}'
pytest tests/test_range_split.py     # no overlap, no gaps
```

### Phase 8 — validation
```bash
curl http://localhost:8000/api/migrations/$JOB
# expect source_row_count, target_row_count, count_match=true, validation_status="MATCH"
```

### Phase 9 — team run (fresh clone)
```bash
cp .env.example .env && $EDITOR .env
docker compose up -d --build
curl http://localhost:8000/api/health
curl http://localhost:8000/api/health/oracle
curl http://localhost:8000/api/health/clickhouse
```

### Phase 10 — hardening
```bash
curl -i http://localhost:8000/                       # GUI protected
curl -X POST http://localhost:8000/api/migrations/$JOB/cancel
# confirm logs are structured JSON and contain no secrets
```

## Safety checks (run any time)
- Oracle: confirm no DDL/DML ever issued (only SELECT) — inspect logs/queries.
- ClickHouse: confirm every created/written table is in `oracle_migration_hazem`.
- Secrets: `grep -ri "password" app/ Dockerfile docker-compose.yml README.md` returns no real credentials.
