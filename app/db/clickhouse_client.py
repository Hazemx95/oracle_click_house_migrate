from typing import Any
import re

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


def _safe_error_message(exc: Exception, settings: Settings) -> str:
    message = str(exc) or exc.__class__.__name__
    if settings.clickhouse_pass:
        message = message.replace(settings.clickhouse_pass, "***")
    return message


def get_client(settings: Settings | None = None) -> Any:
    if clickhouse_connect is None:
        raise RuntimeError("ClickHouse driver is not installed")
    settings = settings or get_settings()
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_pass,
    )


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
