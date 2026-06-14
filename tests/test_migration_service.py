from app.config import TARGET_DATABASE, Settings
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


def test_inline_lob_values_do_not_require_locator_reads() -> None:
    batch = migration_service._normalize_batch(  # noqa: SLF001 - verifies fetch_lobs=False path
        [("clob text", b"\x01\x02")]
    )

    assert batch == [("clob text", "0102")]


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


def test_get_oracle_row_count_validates_metadata_and_runs_count_only(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(migration_service.metadata_service, "schema_exists", lambda schema: True)
    monkeypatch.setattr(
        migration_service.metadata_service,
        "table_exists",
        lambda schema, table: True,
    )

    def fake_run_select(sql, binds=None):  # type: ignore[no-untyped-def]
        captured["sql"] = sql
        captured["binds"] = binds
        return [(123,)]

    monkeypatch.setattr(migration_service.oracle_client, "run_select", fake_run_select)

    count = migration_service.get_oracle_row_count("CM", "COMPONENT")

    assert count == 123
    assert captured["sql"] == 'SELECT COUNT(*) FROM "CM"."COMPONENT"'
    assert captured["binds"] is None


def test_get_clickhouse_row_count_confines_query_to_target_database(monkeypatch) -> None:
    captured = {}

    def fake_count_rows(table, target_database):  # type: ignore[no-untyped-def]
        captured["table"] = table
        captured["target_database"] = target_database
        return 456

    monkeypatch.setattr(migration_service.clickhouse_client, "count_rows", fake_count_rows)

    count = migration_service.get_clickhouse_row_count(TARGET_DATABASE, "CM__COMPONENT")

    assert count == 456
    assert captured == {
        "table": "CM__COMPONENT",
        "target_database": TARGET_DATABASE,
    }


def test_get_clickhouse_row_count_rejects_non_target_database() -> None:
    try:
        migration_service.get_clickhouse_row_count("default", "CM__COMPONENT")
    except ValueError as exc:
        assert str(exc) == "target database must be 'oracle_migration_hazem'"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("non-target database was not rejected")


def test_run_validation_marks_success_when_counts_match(monkeypatch) -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    job_service.update_job(job_id, status=job_service.JobStatus.RUNNING)
    monkeypatch.setattr(migration_service, "count_source", lambda schema, table: 10)
    monkeypatch.setattr(
        migration_service,
        "count_target",
        lambda target_table, target_database: 10,
    )

    migration_service.run_validation(job_id)
    job = job_service.get_job(job_id)

    assert job is not None
    assert job["status"] == "SUCCESS"
    assert job["error_message"] is None
    assert job["source_row_count"] == 10
    assert job["target_row_count"] == 10
    assert job["count_match"] is True
    assert job["validation_status"] == "SUCCESS"
    assert job["validation_error_message"] is None


def test_run_validation_marks_failed_when_counts_mismatch(monkeypatch) -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    job_service.update_job(job_id, status=job_service.JobStatus.RUNNING)
    monkeypatch.setattr(migration_service, "count_source", lambda schema, table: 10)
    monkeypatch.setattr(
        migration_service,
        "count_target",
        lambda target_table, target_database: 9,
    )

    migration_service.run_validation(job_id)
    job = job_service.get_job(job_id)

    assert job is not None
    assert job["status"] == "FAILED"
    assert job["source_row_count"] == 10
    assert job["target_row_count"] == 9
    assert job["count_match"] is False
    assert job["validation_status"] == "FAILED"
    assert job["validation_error_message"] == (
        "Row count mismatch: Oracle source has 10 rows, ClickHouse target has 9 rows."
    )


def test_run_validation_keeps_source_count_when_target_count_fails(monkeypatch) -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    job_service.update_job(job_id, status=job_service.JobStatus.RUNNING)
    monkeypatch.setattr(migration_service, "count_source", lambda schema, table: 10)

    def raise_target_error(target_table, target_database):  # type: ignore[no-untyped-def]
        raise RuntimeError("target count unavailable")

    monkeypatch.setattr(migration_service, "count_target", raise_target_error)

    migration_service.run_validation(job_id)
    job = job_service.get_job(job_id)

    assert job is not None
    assert job["status"] == "SUCCESS"
    assert job["error_message"] is None
    assert job["source_row_count"] == 10
    assert job["target_row_count"] is None
    assert job["count_match"] is None
    assert job["validation_status"] == "FAILED"
    assert job["validation_error_message"] == "validation: target count unavailable"


def test_run_validation_records_duration_when_count_fails(monkeypatch) -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    ticks = iter([100.0, 102.5])
    monkeypatch.setattr(migration_service, "perf_counter", lambda: next(ticks))

    def raise_source_error(schema, table):  # type: ignore[no-untyped-def]
        raise RuntimeError("source count unavailable")

    monkeypatch.setattr(migration_service, "count_source", raise_source_error)

    migration_service.run_validation(job_id)
    job = job_service.get_job(job_id)

    assert job is not None
    assert job["performance_diagnostics"]["validation_duration_seconds"] == 2.5


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


def test_run_parallel_reports_actual_range_count_when_fewer_than_requested(monkeypatch) -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
        partition_column="ID",
        partition_mode="numeric",
        worker_count=8,
        requested_parallel_mode="numeric_range",
        resolved_parallel_mode="numeric_range",
    )
    request = migration_service.InitialLoadRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_schema="CM",
        target_table="COMPONENT",
        partition_column="ID",
        workers=8,
        batch_size=100,
        requested_parallel_mode="numeric_range",
        resolved_parallel_mode="numeric_range",
        partition_mode="numeric",
    )
    monkeypatch.setattr(
        migration_service,
        "_build_worker_ranges",
        lambda request: [
            migration_service.PartitionRange(0, 1, 2, False, True),
            migration_service.PartitionRange(1, 2, 3, False, False),
            migration_service.PartitionRange(2, 3, 3, True, False),
        ],
    )
    monkeypatch.setattr(migration_service, "_run_worker", lambda *args: None)

    migration_service.run_parallel(job_id, request, "CM__COMPONENT", ["ID"])
    status = job_service.get_status(job_id)

    assert status is not None
    assert status["requested_workers"] == 8
    assert status["worker_count"] == 3
    assert len(status["workers"]) == 3


def test_small_table_auto_mode_downgrades_to_single_with_warning(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(migration_parallel_min_rows=100000),
    )
    request = migration_service.InitialLoadRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_schema="CM",
        target_table="COMPONENT",
        partition_column="ID",
        workers=8,
        batch_size=1000,
        requested_parallel_mode="auto",
        resolved_parallel_mode="numeric_range",
        partition_mode="numeric",
    )

    resolved, warning = migration_service.apply_small_table_rule(request, 29792)

    assert resolved.workers == 1
    assert resolved.resolved_parallel_mode == "single"
    assert resolved.partition_mode == "single"
    assert warning == migration_service.SMALL_TABLE_WARNING


def test_small_table_explicit_parallel_mode_is_preserved_with_warning(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(migration_parallel_min_rows=100000),
    )
    request = migration_service.InitialLoadRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_schema="CM",
        target_table="COMPONENT",
        partition_column="ID",
        workers=8,
        batch_size=1000,
        requested_parallel_mode="numeric_range",
        resolved_parallel_mode="numeric_range",
        partition_mode="numeric",
    )

    resolved, warning = migration_service.apply_small_table_rule(request, 29792)

    assert resolved.workers == 8
    assert resolved.resolved_parallel_mode == "numeric_range"
    assert resolved.partition_mode == "numeric"
    assert warning == migration_service.SMALL_TABLE_WARNING


def test_integer_numeric_ranges_use_integer_boundaries_without_gaps() -> None:
    ranges = migration_service.compute_numeric_ranges(
        41765960,
        41766031,
        8,
        integer_boundaries=True,
    )

    assert len(ranges) == 8
    assert all(isinstance(item.start, int) and isinstance(item.end, int) for item in ranges)
    assert all("." not in str(item.start) and "." not in str(item.end) for item in ranges)
    assert ranges[0].start == 41765960
    assert ranges[-1].end == 41766031
    assert ranges[-1].inclusive_end is True
    for left, right in zip(ranges, ranges[1:]):
        assert left.end == right.start
        assert left.inclusive_end is False


def test_error_message_includes_step_and_redacts_secret(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(p5_qa_oracle_password="super-secret"),
    )

    message = migration_service._safe_error_message(  # noqa: SLF001
        RuntimeError("failed with super-secret"),
        "oracle_fetch",
    )

    assert message == "oracle_fetch: failed with ***"
