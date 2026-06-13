from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import date, datetime, time as datetime_time
from decimal import Decimal
from threading import Thread
from time import perf_counter
from typing import Any, Iterator

from app.config import TARGET_DATABASE, get_settings
from app.db import clickhouse_client, oracle_client
from app.services import ddl_mapper, job_service, metadata_service

MAX_WORKERS = 16
PARALLEL_MODES = {"auto", "numeric_range", "date_range", "hash"}
MODE_TO_PARTITION = {
    "single": "single",
    "numeric_range": "numeric",
    "date_range": "date",
    "hash": "hash",
}
SMALL_TABLE_WARNING = "Small table detected; single-thread mode may be faster than parallel mode."


@dataclass(frozen=True)
class InitialLoadRequest:
    source_schema: str
    source_table: str
    target_schema: str | None
    target_table: str
    partition_column: str | None
    workers: int
    batch_size: int
    requested_parallel_mode: str = "auto"
    resolved_parallel_mode: str = "single"
    partition_mode: str = "single"
    warning_message: str | None = None
    partition_column_scale: int | None = None
    target_database: str = TARGET_DATABASE


@dataclass(frozen=True)
class PartitionRange:
    worker_id: int
    start: Any
    end: Any
    inclusive_end: bool
    include_nulls: bool = False


def _safe_error_message(exc: Exception, step: str | None = None) -> str:
    settings = get_settings()
    message = str(exc) or exc.__class__.__name__
    for secret in (settings.p5_qa_oracle_password, settings.clickhouse_pass):
        if secret:
            message = message.replace(secret, "***")
    if step and not message.startswith(f"{step}:"):
        message = f"{step}: {message}"
    return message


def _record_timing(job_id: str, field: str, started_at: float) -> None:
    job_service.add_diagnostic_timing(job_id, field, perf_counter() - started_at)


def _chunk_rows(rows: list[Any], chunk_size: int) -> Iterator[list[Any]]:
    for index in range(0, len(rows), chunk_size):
        yield rows[index : index + chunk_size]


def _clean(value: str | None) -> str:
    return (value or "").strip()


def clamp_worker_count(workers: int | None) -> int:
    settings = get_settings()
    requested = workers if workers is not None else settings.migration_default_workers
    if requested <= 0:
        raise ValueError("workers must be greater than zero")
    return min(requested, MAX_WORKERS)


def _normalize_data_type(data_type: Any) -> str:
    return " ".join(str(data_type or "").strip().upper().split())


def _is_number_type(data_type: Any) -> bool:
    return _normalize_data_type(data_type) == "NUMBER"


def _is_date_type(data_type: Any) -> bool:
    normalized = _normalize_data_type(data_type)
    return normalized == "DATE" or normalized.startswith("TIMESTAMP")


def _find_column(
    partition_column: str | None,
    column_metadata: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not partition_column:
        return None
    for column in column_metadata:
        if str(column.get("column_name") or "") == partition_column:
            return column
    return None


def resolve_parallel_mode(
    parallel_mode: str | None,
    partition_column: str | None,
    column_metadata: list[dict[str, Any]],
    workers: int,
) -> dict[str, object]:
    requested_mode = _clean(parallel_mode) or "auto"
    if requested_mode not in PARALLEL_MODES:
        raise ValueError(
            "parallel_mode must be one of auto, numeric_range, date_range, hash"
        )

    worker_count = clamp_worker_count(workers)
    column_name = _clean(partition_column) or None
    column = _find_column(column_name, column_metadata)
    if column_name and column is None:
        raise ValueError(f"partition/hash column '{column_name}' not found")
    if requested_mode != "auto" and column is None:
        raise ValueError(f"{requested_mode} requires a selected partition/hash column")
    if worker_count == 1 and requested_mode == "auto" and column is None:
        return {
            "requested_parallel_mode": requested_mode,
            "resolved_parallel_mode": "single",
            "partition_mode": "single",
            "worker_count": 1,
            "warning_message": "Parallel mode only takes effect when workers is greater than 1.",
        }
    if column is None:
        raise ValueError("a partition/hash column is required for parallel execution")

    data_type = _normalize_data_type(column.get("data_type"))
    if requested_mode == "auto":
        if _is_number_type(data_type):
            resolved_mode = "numeric_range"
        elif _is_date_type(data_type):
            resolved_mode = "date_range"
        else:
            resolved_mode = "hash"
    elif requested_mode == "numeric_range":
        if not _is_number_type(data_type):
            raise ValueError(
                f"numeric_range requires a NUMBER column; '{column_name}' is {data_type}"
            )
        resolved_mode = requested_mode
    elif requested_mode == "date_range":
        if not _is_date_type(data_type):
            raise ValueError(
                f"date_range requires a DATE or TIMESTAMP column; '{column_name}' is {data_type}"
            )
        resolved_mode = requested_mode
    else:
        resolved_mode = "hash"

    if worker_count == 1:
        return {
            "requested_parallel_mode": requested_mode,
            "resolved_parallel_mode": "single",
            "partition_mode": "single",
            "worker_count": 1,
            "warning_message": "Parallel mode only takes effect when workers is greater than 1.",
        }

    return {
        "requested_parallel_mode": requested_mode,
        "resolved_parallel_mode": resolved_mode,
        "partition_mode": MODE_TO_PARTITION[resolved_mode],
        "worker_count": worker_count,
        "warning_message": None,
    }


def _quote_oracle_identifier(identifier: str) -> str:
    ddl_mapper.quote_identifier(identifier)
    return f'"{identifier}"'


def _oracle_table_path(schema: str, table: str) -> str:
    return f"{_quote_oracle_identifier(schema)}.{_quote_oracle_identifier(table)}"


def _first_value(row: Any) -> Any:
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, dict):
        return row[key] if key in row else list(row.values())[index]
    return row[index]


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _bound_for_sql(value: Decimal) -> int | float | Decimal:
    if value == value.to_integral_value():
        return int(value)
    return value


def compute_numeric_ranges(
    min_value: Any,
    max_value: Any,
    workers: int,
    integer_boundaries: bool = False,
) -> list[PartitionRange]:
    worker_count = clamp_worker_count(workers)
    if min_value is None or max_value is None:
        return [
            PartitionRange(
                worker_id=0,
                start=None,
                end=None,
                inclusive_end=False,
                include_nulls=True,
            )
        ]

    start_value = _to_decimal(min_value)
    end_value = _to_decimal(max_value)
    if start_value > end_value:
        raise ValueError("numeric range minimum cannot be greater than maximum")
    if start_value == end_value:
        return [
            PartitionRange(
                worker_id=0,
                start=_bound_for_sql(start_value),
                end=_bound_for_sql(end_value),
                inclusive_end=True,
                include_nulls=True,
            )
        ]

    if integer_boundaries:
        start_int = int(start_value)
        end_int = int(end_value)
        value_count = end_int - start_int + 1
        range_count = min(worker_count, value_count)
        base_width = value_count // range_count
        remainder = value_count % range_count
        ranges: list[PartitionRange] = []
        current = start_int
        for worker_id in range(range_count):
            width = base_width + (1 if worker_id < remainder else 0)
            is_final = worker_id == range_count - 1
            next_value = end_int if is_final else current + width
            ranges.append(
                PartitionRange(
                    worker_id=worker_id,
                    start=current,
                    end=next_value,
                    inclusive_end=is_final,
                    include_nulls=worker_id == 0,
                )
            )
            current = next_value
        return ranges

    step = (end_value - start_value) / Decimal(worker_count)
    ranges: list[PartitionRange] = []
    current = start_value
    for worker_id in range(worker_count):
        next_value = (
            end_value
            if worker_id == worker_count - 1
            else start_value + step * Decimal(worker_id + 1)
        )
        ranges.append(
            PartitionRange(
                worker_id=worker_id,
                start=_bound_for_sql(current),
                end=_bound_for_sql(next_value),
                inclusive_end=worker_id == worker_count - 1,
                include_nulls=worker_id == 0,
            )
        )
        current = next_value
    return ranges


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime_time.min)
    raise ValueError("date range bounds must be date or datetime values")


def compute_date_ranges(min_ts: Any, max_ts: Any, workers: int) -> list[PartitionRange]:
    worker_count = clamp_worker_count(workers)
    if min_ts is None or max_ts is None:
        return [
            PartitionRange(
                worker_id=0,
                start=None,
                end=None,
                inclusive_end=False,
                include_nulls=True,
            )
        ]

    start_ts = _as_datetime(min_ts)
    end_ts = _as_datetime(max_ts)
    if start_ts > end_ts:
        raise ValueError("date range minimum cannot be greater than maximum")
    if start_ts == end_ts:
        return [
            PartitionRange(
                worker_id=0,
                start=start_ts,
                end=end_ts,
                inclusive_end=True,
                include_nulls=True,
            )
        ]

    span = end_ts - start_ts
    step = span / worker_count
    ranges: list[PartitionRange] = []
    current = start_ts
    for worker_id in range(worker_count):
        next_ts = (
            end_ts if worker_id == worker_count - 1 else start_ts + step * (worker_id + 1)
        )
        ranges.append(
            PartitionRange(
                worker_id=worker_id,
                start=current,
                end=next_ts,
                inclusive_end=worker_id == worker_count - 1,
                include_nulls=worker_id == 0,
            )
        )
        current = next_ts
    return ranges


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


def _ensure_source_exists(source_schema: str, source_table: str) -> None:
    if not metadata_service.schema_exists(source_schema):
        raise ValueError(f"source schema '{source_schema}' not found")
    if not metadata_service.table_exists(source_schema, source_table):
        raise ValueError(f"source table '{source_schema}.{source_table}' not found")


def _oracle_row_count(source_schema: str, source_table: str) -> int:
    sql = f"SELECT COUNT(*) FROM {_oracle_table_path(source_schema, source_table)}"
    rows = oracle_client.run_select(sql)
    if not rows:
        return 0
    return int(_first_value(rows[0]) or 0)


def count_source(schema: str, table: str) -> int:
    _ensure_source_exists(schema, table)
    return _oracle_row_count(schema, table)


def get_oracle_row_count(source_schema: str, source_table: str) -> int:
    return count_source(source_schema, source_table)


def count_target(target_table: str, target_database: str = TARGET_DATABASE) -> int:
    return clickhouse_client.count_rows(target_table, target_database)


def get_clickhouse_row_count(target_database: str, target_table: str) -> int:
    return count_target(target_table, target_database)


def _row_count_mismatch_message(source_count: int, target_count: int) -> str:
    return (
        "Row count mismatch: Oracle source has "
        f"{source_count} rows, ClickHouse target has {target_count} rows."
    )


def _mark_validation_mismatch(
    job_id: str,
    message: str,
    source_count: int,
    target_count: int,
) -> None:
    job_service.update_job(
        job_id,
        status=job_service.JobStatus.FAILED,
        error_message=message,
        source_row_count=source_count,
        target_row_count=target_count,
        count_match=False,
        validation_status=job_service.ValidationStatus.FAILED.value,
        validation_error_message=message,
    )


def _mark_validation_unavailable(
    job_id: str,
    message: str,
    source_count: int | None = None,
    target_count: int | None = None,
) -> None:
    job_service.update_job(
        job_id,
        status=job_service.JobStatus.SUCCESS,
        error_message=None,
        source_row_count=source_count,
        target_row_count=target_count,
        count_match=None,
        validation_status=job_service.ValidationStatus.FAILED.value,
        validation_error_message=message,
    )


def _mark_validation_success(
    job_id: str,
    source_count: int,
    target_count: int,
) -> None:
    job_service.update_job(
        job_id,
        status=job_service.JobStatus.SUCCESS,
        source_row_count=source_count,
        target_row_count=target_count,
        count_match=True,
        validation_status=job_service.ValidationStatus.SUCCESS.value,
        validation_error_message=None,
    )


def run_validation(job_id: str) -> None:
    validation_started_at = perf_counter()
    job = job_service.get_job(job_id)
    if job is None:
        raise KeyError(f"job '{job_id}' not found")

    job_service.update_job(
        job_id,
        validation_status=job_service.ValidationStatus.RUNNING.value,
        validation_error_message=None,
    )
    source_count: int | None = None
    target_count: int | None = None
    try:
        source_count = count_source(
            str(job.get("source_schema") or ""),
            str(job.get("source_table") or ""),
        )
        target_count = count_target(
            str(job.get("target_table") or ""),
            str(job.get("target_database") or TARGET_DATABASE),
        )
        count_match = source_count == target_count
        if count_match:
            _mark_validation_success(job_id, source_count, target_count)
            return

        message = _row_count_mismatch_message(source_count, target_count)
        _mark_validation_mismatch(job_id, message, source_count, target_count)
    except Exception as exc:  # noqa: BLE001 - validation failure is stored on the job
        message = _safe_error_message(exc, "validation")
        _mark_validation_unavailable(job_id, message, source_count, target_count)
    finally:
        _record_timing(job_id, "validation_duration_seconds", validation_started_at)


def _select_source_sql(schema: str, table: str, column_names: list[str]) -> str:
    projection = ", ".join(_quote_oracle_identifier(column) for column in column_names)
    return f"SELECT {projection} FROM {_oracle_table_path(schema, table)}"


def _select_partition_sql(
    schema: str,
    table: str,
    column_names: list[str],
    where_clause: str | None = None,
) -> str:
    sql = _select_source_sql(schema, table, column_names)
    if where_clause:
        return f"{sql} WHERE {where_clause}"
    return sql


def _min_max_values(schema: str, table: str, partition_column: str) -> tuple[Any, Any]:
    column = _quote_oracle_identifier(partition_column)
    sql = f"SELECT MIN({column}), MAX({column}) FROM {_oracle_table_path(schema, table)}"
    rows = oracle_client.run_select(sql)
    if not rows:
        return None, None
    return _row_value(rows[0], 0, "MIN"), _row_value(rows[0], 1, "MAX")


def _serialize_bound(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _prepare_recreate(
    job_id: str,
    request: InitialLoadRequest,
) -> tuple[list[dict[str, Any]], list[str], str]:
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

    started_at = perf_counter()
    try:
        clickhouse_client.execute_ddl(str(recreate["drop_ddl"]))
        clickhouse_client.execute_ddl(str(recreate["create_ddl"]))
    finally:
        _record_timing(job_id, "ddl_duration_seconds", started_at)
    return columns, _column_names(columns), target_table


def _build_request(
    source_schema: str,
    source_table: str,
    target_schema: str | None,
    target_table: str,
    partition_column: str | None,
    workers: int | None,
    batch_size: int | None,
    target_database: str,
    parallel_mode: str | None,
    column_metadata: list[dict[str, Any]],
) -> InitialLoadRequest:
    settings = get_settings()
    resolved_batch_size = batch_size or settings.migration_batch_size
    if resolved_batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    mode_resolution = resolve_parallel_mode(
        parallel_mode,
        _clean(partition_column) or None,
        column_metadata,
        clamp_worker_count(workers),
    )
    partition_metadata = _find_column(_clean(partition_column) or None, column_metadata)
    partition_column_scale = None
    if partition_metadata is not None and partition_metadata.get("data_scale") is not None:
        partition_column_scale = int(partition_metadata["data_scale"])

    return InitialLoadRequest(
        source_schema=_clean(source_schema),
        source_table=_clean(source_table),
        target_schema=_clean(target_schema) or None,
        target_table=_clean(target_table),
        partition_column=_clean(partition_column) or None,
        workers=int(mode_resolution["worker_count"]),
        batch_size=resolved_batch_size,
        requested_parallel_mode=str(mode_resolution["requested_parallel_mode"]),
        resolved_parallel_mode=str(mode_resolution["resolved_parallel_mode"]),
        partition_mode=str(mode_resolution["partition_mode"]),
        warning_message=mode_resolution["warning_message"]
        if isinstance(mode_resolution["warning_message"], str)
        else None,
        partition_column_scale=partition_column_scale,
        target_database=target_database,
    )


def apply_small_table_rule(
    request: InitialLoadRequest,
    total_rows: int,
) -> tuple[InitialLoadRequest, str | None]:
    settings = get_settings()
    if total_rows >= settings.migration_parallel_min_rows:
        return request, None
    if request.requested_parallel_mode == "auto":
        return (
            replace(
                request,
                workers=1,
                resolved_parallel_mode="single",
                partition_mode="single",
            ),
            SMALL_TABLE_WARNING,
        )
    return request, SMALL_TABLE_WARNING


def launch_initial_load(
    source_schema: str,
    source_table: str,
    target_schema: str | None,
    target_table: str,
    partition_column: str | None,
    workers: int | None,
    batch_size: int | None = None,
    target_database: str = TARGET_DATABASE,
    parallel_mode: str | None = "auto",
) -> str:
    cleaned_schema = _clean(source_schema)
    cleaned_table = _clean(source_table)
    if not metadata_service.schema_exists(cleaned_schema):
        raise ValueError(f"source schema '{cleaned_schema}' not found")
    if not metadata_service.table_exists(cleaned_schema, cleaned_table):
        raise ValueError(f"source table '{cleaned_schema}.{cleaned_table}' not found")
    columns = metadata_service.list_columns(cleaned_schema, cleaned_table)
    if not columns:
        raise ValueError("source table has no columns")

    request = _build_request(
        cleaned_schema,
        cleaned_table,
        target_schema,
        target_table,
        partition_column,
        workers,
        batch_size,
        target_database,
        parallel_mode,
        columns,
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
        partition_mode=request.partition_mode,
        worker_count=request.workers,
        requested_parallel_mode=request.requested_parallel_mode,
        resolved_parallel_mode=request.resolved_parallel_mode,
        warning_message=request.warning_message,
        batch_size=request.batch_size,
    )
    thread = Thread(target=run_initial_load, args=(job_id, request), daemon=True)
    thread.start()
    return job_id


def _add_metadata_warnings(job_id: str, request: InitialLoadRequest) -> None:
    try:
        heavy_columns = metadata_service.detect_heavy_columns(
            request.source_schema,
            request.source_table,
        )
        if heavy_columns:
            names = ", ".join(
                f"{column.get('column_name')} ({column.get('data_type')})"
                for column in heavy_columns
            )
            job_service.add_warning(
                job_id,
                f"Heavy LOB columns detected ({names}) - per-LOB reads may dominate fetch time.",
            )
    except Exception as exc:  # noqa: BLE001 - diagnostics warnings must not block migration
        job_service.add_warning(
            job_id,
            f"Unable to evaluate heavy column warning: {_safe_error_message(exc)}",
        )

    if request.partition_mode not in {"numeric", "date"} or not request.partition_column:
        return
    try:
        if not metadata_service.is_column_indexed(
            request.source_schema,
            request.source_table,
            request.partition_column,
        ):
            job_service.add_warning(
                job_id,
                "Range mode on a non-indexed column may be slow.",
            )
    except Exception as exc:  # noqa: BLE001 - diagnostics warnings must not block migration
        job_service.add_warning(
            job_id,
            f"Unable to evaluate range-column index warning: {_safe_error_message(exc)}",
        )


def _copy_batches(
    *,
    select_sql: str,
    binds: dict[str, Any] | None,
    request: InitialLoadRequest,
    target_table: str,
    column_names: list[str],
    job_id: str,
    worker_id: int | None = None,
) -> tuple[int, int, int]:
    settings = get_settings()
    clickhouse = None
    processed_rows = 0
    inserted_rows = 0
    batches_completed = 0
    step = "oracle_connect"
    worker_timings = {
        "oracle_execute_duration_seconds": 0.0,
        "oracle_fetch_duration_seconds": 0.0,
        "row_conversion_duration_seconds": 0.0,
        "clickhouse_insert_duration_seconds": 0.0,
        "batches_completed": 0,
        "average_seconds_per_batch": 0.0,
    }
    try:
        clickhouse = clickhouse_client.get_client()
        with oracle_client.get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.arraysize = settings.oracle_arraysize
                cursor.prefetchrows = settings.oracle_prefetchrows
                step = "oracle_execute"
                started_at = perf_counter()
                cursor.execute(select_sql, binds or {})
                elapsed = perf_counter() - started_at
                worker_timings["oracle_execute_duration_seconds"] += elapsed
                job_service.add_diagnostic_timing(
                    job_id,
                    "oracle_execute_duration_seconds",
                    elapsed,
                )

                while True:
                    step = "oracle_fetch"
                    started_at = perf_counter()
                    batch = cursor.fetchmany(request.batch_size)
                    elapsed = perf_counter() - started_at
                    worker_timings["oracle_fetch_duration_seconds"] += elapsed
                    job_service.add_diagnostic_timing(
                        job_id,
                        "oracle_fetch_duration_seconds",
                        elapsed,
                    )
                    if not batch:
                        break

                    step = "row_conversion"
                    started_at = perf_counter()
                    normalized_batch = _normalize_batch(batch)
                    elapsed = perf_counter() - started_at
                    worker_timings["row_conversion_duration_seconds"] += elapsed
                    job_service.add_diagnostic_timing(
                        job_id,
                        "row_conversion_duration_seconds",
                        elapsed,
                    )

                    inserted = 0
                    for insert_chunk in _chunk_rows(
                        normalized_batch,
                        settings.clickhouse_insert_batch_size,
                    ):
                        step = "clickhouse_insert"
                        started_at = perf_counter()
                        inserted += clickhouse_client.insert_rows(
                            target_table,
                            insert_chunk,
                            column_names,
                            request.target_database,
                            clickhouse,
                        )
                        elapsed = perf_counter() - started_at
                        worker_timings["clickhouse_insert_duration_seconds"] += elapsed
                        job_service.add_diagnostic_timing(
                            job_id,
                            "clickhouse_insert_duration_seconds",
                            elapsed,
                        )
                    processed_rows += len(batch)
                    inserted_rows += inserted
                    batches_completed += 1
                    worker_timings["batches_completed"] = batches_completed
                    copy_seconds = sum(
                        float(worker_timings[key])
                        for key in (
                            "oracle_execute_duration_seconds",
                            "oracle_fetch_duration_seconds",
                            "row_conversion_duration_seconds",
                            "clickhouse_insert_duration_seconds",
                        )
                    )
                    worker_timings["average_seconds_per_batch"] = (
                        round(copy_seconds / batches_completed, 3)
                        if batches_completed
                        else 0.0
                    )
                    if worker_id is None:
                        job_service.update_job(
                            job_id,
                            processed_rows=processed_rows,
                            inserted_rows=inserted_rows,
                            batches_completed=batches_completed,
                            current_batch_number=batches_completed,
                        )
                    else:
                        job_service.update_worker(
                            job_id,
                            worker_id,
                            processed_rows=processed_rows,
                            inserted_rows=inserted_rows,
                            batches_completed=batches_completed,
                            timings=dict(worker_timings),
                        )
        return processed_rows, inserted_rows, batches_completed
    except Exception as exc:  # noqa: BLE001 - caller stores credential-free step failure
        raise RuntimeError(_safe_error_message(exc, step)) from exc
    finally:
        if worker_id is not None:
            job_service.set_worker_diagnostics(job_id, worker_id, dict(worker_timings))
        if clickhouse is not None and hasattr(clickhouse, "close"):
            clickhouse.close()


def _range_where_clause(partition_column: str, partition_range: PartitionRange) -> str:
    column = _quote_oracle_identifier(partition_column)
    if partition_range.start is None or partition_range.end is None:
        if partition_range.include_nulls:
            return f"{column} IS NULL"
        raise ValueError("range bounds are required for range partition workers")
    end_operator = "<=" if partition_range.inclusive_end else "<"
    bounded = f"{column} >= :range_start AND {column} {end_operator} :range_end"
    if partition_range.include_nulls:
        return f"({column} IS NULL OR ({bounded}))"
    return bounded


def _worker_base(
    worker_id: int,
    request: InitialLoadRequest,
    range_start: Any = None,
    range_end: Any = None,
) -> dict[str, object]:
    return {
        "worker_id": worker_id,
        "partition_mode": request.partition_mode,
        "resolved_parallel_mode": request.resolved_parallel_mode,
        "partition_column": request.partition_column,
        "range_start": _serialize_bound(range_start),
        "range_end": _serialize_bound(range_end),
        "status": job_service.JobStatus.PENDING.value,
        "processed_rows": 0,
        "inserted_rows": 0,
        "batches_completed": 0,
        "rows_per_second": 0.0,
        "error_message": None,
    }


def _build_worker_ranges(request: InitialLoadRequest) -> list[PartitionRange]:
    if request.partition_mode == "hash":
        return [
            PartitionRange(worker_id=worker_id, start=None, end=None, inclusive_end=False)
            for worker_id in range(request.workers)
        ]

    if not request.partition_column:
        raise ValueError("partition/hash column is required for parallel execution")
    min_value, max_value = _min_max_values(
        request.source_schema,
        request.source_table,
        request.partition_column,
    )
    if request.partition_mode == "numeric":
        return compute_numeric_ranges(
            min_value,
            max_value,
            request.workers,
            integer_boundaries=request.partition_column_scale == 0,
        )
    if request.partition_mode == "date":
        return compute_date_ranges(min_value, max_value, request.workers)
    raise ValueError(f"unsupported partition mode '{request.partition_mode}'")


def _run_worker(
    job_id: str,
    request: InitialLoadRequest,
    target_table: str,
    column_names: list[str],
    partition_range: PartitionRange,
) -> None:
    worker_id = partition_range.worker_id
    job_service.update_worker(job_id, worker_id, status=job_service.JobStatus.RUNNING)
    try:
        binds: dict[str, Any] = {}
        if request.partition_mode == "hash":
            if not request.partition_column:
                raise ValueError("hash mode requires a partition/hash column")
            column = _quote_oracle_identifier(request.partition_column)
            where_clause = f"MOD(NVL(ORA_HASH({column}), 0), :workers) = :worker_id"
            binds = {"workers": request.workers, "worker_id": worker_id}
        else:
            if not request.partition_column:
                raise ValueError("range mode requires a partition/hash column")
            where_clause = _range_where_clause(request.partition_column, partition_range)
            binds = {"range_start": partition_range.start, "range_end": partition_range.end}

        select_sql = _select_partition_sql(
            request.source_schema,
            request.source_table,
            column_names,
            where_clause,
        )
        _copy_batches(
            select_sql=select_sql,
            binds=binds,
            request=request,
            target_table=target_table,
            column_names=column_names,
            job_id=job_id,
            worker_id=worker_id,
        )
        job_service.update_worker(job_id, worker_id, status=job_service.JobStatus.SUCCESS)
    except Exception as exc:  # noqa: BLE001 - worker error is surfaced on the job
        message = _safe_error_message(exc)
        job_service.update_worker(
            job_id,
            worker_id,
            status=job_service.JobStatus.FAILED,
            error_message=message,
        )
        raise RuntimeError(f"worker {worker_id} failed: {message}") from exc


def run_parallel(
    job_id: str,
    request: InitialLoadRequest,
    target_table: str,
    column_names: list[str],
) -> None:
    started_at = perf_counter()
    try:
        ranges = _build_worker_ranges(request)
    finally:
        if request.partition_mode in {"numeric", "date"}:
            _record_timing(job_id, "range_discovery_duration_seconds", started_at)
    if not ranges:
        job_service.set_workers(job_id, [])
        return

    workers = [
        _worker_base(
            partition_range.worker_id,
            request,
            partition_range.start,
            partition_range.end,
        )
        for partition_range in ranges
    ]
    job_service.set_workers(job_id, workers)

    with ThreadPoolExecutor(max_workers=min(request.workers, len(ranges))) as executor:
        futures = [
            executor.submit(_run_worker, job_id, request, target_table, column_names, item)
            for item in ranges
        ]
        errors: list[str] = []
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001 - collect all completed worker errors
                errors.append(_safe_error_message(exc))
        if errors:
            raise RuntimeError(errors[0])


def run_initial_load(job_id: str, request: InitialLoadRequest) -> None:
    try:
        job_service.update_job(job_id, status=job_service.JobStatus.RUNNING)
        _ensure_source_exists(request.source_schema, request.source_table)
        if request.warning_message:
            job_service.add_warning(job_id, request.warning_message)
        _add_metadata_warnings(job_id, request)
        count_started_at = perf_counter()
        try:
            total_rows = _oracle_row_count(
                request.source_schema,
                request.source_table,
            )
        finally:
            _record_timing(job_id, "oracle_count_duration_seconds", count_started_at)
        request, small_table_warning = apply_small_table_rule(request, total_rows)
        if small_table_warning:
            job_service.add_warning(job_id, small_table_warning)
            job_service.update_job(
                job_id,
                worker_count=request.workers,
                resolved_parallel_mode=request.resolved_parallel_mode,
                partition_mode=request.partition_mode,
            )

        _columns, column_names, target_table = _prepare_recreate(job_id, request)
        job_service.update_job(job_id, total_rows=total_rows, remaining_rows=total_rows)
        if total_rows == 0:
            run_validation(job_id)
            return

        if request.resolved_parallel_mode == "single":
            select_sql = _select_source_sql(
                request.source_schema,
                request.source_table,
                column_names,
            )
            processed_rows, inserted_rows, _batches_completed = _copy_batches(
                select_sql=select_sql,
                binds=None,
                request=request,
                target_table=target_table,
                column_names=column_names,
                job_id=job_id,
            )
        else:
            run_parallel(job_id, request, target_table, column_names)
            job = job_service.get_job(job_id) or {}
            processed_rows = int(job.get("processed_rows") or 0)
            inserted_rows = int(job.get("inserted_rows") or 0)

        job_service.update_job(
            job_id,
            processed_rows=processed_rows,
            inserted_rows=inserted_rows,
            remaining_rows=0,
            progress_percent=100.0,
        )
        run_validation(job_id)
    except Exception as exc:  # noqa: BLE001 - job surfaces a credential-free failure
        job_service.update_job(
            job_id,
            status=job_service.JobStatus.FAILED,
            error_message=_safe_error_message(exc),
        )
