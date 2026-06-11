import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import TARGET_DATABASE
from app.db import clickhouse_client
from app.services import ddl_mapper, metadata_service

router = APIRouter(prefix="/api/clickhouse")
logger = logging.getLogger(__name__)


class CreateTableRequest(BaseModel):
    source_schema: str = Field(alias="schema")
    table: str
    target_database: str = TARGET_DATABASE
    target_schema: str | None = None
    target_table: str | None = None
    order_by: str | None = None


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"status": "error", "error": message})


def _metadata_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"status": "error", "error": "Oracle metadata lookup failed"},
    )


def _require_table(schema: str, table: str) -> tuple[str, str]:
    schema_name = schema.strip()
    table_name = table.strip()
    if not schema_name or not table_name:
        raise _bad_request("schema and table are required")
    try:
        exists = metadata_service.table_exists(schema_name, table_name)
    except Exception as exc:  # noqa: BLE001 - response must stay credential-free
        logger.exception("Oracle table metadata lookup failed")
        raise _metadata_error() from exc
    if not exists:
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "error": f"table '{schema_name}.{table_name}' not found"},
        )
    return schema_name, table_name


def _build_response(request: CreateTableRequest) -> dict[str, Any]:
    try:
        ddl_mapper.assert_target_database(request.target_database)
    except ValueError as exc:
        raise _bad_request(str(exc)) from exc

    schema_name, table_name = _require_table(request.source_schema, request.table)
    try:
        columns = metadata_service.list_columns(schema_name, table_name)
        return ddl_mapper.build_recreate_ddl(
            schema_name,
            table_name,
            columns,
            request.order_by,
            request.target_database,
            request.target_table,
            request.target_schema,
        )
    except ValueError as exc:
        raise _bad_request(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - response must stay credential-free
        logger.exception("DDL preview generation failed")
        raise _metadata_error() from exc


@router.post("/create-table-preview")
def create_table_preview(request: CreateTableRequest) -> dict[str, Any]:
    return _build_response(request)


@router.post("/create-table")
def create_table(request: CreateTableRequest) -> dict[str, Any]:
    response = _build_response(request)
    try:
        clickhouse_client.execute_ddl(response["drop_ddl"])
        clickhouse_client.execute_ddl(response["create_ddl"])
    except ValueError as exc:
        raise _bad_request(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - response must stay credential-free
        logger.exception("ClickHouse table creation failed")
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "error": "ClickHouse DDL execution failed"},
        ) from exc

    return {
        "status": "created",
        "target_database": response["target_database"],
        "target_table": response["target_table"],
        "dropped_existing": True,
        "warnings": response["warnings"],
    }
