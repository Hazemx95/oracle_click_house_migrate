import pytest

from app.config import TARGET_DATABASE, get_settings


def test_target_database_constant() -> None:
    assert TARGET_DATABASE == "oracle_migration_hazem"


def test_settings_load_defaults() -> None:
    settings = get_settings()
    assert settings.clickhouse_database == TARGET_DATABASE
    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 8000
    assert settings.oracle_arraysize == settings.migration_batch_size
    assert settings.oracle_prefetchrows == settings.migration_batch_size
    assert settings.clickhouse_insert_batch_size == settings.migration_batch_size
    assert settings.migration_parallel_min_rows == 100000


def test_phase_8_1_settings_validate_positive_integers(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("MIGRATION_BATCH_SIZE", "0")

    with pytest.raises(ValueError, match="MIGRATION_BATCH_SIZE must be a positive integer"):
        get_settings()

    get_settings.cache_clear()


def test_app_imports() -> None:
    from app.main import app

    assert app.title == "Oracle to ClickHouse Migration Engine"
