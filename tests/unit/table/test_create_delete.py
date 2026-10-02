from contextlib import nullcontext
from typing import Literal

import pytest

import ducklake as dl
import ducklake.exceptions as dlexc


@pytest.fixture()
def table(shared_ducklake: dl.Ducklake, random_table_name: str) -> dl.Table:
    return shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})


def test_create_table(shared_ducklake: dl.Ducklake, random_table_name: str) -> None:
    # Act
    table = shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})

    # Assert
    assert table.name == ("main", random_table_name)
    assert table.schema.columns == [dl.Column("x", dl.Int64(), field_id=1)]
    assert table.partitioning is None
    assert table.tags == {}


def test_create_table_with_variant(ducklake: dl.Ducklake, random_table_name: str) -> None:
    # Arrange
    columns = {"payload": dl.Variant()}

    # Act
    ducklake.create_table(random_table_name, columns)
    table = ducklake.table(random_table_name)

    # Assert
    assert table.schema.columns == [dl.Column("payload", dl.Variant(), field_id=1)]


def test_table_equality(shared_ducklake: dl.Ducklake, random_table_name: str) -> None:
    # Arrange
    created = shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})

    # Act
    fetched = shared_ducklake.table(random_table_name)

    # Assert
    assert created == fetched


def test_table_repr(
    ducklake: dl.Ducklake, random_schema_name: str, random_table_name: str
) -> None:
    # Arrange
    ducklake.create_schema(random_schema_name)
    table = ducklake.create_table((random_schema_name, random_table_name), {"x": dl.Int64()})

    # Act
    actual = repr(table)

    # Assert
    assert actual == f"Table(schema='{random_schema_name}', name='{random_table_name}')"


def test_create_table_with_tags(shared_ducklake: dl.Ducklake, random_table_name: str) -> None:
    # Act
    table = shared_ducklake.create_table(
        random_table_name, {"x": dl.Int64()}, tags={"env": "prod", "owner": "team-a"}
    )

    # Assert
    assert table.tags == {"env": "prod", "owner": "team-a"}


def test_create_table_with_partitioning(
    shared_ducklake: dl.Ducklake, random_table_name: str
) -> None:
    # Act
    table = shared_ducklake.create_table(
        random_table_name,
        {"x": dl.Int64(), "y": dl.Varchar()},
        partition_by=dl.Partitioning(["x"]),
    )

    # Assert
    assert table.partitioning is not None
    assert [c.name for c in table.partitioning.columns] == ["x"]


def test_create_table_in_schema_via_tuple(
    ducklake: dl.Ducklake, random_schema_name: str, random_table_name: str
) -> None:
    # Arrange
    ducklake.create_schema(random_schema_name)

    # Act
    table = ducklake.create_table((random_schema_name, random_table_name), {"x": dl.Int64()})

    # Assert
    assert table.name == (random_schema_name, random_table_name)


def test_create_existing_table_raises(
    shared_ducklake: dl.Ducklake, random_table_name: str
) -> None:
    # Arrange
    shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})

    # Act & Assert
    with pytest.raises(dlexc.AlreadyExistsError):
        shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})


def test_create_existing_table_skip(shared_ducklake: dl.Ducklake, random_table_name: str) -> None:
    # Arrange
    shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})

    # Act
    table = shared_ducklake.create_table(random_table_name, {"y": dl.Varchar()}, if_exists="skip")

    # Assert
    assert table.name == ("main", random_table_name)
    assert table.schema.columns == [dl.Column("x", dl.Int64(), field_id=1)]


def test_create_table_skip_when_missing(
    shared_ducklake: dl.Ducklake, random_table_name: str
) -> None:
    # Act
    table = shared_ducklake.create_table(random_table_name, {"x": dl.Int64()}, if_exists="skip")

    # Assert
    assert table.name == ("main", random_table_name)
    assert table.schema.columns == [dl.Column("x", dl.Int64(), field_id=1)]


@pytest.mark.parametrize("if_not_exists", ["fail", "skip"])
def test_delete_table(
    shared_ducklake: dl.Ducklake,
    table: dl.Table,
    random_table_name: str,
    if_not_exists: Literal["fail", "skip"],
) -> None:
    # Arrange
    snapshot = shared_ducklake.get_latest_snapshot()

    # Act
    shared_ducklake.delete_table(table.name, if_not_exists=if_not_exists)

    # Assert
    assert not shared_ducklake.has_table(random_table_name)
    assert shared_ducklake.get_latest_snapshot().id == snapshot.id + 1


@pytest.mark.parametrize(
    ("name", "schema"),
    [
        ("test", "main"),
        ("custom.test", "custom"),
        ('"custom"."test"', "custom"),
        (dl.TableName("custom", "test"), "custom"),
        (("custom", "test"), "custom"),
    ],
)
def test_delete_table_by_name(
    ducklake: dl.Ducklake, name: str | tuple[str, str], schema: str
) -> None:
    # Arrange
    ducklake.create_schema("custom")
    for schema_name in ("main", "custom"):
        ducklake.create_table((schema_name, "test"), {"x": dl.Int64()})

    # Act
    ducklake.delete_table(name)

    # Assert
    remaining_schema = "custom" if schema == "main" else "main"
    assert [item.name for item in ducklake.list_tables()] == [(remaining_schema, "test")]


@pytest.mark.parametrize("name", ["missing", "missing_schema.test"])
def test_delete_missing_table_raises(ducklake: dl.Ducklake, name: str) -> None:
    # Act & Assert
    with pytest.raises(dlexc.NotFoundError):
        ducklake.delete_table(name)


@pytest.mark.parametrize("name", ["missing", "missing_schema.test"])
def test_delete_missing_table_skip(ducklake: dl.Ducklake, name: str) -> None:
    # Arrange
    snapshot = ducklake.get_latest_snapshot()

    # Act
    ducklake.delete_table(name, if_not_exists="skip")

    # Assert
    assert ducklake.list_tables() == []
    assert ducklake.get_latest_snapshot().id == snapshot.id


def test_delete_table_invalid_strategy_raises(
    shared_ducklake: dl.Ducklake, table: dl.Table
) -> None:
    # Arrange
    snapshot = shared_ducklake.get_latest_snapshot()

    # Act
    with pytest.raises(ValueError, match="Invalid IfExistsStrategy"):
        shared_ducklake.delete_table(table.name, if_not_exists="invalid")  # ty: ignore[invalid-argument-type]

    # Assert
    assert shared_ducklake.has_table(table.name)
    assert shared_ducklake.get_latest_snapshot().id == snapshot.id


@pytest.mark.parametrize("if_not_exists", ["fail", "skip"])
def test_delete_table_does_not_delete_view(
    ducklake: dl.Ducklake, if_not_exists: Literal["fail", "skip"]
) -> None:
    # Arrange
    view = ducklake.create_view("test", "SELECT 1 AS x")
    snapshot = ducklake.get_latest_snapshot()
    expected = pytest.raises(dlexc.NotFoundError) if if_not_exists == "fail" else nullcontext()

    # Act
    with expected:
        ducklake.delete_table(view.name, if_not_exists=if_not_exists)

    # Assert
    assert [item.name for item in ducklake.list_views()] == [view.name]
    assert ducklake.get_latest_snapshot().id == snapshot.id
