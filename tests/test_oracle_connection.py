import pytest

from app.config import Settings
from app.db import oracle_client


class FakeOracleCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object]] = []

    def __enter__(self) -> "FakeOracleCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    def execute(self, sql: str, binds: object = None) -> None:
        self.executed.append((sql, binds))

    def fetchone(self) -> tuple[int]:
        return (1,)

    def fetchall(self) -> list[tuple[int]]:
        return [(1,)]


class FakeOracleConnection:
    def __init__(self, cursor: FakeOracleCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "FakeOracleConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    def cursor(self) -> FakeOracleCursor:
        return self._cursor


def test_oracle_health_runs_connect_and_metadata_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeOracleCursor()
    monkeypatch.setattr(
        oracle_client,
        "get_connection",
        lambda settings=None: FakeOracleConnection(cursor),
    )

    result = oracle_client.health()

    assert result == {
        "status": "success",
        "database": "oracle",
        "can_connect": True,
        "can_read_metadata": True,
    }
    assert cursor.executed == [
        ("SELECT 1 FROM dual", None),
        ("SELECT COUNT(*) FROM all_tables", None),
    ]


def test_oracle_run_select_rejects_non_select() -> None:
    with pytest.raises(ValueError, match="only permits SELECT"):
        oracle_client.run_select("DELETE FROM example_table")


def test_oracle_select_guard_allows_leading_comment() -> None:
    oracle_client._assert_select_only("/* health */ SELECT 1 FROM dual")


def test_oracle_select_guard_rejects_for_update() -> None:
    with pytest.raises(ValueError, match="FOR UPDATE"):
        oracle_client._assert_select_only("SELECT * FROM example_table FOR UPDATE")


def test_oracle_connection_wrapper_applies_select_guard() -> None:
    cursor = FakeOracleCursor()
    connection = oracle_client.ReadOnlyOracleConnection(FakeOracleConnection(cursor))

    with connection.cursor() as guarded_cursor:
        guarded_cursor.execute("SELECT 1 FROM dual")
        with pytest.raises(ValueError, match="only permits SELECT"):
            guarded_cursor.execute("UPDATE example_table SET value = 1")

    assert cursor.executed == [("SELECT 1 FROM dual", None)]


def test_oracle_health_redacts_password(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(p5_qa_oracle_password="super-secret")
    monkeypatch.setattr(oracle_client, "get_settings", lambda: settings)

    def fail_connection(settings=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("connection failed for password super-secret")

    monkeypatch.setattr(oracle_client, "get_connection", fail_connection)

    result = oracle_client.health()

    assert result["status"] == "error"
    assert "super-secret" not in str(result["error"])
    assert "***" in str(result["error"])


def test_oracle_defaults_disable_lob_locator_fetching(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDefaults:
        fetch_lobs = True

    class FakeOracleModule:
        defaults = FakeDefaults()

    monkeypatch.setattr(oracle_client, "oracledb", FakeOracleModule())

    oracle_client.configure_oracle_defaults()

    assert FakeOracleModule.defaults.fetch_lobs is False
