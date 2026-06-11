import re
from typing import Any

from app.config import TARGET_DATABASE


_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TIMESTAMP_PRECISION_RE = re.compile(r"\(\d+\)")

_STRING_TYPES = {"VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "CLOB", "NCLOB"}
_TIMESTAMP_TYPES = {
    "TIMESTAMP",
    "TIMESTAMP WITH TIME ZONE",
    "TIMESTAMP WITH LOCAL TIME ZONE",
}


def _column_value(column: dict[str, Any], key: str) -> Any:
    if key in column:
        return column[key]
    return column.get(key.upper())


def _normalize_oracle_type(data_type: Any) -> str:
    normalized = str(data_type or "").strip().upper()
    normalized = _TIMESTAMP_PRECISION_RE.sub("", normalized)
    return " ".join(normalized.split())


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _base_clickhouse_type(column: dict[str, Any]) -> tuple[str, bool]:
    oracle_type = _normalize_oracle_type(_column_value(column, "data_type"))
    precision = _int_or_none(_column_value(column, "data_precision"))
    scale = _int_or_none(_column_value(column, "data_scale"))

    if oracle_type == "NUMBER":
        if precision is None or scale is None:
            return "Float64", True
        if scale == 0 and precision <= 18:
            return "Int64", True
        if scale == 0 and 18 < precision <= 76:
            return f"Decimal({precision},0)", True
        if scale > 0 and precision <= 76 and scale <= precision:
            return f"Decimal({precision},{scale})", True
        return "String", False
    if oracle_type == "FLOAT":
        return "Float64", True
    if oracle_type == "BINARY_FLOAT":
        return "Float32", True
    if oracle_type == "BINARY_DOUBLE":
        return "Float64", True
    if oracle_type in _STRING_TYPES:
        return "String", True
    if oracle_type == "DATE":
        return "DateTime", True
    if oracle_type in _TIMESTAMP_TYPES:
        return "DateTime64(6)", True
    if oracle_type in {"RAW", "BLOB"}:
        return "String", True
    return "String", False


def _nullable_type(base_type: str) -> str:
    return f"Nullable({base_type})"


def _is_nullable(column: dict[str, Any]) -> bool:
    return str(_column_value(column, "nullable") or "Y").strip().upper() != "N"


def map_oracle_type(column: dict[str, Any]) -> str:
    base_type, _supported = _base_clickhouse_type(column)
    return _nullable_type(base_type)


def map_columns(
    columns: list[dict[str, Any]],
    non_nullable_columns: set[str] | None = None,
) -> tuple[list[str], list[dict[str, str]]]:
    non_nullable_columns = non_nullable_columns or set()
    column_defs: list[str] = []
    warnings: list[dict[str, str]] = []

    for column in columns:
        column_name = str(_column_value(column, "column_name") or "")
        base_type, supported = _base_clickhouse_type(column)
        clickhouse_type = (
            base_type if column_name in non_nullable_columns else _nullable_type(base_type)
        )
        column_defs.append(f"{quote_identifier(column_name)} {clickhouse_type}")

        if not supported:
            warnings.append(
                {
                    "column": column_name,
                    "oracle_type": str(_column_value(column, "data_type") or ""),
                    "mapped_to": _nullable_type(base_type),
                }
            )

    return column_defs, warnings


def quote_identifier(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("ClickHouse identifier must be a string")
    if not name:
        raise ValueError("ClickHouse identifier must not be empty")
    if "`" in name:
        raise ValueError("ClickHouse identifier must not contain backticks")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError("ClickHouse identifier must not contain control characters")
    if not _SAFE_IDENTIFIER_RE.fullmatch(name):
        raise ValueError("ClickHouse identifier contains unsafe characters")
    return f"`{name}`"


def safe_target_name(schema: str, table: str) -> str:
    quote_identifier(schema)
    quote_identifier(table)
    target_name = f"{schema}__{table}"
    quote_identifier(target_name)
    return target_name


def resolve_target_name(
    schema: str,
    table: str,
    target_table: str | None = None,
    target_schema: str | None = None,
) -> str:
    if target_table is None or not target_table.strip():
        return safe_target_name(target_schema or schema, table)

    target_table = target_table.strip()
    if "__" in target_table:
        quote_identifier(target_table)
        return target_table
    return safe_target_name(target_schema or schema, target_table)


def assert_target_database(db: str = TARGET_DATABASE) -> None:
    if db != TARGET_DATABASE:
        raise ValueError(f"target database must be '{TARGET_DATABASE}'")
    quote_identifier(db)


def _target_path(
    schema: str,
    table: str,
    target_database: str,
    target_table_name: str | None = None,
    target_schema: str | None = None,
) -> tuple[str, str]:
    assert_target_database(target_database)
    target_table = resolve_target_name(schema, table, target_table_name, target_schema)
    return target_table, f"{quote_identifier(target_database)}.{quote_identifier(target_table)}"


def _order_by_clause(columns: list[dict[str, Any]], order_by: str | None) -> tuple[str, set[str]]:
    if order_by is None or not str(order_by).strip():
        return "tuple()", set()

    order_column = str(order_by).strip()
    quoted_order_column = quote_identifier(order_column)
    for column in columns:
        column_name = str(_column_value(column, "column_name") or "")
        if column_name != order_column:
            continue
        _base_type, supported = _base_clickhouse_type(column)
        if supported and not _is_nullable(column):
            return quoted_order_column, {column_name}
        return "tuple()", set()

    return "tuple()", set()


def build_drop_ddl(
    schema: str,
    table: str,
    target_database: str = TARGET_DATABASE,
    target_table: str | None = None,
    target_schema: str | None = None,
) -> str:
    _target_table, target_path = _target_path(
        schema,
        table,
        target_database,
        target_table,
        target_schema,
    )
    return f"DROP TABLE IF EXISTS {target_path}"


def build_create_ddl(
    schema: str,
    table: str,
    columns: list[dict[str, Any]],
    order_by: str | None = None,
    target_database: str = TARGET_DATABASE,
    target_table: str | None = None,
    target_schema: str | None = None,
) -> tuple[str, list[dict[str, str]]]:
    if not columns:
        raise ValueError("CREATE TABLE requires at least one column")

    _target_table, target_path = _target_path(
        schema,
        table,
        target_database,
        target_table,
        target_schema,
    )
    order_clause, non_nullable_columns = _order_by_clause(columns, order_by)
    column_defs, warnings = map_columns(columns, non_nullable_columns)
    create_ddl = (
        f"CREATE TABLE {target_path} ("
        f"{', '.join(column_defs)}"
        f") ENGINE = MergeTree ORDER BY {order_clause}"
    )
    return create_ddl, warnings


def build_recreate_ddl(
    schema: str,
    table: str,
    columns: list[dict[str, Any]],
    order_by: str | None = None,
    target_database: str = TARGET_DATABASE,
    target_table: str | None = None,
    target_schema: str | None = None,
) -> dict[str, Any]:
    drop_ddl = build_drop_ddl(
        schema,
        table,
        target_database,
        target_table,
        target_schema,
    )
    create_ddl, warnings = build_create_ddl(
        schema,
        table,
        columns,
        order_by,
        target_database,
        target_table,
        target_schema,
    )
    resolved_target_table = resolve_target_name(schema, table, target_table, target_schema)
    return {
        "target_database": target_database,
        "target_table": resolved_target_table,
        "drop_ddl": drop_ddl,
        "create_ddl": create_ddl,
        "warnings": warnings,
    }
