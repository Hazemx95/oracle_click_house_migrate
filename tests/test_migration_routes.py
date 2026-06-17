import logging

import pytest
from fastapi import HTTPException

from app.api import migration_routes
from app.config import TARGET_DATABASE


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
