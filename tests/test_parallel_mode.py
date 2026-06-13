import pytest

from app.config import TARGET_DATABASE
from app.services import job_service
from app.services.migration_service import resolve_parallel_mode


def col(name: str, data_type: str) -> dict[str, object]:
    return {"column_name": name, "data_type": data_type}


def setup_function() -> None:
    job_service.clear_jobs()


def test_auto_number_resolves_to_numeric_range() -> None:
    result = resolve_parallel_mode("auto", "ID", [col("ID", "NUMBER")], 8)

    assert result["resolved_parallel_mode"] == "numeric_range"
    assert result["partition_mode"] == "numeric"


@pytest.mark.parametrize("data_type", ["DATE", "TIMESTAMP(6)", "TIMESTAMP WITH TIME ZONE"])
def test_auto_date_and_timestamp_resolve_to_date_range(data_type: str) -> None:
    result = resolve_parallel_mode("auto", "CREATED_AT", [col("CREATED_AT", data_type)], 8)

    assert result["resolved_parallel_mode"] == "date_range"
    assert result["partition_mode"] == "date"


def test_auto_other_valid_column_resolves_to_hash() -> None:
    result = resolve_parallel_mode("auto", "CODE", [col("CODE", "VARCHAR2")], 8)

    assert result["resolved_parallel_mode"] == "hash"
    assert result["partition_mode"] == "hash"


@pytest.mark.parametrize("data_type", ["DATE", "VARCHAR2"])
def test_explicit_numeric_range_rejects_non_number(data_type: str) -> None:
    with pytest.raises(ValueError, match="numeric_range requires a NUMBER column"):
        resolve_parallel_mode("numeric_range", "COL", [col("COL", data_type)], 8)


@pytest.mark.parametrize("data_type", ["NUMBER", "VARCHAR2"])
def test_explicit_date_range_rejects_non_date(data_type: str) -> None:
    with pytest.raises(ValueError, match="date_range requires a DATE or TIMESTAMP column"):
        resolve_parallel_mode("date_range", "COL", [col("COL", data_type)], 8)


@pytest.mark.parametrize("data_type", ["NUMBER", "DATE"])
def test_explicit_hash_accepts_number_and_date(data_type: str) -> None:
    result = resolve_parallel_mode("hash", "COL", [col("COL", data_type)], 8)

    assert result["resolved_parallel_mode"] == "hash"
    assert result["partition_mode"] == "hash"


def test_hash_requires_selected_column() -> None:
    with pytest.raises(ValueError, match="hash requires a selected partition/hash column"):
        resolve_parallel_mode("hash", None, [col("ID", "NUMBER")], 8)


def test_auto_parallel_requires_column() -> None:
    with pytest.raises(ValueError, match="partition/hash column is required"):
        resolve_parallel_mode("auto", None, [col("ID", "NUMBER")], 8)


def test_unknown_parallel_mode_rejected() -> None:
    with pytest.raises(ValueError, match="parallel_mode must be one of"):
        resolve_parallel_mode("round_robin", "ID", [col("ID", "NUMBER")], 8)


def test_workers_equal_one_resolves_to_single_with_warning() -> None:
    result = resolve_parallel_mode("numeric_range", "ID", [col("ID", "NUMBER")], 1)

    assert result["resolved_parallel_mode"] == "single"
    assert result["partition_mode"] == "single"
    assert result["warning_message"]


def test_workers_above_max_are_capped() -> None:
    result = resolve_parallel_mode("hash", "ID", [col("ID", "NUMBER")], 99)

    assert result["worker_count"] == 16


def test_status_shape_contains_parallel_mode_and_workers_array() -> None:
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
    job_service.set_workers(
        job_id,
        [
            {
                "worker_id": 0,
                "partition_mode": "numeric",
                "resolved_parallel_mode": "numeric_range",
                "partition_column": "ID",
                "range_start": 1,
                "range_end": 10,
                "status": "PENDING",
                "processed_rows": 0,
                "inserted_rows": 0,
                "batches_completed": 0,
                "rows_per_second": 0.0,
                "error_message": None,
            }
        ],
    )

    status = job_service.get_status(job_id)

    assert status is not None
    assert status["requested_parallel_mode"] == "auto"
    assert status["resolved_parallel_mode"] == "numeric_range"
    assert isinstance(status["workers"], list)
    assert status["workers"][0]["resolved_parallel_mode"] == "numeric_range"
