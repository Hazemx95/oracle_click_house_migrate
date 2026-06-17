import logging

import pytest
from fastapi import HTTPException

from app.api import migration_routes
from app.config import TARGET_DATABASE
from app.services import job_service


def setup_function() -> None:
    job_service.clear_jobs()


def test_launch_migration_logs_only_error_class_on_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = migration_routes.MigrationRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="COMPONENT",
    )
    monkeypatch.setattr(migration_routes.ddl_mapper, "assert_target_database", lambda db: None)

    def fail_launch(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("dsn contains super-secret")

    monkeypatch.setattr(migration_routes.migration_service, "launch_initial_load", fail_launch)

    with caplog.at_level(logging.ERROR), pytest.raises(HTTPException):
        migration_routes.launch_migration(request)

    assert "RuntimeError" in caplog.text
    assert "super-secret" not in caplog.text
    assert "dsn contains" not in caplog.text


def test_launch_migration_accepts_gui_override_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    request = migration_routes.MigrationRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="COMPONENT",
        oracle_fetch_batch_size=50000,
        clickhouse_insert_batch_size=10000,
        max_concurrent_clickhouse_inserts=1,
        validation_mode="fast",
        dynamic_chunks_per_worker=64,
    )
    monkeypatch.setattr(migration_routes.ddl_mapper, "assert_target_database", lambda db: None)
    monkeypatch.setattr(migration_routes.migration_service, "resolve_effective_settings", lambda overrides: captured.setdefault("overrides", overrides))

    def fake_launch(**kwargs):  # type: ignore[no-untyped-def]
        captured["launch"] = kwargs
        return job_service.create_job(
            source_schema="CM",
            source_table="COMPONENT",
            target_database=TARGET_DATABASE,
            target_table="CM__COMPONENT",
            effective_settings={"effective_clickhouse_insert_batch_size": 10000},
        )

    monkeypatch.setattr(migration_routes.migration_service, "launch_initial_load", fake_launch)

    response = migration_routes.launch_migration(request)

    assert response["effective_settings"]["effective_clickhouse_insert_batch_size"] == 10000
    assert captured["overrides"] == {
        "oracle_fetch_batch_size": 50000,
        "clickhouse_insert_batch_size": 10000,
        "max_concurrent_clickhouse_inserts": 1,
        "validation_mode": "fast",
        "dynamic_chunks_per_worker": 64,
    }
    assert captured["launch"]["overrides"] == captured["overrides"]


def test_invalid_gui_override_returns_400_and_creates_no_job(monkeypatch: pytest.MonkeyPatch) -> None:
    request = migration_routes.MigrationRequest(
        source_schema="CM",
        source_table="COMPONENT",
        target_database=TARGET_DATABASE,
        target_table="COMPONENT",
        clickhouse_insert_batch_size=-5,
    )
    monkeypatch.setattr(migration_routes.ddl_mapper, "assert_target_database", lambda db: None)
    monkeypatch.setattr(
        migration_routes.migration_service,
        "resolve_effective_settings",
        lambda overrides: (_ for _ in ()).throw(ValueError("clickhouse_insert_batch_size must be a positive integer")),
    )

    with pytest.raises(HTTPException) as exc:
        migration_routes.launch_migration(request)

    assert exc.value.status_code == 400
    assert job_service.get_status("missing") is None
