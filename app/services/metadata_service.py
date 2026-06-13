from typing import Any

from app.db import oracle_client


LIST_SCHEMAS_SQL = """
SELECT DISTINCT owner
FROM all_tables
ORDER BY owner
"""

SCHEMA_EXISTS_SQL = """
SELECT COUNT(*)
FROM all_tables
WHERE owner = :schema_name
"""

LIST_TABLES_SQL = """
SELECT table_name
FROM all_tables
WHERE owner = :schema_name
ORDER BY table_name
"""

TABLE_EXISTS_SQL = """
SELECT COUNT(*)
FROM all_tables
WHERE owner = :schema_name
  AND table_name = :table_name
"""

LIST_COLUMNS_SQL = """
SELECT
    column_name,
    data_type,
    data_length,
    data_precision,
    data_scale,
    nullable,
    char_length,
    char_used
FROM all_tab_columns
WHERE owner = :schema_name
  AND table_name = :table_name
ORDER BY column_id
"""

LIST_PARTITION_CANDIDATES_SQL = """
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
"""

HEAVY_COLUMNS_SQL = """
SELECT
    column_name,
    data_type,
    data_length,
    char_length
FROM all_tab_columns
WHERE owner = :schema_name
  AND table_name = :table_name
  AND (
        data_type IN ('CLOB', 'BLOB', 'NCLOB', 'LONG', 'RAW')
        OR (data_type IN ('VARCHAR2', 'NVARCHAR2') AND NVL(char_length, data_length) > :large_text_threshold)
      )
ORDER BY column_id
"""

INDEXED_COLUMN_SQL = """
SELECT COUNT(*)
FROM all_ind_columns
WHERE table_owner = :schema_name
  AND table_name = :table_name
  AND column_name = :column_name
"""

LARGE_TEXT_THRESHOLD = 4000


def _clean_identifier(value: str) -> str:
    return value.strip()


def _first_value(row: Any) -> Any:
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _count_value(rows: list[Any]) -> int:
    if not rows:
        return 0
    return int(_first_value(rows[0]) or 0)


def _column(row: Any, index: int, key: str) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[index]


def list_schemas() -> list[str]:
    rows = oracle_client.run_select(LIST_SCHEMAS_SQL)
    return [str(_first_value(row)) for row in rows]


def schema_exists(schema: str) -> bool:
    schema_name = _clean_identifier(schema)
    if not schema_name:
        return False
    rows = oracle_client.run_select(
        SCHEMA_EXISTS_SQL,
        {"schema_name": schema_name},
    )
    return _count_value(rows) > 0


def list_tables(schema: str) -> list[str]:
    schema_name = _clean_identifier(schema)
    rows = oracle_client.run_select(
        LIST_TABLES_SQL,
        {"schema_name": schema_name},
    )
    return [str(_first_value(row)) for row in rows]


def table_exists(schema: str, table: str) -> bool:
    schema_name = _clean_identifier(schema)
    table_name = _clean_identifier(table)
    if not schema_name or not table_name:
        return False
    rows = oracle_client.run_select(
        TABLE_EXISTS_SQL,
        {"schema_name": schema_name, "table_name": table_name},
    )
    return _count_value(rows) > 0


def list_columns(schema: str, table: str) -> list[dict[str, Any]]:
    schema_name = _clean_identifier(schema)
    table_name = _clean_identifier(table)
    rows = oracle_client.run_select(
        LIST_COLUMNS_SQL,
        {"schema_name": schema_name, "table_name": table_name},
    )
    return [
        {
            "column_name": _column(row, 0, "column_name"),
            "data_type": _column(row, 1, "data_type"),
            "data_length": _column(row, 2, "data_length"),
            "data_precision": _column(row, 3, "data_precision"),
            "data_scale": _column(row, 4, "data_scale"),
            "nullable": _column(row, 5, "nullable"),
            "char_length": _column(row, 6, "char_length"),
            "char_used": _column(row, 7, "char_used"),
        }
        for row in rows
    ]


def _suggested_mode(data_type: str) -> str:
    if data_type == "NUMBER":
        return "numeric"
    return "date"


def list_partition_candidates(schema: str, table: str) -> list[dict[str, Any]]:
    schema_name = _clean_identifier(schema)
    table_name = _clean_identifier(table)
    rows = oracle_client.run_select(
        LIST_PARTITION_CANDIDATES_SQL,
        {"schema_name": schema_name, "table_name": table_name},
    )
    candidates = []
    for row in rows:
        data_type = _column(row, 1, "data_type")
        candidates.append(
            {
                "column_name": _column(row, 0, "column_name"),
                "data_type": data_type,
                "data_precision": _column(row, 2, "data_precision"),
                "data_scale": _column(row, 3, "data_scale"),
                "nullable": _column(row, 4, "nullable"),
                "suggested_mode": _suggested_mode(str(data_type)),
            }
        )
    return candidates


def detect_heavy_columns(schema: str, table: str) -> list[dict[str, Any]]:
    schema_name = _clean_identifier(schema)
    table_name = _clean_identifier(table)
    rows = oracle_client.run_select(
        HEAVY_COLUMNS_SQL,
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "large_text_threshold": LARGE_TEXT_THRESHOLD,
        },
    )
    return [
        {
            "column_name": _column(row, 0, "column_name"),
            "data_type": _column(row, 1, "data_type"),
            "data_length": _column(row, 2, "data_length"),
            "char_length": _column(row, 3, "char_length"),
        }
        for row in rows
    ]


def is_column_indexed(schema: str, table: str, column: str) -> bool:
    schema_name = _clean_identifier(schema)
    table_name = _clean_identifier(table)
    column_name = _clean_identifier(column)
    if not schema_name or not table_name or not column_name:
        return False
    rows = oracle_client.run_select(
        INDEXED_COLUMN_SQL,
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "column_name": column_name,
        },
    )
    return _count_value(rows) > 0
