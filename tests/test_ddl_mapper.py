import pytest

from app.config import TARGET_DATABASE
from app.services import ddl_mapper


def col(
    name: str,
    data_type: str,
    precision=None,  # type: ignore[no-untyped-def]
    scale=None,  # type: ignore[no-untyped-def]
    nullable: str = "Y",
) -> dict[str, object]:
    return {
        "column_name": name,
        "data_type": data_type,
        "data_length": None,
        "data_precision": precision,
        "data_scale": scale,
        "nullable": nullable,
        "char_length": None,
        "char_used": None,
    }


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        (col("ID", "NUMBER", 18, 0), "Nullable(Int64)"),
        (col("BIG_ID", "NUMBER", 19, 0), "Nullable(Decimal(19,0))"),
        (col("MAX_DEC", "NUMBER", 76, 0), "Nullable(Decimal(76,0))"),
        (col("AMOUNT", "NUMBER", 12, 2), "Nullable(Decimal(12,2))"),
        (col("UNKNOWN_NUM", "NUMBER"), "Nullable(Float64)"),
        (col("RATIO", "FLOAT"), "Nullable(Float64)"),
        (col("F32", "BINARY_FLOAT"), "Nullable(Float32)"),
        (col("F64", "BINARY_DOUBLE"), "Nullable(Float64)"),
        (col("TXT", "VARCHAR2"), "Nullable(String)"),
        (col("NTXT", "NVARCHAR2"), "Nullable(String)"),
        (col("CHR", "CHAR"), "Nullable(String)"),
        (col("NCHR", "NCHAR"), "Nullable(String)"),
        (col("DOC", "CLOB"), "Nullable(String)"),
        (col("NDOC", "NCLOB"), "Nullable(String)"),
        (col("D", "DATE"), "Nullable(DateTime)"),
        (col("TS", "TIMESTAMP"), "Nullable(DateTime64(6))"),
        (col("TS6", "TIMESTAMP(6)"), "Nullable(DateTime64(6))"),
        (col("TSTZ", "TIMESTAMP WITH TIME ZONE"), "Nullable(DateTime64(6))"),
        (col("TSLTZ", "TIMESTAMP(6) WITH LOCAL TIME ZONE"), "Nullable(DateTime64(6))"),
        (col("RAW_DATA", "RAW"), "Nullable(String)"),
        (col("BLOB_DATA", "BLOB"), "Nullable(String)"),
    ],
)
def test_map_oracle_type(column: dict[str, object], expected: str) -> None:
    assert ddl_mapper.map_oracle_type(column) == expected


def test_unsupported_type_falls_back_with_warning() -> None:
    column_defs, warnings = ddl_mapper.map_columns([col("GEOM", "SDO_GEOMETRY")])

    assert column_defs == ["`GEOM` Nullable(String)"]
    assert warnings == [
        {
            "column": "GEOM",
            "oracle_type": "SDO_GEOMETRY",
            "mapped_to": "Nullable(String)",
        }
    ]


def test_number_scale_greater_than_precision_falls_back_with_warning() -> None:
    column_defs, warnings = ddl_mapper.map_columns([col("ODD_NUM", "NUMBER", 3, 5)])

    assert column_defs == ["`ODD_NUM` Nullable(String)"]
    assert warnings == [
        {
            "column": "ODD_NUM",
            "oracle_type": "NUMBER",
            "mapped_to": "Nullable(String)",
        }
    ]


@pytest.mark.parametrize("unsafe", ["", "bad-name", "has space", "a`b", "1starts", "line\nbreak"])
def test_quote_identifier_rejects_unsafe_identifiers(unsafe: str) -> None:
    with pytest.raises(ValueError):
        ddl_mapper.quote_identifier(unsafe)


def test_quote_identifier_quotes_safe_identifier() -> None:
    assert ddl_mapper.quote_identifier("CM__COMPONENT") == "`CM__COMPONENT`"


def test_safe_target_name_uses_schema_table_prefix() -> None:
    assert ddl_mapper.safe_target_name("CM", "COMPONENT") == "CM__COMPONENT"


def test_resolve_target_name_supports_safe_custom_target_parts() -> None:
    assert ddl_mapper.resolve_target_name("CM", "COMPONENT", "CUSTOM") == "CM__CUSTOM"
    assert (
        ddl_mapper.resolve_target_name("CM", "COMPONENT", "CUSTOM", "DST")
        == "DST__CUSTOM"
    )
    assert ddl_mapper.resolve_target_name("CM", "COMPONENT", "CM__COMPONENT") == "CM__COMPONENT"


def test_build_recreate_ddl_generates_drop_then_create_without_if_not_exists() -> None:
    result = ddl_mapper.build_recreate_ddl(
        "CM",
        "COMPONENT",
        [col("ID", "NUMBER", 10, 0, "N"), col("NAME", "VARCHAR2")],
        order_by="ID",
    )

    assert result["drop_ddl"] == "DROP TABLE IF EXISTS `oracle_migration_hazem`.`CM__COMPONENT`"
    assert result["create_ddl"].startswith(
        "CREATE TABLE `oracle_migration_hazem`.`CM__COMPONENT` ("
    )
    assert "IF NOT EXISTS" not in result["create_ddl"]
    assert "`ID` Int64" in result["create_ddl"]
    assert "`NAME` Nullable(String)" in result["create_ddl"]
    assert result["create_ddl"].endswith("ENGINE = MergeTree ORDER BY `ID`")
    assert result["warnings"] == []


def test_order_by_nullable_column_falls_back_to_tuple() -> None:
    create_ddl, warnings = ddl_mapper.build_create_ddl(
        "CM",
        "COMPONENT",
        [col("ID", "NUMBER", 10, 0, "Y")],
        order_by="ID",
    )

    assert create_ddl.endswith("ENGINE = MergeTree ORDER BY tuple()")
    assert "`ID` Nullable(Int64)" in create_ddl
    assert warnings == []


def test_order_by_unsupported_column_falls_back_to_tuple_and_warning() -> None:
    create_ddl, warnings = ddl_mapper.build_create_ddl(
        "CM",
        "COMPONENT",
        [col("GEOM", "SDO_GEOMETRY", nullable="N")],
        order_by="GEOM",
    )

    assert create_ddl.endswith("ENGINE = MergeTree ORDER BY tuple()")
    assert warnings[0]["column"] == "GEOM"


def test_non_target_database_rejected_for_drop_and_create() -> None:
    with pytest.raises(ValueError):
        ddl_mapper.build_drop_ddl("CM", "COMPONENT", target_database="default")
    with pytest.raises(ValueError):
        ddl_mapper.build_create_ddl(
            "CM",
            "COMPONENT",
            [col("ID", "NUMBER", 10, 0)],
            target_database="default",
        )


def test_unsafe_custom_target_table_rejected() -> None:
    with pytest.raises(ValueError):
        ddl_mapper.build_recreate_ddl(
            "CM",
            "COMPONENT",
            [col("ID", "NUMBER", 10, 0)],
            target_table="bad-name",
        )


def test_target_database_constant_is_used() -> None:
    ddl_mapper.assert_target_database(TARGET_DATABASE)
