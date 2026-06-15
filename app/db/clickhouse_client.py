import inspect
import re
import socket
from typing import Any

from app.config import TARGET_DATABASE, Settings, get_settings

try:
    import clickhouse_connect
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    clickhouse_connect = None  # type: ignore[assignment]


CLICKHOUSE_CONNECT_QUERY = "SELECT 1"
CLICKHOUSE_TARGET_DATABASE_QUERY = (
    "SELECT name FROM system.databases "
    "WHERE name = {database:String}"
)

_IDENTIFIER = r"(?:`[A-Za-z_][A-Za-z0-9_]*`|[A-Za-z_][A-Za-z0-9_]*)"
_TARGET = rf"(?P<db>{_IDENTIFIER})\.(?P<table>{_IDENTIFIER})"
_DROP_DDL_RE = re.compile(rf"^DROP\s+TABLE\s+IF\s+EXISTS\s+{_TARGET}$", re.IGNORECASE)
_CREATE_DDL_RE = re.compile(
    rf"^CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS){_TARGET}\s*\(",
    re.IGNORECASE,
)
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")


class ClickHouseInsertTimeoutError(RuntimeError):
    """Raised when an insert may have reached ClickHouse but timed out client-side."""


def _safe_error_message(exc: Exception, settings: Settings) -> str:
    message = str(exc) or exc.__class__.__name__
    if settings.clickhouse_pass:
        message = message.replace(settings.clickhouse_pass, "***")
    return message


def _call_supports_kwarg(func: Any, kwarg: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return True
    return kwarg in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _capability_guarded_kwargs(func: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if _call_supports_kwarg(func, key)}


def is_transient_connection_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout, ClickHouseInsertTimeoutError)):
        return True
    message = str(exc).lower()
    transient_markers = (
        "connection aborted",
        "timed out",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "remote end closed connection",
    )
    return any(marker in message for marker in transient_markers)


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout, ClickHouseInsertTimeoutError)):
        return True
    message = str(exc).lower()
    return "timeout" in message or "timed out" in message or "connection aborted" in message


def get_client(settings: Settings | None = None) -> Any:
    if clickhouse_connect is None:
        raise RuntimeError("ClickHouse driver is not installed")
    settings = settings or get_settings()
    kwargs = {
        "host": settings.clickhouse_host,
        "port": settings.clickhouse_port,
        "username": settings.clickhouse_user,
        "password": settings.clickhouse_pass,
        "connect_timeout": settings.clickhouse_connect_timeout_seconds,
        "send_receive_timeout": settings.clickhouse_send_receive_timeout_seconds,
        "compress": settings.clickhouse_compress,
    }
    guarded_kwargs = _capability_guarded_kwargs(clickhouse_connect.get_client, kwargs)
    try:
        return clickhouse_connect.get_client(**guarded_kwargs)
    except TypeError:
        minimal_kwargs = {
            "host": settings.clickhouse_host,
            "port": settings.clickhouse_port,
            "username": settings.clickhouse_user,
            "password": settings.clickhouse_pass,
        }
        return clickhouse_connect.get_client(**minimal_kwargs)


def _rows(query_result: Any) -> list[Any]:
    return list(getattr(query_result, "result_rows", []) or [])


def target_database_exists(client: Any | None = None) -> bool:
    close_client = client is None
    client = client or get_client()
    try:
        result = client.query(
            CLICKHOUSE_TARGET_DATABASE_QUERY,
            parameters={"database": TARGET_DATABASE},
        )
        return bool(_rows(result))
    finally:
        if close_client and hasattr(client, "close"):
            client.close()


def _unquote_identifier(identifier: str) -> str:
    if identifier.startswith("`") and identifier.endswith("`"):
        return identifier[1:-1]
    return identifier


def _assert_allowed_ddl(ddl: str) -> str:
    statement = ddl.strip()
    if statement.endswith(";"):
        statement = statement[:-1].strip()
    if ";" in statement:
        raise ValueError("ClickHouse DDL must contain a single statement")

    match = _DROP_DDL_RE.match(statement) or _CREATE_DDL_RE.match(statement)
    if not match:
        raise ValueError("ClickHouse DDL must be DROP TABLE IF EXISTS or CREATE TABLE")

    database = _unquote_identifier(match.group("db"))
    if database != TARGET_DATABASE:
        raise ValueError(f"target database must be '{TARGET_DATABASE}'")
    return statement


def execute_ddl(ddl: str, client: Any | None = None) -> None:
    statement = _assert_allowed_ddl(ddl)
    close_client = client is None
    client = client or get_client()
    try:
        if hasattr(client, "command"):
            client.command(statement)
        else:
            client.query(statement)
    finally:
        if close_client and hasattr(client, "close"):
            client.close()


def _assert_safe_identifier(identifier: str, label: str) -> None:
    if not isinstance(identifier, str) or not _SAFE_IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"ClickHouse {label} contains unsafe characters")


def _quote_identifier(identifier: str, label: str) -> str:
    _assert_safe_identifier(identifier, label)
    return f"`{identifier}`"


def count_rows(
    table: str,
    target_database: str = TARGET_DATABASE,
    client: Any | None = None,
) -> int:
    if target_database != TARGET_DATABASE:
        raise ValueError(f"target database must be '{TARGET_DATABASE}'")
    target_path = (
        f"{_quote_identifier(target_database, 'database')}."
        f"{_quote_identifier(table, 'table')}"
    )
    close_client = client is None
    client = client or get_client()
    try:
        result = client.query(f"SELECT COUNT(*) FROM {target_path}")
        rows = _rows(result)
        if not rows:
            return 0
        first_row = rows[0]
        return int(first_row[0] if not isinstance(first_row, dict) else next(iter(first_row.values())))
    finally:
        if close_client and hasattr(client, "close"):
            client.close()


def insert_rows(
    table: str,
    rows: list[Any] | tuple[Any, ...],
    column_names: list[str],
    target_database: str = TARGET_DATABASE,
    client: Any | None = None,
) -> int:
    settings = get_settings()
    if target_database != TARGET_DATABASE:
        raise ValueError(f"target database must be '{TARGET_DATABASE}'")
    _assert_safe_identifier(table, "table")
    for column_name in column_names:
        _assert_safe_identifier(column_name, "column")

    if not rows:
        return 0

    close_client = client is None
    client = client or get_client()
    try:
        insert_kwargs = {
            "table": table,
            "data": list(rows),
            "column_names": column_names,
            "database": target_database,
        }
        # One client.insert call per chunk keeps this path batch-oriented, never row-by-row.
        client.insert(**insert_kwargs)
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - caller needs typed timeout failures
        if _is_timeout_error(exc):
            raise ClickHouseInsertTimeoutError(_safe_error_message(exc, settings)) from exc
        raise
    finally:
        if close_client and hasattr(client, "close"):
            client.close()


def health() -> dict[str, Any]:
    settings = get_settings()
    result: dict[str, Any] = {
        "status": "error",
        "database": "clickhouse",
        "can_connect": False,
        "target_database": TARGET_DATABASE,
        "target_database_exists": False,
    }

    client = None
    try:
        client = get_client(settings)
        client.query(CLICKHOUSE_CONNECT_QUERY)
        result["can_connect"] = True
        result["target_database_exists"] = target_database_exists(client)
    except Exception as exc:  # noqa: BLE001 - endpoint returns a safe DB health error
        result["error"] = _safe_error_message(exc, settings)
        return result
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()

    result["status"] = "success"
    return result
