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


def test_clickhouse_insert_rows_uses_batch_insert_with_explicit_columns(monkeypatch) -> None:
    class FakeClickHouse:
        def __init__(self) -> None:
            self.calls = []

        def insert(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls.append(kwargs)

    client = FakeClickHouse()
    monkeypatch.setattr(clickhouse_client, "get_settings", lambda: Settings())

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
    work_queue = migration_service.Queue()
    work_queue.put(migration_service.PartitionRange(0, None, None, False))

    migration_service._run_worker(  # noqa: SLF001
        job_id,
        request,
        "CM__COMPONENT",
        ["ID", "CODE"],
        work_queue,
        migration_service._new_insert_controller(),  # noqa: SLF001
        0,
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

    def fake_run_worker(job_id, request, target_table, column_names, work_queue, controller, worker_id):  # type: ignore[no-untyped-def]
        partition_range = work_queue.get_nowait()
        job_service.update_worker(
            job_id,
            worker_id,
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
    assert status["worker_count"] == 8
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


def test_insert_semaphore_limits_concurrency_and_releases_after_failure(monkeypatch) -> None:
    settings = Settings(clickhouse_max_concurrent_inserts=1, clickhouse_insert_batch_size=1)
    monkeypatch.setattr(migration_service, "get_settings", lambda: settings)
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    controller = migration_service._new_insert_controller()  # noqa: SLF001
    observed = {"permit_was_held": False}

    class FakeCursor:
        arraysize = 0
        prefetchrows = 0

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        def execute(self, sql, binds):  # type: ignore[no-untyped-def]
            return None

        def fetchmany(self, size):  # type: ignore[no-untyped-def]
            if not hasattr(self, "returned"):
                self.returned = True
                return [(1,)]
            return []

    class FakeConnection:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        def cursor(self):  # type: ignore[no-untyped-def]
            return FakeCursor()

    class FakeClickHouse:
        def close(self):  # type: ignore[no-untyped-def]
            return None

    request = migration_service.InitialLoadRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_schema="CM",
        target_table="COMPONENT",
        partition_column=None,
        workers=1,
        batch_size=10,
    )

    def failing_insert_rows(*args, **kwargs):  # type: ignore[no-untyped-def]
        observed["permit_was_held"] = not controller.semaphore.acquire(blocking=False)
        raise RuntimeError("insert failed")

    monkeypatch.setattr(migration_service.clickhouse_client, "get_insert_client", lambda: FakeClickHouse())
    monkeypatch.setattr(migration_service.oracle_client, "get_connection", lambda: FakeConnection())
    monkeypatch.setattr(migration_service.clickhouse_client, "insert_rows", failing_insert_rows)

    try:
        migration_service._copy_batches(  # noqa: SLF001
            select_sql='SELECT "ID" FROM "CM"."COMPONENT"',
            binds=None,
            request=request,
            target_table="CM__COMPONENT",
            column_names=["ID"],
            job_id=job_id,
            controller=controller,
        )
    except RuntimeError:
        pass

    assert observed["permit_was_held"] is True
    assert controller.semaphore.acquire(blocking=False) is True


def test_oracle_batch_splits_into_smaller_clickhouse_chunks(monkeypatch) -> None:
    rows = [(1,), (2,), (3,), (4,), (5,)]
    chunks = [chunk for chunk in migration_service._chunk_rows(rows, 2)]  # noqa: SLF001

    assert chunks == [[(1,), (2,)], [(3,), (4,)], [(5,)]]


def test_clickhouse_timeout_marks_job_failed_and_skips_validation(monkeypatch) -> None:
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    job_service.update_job(job_id, status=job_service.JobStatus.RUNNING)
    called = {"validation": False}

    def timeout_insert(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise clickhouse_client.ClickHouseInsertTimeoutError("timed out")

    monkeypatch.setattr(migration_service.clickhouse_client, "insert_rows", timeout_insert)
    monkeypatch.setattr(migration_service, "run_validation", lambda job_id: called.__setitem__("validation", True))

    try:
        migration_service._insert_with_retry(  # noqa: SLF001
            job_id=job_id,
            target_table="CM__COMPONENT",
            insert_chunk=[(1,)],
            column_names=["ID"],
            target_database=TARGET_DATABASE,
            clickhouse=object(),
        )
    except clickhouse_client.ClickHouseInsertTimeoutError as exc:
        migration_service._record_insert_failure(  # noqa: SLF001
            job_id=job_id,
            worker_id=0,
            chunk_id=1,
            batch_number=1,
            range_start=1,
            range_end=2,
            inserted_rows_before_failure=0,
            exc=exc,
        )

    job = job_service.get_job(job_id)

    assert job is not None
    assert job["status"] == "FAILED"
    assert job["error_message"] == migration_service.INSERT_TIMEOUT_MESSAGE
    assert job["insert_failure"]["worker_id"] == 0
    assert called["validation"] is False


def test_cancellation_flag_stops_workers_at_safe_boundary() -> None:
    controller = migration_service._new_insert_controller()  # noqa: SLF001
    controller.cancellation.set()

    try:
        migration_service._raise_if_cancelled(controller)  # noqa: SLF001
    except RuntimeError as exc:
        assert "cancelled" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("cancellation flag was not honored")


def test_validation_fast_mode_reuses_initial_oracle_count(monkeypatch) -> None:
    monkeypatch.setattr(migration_service, "get_settings", lambda: Settings(validation_mode="fast"))
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    job_service.update_job(job_id, status=job_service.JobStatus.RUNNING, total_rows=10)
    monkeypatch.setattr(migration_service, "count_source", lambda schema, table: (_ for _ in ()).throw(AssertionError("source recounted")))
    monkeypatch.setattr(migration_service, "count_target", lambda target_table, target_database: 10)

    migration_service.run_validation(job_id)

    assert job_service.get_job(job_id)["validation_status"] == "SUCCESS"


def test_validation_strict_mode_recounts_oracle(monkeypatch) -> None:
    monkeypatch.setattr(migration_service, "get_settings", lambda: Settings(validation_mode="strict"))
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    called = {"source": 0}

    def count_source(schema, table):  # type: ignore[no-untyped-def]
        called["source"] += 1
        return 10

    monkeypatch.setattr(migration_service, "count_source", count_source)
    monkeypatch.setattr(migration_service, "count_target", lambda target_table, target_database: 10)

    migration_service.run_validation(job_id)

    assert called["source"] == 1


def test_validation_none_mode_skips_counts(monkeypatch) -> None:
    monkeypatch.setattr(migration_service, "get_settings", lambda: Settings(validation_mode="none"))
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    monkeypatch.setattr(migration_service, "count_source", lambda *args: (_ for _ in ()).throw(AssertionError("source counted")))
    monkeypatch.setattr(migration_service, "count_target", lambda *args: (_ for _ in ()).throw(AssertionError("target counted")))

    migration_service.run_validation(job_id)
    job = job_service.get_job(job_id)

    assert job["validation_status"] == "SKIPPED"
    assert job["count_match"] is None


def test_retry_transient_insert_failure_then_success_records_warning_and_backoff(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(
            clickhouse_insert_retry_attempts=2,
            clickhouse_insert_retry_backoff_seconds=3,
        ),
    )
    sleeps = []
    calls = {"count": 0}
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )

    def flaky_insert(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("connection reset by peer")
        return 1

    monkeypatch.setattr(migration_service.clickhouse_client, "insert_rows", flaky_insert)
    monkeypatch.setattr(migration_service, "sleep", lambda seconds: sleeps.append(seconds))

    inserted, _wait_seconds, _insert_seconds = migration_service._insert_with_retry(  # noqa: SLF001
        job_id=job_id,
        target_table="CM__COMPONENT",
        insert_chunk=[(1,)],
        column_names=["ID"],
        target_database=TARGET_DATABASE,
        clickhouse=object(),
    )
    status = job_service.get_status(job_id)

    assert inserted == 1
    assert calls["count"] == 2
    assert sleeps == [3]
    assert migration_service.INSERT_RETRY_WARNING in status["warnings"]
    assert status["clickhouse_insert_retries"] == 1.0
    assert status["clickhouse_insert_error_count"] == 1.0


def test_non_transient_insert_error_is_not_retried(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(clickhouse_insert_retry_attempts=2),
    )
    calls = {"count": 0}
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )

    def bad_insert(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        raise ValueError("bad row encoding")

    monkeypatch.setattr(migration_service.clickhouse_client, "insert_rows", bad_insert)

    try:
        migration_service._insert_with_retry(  # noqa: SLF001
            job_id=job_id,
            target_table="CM__COMPONENT",
            insert_chunk=[(1,)],
            column_names=["ID"],
            target_database=TARGET_DATABASE,
            clickhouse=object(),
        )
    except ValueError:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("non-transient insert error was swallowed")

    assert calls["count"] == 1


def test_insert_timeout_is_never_retried_even_when_retries_enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(clickhouse_insert_retry_attempts=2),
    )
    calls = {"count": 0}
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    controller = migration_service._new_insert_controller()  # noqa: SLF001

    def timeout_insert(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        raise clickhouse_client.ClickHouseInsertTimeoutError("timed out")

    monkeypatch.setattr(migration_service.clickhouse_client, "insert_rows", timeout_insert)

    try:
        migration_service._insert_with_retry(  # noqa: SLF001
            job_id=job_id,
            target_table="CM__COMPONENT",
            insert_chunk=[(1,)],
            column_names=["ID"],
            target_database=TARGET_DATABASE,
            clickhouse=object(),
            controller=controller,
        )
    except clickhouse_client.ClickHouseInsertTimeoutError:
        migration_service._record_insert_failure(  # noqa: SLF001
            job_id=job_id,
            worker_id=None,
            chunk_id=1,
            batch_number=1,
            range_start=None,
            range_end=None,
            inserted_rows_before_failure=0,
            exc=clickhouse_client.ClickHouseInsertTimeoutError("timed out"),
        )
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("timeout insert was retried or swallowed")

    status = job_service.get_status(job_id)
    assert calls["count"] == 1
    assert controller.cancellation.is_set()
    assert status["status"] == "FAILED"
    assert status["clickhouse_insert_timeout_count"] == 1.0
    assert status["clickhouse_insert_retries"] == 0


def test_run_parallel_timeout_cancels_other_workers_and_fails_job(monkeypatch) -> None:
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

    class FakeFuture:
        def __init__(self, exc=None):  # type: ignore[no-untyped-def]
            self.exc = exc

        def result(self):  # type: ignore[no-untyped-def]
            if self.exc:
                raise self.exc

    class ImmediateExecutor:
        def __init__(self, max_workers):  # type: ignore[no-untyped-def]
            self.max_workers = max_workers

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        def submit(self, func, *args):  # type: ignore[no-untyped-def]
            try:
                func(*args)
            except Exception as exc:  # noqa: BLE001 - fake future captures worker failure
                return FakeFuture(exc)
            return FakeFuture()

    def timeout_copy_batches(**kwargs):  # type: ignore[no-untyped-def]
        controller = kwargs["controller"]
        partition_range = kwargs["partition_range"]
        if partition_range.worker_id == 0:
            controller.cancellation.set()
            exc = clickhouse_client.ClickHouseInsertTimeoutError("timed out")
            migration_service._record_insert_failure(  # noqa: SLF001
                job_id=job_id,
                worker_id=kwargs["worker_id"],
                chunk_id=partition_range.worker_id,
                batch_number=1,
                range_start=partition_range.start,
                range_end=partition_range.end,
                inserted_rows_before_failure=0,
                exc=exc,
            )
            raise exc
        migration_service._raise_if_cancelled(controller)  # noqa: SLF001
        return 0, 0, 0

    monkeypatch.setattr(
        migration_service,
        "_build_worker_ranges",
        lambda request: [
            migration_service.PartitionRange(0, 0, 50, False, True),
            migration_service.PartitionRange(1, 50, 100, True, False),
        ],
    )
    monkeypatch.setattr(migration_service, "_copy_batches", timeout_copy_batches)
    monkeypatch.setattr(migration_service, "ThreadPoolExecutor", ImmediateExecutor)
    monkeypatch.setattr(migration_service, "as_completed", lambda futures: futures)

    try:
        migration_service.run_parallel(job_id, request, "CM__COMPONENT", ["ID"])
    except RuntimeError:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("parallel timeout did not fail the run")
    status = job_service.get_status(job_id)

    assert status["status"] == "FAILED"
    assert status["error_message"] == migration_service.INSERT_TIMEOUT_MESSAGE
    assert status["workers"][0]["status"] == "FAILED"
    assert status["workers"][1]["status"] == "CANCELLED"


def test_validation_timeout_sets_timeout_status(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(validation_mode="fast", validation_timeout_seconds=1),
    )
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
    )
    job_service.update_job(job_id, status=job_service.JobStatus.RUNNING, total_rows=10)
    monkeypatch.setattr(migration_service, "_run_validation_counts_with_timeout", lambda *args: None)

    migration_service.run_validation(job_id)
    status = job_service.get_status(job_id)

    assert status["status"] == "SUCCESS"
    assert status["validation_status"] == "TIMEOUT"
    assert status["count_match"] is None
    assert "validation timed out" in status["warnings"][-1]


def test_build_worker_ranges_uses_dynamic_chunk_count_for_numeric_and_date(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(migration_dynamic_chunks_enabled=True, migration_chunks_per_worker=4),
    )
    monkeypatch.setattr(migration_service, "_min_max_values", lambda schema, table, column: (0, 1000))
    numeric_request = migration_service.InitialLoadRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_schema="CM",
        target_table="COMPONENT",
        partition_column="ID",
        workers=3,
        batch_size=100,
        partition_mode="numeric",
        partition_column_scale=0,
        total_rows=12_000_000,
    )
    date_request = migration_service.InitialLoadRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_schema="CM",
        target_table="COMPONENT",
        partition_column="CREATED_AT",
        workers=3,
        batch_size=100,
        partition_mode="date",
        total_rows=12_000_000,
    )
    monkeypatch.setattr(
        migration_service,
        "_min_max_values",
        lambda schema, table, column: (0, 1000) if column == "ID" else (
            migration_service.datetime(2026, 1, 1),
            migration_service.datetime(2026, 1, 13),
        ),
    )

    assert len(migration_service._build_worker_ranges(numeric_request)) >= 3 * 64  # noqa: SLF001
    assert len(migration_service._build_worker_ranges(date_request)) >= 3 * 64  # noqa: SLF001


def test_resolve_effective_settings_defaults_and_override_isolation(monkeypatch) -> None:
    settings = Settings(
        oracle_arraysize=50000,
        clickhouse_insert_batch_size=25000,
        clickhouse_max_concurrent_inserts=2,
        migration_chunks_per_worker=64,
        validation_mode="fast",
    )
    monkeypatch.setattr(migration_service, "get_settings", lambda: settings)

    defaults = migration_service.resolve_effective_settings({})
    override = migration_service.resolve_effective_settings(
        {
            "oracle_fetch_batch_size": 10000,
            "clickhouse_insert_batch_size": 5000,
            "max_concurrent_clickhouse_inserts": 1,
            "validation_mode": "none",
            "dynamic_chunks_per_worker": 128,
        }
    )

    assert defaults.effective_oracle_fetch_batch_size == 50000
    assert defaults.effective_clickhouse_insert_batch_size == 25000
    assert override.effective_oracle_fetch_batch_size == 10000
    assert override.effective_clickhouse_insert_batch_size == 5000
    assert override.effective_max_concurrent_clickhouse_inserts == 1
    assert override.effective_validation_mode == "none"
    assert settings.clickhouse_insert_batch_size == 25000


def test_adaptive_insert_size_decreases_and_respects_min(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(
            clickhouse_insert_slow_seconds=45,
            clickhouse_insert_target_seconds=30,
            clickhouse_min_insert_batch_size=1000,
            clickhouse_max_insert_batch_size=25000,
        ),
    )
    effective = migration_service.resolve_effective_settings({"clickhouse_insert_batch_size": 2000})
    controller = migration_service._new_insert_controller(effective)  # noqa: SLF001
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
        effective_settings=effective.as_dict(),
    )

    migration_service._record_adaptive_duration(job_id, controller, 60.0)  # noqa: SLF001
    migration_service._record_adaptive_duration(job_id, controller, 60.0)  # noqa: SLF001

    status = job_service.get_status(job_id)
    assert controller.adaptive_batch_size == 1000
    assert status["current_adaptive_insert_batch_size"] == 1000


def test_adaptive_insert_size_increases_without_exceeding_max(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(
            clickhouse_insert_slow_seconds=45,
            clickhouse_insert_target_seconds=30,
            clickhouse_min_insert_batch_size=1000,
            clickhouse_max_insert_batch_size=3000,
        ),
    )
    effective = migration_service.resolve_effective_settings({"clickhouse_insert_batch_size": 2000})
    controller = migration_service._new_insert_controller(effective)  # noqa: SLF001
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
        effective_settings=effective.as_dict(),
    )

    for _ in range(9):
        migration_service._record_adaptive_duration(job_id, controller, 1.0)  # noqa: SLF001

    assert controller.adaptive_batch_size == 3000


def test_adaptive_insert_disabled_keeps_batch_size_fixed(monkeypatch) -> None:
    monkeypatch.setattr(
        migration_service,
        "get_settings",
        lambda: Settings(
            clickhouse_adaptive_insert_enabled=False,
            clickhouse_insert_slow_seconds=45,
            clickhouse_insert_target_seconds=30,
            clickhouse_min_insert_batch_size=1000,
            clickhouse_max_insert_batch_size=25000,
        ),
    )
    effective = migration_service.resolve_effective_settings({"clickhouse_insert_batch_size": 2000})
    controller = migration_service._new_insert_controller(effective)  # noqa: SLF001
    job_id = job_service.create_job(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="CM__COMPONENT",
        effective_settings=effective.as_dict(),
    )

    migration_service._record_adaptive_duration(job_id, controller, 60.0)  # noqa: SLF001
    migration_service._record_adaptive_duration(job_id, controller, 1.0)  # noqa: SLF001

    status = job_service.get_status(job_id)
    assert controller.adaptive_batch_size == 2000
    assert status["current_adaptive_insert_batch_size"] == 2000
    assert status["performance_diagnostics"]["slow_insert_count"] == 1.0
