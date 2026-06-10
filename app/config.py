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


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
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
        migration_batch_size=int(os.getenv("MIGRATION_BATCH_SIZE", "100000")),
        migration_default_workers=int(os.getenv("MIGRATION_DEFAULT_WORKERS", "8")),
    )
