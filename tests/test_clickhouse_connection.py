import pytest

from app.config import Settings, TARGET_DATABASE
from app.db import clickhouse_client


class FakeClickHouseResult:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self.result_rows = rows


class FakeClickHouseClient:
    def __init__(self, database_rows: list[tuple[str]] | None = None) -> None:
        self.database_rows = database_rows if database_rows is not None else [(TARGET_DATABASE,)]
        self.queries: list[str] = []
        self.parameters: list[dict[str, str] | None] = []
        self.closed = False

    def query(
        self,
        sql: str,
        parameters: dict[str, str] | None = None,
    ) -> FakeClickHouseResult:
        self.queries.append(sql)
        self.parameters.append(parameters)
        if "system.databases" in sql:
            return FakeClickHouseResult(self.database_rows)
        return FakeClickHouseResult([("1",)])

    def close(self) -> None:
        self.closed = True


def test_clickhouse_health_runs_connect_and_target_database_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClickHouseClient()
    monkeypatch.setattr(clickhouse_client, "get_client", lambda settings=None: client)

    result = clickhouse_client.health()

    assert result == {
        "status": "success",
        "database": "clickhouse",
        "can_connect": True,
        "target_database": TARGET_DATABASE,
        "target_database_exists": True,
    }
    assert client.queries == [
        "SELECT 1",
        "SELECT name FROM system.databases WHERE name = {database:String}",
    ]
    assert client.parameters == [
        None,
        {"database": "oracle_migration_hazem"},
    ]
    assert client.closed is True


def test_clickhouse_target_database_exists_false() -> None:
    client = FakeClickHouseClient(database_rows=[])

    assert clickhouse_client.target_database_exists(client) is False


def test_clickhouse_health_redacts_password(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(clickhouse_pass="super-secret")
    monkeypatch.setattr(clickhouse_client, "get_settings", lambda: settings)

    def fail_client(settings=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("connection failed for password super-secret")

    monkeypatch.setattr(clickhouse_client, "get_client", fail_client)

    result = clickhouse_client.health()

    assert result["status"] == "error"
    assert "super-secret" not in str(result["error"])
    assert "***" in str(result["error"])
