import re
from typing import Any

from app.config import Settings, get_settings

try:
    import oracledb
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    oracledb = None  # type: ignore[assignment]


ORACLE_CONNECT_QUERY = "SELECT 1 FROM dual"
ORACLE_METADATA_QUERY = "SELECT COUNT(*) FROM all_tables"

_LEADING_COMMENT_RE = re.compile(r"\s*(?:--[^\n]*(?:\n|$)|/\*.*?\*/)", re.DOTALL)
_FOR_UPDATE_RE = re.compile(r"\bFOR\s+UPDATE\b", re.IGNORECASE)


def _safe_error_message(exc: Exception, settings: Settings) -> str:
    message = str(exc) or exc.__class__.__name__
    if settings.p5_qa_oracle_password:
        message = message.replace(settings.p5_qa_oracle_password, "***")
    return message


def configure_oracle_defaults() -> None:
    if oracledb is not None and hasattr(oracledb, "defaults"):
        oracledb.defaults.fetch_lobs = False


def _assert_select_only(sql: str) -> None:
    stripped = sql.strip()
    while True:
        without_comment = _LEADING_COMMENT_RE.sub("", stripped, count=1)
        if without_comment == stripped:
            break
        stripped = without_comment.strip()
    stripped_upper = stripped.upper()
    if not (stripped_upper.startswith("SELECT") or stripped_upper.startswith("WITH")):
        raise ValueError("Oracle client only permits SELECT statements")
    if _FOR_UPDATE_RE.search(stripped):
        raise ValueError("Oracle client does not permit SELECT FOR UPDATE")


class ReadOnlyOracleCursor:
    def __init__(self, cursor: Any) -> None:
        object.__setattr__(self, "_cursor", cursor)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_cursor":
            object.__setattr__(self, name, value)
            return
        setattr(self._cursor, name, value)

    def __enter__(self) -> "ReadOnlyOracleCursor":
        if hasattr(self._cursor, "__enter__"):
            self._cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> Any:  # type: ignore[no-untyped-def]
        if hasattr(self._cursor, "__exit__"):
            return self._cursor.__exit__(exc_type, exc, tb)
        if hasattr(self._cursor, "close"):
            self._cursor.close()
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def execute(self, sql: str, parameters: Any = None, **kwargs: Any) -> Any:
        _assert_select_only(sql)
        if parameters is None:
            return self._cursor.execute(sql, **kwargs)
        return self._cursor.execute(sql, parameters, **kwargs)


class ReadOnlyOracleConnection:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def __enter__(self) -> "ReadOnlyOracleConnection":
        if hasattr(self._connection, "__enter__"):
            self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> Any:  # type: ignore[no-untyped-def]
        if hasattr(self._connection, "__exit__"):
            return self._connection.__exit__(exc_type, exc, tb)
        if hasattr(self._connection, "close"):
            self._connection.close()
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def cursor(self) -> ReadOnlyOracleCursor:
        return ReadOnlyOracleCursor(self._connection.cursor())


def build_dsn(settings: Settings) -> str:
    if settings.p5_qa_oracle_dsn:
        return settings.p5_qa_oracle_dsn
    if oracledb is None:
        raise RuntimeError("Oracle driver is not installed")
    return oracledb.makedsn(
        settings.p5_qa_oracle_host,
        settings.p5_qa_oracle_port,
        service_name=settings.p5_qa_oracle_service_name,
    )


def get_connection(settings: Settings | None = None) -> Any:
    if oracledb is None:
        raise RuntimeError("Oracle driver is not installed")
    configure_oracle_defaults()
    settings = settings or get_settings()
    connection = oracledb.connect(
        user=settings.p5_qa_oracle_user,
        password=settings.p5_qa_oracle_password,
        dsn=build_dsn(settings),
    )
    return ReadOnlyOracleConnection(connection)


def run_select(sql: str, binds: dict[str, Any] | None = None) -> list[Any]:
    _assert_select_only(sql)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, binds or {})
            return cursor.fetchall()


def health() -> dict[str, Any]:
    settings = get_settings()
    result: dict[str, Any] = {
        "status": "error",
        "database": "oracle",
        "can_connect": False,
        "can_read_metadata": False,
    }

    try:
        with get_connection(settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(ORACLE_CONNECT_QUERY)
                cursor.fetchone()
                result["can_connect"] = True

                cursor.execute(ORACLE_METADATA_QUERY)
                cursor.fetchone()
                result["can_read_metadata"] = True
    except Exception as exc:  # noqa: BLE001 - endpoint returns a safe DB health error
        result["error"] = _safe_error_message(exc, settings)
        return result

    result["status"] = "success"
    return result
