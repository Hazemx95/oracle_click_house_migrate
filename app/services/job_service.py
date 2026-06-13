from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from time import time
from uuid import uuid4

from app.config import TARGET_DATABASE


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = {
    JobStatus.SUCCESS.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
}

_JOBS: dict[str, dict[str, object]] = {}
_LOCK = RLock()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _duration_seconds(started_at_ts: object, finished_at_ts: object | None = None) -> float:
    if not isinstance(started_at_ts, (int, float)):
        return 0.0
    end = finished_at_ts if isinstance(finished_at_ts, (int, float)) else time()
    return max(0.0, round(end - started_at_ts, 3))


def _apply_derived_progress(job: dict[str, object]) -> None:
    total_rows = int(job.get("total_rows") or 0)
    processed_rows = int(job.get("processed_rows") or 0)
    remaining_rows = max(total_rows - processed_rows, 0) if total_rows else 0
    elapsed_seconds = _duration_seconds(job.get("_started_at_ts"))

    job["remaining_rows"] = remaining_rows
    job["progress_percent"] = (
        100.0 if total_rows == 0 and job.get("status") == JobStatus.SUCCESS.value
        else round((processed_rows / total_rows) * 100, 2) if total_rows else 0.0
    )
    job["elapsed_seconds"] = elapsed_seconds
    job["rows_per_second"] = (
        round(processed_rows / elapsed_seconds, 2) if elapsed_seconds > 0 else 0.0
    )


def _public_job(job: dict[str, object]) -> dict[str, object]:
    public = {key: value for key, value in job.items() if not key.startswith("_")}
    return deepcopy(public)


def create_job(
    *,
    source_schema: str,
    source_table: str,
    target_table: str,
    target_database: str = TARGET_DATABASE,
    target_schema: str | None = None,
    partition_column: str | None = None,
    worker_count: int = 1,
    batch_size: int | None = None,
) -> str:
    job_id = str(uuid4())
    job: dict[str, object] = {
        "job_id": job_id,
        "source_schema": source_schema,
        "source_table": source_table,
        "target_database": target_database,
        "target_schema": target_schema,
        "target_table": target_table,
        "partition_column": partition_column,
        "partition_mode": "single",
        "worker_count": 1,
        "requested_workers": worker_count,
        "batch_size": batch_size,
        "status": JobStatus.PENDING.value,
        "total_rows": 0,
        "processed_rows": 0,
        "inserted_rows": 0,
        "remaining_rows": 0,
        "progress_percent": 0.0,
        "batches_completed": 0,
        "current_batch": 0,
        "current_batch_number": 0,
        "started_at": None,
        "finished_at": None,
        "duration_seconds": None,
        "elapsed_seconds": 0.0,
        "rows_per_second": 0.0,
        "error_message": None,
        "workers": [],
    }
    with _LOCK:
        _JOBS[job_id] = job
    return job_id


def get_job(job_id: str) -> dict[str, object] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        if job.get("status") == JobStatus.RUNNING.value:
            _apply_derived_progress(job)
        return _public_job(job)


def update_job(job_id: str, **fields: object) -> dict[str, object]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(f"job '{job_id}' not found")

        status = fields.get("status")
        if isinstance(status, JobStatus):
            fields["status"] = status.value

        if fields.get("status") == JobStatus.RUNNING.value and not job.get("started_at"):
            job["started_at"] = _utc_now_iso()
            job["_started_at_ts"] = time()

        if fields.get("status") in TERMINAL_STATUSES and not job.get("finished_at"):
            finished_at_ts = time()
            job["finished_at"] = _utc_now_iso()
            job["_finished_at_ts"] = finished_at_ts
            job["duration_seconds"] = _duration_seconds(job.get("_started_at_ts"), finished_at_ts)

        job.update(fields)

        if "current_batch_number" in fields and "current_batch" not in fields:
            job["current_batch"] = fields["current_batch_number"]
        if "current_batch" in fields and "current_batch_number" not in fields:
            job["current_batch_number"] = fields["current_batch"]

        _apply_derived_progress(job)
        return _public_job(job)


def get_status(job_id: str) -> dict[str, object] | None:
    job = get_job(job_id)
    if job is None:
        return None

    keys = [
        "job_id",
        "status",
        "source_schema",
        "source_table",
        "target_database",
        "target_table",
        "total_rows",
        "processed_rows",
        "inserted_rows",
        "remaining_rows",
        "progress_percent",
        "batches_completed",
        "current_batch",
        "current_batch_number",
        "elapsed_seconds",
        "rows_per_second",
        "error_message",
        "workers",
    ]
    return {key: job.get(key) for key in keys}


def clear_jobs() -> None:
    with _LOCK:
        _JOBS.clear()
