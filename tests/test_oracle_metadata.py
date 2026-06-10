from typing import Any

import pytest
from fastapi import HTTPException

from app.api import oracle_routes
from app.services import metadata_service


def test_list_schemas_uses_read_only_client(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, dict[str, Any] | None]] = []

    def fake_run_select(sql: str, binds: dict[str, Any] | None = None) -> list[tuple[str]]:
        calls.append((sql, binds))
        return [("CM",), ("HR",)]

    monkeypatch.setattr(metadata_service.oracle_client, "run_select", fake_run_select)

    assert metadata_service.list_schemas() == ["CM", "HR"]
    assert calls[0][0].strip().startswith("SELECT DISTINCT owner")
    assert calls[0][1] is None


def test_list_tables_uses_schema_bind_variable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, dict[str, Any] | None]] = []

    def fake_run_select(sql: str, binds: dict[str, Any] | None = None) -> list[tuple[str]]:
        calls.append((sql, binds))
        return [("COMPONENT",), ("ASSEMBLY",)]

    monkeypatch.setattr(metadata_service.oracle_client, "run_select", fake_run_select)

    assert metadata_service.list_tables("CM") == ["COMPONENT", "ASSEMBLY"]
    assert ":schema_name" in calls[0][0]
    assert calls[0][1] == {"schema_name": "CM"}


def test_list_columns_uses_schema_and_table_bind_variables(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, dict[str, Any] | None]] = []

    def fake_run_select(sql: str, binds: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
        calls.append((sql, binds))
        return [
            ("ID", "NUMBER", 22, 10, 0, "N"),
            ("NAME", "VARCHAR2", 100, None, None, "Y"),
        ]

    monkeypatch.setattr(metadata_service.oracle_client, "run_select", fake_run_select)

    assert metadata_service.list_columns("CM", "COMPONENT") == [
        {
            "column_name": "ID",
            "data_type": "NUMBER",
            "data_length": 22,
            "data_precision": 10,
            "data_scale": 0,
            "nullable": "N",
        },
        {
            "column_name": "NAME",
            "data_type": "VARCHAR2",
            "data_length": 100,
            "data_precision": None,
            "data_scale": None,
            "nullable": "Y",
        },
    ]
    assert calls[0][1] == {"schema_name": "CM", "table_name": "COMPONENT"}


def test_partition_candidates_include_suggested_modes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_run_select(sql: str, binds: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
        assert "data_type IN ('NUMBER', 'DATE')" in sql
        assert "data_type LIKE 'TIMESTAMP%'" in sql
        assert binds == {"schema_name": "CM", "table_name": "COMPONENT"}
        return [
            ("ID", "NUMBER", 10, 0, "N"),
            ("CREATED_AT", "TIMESTAMP(6)", None, None, "Y"),
        ]

    monkeypatch.setattr(metadata_service.oracle_client, "run_select", fake_run_select)

    assert metadata_service.list_partition_candidates("CM", "COMPONENT") == [
        {
            "column_name": "ID",
            "data_type": "NUMBER",
            "data_precision": 10,
            "data_scale": 0,
            "nullable": "N",
            "suggested_mode": "numeric",
        },
        {
            "column_name": "CREATED_AT",
            "data_type": "TIMESTAMP(6)",
            "data_precision": None,
            "data_scale": None,
            "nullable": "Y",
            "suggested_mode": "date",
        },
    ]


def test_oracle_metadata_routes_return_expected_payloads(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(metadata_service, "list_schemas", lambda: ["CM"])
    monkeypatch.setattr(metadata_service, "schema_exists", lambda schema: schema == "CM")
    monkeypatch.setattr(metadata_service, "table_exists", lambda schema, table: table == "COMPONENT")
    monkeypatch.setattr(metadata_service, "list_tables", lambda schema: ["COMPONENT"])
    monkeypatch.setattr(
        metadata_service,
        "list_columns",
        lambda schema, table: [
            {
                "column_name": "ID",
                "data_type": "NUMBER",
                "data_length": 22,
                "data_precision": 10,
                "data_scale": 0,
                "nullable": "N",
            }
        ],
    )
    monkeypatch.setattr(
        metadata_service,
        "list_partition_candidates",
        lambda schema, table: [
            {
                "column_name": "ID",
                "data_type": "NUMBER",
                "data_precision": 10,
                "data_scale": 0,
                "nullable": "N",
                "suggested_mode": "numeric",
            }
        ],
    )
    assert oracle_routes.schemas() == {"schemas": ["CM"]}
    assert oracle_routes.tables(schema="CM") == {
        "schema": "CM",
        "tables": ["COMPONENT"],
    }
    assert oracle_routes.columns(schema="CM", table="COMPONENT") == {
        "schema": "CM",
        "table": "COMPONENT",
        "columns": [
            {
                "column_name": "ID",
                "data_type": "NUMBER",
                "data_length": 22,
                "data_precision": 10,
                "data_scale": 0,
                "nullable": "N",
            }
        ],
    }
    assert oracle_routes.partition_columns(schema="CM", table="COMPONENT") == {
        "schema": "CM",
        "table": "COMPONENT",
        "candidates": [
            {
                "column_name": "ID",
                "data_type": "NUMBER",
                "data_precision": 10,
                "data_scale": 0,
                "nullable": "N",
                "suggested_mode": "numeric",
            }
        ],
    }


def test_invalid_schema_returns_controlled_error_without_table_lookup(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    table_lookup_called = False

    def fake_list_tables(schema: str) -> list[str]:
        nonlocal table_lookup_called
        table_lookup_called = True
        return []

    monkeypatch.setattr(metadata_service, "schema_exists", lambda schema: False)
    monkeypatch.setattr(metadata_service, "list_tables", fake_list_tables)

    with pytest.raises(HTTPException) as exc_info:
        oracle_routes.tables(schema="CM'--")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {"status": "error", "error": "schema 'CM'--' not found"}
    assert table_lookup_called is False
