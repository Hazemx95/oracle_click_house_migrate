from datetime import datetime

from app.services import migration_service
from app.services.migration_service import compute_date_ranges, compute_numeric_ranges


def test_compute_numeric_ranges_are_contiguous_and_non_overlapping() -> None:
    ranges = compute_numeric_ranges(0, 100, 4)

    assert len(ranges) == 4
    assert ranges[0].start == 0
    assert ranges[-1].end == 100
    assert ranges[-1].inclusive_end is True
    for left, right in zip(ranges, ranges[1:]):
        assert left.end == right.start
        assert left.inclusive_end is False


def test_compute_numeric_ranges_collapses_equal_bounds_to_one_range() -> None:
    ranges = compute_numeric_ranges(7, 7, 8)

    assert len(ranges) == 1
    assert ranges[0].start == 7
    assert ranges[0].end == 7
    assert ranges[0].inclusive_end is True


def test_compute_numeric_ranges_clamps_workers_to_sixteen() -> None:
    ranges = compute_numeric_ranges(0, 160, 32)

    assert len(ranges) == 16


def test_compute_numeric_ranges_covers_all_null_partition_values() -> None:
    ranges = compute_numeric_ranges(None, None, 8)

    assert len(ranges) == 1
    assert ranges[0].start is None
    assert ranges[0].end is None
    assert ranges[0].include_nulls is True


def test_compute_date_ranges_are_contiguous_and_non_overlapping() -> None:
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 5)

    ranges = compute_date_ranges(start, end, 4)

    assert len(ranges) == 4
    assert ranges[0].start == start
    assert ranges[-1].end == end
    assert ranges[-1].inclusive_end is True
    for left, right in zip(ranges, ranges[1:]):
        assert left.end == right.start
        assert left.inclusive_end is False


def test_compute_date_ranges_collapses_equal_bounds_to_one_range() -> None:
    value = datetime(2026, 1, 1, 12, 30)

    ranges = compute_date_ranges(value, value, 8)

    assert len(ranges) == 1
    assert ranges[0].start == value
    assert ranges[0].end == value
    assert ranges[0].inclusive_end is True


def test_compute_date_ranges_covers_all_null_partition_values() -> None:
    ranges = compute_date_ranges(None, None, 8)

    assert len(ranges) == 1
    assert ranges[0].start is None
    assert ranges[0].end is None
    assert ranges[0].include_nulls is True


def test_range_where_clause_sends_all_null_slice_to_one_worker() -> None:
    partition_range = compute_numeric_ranges(None, None, 8)[0]

    where_clause = migration_service._range_where_clause("ID", partition_range)  # noqa: SLF001

    assert where_clause == '"ID" IS NULL'


def test_range_where_clause_includes_nulls_on_first_bounded_worker() -> None:
    partition_range = compute_numeric_ranges(1, 9, 2)[0]

    where_clause = migration_service._range_where_clause("ID", partition_range)  # noqa: SLF001

    assert where_clause == '("ID" IS NULL OR ("ID" >= :range_start AND "ID" < :range_end))'
