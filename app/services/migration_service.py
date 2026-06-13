from __future__ import annotations

from dataclasses import dataclass
from threading import Thread
from typing import Any

from app.config import TARGET_DATABASE, get_settings
from app.db import clickhouse_client, oracle_client
from app.services import ddl_mapper, job_service, metadata_service


@dataclass(frozen=True)
class InitialLoadRequest:
    source_schema: str
    source_table: str
    target_schema: str | None
    target_table: str
    partition_column: str | None
    workers: int
    batch_size: int
    target_database: str = TARGET_DATABASE


def _safe_error_message(exc: Exception) -> str:
    settings = get_settings()
    message = str(exc) or exc.__class__.__name__
    for secret in (settings.p5_qa_oracle_password, settings.clickhouse_pass):
        if secret:
            message = message.replace(secret, "***")
    return message


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _quote_oracle_identifier(identifier: str) -> str:
    ddl_mapper.quote_identifier(identifier)
    return f'"{identifier}"'


def _oracle_table_path(schema: str, table: str) -> str:
    return f"{_quote_oracle_identifier(schema)}.{_quote_oracle_identifier(table)}"


def _first_value(row: Any) -> Any:
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _column_names(columns: list[dict[str, Any]]) -> list[str]:
    return [str(column["column_name"]) for column in columns]


def _normalize_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if hasattr(value, "read"):
        return _normalize_cell(value.read())
    return value


def _normalize_batch(rows: list[Any]) -> list[tuple[Any, ...]]:
    normalized: list[tuple[Any, ...]] = []
    for row in rows:
        values = row.values() if isinstance(row, dict) else row
        normalized.append(tuple(_normalize_cell(value) for value in values))
    return normalized


def _count_source_rows(schema: str, table: str) -> int:
    sql = f"SELECT COUNT(*) FROM {_oracle_table_path(schema, table)}"
    rows = oracle_client.run_select(sql)
    if not rows:
        return 0
    return int(_first_value(rows[0]) or 0)


def _select_source_sql(schema: str, table: str, column_names: list[str]) -> str:
    projection = ", ".join(_quote_oracle_identifier(column) for column in column_names)
    return f"SELECT {projection} FROM {_oracle_table_path(schema, table)}"


def _build_request(
    source_schema: str,
    source_table: str,
    target_schema: str | None,
    target_table: str,
    partition_column: str | None,
    workers: int,
    batch_size: int | None,
    target_database: str,
) -> InitialLoadRequest:
    settings = get_settings()
    resolved_batch_size = batch_size or settings.migration_batch_size
    if resolved_batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    return InitialLoadRequest(
        source_schema=_clean(source_schema),
        source_table=_clean(source_table),
        target_schema=_clean(target_schema) or None,
        target_table=_clean(target_table),
        partition_column=_clean(partition_column) or None,
        # Phase 6 is intentionally single-threaded; Phase 7 owns worker fan-out.
        workers=1,
        batch_size=resolved_batch_size,
        target_database=target_database,
    )


def launch_initial_load(
    source_schema: str,
    source_table: str,
    target_schema: str | None,
    target_table: str,
    partition_column: str | None,
    workers: int,
    batch_size: int | None = None,
    target_database: str = TARGET_DATABASE,
) -> str:
    request = _build_request(
        source_schema,
        source_table,
        target_schema,
        target_table,
        partition_column,
        workers,
        batch_size,
        target_database,
    )
    display_target = (
        request.target_table
        if "__" in request.target_table
        else f"{request.target_schema or request.source_schema}__{request.target_table}"
    )
    job_id = job_service.create_job(
        source_schema=request.source_schema,
        source_table=request.source_table,
        target_database=request.target_database,
        target_schema=request.target_schema,
        target_table=display_target,
        partition_column=request.partition_column,
        worker_count=workers,
        batch_size=request.batch_size,
    )
    thread = Thread(target=run_initial_load, args=(job_id, request), daemon=True)
    thread.start()
    return job_id


def run_initial_load(job_id: str, request: InitialLoadRequest) -> None:
    clickhouse = None
    try:
        job_service.update_job(job_id, status=job_service.JobStatus.RUNNING)
        ddl_mapper.assert_target_database(request.target_database)
        if request.target_database != TARGET_DATABASE:
            raise ValueError(f"target database must be '{TARGET_DATABASE}'")

        if not metadata_service.schema_exists(request.source_schema):
            raise ValueError(f"source schema '{request.source_schema}' not found")
        if not metadata_service.table_exists(request.source_schema, request.source_table):
            raise ValueError(
                f"source table '{request.source_schema}.{request.source_table}' not found"
            )

        columns = metadata_service.list_columns(request.source_schema, request.source_table)
        if not columns:
            raise ValueError("source table has no columns")

        recreate = ddl_mapper.build_recreate_ddl(
            request.source_schema,
            request.source_table,
            columns,
            request.partition_column,
            request.target_database,
            request.target_table,
            request.target_schema,
        )
        target_table = str(recreate["target_table"])
        job_service.update_job(job_id, target_table=target_table)

        clickhouse_client.execute_ddl(str(recreate["drop_ddl"]))
        clickhouse_client.execute_ddl(str(recreate["create_ddl"]))

        total_rows = _count_source_rows(request.source_schema, request.source_table)
        job_service.update_job(job_id, total_rows=total_rows, remaining_rows=total_rows)
        if total_rows == 0:
            job_service.update_job(
                job_id,
                status=job_service.JobStatus.SUCCESS,
                progress_percent=100.0,
            )
            return

        column_names = _column_names(columns)
        select_sql = _select_source_sql(request.source_schema, request.source_table, column_names)
        clickhouse = clickhouse_client.get_client()

        processed_rows = 0
        inserted_rows = 0
        batches_completed = 0

        with oracle_client.get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.arraysize = request.batch_size
                cursor.prefetchrows = request.batch_size
                cursor.execute(select_sql)

                while True:
                    batch = cursor.fetchmany(request.batch_size)
                    if not batch:
                        break

                    current_batch = batches_completed + 1
                    normalized_batch = _normalize_batch(batch)
                    inserted = clickhouse_client.insert_rows(
                        target_table,
                        normalized_batch,
                        column_names,
                        request.target_database,
                        clickhouse,
                    )
                    batch_rows = len(batch)
                    processed_rows += batch_rows
                    inserted_rows += inserted
                    batches_completed = current_batch
                    job_service.update_job(
                        job_id,
                        processed_rows=processed_rows,
                        inserted_rows=inserted_rows,
                        batches_completed=batches_completed,
                        current_batch_number=current_batch,
                    )

        job_service.update_job(
            job_id,
            status=job_service.JobStatus.SUCCESS,
            processed_rows=processed_rows,
            inserted_rows=inserted_rows,
            remaining_rows=0,
            progress_percent=100.0,
        )
    except Exception as exc:  # noqa: BLE001 - job surfaces a credential-free failure
        job_service.update_job(
            job_id,
            status=job_service.JobStatus.FAILED,
            error_message=_safe_error_message(exc),
        )
    finally:
        if clickhouse is not None and hasattr(clickhouse, "close"):
            clickhouse.close()
