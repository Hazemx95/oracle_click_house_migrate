# Contract: Health Endpoints

## GET /api/health
Service liveness. Introduced in Phase 1.

**Response 200**
```json
{ "status": "ok", "service": "oracle-clickhouse-migration-engine" }
```

## GET /api/health/oracle
Oracle connectivity + metadata readability. Read-only. Introduced in Phase 2.

Internally runs `SELECT 1 FROM dual` and `SELECT COUNT(*) FROM all_tables`.

**Response 200 (healthy)**
```json
{
  "status": "success",
  "database": "oracle",
  "can_connect": true,
  "can_read_metadata": true
}
```

**Response 200/503 (unhealthy)** — clear, credential-free error
```json
{
  "status": "error",
  "database": "oracle",
  "can_connect": false,
  "can_read_metadata": false,
  "error": "<safe message, no credentials>"
}
```

## GET /api/health/clickhouse
ClickHouse connectivity + fixed target-database presence. Introduced in Phase 2.

Internally runs `SELECT 1` and `SELECT name FROM system.databases WHERE name = 'oracle_migration_hazem'`. Does **not** create the database unless `CLICKHOUSE_ALLOW_CREATE_DATABASE=true`.

**Response 200 (healthy)**
```json
{
  "status": "success",
  "database": "clickhouse",
  "can_connect": true,
  "target_database": "oracle_migration_hazem",
  "target_database_exists": true
}
```

**Notes**
- No credentials appear in any response or log line.
- `target_database_exists` may be `false`; this is reported, not auto-fixed by default.
