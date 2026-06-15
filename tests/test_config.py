import pytest

from app.config import TARGET_DATABASE, get_settings


def test_target_database_constant() -> None:
    assert TARGET_DATABASE == "oracle_migration_hazem"


def test_settings_load_defaults(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setattr("app.config.load_dotenv", lambda: None)
    settings = get_settings()
    assert settings.clickhouse_database == TARGET_DATABASE
    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 8000
    assert settings.migration_batch_size == 50000
    assert settings.oracle_arraysize == settings.migration_batch_size
    assert settings.oracle_prefetchrows == settings.migration_batch_size
    assert settings.clickhouse_connect_timeout_seconds == 15
    assert settings.clickhouse_send_receive_timeout_seconds == 900
    assert settings.clickhouse_insert_timeout_seconds == 900
    assert settings.clickhouse_compress is True
    assert settings.clickhouse_insert_batch_size == 25000
    assert settings.clickhouse_max_concurrent_inserts == 2
    assert settings.clickhouse_insert_retry_attempts == 0
    assert settings.clickhouse_insert_retry_backoff_seconds == 2
    assert settings.migration_default_workers == 4
    assert settings.migration_max_workers == 8
    assert settings.migration_absolute_max_workers == 16
    assert settings.migration_dynamic_chunks_enabled is True
    assert settings.migration_chunks_per_worker == 16
    assert settings.migration_parallel_min_rows == 100000
    assert settings.validation_mode == "fast"
    assert settings.validation_timeout_seconds == 600
    get_settings.cache_clear()


def test_phase_8_1_settings_validate_positive_integers(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setattr("app.config.load_dotenv", lambda: None)
    monkeypatch.setenv("MIGRATION_BATCH_SIZE", "0")

    with pytest.raises(ValueError, match="MIGRATION_BATCH_SIZE must be a positive integer"):
        get_settings()

    get_settings.cache_clear()


def test_empty_clickhouse_password_is_allowed(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setattr("app.config.load_dotenv", lambda: None)
    monkeypatch.setenv("CLICKHOUSE_PASS", "")

    settings = get_settings()

    assert settings.clickhouse_pass == ""
    get_settings.cache_clear()


def test_phase_8_2_settings_reject_invalid_values(monkeypatch) -> None:
    monkeypatch.setattr("app.config.load_dotenv", lambda: None)
    invalid_cases = [
        ("CLICKHOUSE_MAX_CONCURRENT_INSERTS", "0", "positive integer"),
        ("CLICKHOUSE_INSERT_RETRY_ATTEMPTS", "-1", "zero or a positive integer"),
        ("VALIDATION_TIMEOUT_SECONDS", "0", "positive integer"),
        ("MIGRATION_MAX_WORKERS", "17", "less than or equal"),
        ("VALIDATION_MODE", "bogus", "fast, strict, none"),
    ]

    for name, value, message in invalid_cases:
        get_settings.cache_clear()
        monkeypatch.setenv(name, value)
        with pytest.raises(ValueError, match=message):
            get_settings()
        monkeypatch.delenv(name, raising=False)

    get_settings.cache_clear()


def test_app_imports() -> None:
    from app.main import app

    assert app.title == "Oracle to ClickHouse Migration Engine"
