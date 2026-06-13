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

    job_id = migration_service.launch_initial_load(
        source_schema="CM",
        source_table="COMPONENT",
        target_schema="CM",
        target_table="COMPONENT",
        partition_column="ID",
        workers=8,
        batch_size=500,
    )
    job = job_service.get_job(job_id)

    assert job is not None
    assert job["status"] == "PENDING"
    assert job["target_database"] == TARGET_DATABASE
    assert job["target_table"] == "CM__COMPONENT"
    assert job["worker_count"] == 1
    assert job["requested_workers"] == 8
    assert FakeThread.last_args[0] == job_id
    assert FakeThread.last_args[1].workers == 1
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
