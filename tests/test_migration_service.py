from app.config import TARGET_DATABASE
from app.db import clickhouse_client
from app.services import job_service, migration_service


def setup_function() -> None:
    job_service.clear_jobs()


class FakeThread:
    last_args = None

    def __init__(self, target, args, daemon):  # type: ignore[no-untyped-def]
        self.target = target
        self.args = args
        self.daemon = daemon
        FakeThread.last_args = args

    def start(self) -> None:
        return None


def test_launch_initial_load_returns_job_id_and_starts_background_thread(monkeypatch) -> None:
    monkeypatch.setattr(migration_service, "Thread", FakeThread)
    monkeypatch.setattr(migration_service.metadata_service, "schema_exists", lambda schema: True)
    monkeypatch.setattr(
        migration_service.metadata_service,
        "table_exists",
        lambda schema, table: True,
    )
    monkeypatch.setattr(
        migration_service.metadata_service,
        "list_columns",
        lambda schema, table: [{"column_name": "ID", "data_type": "NUMBER"}],
    )

    job_id = migration_service.launch_initial_load(
        source_schema="CM",
        source_table="COMPONENT",
        target_schema="CM",
        target_table="COMPONENT",
        partition_column="ID",
        workers=8,
        batch_size=500,
        parallel_mode="numeric_range",
    )
    job = job_service.get_job(job_id)

    assert job is not None
    assert job["status"] == "PENDING"
    assert job["target_database"] == TARGET_DATABASE
    assert job["target_table"] == "CM__COMPONENT"
    assert job["worker_count"] == 8
    assert job["requested_workers"] == 8
    assert job["requested_parallel_mode"] == "numeric_range"
    assert job["resolved_parallel_mode"] == "numeric_range"
    assert FakeThread.last_args[0] == job_id
    assert FakeThread.last_args[1].workers == 8
    assert FakeThread.last_args[1].batch_size == 500


def test_run_initial_load_marks_failed_when_oracle_schema_validation_fails(monkeypatch) -> None:
    job_id = job_service.create_job(
        source_schema="BAD",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="BAD__COMPONENT",
    )
    request = migration_service.InitialLoadRequest(
        source_schema="BAD",
        source_table="COMPONENT",
        target_schema="BAD",
        target_table="COMPONENT",
        partition_column=None,
        workers=1,
        batch_size=100,
    )
    monkeypatch.setattr(migration_service.metadata_service, "schema_exists", lambda schema: False)

    migration_service.run_initial_load(job_id, request)
    job = job_service.get_job(job_id)

    assert job is not None
    assert job["status"] == "FAILED"
    assert "source schema 'BAD' not found" in str(job["error_message"])


def test_clickhouse_insert_rows_rejects_non_target_database() -> None:
    try:
        clickhouse_client.insert_rows(
            "CM__COMPONENT",
            [(1,)],
            ["ID"],
            target_database="default",
        )
    except ValueError as exc:
        assert str(exc) == "target database must be 'oracle_migration_hazem'"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("non-target database was not rejected")


def test_binary_and_lob_values_are_normalized_to_hex_strings() -> None:
    class FakeLob:
        def read(self) -> bytes:
            return b"\xff\x00"

    batch = migration_service._normalize_batch(  # noqa: SLF001 - regression test for loader encoding
        [(b"\x01\x02", bytearray(b"\x03\x04"), memoryview(b"\x05\x06"), FakeLob())]
    )

    assert batch == [("0102", "0304", "0506", "ff00")]


def test_clickhouse_insert_rows_uses_batch_insert_with_explicit_columns() -> None:
    class FakeClickHouse:
        def __init__(self) -> None:
            self.calls = []

        def insert(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls.append(kwargs)

    client = FakeClickHouse()

    inserted = clickhouse_client.insert_rows(
        "CM__COMPONENT",
        [(1, "A"), (2, "B")],
        ["ID", "NAME"],
        client=client,
    )

    assert inserted == 2
    assert client.calls == [
        {
            "table": "CM__COMPONENT",
            "data": [(1, "A"), (2, "B")],
            "column_names": ["ID", "NAME"],
            "database": TARGET_DATABASE,
        }
    ]


def test_hash_worker_uses_null_safe_hash_predicate(monkeypatch) -> None:
    captured = {}
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
        partition_column="CODE",
        partition_mode="hash",
        worker_count=2,
        requested_parallel_mode="hash",
        resolved_parallel_mode="hash",
    )
    request = migration_service.InitialLoadRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_schema="CM",
        target_table="COMPONENT",
        partition_column="CODE",
        workers=2,
        batch_size=100,
        requested_parallel_mode="hash",
        resolved_parallel_mode="hash",
        partition_mode="hash",
    )
    job_service.set_workers(
        job_id,
        [
            {
                "worker_id": 0,
                "partition_mode": "hash",
                "resolved_parallel_mode": "hash",
                "partition_column": "CODE",
                "range_start": None,
                "range_end": None,
                "status": "PENDING",
                "processed_rows": 0,
                "inserted_rows": 0,
                "batches_completed": 0,
                "rows_per_second": 0.0,
                "error_message": None,
            }
        ],
    )

    def fake_copy_batches(**kwargs):  # type: ignore[no-untyped-def]
        captured["select_sql"] = kwargs["select_sql"]
        captured["binds"] = kwargs["binds"]
        return 0, 0, 0

    monkeypatch.setattr(migration_service, "_copy_batches", fake_copy_batches)

    migration_service._run_worker(  # noqa: SLF001
        job_id,
        request,
        "CM__COMPONENT",
        ["ID", "CODE"],
        migration_service.PartitionRange(0, None, None, False),
    )

    assert 'MOD(NVL(ORA_HASH("CODE"), 0), :workers) = :worker_id' in captured["select_sql"]
    assert captured["binds"] == {"workers": 2, "worker_id": 0}


def test_run_parallel_aggregates_worker_progress(monkeypatch) -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
        partition_column="ID",
        partition_mode="numeric",
        worker_count=2,
        requested_parallel_mode="numeric_range",
        resolved_parallel_mode="numeric_range",
    )
    job_service.update_job(job_id, status=job_service.JobStatus.RUNNING, total_rows=100)
    request = migration_service.InitialLoadRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_schema="CM",
        target_table="COMPONENT",
        partition_column="ID",
        workers=2,
        batch_size=100,
        requested_parallel_mode="numeric_range",
        resolved_parallel_mode="numeric_range",
        partition_mode="numeric",
    )
    monkeypatch.setattr(
        migration_service,
        "_build_worker_ranges",
        lambda request: [
            migration_service.PartitionRange(0, 0, 50, False, True),
            migration_service.PartitionRange(1, 50, 100, True, False),
        ],
    )

    def fake_run_worker(job_id, request, target_table, column_names, partition_range):  # type: ignore[no-untyped-def]
        job_service.update_worker(
            job_id,
            partition_range.worker_id,
            status=job_service.JobStatus.SUCCESS,
            processed_rows=50,
            inserted_rows=50,
            batches_completed=1,
        )

    monkeypatch.setattr(migration_service, "_run_worker", fake_run_worker)

    migration_service.run_parallel(job_id, request, "CM__COMPONENT", ["ID"])
    status = job_service.get_status(job_id)

    assert status is not None
    assert status["processed_rows"] == 100
    assert status["inserted_rows"] == 100
    assert status["batches_completed"] == 2
    assert status["progress_percent"] == 100.0
