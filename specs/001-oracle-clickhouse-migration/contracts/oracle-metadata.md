# Contract: Oracle Metadata Discovery Endpoints

Introduced in Phase 3. All queries are **read-only** and use **bind variables**. User-supplied `schema`/`table` are validated against Oracle metadata before use; raw input is never concatenated into SQL.

## GET /api/oracle/schemas
Underlying: `SELECT DISTINCT owner FROM all_tables ORDER BY owner`.

**Response 200**
```json
{ "schemas": ["CM", "HR", "SALES"] }
```

## GET /api/oracle/tables?schema=<schema>
Underlying: `SELECT table_name FROM all_tables WHERE owner = :schema_name ORDER BY table_name`.

**Response 200**
```json
{ "schema": "CM", "tables": ["COMPONENT", "ASSEMBLY"] }
```

**Response 400/404** — unknown schema
```json
{ "status": "error", "error": "schema 'XYZ' not found" }
```

## GET /api/oracle/columns?schema=<schema>&table=<table>
Underlying: `all_tab_columns` ordered by `column_id`.

**Response 200**
```json
{
  "schema": "CM",
  "table": "COMPONENT",
  "columns": [
    { "column_name": "ID", "data_type": "NUMBER", "data_length": 22, "data_precision": 10, "data_scale": 0, "nullable": "N" },
    { "column_name": "NAME", "data_type": "VARCHAR2", "data_length": 100, "data_precision": null, "data_scale": null, "nullable": "Y" }
  ]
}
```

## GET /api/oracle/partition-columns?schema=<schema>&table=<table>
Underlying: `all_tab_columns` filtered to `data_type IN ('NUMBER','DATE') OR data_type LIKE 'TIMESTAMP%'`, ordered by `column_id`.

**Response 200**
```json
{
  "schema": "CM",
  "table": "COMPONENT",
  "candidates": [
    { "column_name": "ID", "data_type": "NUMBER", "data_precision": 10, "data_scale": 0, "nullable": "N", "suggested_mode": "numeric" },
    { "column_name": "CREATED_AT", "data_type": "TIMESTAMP(6)", "data_precision": null, "data_scale": null, "nullable": "Y", "suggested_mode": "date" }
  ]
}
```

**Common errors**: unknown schema/table → controlled 400/404 with a safe message; Oracle remains unmodified.
