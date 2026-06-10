from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db import clickhouse_client, oracle_client

router = APIRouter()


@router.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "oracle-clickhouse-migration-engine",
    }


@router.get("/api/health/oracle", response_model=None)
def oracle_health() -> dict[str, object] | JSONResponse:
    result = oracle_client.health()
    if result["status"] == "success":
        return result
    return JSONResponse(status_code=503, content=result)


@router.get("/api/health/clickhouse", response_model=None)
def clickhouse_health() -> dict[str, object] | JSONResponse:
    result = clickhouse_client.health()
    if result["status"] == "success":
        return result
    return JSONResponse(status_code=503, content=result)
