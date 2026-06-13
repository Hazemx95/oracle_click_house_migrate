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
    assert job["worker_count"] == 1
    assert job["requested_workers"] == 8


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
