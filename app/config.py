import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel

TARGET_DATABASE = "oracle_migration_hazem"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    value_text = str(default) if raw_value is None or raw_value == "" else raw_value
    try:
        value = int(value_text)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _env_non_negative_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    value_text = str(default) if raw_value is None or raw_value == "" else raw_value
    try:
        value = int(value_text)
    except ValueError as exc:
        raise ValueError(f"{name} must be zero or a positive integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be zero or a positive integer")
    return value


def _env_validation_mode(name: str, default: str) -> str:
    value = (os.getenv(name, default) or default).strip().lower()
    if value not in {"fast", "strict", "none"}:
        raise ValueError(f"{name} must be one of fast, strict, none")
    return value


class Settings(BaseModel):
    clickhouse_host: str = ""
    clickhouse_port: int = 8123
    clickhouse_user: str = ""
    clickhouse_pass: str = ""
    clickhouse_database: str = TARGET_DATABASE
    clickhouse_allow_create_database: bool = False
    p5_qa_oracle_user: str = ""
    p5_qa_oracle_password: str = ""
    p5_qa_oracle_host: str = ""
    p5_qa_oracle_port: int = 1521
    p5_qa_oracle_service_name: str = ""
    p5_qa_oracle_dsn: str = ""
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    migration_batch_size: int = 50000
    migration_default_workers: int = 4
    oracle_arraysize: int = 50000
    oracle_prefetchrows: int = 50000
    clickhouse_connect_timeout_seconds: int = 15
    clickhouse_send_receive_timeout_seconds: int = 900
    clickhouse_insert_timeout_seconds: int = 900
    clickhouse_compress: bool = True
    clickhouse_insert_batch_size: int = 25000
    clickhouse_max_concurrent_inserts: int = 2
    clickhouse_insert_retry_attempts: int = 0
    clickhouse_insert_retry_backoff_seconds: int = 2
    migration_max_workers: int = 8
    migration_absolute_max_workers: int = 16
    migration_dynamic_chunks_enabled: bool = True
    migration_chunks_per_worker: int = 16
    migration_parallel_min_rows: int = 100000
    validation_mode: str = "fast"
    validation_timeout_seconds: int = 600


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    migration_batch_size = _env_positive_int("MIGRATION_BATCH_SIZE", 50000)
    migration_absolute_max_workers = _env_positive_int(
        "MIGRATION_ABSOLUTE_MAX_WORKERS",
        16,
    )
    if migration_absolute_max_workers > 16:
        raise ValueError("MIGRATION_ABSOLUTE_MAX_WORKERS must be less than or equal to 16")
    migration_max_workers = _env_positive_int("MIGRATION_MAX_WORKERS", 8)
    if migration_max_workers > migration_absolute_max_workers:
        raise ValueError("MIGRATION_MAX_WORKERS must be less than or equal to MIGRATION_ABSOLUTE_MAX_WORKERS")
    migration_default_workers = _env_positive_int("MIGRATION_DEFAULT_WORKERS", 4)
    if migration_default_workers > migration_max_workers:
        raise ValueError("MIGRATION_DEFAULT_WORKERS must be less than or equal to MIGRATION_MAX_WORKERS")
    return Settings(
        clickhouse_host=os.getenv("CLICKHOUSE_HOST", ""),
        clickhouse_port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        clickhouse_user=os.getenv("CLICKHOUSE_USER", ""),
        clickhouse_pass=os.getenv("CLICKHOUSE_PASS", ""),
        clickhouse_database=os.getenv("CLICKHOUSE_DATABASE", TARGET_DATABASE),
        clickhouse_allow_create_database=_env_bool(
            "CLICKHOUSE_ALLOW_CREATE_DATABASE", False
        ),
        p5_qa_oracle_user=os.getenv("P5_QA_ORACLE_USER", ""),
        p5_qa_oracle_password=os.getenv("P5_QA_ORACLE_PASSWORD", ""),
        p5_qa_oracle_host=os.getenv("P5_QA_ORACLE_HOST", ""),
        p5_qa_oracle_port=int(os.getenv("P5_QA_ORACLE_PORT", "1521")),
        p5_qa_oracle_service_name=os.getenv("P5_QA_ORACLE_SERVICE_NAME", ""),
        p5_qa_oracle_dsn=os.getenv("P5_QA_ORACLE_DSN", ""),
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        migration_batch_size=migration_batch_size,
        migration_default_workers=migration_default_workers,
        oracle_arraysize=_env_positive_int("ORACLE_ARRAYSIZE", migration_batch_size),
        oracle_prefetchrows=_env_positive_int("ORACLE_PREFETCHROWS", migration_batch_size),
        clickhouse_connect_timeout_seconds=_env_positive_int(
            "CLICKHOUSE_CONNECT_TIMEOUT_SECONDS",
            15,
        ),
        clickhouse_send_receive_timeout_seconds=_env_positive_int(
            "CLICKHOUSE_SEND_RECEIVE_TIMEOUT_SECONDS",
            900,
        ),
        clickhouse_insert_timeout_seconds=_env_positive_int(
            "CLICKHOUSE_INSERT_TIMEOUT_SECONDS",
            900,
        ),
        clickhouse_compress=_env_bool("CLICKHOUSE_COMPRESS", True),
        clickhouse_insert_batch_size=_env_positive_int(
            "CLICKHOUSE_INSERT_BATCH_SIZE",
            25000,
        ),
        clickhouse_max_concurrent_inserts=_env_positive_int(
            "CLICKHOUSE_MAX_CONCURRENT_INSERTS",
            2,
        ),
        clickhouse_insert_retry_attempts=_env_non_negative_int(
            "CLICKHOUSE_INSERT_RETRY_ATTEMPTS",
            0,
        ),
        clickhouse_insert_retry_backoff_seconds=_env_positive_int(
            "CLICKHOUSE_INSERT_RETRY_BACKOFF_SECONDS",
            2,
        ),
        migration_max_workers=migration_max_workers,
        migration_absolute_max_workers=migration_absolute_max_workers,
        migration_dynamic_chunks_enabled=_env_bool("MIGRATION_DYNAMIC_CHUNKS_ENABLED", True),
        migration_chunks_per_worker=_env_positive_int("MIGRATION_CHUNKS_PER_WORKER", 16),
        migration_parallel_min_rows=_env_positive_int(
            "MIGRATION_PARALLEL_MIN_ROWS",
            100000,
        ),
        validation_mode=_env_validation_mode("VALIDATION_MODE", "fast"),
        validation_timeout_seconds=_env_positive_int("VALIDATION_TIMEOUT_SECONDS", 600),
    )
