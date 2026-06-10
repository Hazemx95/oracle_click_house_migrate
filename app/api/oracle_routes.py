from typing import Any

import logging

from fastapi import APIRouter, HTTPException, Query

from app.services import metadata_service

router = APIRouter(prefix="/api/oracle")
logger = logging.getLogger(__name__)


def _not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"status": "error", "error": message},
    )


def _lookup_failed() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"status": "error", "error": "Oracle metadata lookup failed"},
    )


def _require_schema(schema: str) -> str:
    schema_name = schema.strip()
    if not schema_name:
        raise _not_found("schema not found")
    try:
        exists = metadata_service.schema_exists(schema_name)
    except Exception as exc:  # noqa: BLE001 - response must stay credential-free
        logger.exception("Oracle schema metadata lookup failed")
        raise _lookup_failed() from exc
    if not exists:
        raise _not_found(f"schema '{schema_name}' not found")
    return schema_name


def _require_table(schema: str, table: str) -> tuple[str, str]:
    schema_name = _require_schema(schema)
    table_name = table.strip()
    if not table_name:
        raise _not_found("table not found")
    try:
        exists = metadata_service.table_exists(schema_name, table_name)
    except Exception as exc:  # noqa: BLE001 - response must stay credential-free
        logger.exception("Oracle table metadata lookup failed")
        raise _lookup_failed() from exc
    if not exists:
        raise _not_found(f"table '{schema_name}.{table_name}' not found")
    return schema_name, table_name


@router.get("/schemas")
def schemas() -> dict[str, list[str]]:
    try:
        return {"schemas": metadata_service.list_schemas()}
    except Exception as exc:  # noqa: BLE001 - response must stay credential-free
        logger.exception("Oracle schema listing failed")
        raise _lookup_failed() from exc


@router.get("/tables")
def tables(schema: str = Query(..., min_length=1)) -> dict[str, Any]:
    schema_name = _require_schema(schema)
    try:
        return {"schema": schema_name, "tables": metadata_service.list_tables(schema_name)}
    except Exception as exc:  # noqa: BLE001 - response must stay credential-free
        logger.exception("Oracle table listing failed for schema %r", schema_name)
        raise _lookup_failed() from exc


@router.get("/columns")
def columns(
    schema: str = Query(..., min_length=1),
    table: str = Query(..., min_length=1),
) -> dict[str, Any]:
    schema_name, table_name = _require_table(schema, table)
    try:
        return {
            "schema": schema_name,
            "table": table_name,
            "columns": metadata_service.list_columns(schema_name, table_name),
        }
    except Exception as exc:  # noqa: BLE001 - response must stay credential-free
        logger.exception(
            "Oracle column listing failed for table %r.%r",
            schema_name,
            table_name,
        )
        raise _lookup_failed() from exc


@router.get("/partition-columns")
def partition_columns(
    schema: str = Query(..., min_length=1),
    table: str = Query(..., min_length=1),
) -> dict[str, Any]:
    schema_name, table_name = _require_table(schema, table)
    try:
        return {
            "schema": schema_name,
            "table": table_name,
            "candidates": metadata_service.list_partition_candidates(
                schema_name,
                table_name,
            ),
        }
    except Exception as exc:  # noqa: BLE001 - response must stay credential-free
        logger.exception(
            "Oracle partition candidate listing failed for table %r.%r",
            schema_name,
            table_name,
        )
        raise _lookup_failed() from exc
