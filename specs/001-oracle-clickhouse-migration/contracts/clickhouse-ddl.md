# Contract: ClickHouse DDL Endpoints

Introduced in Phase 5. All operations are confined to database `oracle_migration_hazem`; any other `target_database` value is rejected. Oracle is not touched except read-only metadata lookups for column types.

## Type mapping (Oracle → ClickHouse)
| Oracle Type        | ClickHouse Type           |
| ------------------ | ------------------------- |
| NUMBER scale 0     | `Nullable(Int64)`         |
| NUMBER scale > 0   | `Nullable(Float64)`       |
| VARCHAR2 / NVARCHAR2 / CHAR / NCHAR / CLOB | `Nullable(String)` |
| DATE               | `Nullable(DateTime)`      |
| TIMESTAMP%         | `Nullable(DateTime64(6))` |
| FLOAT              | `Nullable(Float64)`       |
| BINARY_FLOAT       | `Nullable(Float32)`       |
| BINARY_DOUBLE      | `Nullable(Float64)`       |
| (anything else)    | `Nullable(String)` (safe default) |

## Naming
Target table name = `<source_schema>__<source_table>` (or `<target_schema>__<target_table>` if customized). Full path: `oracle_migration_hazem.<name>`.

## Engine
- With order column: `ENGINE = MergeTree ORDER BY <order_column>`
- Without: `ENGINE = MergeTree ORDER BY tuple()`

## POST /api/clickhouse/create-table-preview
Returns generated DDL **without executing**.

**Request**
```json
{ "schema": "CM", "table": "COMPONENT", "target_table": "CM__COMPONENT", "order_by": null }
```

**Response 200**
```json
{
  "target_database": "oracle_migration_hazem",
  "target_table": "CM__COMPONENT",
  "ddl": "CREATE TABLE IF NOT EXISTS oracle_migration_hazem.CM__COMPONENT (`ID` Nullable(Int64), `NAME` Nullable(String)) ENGINE = MergeTree ORDER BY tuple()"
}
```

## POST /api/clickhouse/create-table
Executes `CREATE TABLE IF NOT EXISTS` in `oracle_migration_hazem`.

**Request**: same shape as preview.

**Response 200**
```json
{ "status": "created", "target_database": "oracle_migration_hazem", "target_table": "CM__COMPONENT", "already_existed": false }
```

**Response 400** — rejected target database or invalid input
```json
{ "status": "error", "error": "target database must be 'oracle_migration_hazem'" }
```

**Rules**: unsupported Oracle types do not crash (fall back to `Nullable(String)`); dangerous/other database names rejected; Oracle unchanged.
