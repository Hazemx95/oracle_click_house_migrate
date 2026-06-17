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
    assert job is None
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
    assert job["source_row_count"] is None
    assert job["target_row_count"] is None
    assert job["count_match"] is None
    assert job["validation_status"] == "NOT_STARTED"
    assert job["validation_error_message"] is None
    assert job["warnings"] == []
    assert "performance_diagnostics" in job
    diagnostics = job["performance_diagnostics"]
    assert diagnostics["batch_size"] == 1000
    for key in (
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
        "batches_completed",
        "average_rows_per_batch",
        "average_seconds_per_batch",
        "timing_semantics",
        "per_worker_summary",
        "per_worker",
        "clickhouse_insert_batch_size",
        "max_concurrent_clickhouse_inserts",
        "insert_wait_seconds",
        "clickhouse_insert_timeout_count",
        "clickhouse_insert_retries",
        "clickhouse_insert_error_count",
        "validation_mode",
        "validation_timeout_seconds",
        "insert_failure",
    ):
        assert key in diagnostics


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
    assert status["source_row_count"] is None
    assert status["target_row_count"] is None
    assert status["count_match"] is None
    assert status["validation_status"] == "NOT_STARTED"
    assert status["validation_error_message"] is None
    assert "performance_diagnostics" in status


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
    assert job["performance_diagnostics"]["total_duration_seconds"] == job["duration_seconds"]


def test_warnings_are_appended_and_surface_in_status() -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )

    job_service.add_warning(job_id, "Small table detected; single-thread mode may be faster than parallel mode.")
    status = job_service.get_status(job_id)

    assert status is not None
    assert status["warnings"] == [
        "Small table detected; single-thread mode may be faster than parallel mode."
    ]


def test_hot_path_diagnostic_update_does_not_snapshot_public_job(monkeypatch) -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )

    def fail_snapshot(job):  # type: ignore[no-untyped-def]
        raise AssertionError("hot path should not deepcopy public job")

    monkeypatch.setattr(job_service, "_public_job", fail_snapshot)

    job_service.add_diagnostic_timing(job_id, "oracle_fetch_duration_seconds", 0.25)
    job_service.update_job_progress(job_id, processed_rows=1, inserted_rows=1)


def test_worker_diagnostics_surface_in_status() -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )

    job_service.set_worker_diagnostics(
        job_id,
        0,
        {
            "oracle_execute_duration_seconds": 0.1,
            "oracle_fetch_duration_seconds": 0.2,
            "row_conversion_duration_seconds": 0.3,
            "clickhouse_insert_duration_seconds": 0.4,
            "batches_completed": 1,
            "average_seconds_per_batch": 1.0,
        },
    )
    status = job_service.get_status(job_id)

    assert status is not None
    per_worker = status["performance_diagnostics"]["per_worker"]
    assert per_worker[0]["worker_id"] == 0
    assert per_worker[0]["oracle_fetch_duration_seconds"] == 0.2
    assert status["performance_diagnostics"]["timing_semantics"] == "cumulative_worker_seconds"
    assert status["performance_diagnostics"]["per_worker_summary"]["oracle_fetch_duration_seconds"] == {
        "max": 0.2,
        "average": 0.2,
    }


def test_adaptive_recommendations_surface_from_diagnostics() -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    job_service.update_performance_diagnostics(
        job_id,
        clickhouse_insert_timeout_count=1,
        clickhouse_insert_duration_seconds=100.0,
    )

    status = job_service.get_status(job_id)

    assert status is not None
    assert "ClickHouse insert timeout detected. Reduce CLICKHOUSE_INSERT_BATCH_SIZE" in status["recommendations"][0]
