import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import TARGET_DATABASE
from app.services import ddl_mapper, job_service, migration_service

router = APIRouter(prefix="/api/migrations")
logger = logging.getLogger(__name__)


class MigrationRequest(BaseModel):
    source_schema: str
    source_table: str
    target_schema: str | None = None
    target_database: str = TARGET_DATABASE
    target_table: str
    partition_column: str | None = None
    parallel_mode: str = "auto"
    workers: int | None = Field(default=None, ge=1)
    batch_size: int | None = Field(default=None, gt=0)


def _not_found(job_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"status": "error", "error": f"job '{job_id}' not found"},
    )


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"status": "error", "error": message})


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def launch_migration(request: MigrationRequest) -> dict[str, Any]:
    try:
        ddl_mapper.assert_target_database(request.target_database)
        job_id = migration_service.launch_initial_load(
            source_schema=request.source_schema,
            source_table=request.source_table,
            target_schema=request.target_schema,
            target_table=request.target_table,
            partition_column=request.partition_column,
            workers=request.workers,
            batch_size=request.batch_size,
            target_database=request.target_database,
            parallel_mode=request.parallel_mode,
        )
    except ValueError as exc:
        raise _bad_request(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - response must stay credential-free
        logger.exception("Migration launch failed")
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "error": "migration launch failed"},
        ) from exc

    job = job_service.get_job(job_id) or {}
    return {
        "job_id": job_id,
        "status": job_service.JobStatus.PENDING.value,
        "requested_parallel_mode": job.get("requested_parallel_mode"),
        "resolved_parallel_mode": job.get("resolved_parallel_mode"),
        "warning_message": job.get("warning_message"),
    }


@router.get("/{job_id}")
def get_migration(job_id: str) -> dict[str, Any]:
    job = job_service.get_job(job_id)
    if job is None:
        raise _not_found(job_id)
    return job


@router.get("/{job_id}/status")
def get_migration_status(job_id: str) -> dict[str, Any]:
    job = job_service.get_status(job_id)
    if job is None:
        raise _not_found(job_id)
    return job
