from app.config import TARGET_DATABASE, get_settings


def test_target_database_constant() -> None:
    assert TARGET_DATABASE == "oracle_migration_hazem"


def test_settings_load_defaults() -> None:
    settings = get_settings()
    assert settings.clickhouse_database == TARGET_DATABASE
    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 8000


def test_app_imports() -> None:
    from app.main import app

    assert app.title == "Oracle to ClickHouse Migration Engine"
