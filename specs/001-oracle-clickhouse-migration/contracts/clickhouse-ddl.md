# Contract: ClickHouse DDL Endpoints

Introduced in Phase 5 (the critical DDL & type-mapping gate). All operations are confined to database `oracle_migration_hazem`; any other `target_database` value is rejected. Oracle is not touched except read-only metadata lookups for column types. The mapper (`app/services/ddl_mapper.py`) is framework-agnostic (**no FastAPI imports**) and consumes these `ALL_TAB_COLUMNS` fields: `column_name`, `data_type`, `data_length`, `data_precision`, `data_scale`, `nullable`, `char_length`, `char_used`.

## Type mapping (Oracle → ClickHouse)
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
| anything else / unsupported | — | `Nullable(String)` **+ warning** |

Unsupported types never crash; they fall back to `Nullable(String)` and add a warning (column name + original Oracle type) to the preview response. All ClickHouse identifiers (database/table/column) are safely backtick-quoted.

## Naming
Target table name = `<source_schema>__<source_table>` (or `<target_schema>__<target_table>` if customized). Full path: `oracle_migration_hazem.<name>`.

## Engine
- With order column: `ENGINE = MergeTree ORDER BY <order_column>`
- Without: `ENGINE = MergeTree ORDER BY tuple()`

## Drop-and-recreate semantics
This project performs **initial full load only**. Each launch starts from a fresh empty target, so the DDL is a **DROP-then-CREATE pair** — not an idempotent `CREATE TABLE IF NOT EXISTS`:
```sql
DROP TABLE IF EXISTS oracle_migration_hazem.<schema>__<table>;
CREATE TABLE oracle_migration_hazem.<schema>__<table> (...) ENGINE = MergeTree ORDER BY ...;
```
Both statements are guarded to act only in `oracle_migration_hazem`.

## POST /api/clickhouse/create-table-preview
Returns generated DDL (DROP + CREATE) and any mapping warnings **without executing**.

**Request**
```json
{ "schema": "CM", "table": "COMPONENT", "target_table": "CM__COMPONENT", "order_by": null }
```

**Response 200**
```json
{
  "target_database": "oracle_migration_hazem",
  "target_table": "CM__COMPONENT",
  "drop_ddl": "DROP TABLE IF EXISTS oracle_migration_hazem.CM__COMPONENT",
  "create_ddl": "CREATE TABLE oracle_migration_hazem.CM__COMPONENT (`ID` Nullable(Int64), `NAME` Nullable(String)) ENGINE = MergeTree ORDER BY tuple()",
  "warnings": []
}
```
`warnings` lists any columns whose Oracle type was unsupported and fell back to `Nullable(String)` (e.g. `{"column": "GEOM", "oracle_type": "SDO_GEOMETRY", "mapped_to": "Nullable(String)"}`).

## POST /api/clickhouse/create-table
Executes `DROP TABLE IF EXISTS` then `CREATE TABLE` in `oracle_migration_hazem`, yielding a fresh empty table even on re-run.

**Request**: same shape as preview.

**Response 200**
```json
{ "status": "created", "target_database": "oracle_migration_hazem", "target_table": "CM__COMPONENT", "dropped_existing": true, "warnings": [] }
```

**Response 400** — rejected target database or invalid input
```json
{ "status": "error", "error": "target database must be 'oracle_migration_hazem'" }
```

**Rules**: DROP + CREATE only, both confined to `oracle_migration_hazem`; unsupported Oracle types do not crash (fall back to `Nullable(String)` with a warning); identifiers safely quoted; dangerous/other database names rejected for both statements; Oracle unchanged.
