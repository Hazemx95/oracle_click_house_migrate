from app.config import TARGET_DATABASE
from app.services import job_service


def setup_function() -> None:
    job_service.clear_jobs()


def test_create_job_initializes_phase_6_fields() -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
        partition_column="ID",
        worker_count=8,
        batch_size=1000,
    )

    job = job_service.get_job(job_id)

    assert job is not None
    assert job["job_id"] == job_id
    assert job["status"] == "PENDING"
    assert job["target_database"] == TARGET_DATABASE
    assert job["total_rows"] == 0
    assert job["processed_rows"] == 0
    assert job["inserted_rows"] == 0
    assert job["remaining_rows"] == 0
    assert job["progress_percent"] == 0.0
    assert job["batches_completed"] == 0
    assert job["current_batch_number"] == 0
    assert job["workers"] == []
    assert job["worker_count"] == 8
    assert job["requested_workers"] == 8
    assert job["requested_parallel_mode"] == "auto"
    assert job["resolved_parallel_mode"] == "single"


def test_update_job_recomputes_progress_and_status_view() -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )

    job_service.update_job(job_id, status=job_service.JobStatus.RUNNING, total_rows=100)
    job_service.update_job(
        job_id,
        processed_rows=25,
        inserted_rows=25,
        batches_completed=1,
        current_batch_number=1,
    )
    status = job_service.get_status(job_id)

    assert status is not None
    assert status["status"] == "RUNNING"
    assert status["remaining_rows"] == 75
    assert status["progress_percent"] == 25.0
    assert status["current_batch"] == 1
    assert status["current_batch_number"] == 1
    assert status["workers"] == []


def test_worker_updates_aggregate_into_job_status() -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
        partition_column="ID",
        partition_mode="numeric",
        worker_count=2,
        requested_parallel_mode="auto",
        resolved_parallel_mode="numeric_range",
    )

    job_service.update_job(job_id, status=job_service.JobStatus.RUNNING, total_rows=100)
    job_service.set_workers(
        job_id,
        [
            {
                "worker_id": 0,
                "partition_mode": "numeric",
                "resolved_parallel_mode": "numeric_range",
                "partition_column": "ID",
                "range_start": 0,
                "range_end": 50,
                "status": "PENDING",
                "processed_rows": 0,
                "inserted_rows": 0,
                "batches_completed": 0,
                "rows_per_second": 0.0,
                "error_message": None,
            },
            {
                "worker_id": 1,
                "partition_mode": "numeric",
                "resolved_parallel_mode": "numeric_range",
                "partition_column": "ID",
                "range_start": 50,
                "range_end": 100,
                "status": "PENDING",
                "processed_rows": 0,
                "inserted_rows": 0,
                "batches_completed": 0,
                "rows_per_second": 0.0,
                "error_message": None,
            },
        ],
    )
    job_service.update_worker(
        job_id,
        0,
        processed_rows=25,
        inserted_rows=25,
        batches_completed=1,
    )
    job_service.update_worker(
        job_id,
        1,
        processed_rows=30,
        inserted_rows=30,
        batches_completed=2,
    )

    status = job_service.get_status(job_id)

    assert status is not None
    assert status["processed_rows"] == 55
    assert status["inserted_rows"] == 55
    assert status["batches_completed"] == 3
    assert status["progress_percent"] == 55.0


def test_terminal_status_records_finished_time_and_error() -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )

    job_service.update_job(job_id, status=job_service.JobStatus.RUNNING)
    job = job_service.update_job(
        job_id,
        status=job_service.JobStatus.FAILED,
        error_message="validation failed",
    )

    assert job["status"] == "FAILED"
    assert job["finished_at"] is not None
    assert job["duration_seconds"] is not None
    assert job["error_message"] == "validation failed"
