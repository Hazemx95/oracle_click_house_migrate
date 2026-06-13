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
    migration_batch_size: int = 100000
    migration_default_workers: int = 8
    oracle_arraysize: int = 100000
    oracle_prefetchrows: int = 100000
    clickhouse_insert_batch_size: int = 100000
    migration_parallel_min_rows: int = 100000


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    migration_batch_size = _env_positive_int("MIGRATION_BATCH_SIZE", 100000)
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
        migration_default_workers=_env_positive_int("MIGRATION_DEFAULT_WORKERS", 8),
        oracle_arraysize=_env_positive_int("ORACLE_ARRAYSIZE", migration_batch_size),
        oracle_prefetchrows=_env_positive_int("ORACLE_PREFETCHROWS", migration_batch_size),
        clickhouse_insert_batch_size=_env_positive_int(
            "CLICKHOUSE_INSERT_BATCH_SIZE",
            migration_batch_size,
        ),
        migration_parallel_min_rows=_env_positive_int(
            "MIGRATION_PARALLEL_MIN_ROWS",
            100000,
        ),
    )
