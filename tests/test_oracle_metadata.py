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
            ("ID", "NUMBER", 22, 10, 0, "N", None, None),
            ("NAME", "VARCHAR2", 100, None, None, "Y", 100, "B"),
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
            "char_length": None,
            "char_used": None,
        },
        {
            "column_name": "NAME",
            "data_type": "VARCHAR2",
            "data_length": 100,
            "data_precision": None,
            "data_scale": None,
            "nullable": "Y",
            "char_length": 100,
            "char_used": "B",
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


def test_detect_heavy_columns_uses_read_only_metadata_query(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, dict[str, Any] | None]] = []

    def fake_run_select(sql: str, binds: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
        calls.append((sql, binds))
        return [("DOC", "CLOB", 4000, 4000), ("RAW_DATA", "RAW", 2000, None)]

    monkeypatch.setattr(metadata_service.oracle_client, "run_select", fake_run_select)

    assert metadata_service.detect_heavy_columns("CM", "COMPONENT") == [
        {"column_name": "DOC", "data_type": "CLOB", "data_length": 4000, "char_length": 4000},
        {"column_name": "RAW_DATA", "data_type": "RAW", "data_length": 2000, "char_length": None},
    ]
    assert calls[0][0].strip().startswith("SELECT")
    assert "all_tab_columns" in calls[0][0]
    assert calls[0][1] == {
        "schema_name": "CM",
        "table_name": "COMPONENT",
        "large_text_threshold": metadata_service.LARGE_TEXT_THRESHOLD,
    }


def test_is_column_indexed_checks_all_ind_columns_with_binds(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, dict[str, Any] | None]] = []

    def fake_run_select(sql: str, binds: dict[str, Any] | None = None) -> list[tuple[int]]:
        calls.append((sql, binds))
        return [(1,)]

    monkeypatch.setattr(metadata_service.oracle_client, "run_select", fake_run_select)

    assert metadata_service.is_column_indexed("CM", "COMPONENT", "ID") is True
    assert calls[0][0].strip().startswith("SELECT COUNT(*)")
    assert "all_ind_columns" in calls[0][0]
    assert calls[0][1] == {
        "schema_name": "CM",
        "table_name": "COMPONENT",
        "column_name": "ID",
    }


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
                "char_length": None,
                "char_used": None,
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
                "char_length": None,
                "char_used": None,
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
