from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from time import perf_counter
from uuid import uuid4

from app.config import TARGET_DATABASE


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ValidationStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


TERMINAL_STATUSES = {
    JobStatus.SUCCESS.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
}

_JOBS: dict[str, dict[str, object]] = {}
_LOCK = RLock()

PERFORMANCE_TIMING_KEYS = (
    "ddl_duration_seconds",
    "oracle_count_duration_seconds",
    "range_discovery_duration_seconds",
    "oracle_execute_duration_seconds",
    "oracle_fetch_duration_seconds",
    "row_conversion_duration_seconds",
    "clickhouse_insert_duration_seconds",
    "validation_duration_seconds",
    "total_duration_seconds",
    "oracle_connect_duration_seconds",
    "clickhouse_connect_duration_seconds",
)


def _new_performance_diagnostics(batch_size: int | None = None) -> dict[str, object]:
    diagnostics: dict[str, object] = {key: 0.0 for key in PERFORMANCE_TIMING_KEYS}
    diagnostics.update(
        {
            "batch_size": batch_size or 0,
            "batches_completed": 0,
            "average_rows_per_batch": 0.0,
            "average_seconds_per_batch": 0.0,
            "timing_semantics": "wall_clock_seconds",
            "per_worker_summary": {},
            "per_worker": [],
        }
    )
    return diagnostics


def _worker_timing_summary(per_worker: list[object]) -> dict[str, dict[str, float]]:
    timing_keys = (
        "oracle_connect_duration_seconds",
        "clickhouse_connect_duration_seconds",
        "oracle_execute_duration_seconds",
        "oracle_fetch_duration_seconds",
        "row_conversion_duration_seconds",
        "clickhouse_insert_duration_seconds",
    )
    worker_timings = [entry for entry in per_worker if isinstance(entry, dict)]
    if not worker_timings:
        return {}
    summary: dict[str, dict[str, float]] = {}
    for key in timing_keys:
        values = [float(entry.get(key) or 0.0) for entry in worker_timings]
        summary[key] = {
            "max": round(max(values), 3),
            "average": round(sum(values) / len(values), 3),
        }
    return summary


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _duration_seconds(started_at_ts: object, finished_at_ts: object | None = None) -> float:
    if not isinstance(started_at_ts, (int, float)):
        return 0.0
    end = finished_at_ts if isinstance(finished_at_ts, (int, float)) else perf_counter()
    return max(0.0, round(end - started_at_ts, 3))


def _apply_derived_progress(job: dict[str, object]) -> None:
    workers = job.get("workers")
    if isinstance(workers, list) and workers:
        processed_rows = sum(int(worker.get("processed_rows") or 0) for worker in workers)
        inserted_rows = sum(int(worker.get("inserted_rows") or 0) for worker in workers)
        batches_completed = sum(int(worker.get("batches_completed") or 0) for worker in workers)
        job["processed_rows"] = processed_rows
        job["inserted_rows"] = inserted_rows
        job["batches_completed"] = batches_completed
        job["current_batch"] = batches_completed
        job["current_batch_number"] = batches_completed

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

    diagnostics = job.get("performance_diagnostics")
    if isinstance(diagnostics, dict):
        batches_completed = int(job.get("batches_completed") or 0)
        diagnostics["batches_completed"] = batches_completed
        if not diagnostics.get("batch_size") and job.get("batch_size"):
            diagnostics["batch_size"] = int(job.get("batch_size") or 0)
        diagnostics["average_rows_per_batch"] = (
            round(processed_rows / batches_completed, 2) if batches_completed else 0.0
        )
        batch_seconds = sum(
            float(diagnostics.get(key) or 0.0)
            for key in (
                "oracle_execute_duration_seconds",
                "oracle_fetch_duration_seconds",
                "row_conversion_duration_seconds",
                "clickhouse_insert_duration_seconds",
            )
        )
        diagnostics["average_seconds_per_batch"] = (
            round(batch_seconds / batches_completed, 3) if batches_completed else 0.0
        )
        per_worker = diagnostics.get("per_worker")
        if isinstance(per_worker, list) and per_worker:
            diagnostics["timing_semantics"] = "cumulative_worker_seconds"
            diagnostics["per_worker_summary"] = _worker_timing_summary(per_worker)
        else:
            diagnostics["timing_semantics"] = "wall_clock_seconds"
            diagnostics["per_worker_summary"] = {}


def _public_job(job: dict[str, object]) -> dict[str, object]:
    public = {key: value for key, value in job.items() if not key.startswith("_")}
    public["workers"] = [
        {key: value for key, value in worker.items() if not key.startswith("_")}
        for worker in public.get("workers", [])
        if isinstance(worker, dict)
    ]
    return deepcopy(public)


def create_job(
    *,
    source_schema: str,
    source_table: str,
    target_table: str,
    target_database: str = TARGET_DATABASE,
    target_schema: str | None = None,
    partition_column: str | None = None,
    partition_mode: str = "single",
    worker_count: int = 1,
    requested_parallel_mode: str = "auto",
    resolved_parallel_mode: str = "single",
    warning_message: str | None = None,
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
        "partition_mode": partition_mode,
        "requested_parallel_mode": requested_parallel_mode,
        "resolved_parallel_mode": resolved_parallel_mode,
        "worker_count": worker_count,
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
        "warning_message": warning_message,
        "warnings": [warning_message] if warning_message else [],
        "source_row_count": None,
        "target_row_count": None,
        "count_match": None,
        "validation_status": ValidationStatus.NOT_STARTED.value,
        "validation_error_message": None,
        "workers": [],
        "performance_diagnostics": _new_performance_diagnostics(batch_size),
    }
    with _LOCK:
        _JOBS[job_id] = job
    return job_id


def get_job(job_id: str) -> dict[str, object] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
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
            job["_started_at_ts"] = perf_counter()

        if fields.get("status") in TERMINAL_STATUSES and not job.get("finished_at"):
            finished_at_ts = perf_counter()
            job["finished_at"] = _utc_now_iso()
            job["_finished_at_ts"] = finished_at_ts
            job["duration_seconds"] = _duration_seconds(job.get("_started_at_ts"), finished_at_ts)
            diagnostics = job.get("performance_diagnostics")
            if isinstance(diagnostics, dict):
                diagnostics["total_duration_seconds"] = job["duration_seconds"]

        job.update(fields)

        if "current_batch_number" in fields and "current_batch" not in fields:
            job["current_batch"] = fields["current_batch_number"]
        if "current_batch" in fields and "current_batch_number" not in fields:
            job["current_batch_number"] = fields["current_batch"]

        _apply_derived_progress(job)
        return _public_job(job)


def update_job_progress(job_id: str, **fields: object) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(f"job '{job_id}' not found")
        job.update(fields)
        if "current_batch_number" in fields and "current_batch" not in fields:
            job["current_batch"] = fields["current_batch_number"]
        if "current_batch" in fields and "current_batch_number" not in fields:
            job["current_batch_number"] = fields["current_batch"]
        _apply_derived_progress(job)


def add_warning(job_id: str, message: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(f"job '{job_id}' not found")
        warnings = job.setdefault("warnings", [])
        if not isinstance(warnings, list):
            warnings = []
            job["warnings"] = warnings
        if message and message not in warnings:
            warnings.append(message)
        if not job.get("warning_message") and warnings:
            job["warning_message"] = warnings[0]


def add_diagnostic_timing(job_id: str, field: str, seconds: float) -> None:
    if field not in PERFORMANCE_TIMING_KEYS:
        raise ValueError(f"unknown diagnostic timing field '{field}'")
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(f"job '{job_id}' not found")
        diagnostics = job.get("performance_diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = _new_performance_diagnostics()
            job["performance_diagnostics"] = diagnostics
        diagnostics[field] = round(float(diagnostics.get(field) or 0.0) + seconds, 3)


def update_performance_diagnostics(job_id: str, **fields: object) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(f"job '{job_id}' not found")
        diagnostics = job.get("performance_diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = _new_performance_diagnostics()
            job["performance_diagnostics"] = diagnostics
        diagnostics.update(fields)


def set_worker_diagnostics(job_id: str, worker_id: int, timings: dict[str, object]) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(f"job '{job_id}' not found")
        diagnostics = job.get("performance_diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = _new_performance_diagnostics()
            job["performance_diagnostics"] = diagnostics
        per_worker = diagnostics.setdefault("per_worker", [])
        if not isinstance(per_worker, list):
            per_worker = []
            diagnostics["per_worker"] = per_worker
        public_timings = deepcopy(timings)
        public_timings["worker_id"] = worker_id
        for index, existing in enumerate(per_worker):
            if isinstance(existing, dict) and existing.get("worker_id") == worker_id:
                per_worker[index] = public_timings
                break
        else:
            per_worker.append(public_timings)


def set_workers(job_id: str, workers: list[dict[str, object]]) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(f"job '{job_id}' not found")
        job["workers"] = deepcopy(workers)
        _apply_derived_progress(job)


def update_worker(job_id: str, worker_id: int, **fields: object) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(f"job '{job_id}' not found")

        workers = job.get("workers")
        if not isinstance(workers, list):
            raise ValueError("job has no worker registry")

        worker = next(
            (
                item
                for item in workers
                if isinstance(item, dict) and item.get("worker_id") == worker_id
            ),
            None,
        )
        if worker is None:
            raise KeyError(f"worker '{worker_id}' not found")

        status = fields.get("status")
        if isinstance(status, JobStatus):
            fields["status"] = status.value

        if fields.get("status") == JobStatus.RUNNING.value and not worker.get("_started_at_ts"):
            worker["_started_at_ts"] = perf_counter()

        worker.update(fields)
        elapsed_seconds = _duration_seconds(worker.get("_started_at_ts"))
        worker["rows_per_second"] = (
            round(int(worker.get("processed_rows") or 0) / elapsed_seconds, 2)
            if elapsed_seconds > 0
            else 0.0
        )
        _apply_derived_progress(job)


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
        "partition_column",
        "partition_mode",
        "worker_count",
        "requested_workers",
        "requested_parallel_mode",
        "resolved_parallel_mode",
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
        "warning_message",
        "warnings",
        "source_row_count",
        "target_row_count",
        "count_match",
        "validation_status",
        "validation_error_message",
        "workers",
        "performance_diagnostics",
    ]
    return {key: job.get(key) for key in keys}


def clear_jobs() -> None:
    with _LOCK:
        _JOBS.clear()
