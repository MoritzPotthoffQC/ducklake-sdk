from collections.abc import Callable
from contextlib import nullcontext
from typing import Literal

import pytest

import ducklake as dl
import ducklake.exceptions as dlexc


@pytest.fixture(params=["ducklake", "transaction"])
def delete_table(request: pytest.FixtureRequest, ducklake: dl.Ducklake) -> Callable[..., None]:
    def delete_in_transaction(
        name: str | tuple[str, str] | dl.TableName,
        *,
        if_not_exists: Literal["fail", "skip"] = "fail",
    ) -> None:
        with ducklake.transaction() as tx:
            tx.delete_table(name, if_not_exists=if_not_exists)

    return ducklake.delete_table if request.param == "ducklake" else delete_in_transaction


@pytest.fixture()
def tables(ducklake: dl.Ducklake) -> set[dl.TableName]:
    ducklake.create_schema("custom")
    names = {
        dl.TableName(schema, name) for schema in ("main", "custom") for name in ("test", "sibling")
    }
    for name in names:
        ducklake.create_table(name, {"x": dl.Int64()})
    return names


# -------------------------------------------- TESTS -------------------------------------------- #


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
@pytest.mark.parametrize("if_not_exists", ["fail", "skip"])
def test_delete_table(
    ducklake: dl.Ducklake,
    delete_table: Callable[..., None],
    tables: set[dl.TableName],
    name: str | tuple[str, str],
    schema: str,
    if_not_exists: Literal["fail", "skip"],
) -> None:
    # Arrange
    deleted = dl.TableName(schema, "test")

    # Act
    delete_table(name, if_not_exists=if_not_exists)

    # Assert
    assert {table.name for table in ducklake.list_tables()} == tables - {deleted}
    assert not ducklake.has_table(deleted)


@pytest.mark.parametrize("name", ["missing", "missing_schema.test"])
@pytest.mark.parametrize("if_not_exists", ["fail", "skip"])
def test_delete_missing_table(
    ducklake: dl.Ducklake,
    delete_table: Callable[..., None],
    tables: set[dl.TableName],
    name: str,
    if_not_exists: Literal["fail", "skip"],
) -> None:
    # Arrange
    snapshot = ducklake.get_latest_snapshot()
    expected = pytest.raises(dlexc.NotFoundError) if if_not_exists == "fail" else nullcontext()

    # Act
    with expected:
        delete_table(name, if_not_exists=if_not_exists)

    # Assert
    assert {table.name for table in ducklake.list_tables()} == tables
    assert ducklake.get_latest_snapshot().id == snapshot.id


def test_delete_missing_table_fails_by_default(
    ducklake: dl.Ducklake, delete_table: Callable[..., None]
) -> None:
    # Arrange
    snapshot = ducklake.get_latest_snapshot()

    # Act
    with pytest.raises(dlexc.NotFoundError):
        delete_table("missing")

    # Assert
    assert ducklake.get_latest_snapshot().id == snapshot.id


def test_delete_table_invalid_strategy_raises(
    ducklake: dl.Ducklake, delete_table: Callable[..., None], tables: set[dl.TableName]
) -> None:
    # Arrange
    snapshot = ducklake.get_latest_snapshot()

    # Act
    with pytest.raises(ValueError, match="Invalid IfExistsStrategy"):
        delete_table("test", if_not_exists="invalid")

    # Assert
    assert {table.name for table in ducklake.list_tables()} == tables
    assert ducklake.get_latest_snapshot().id == snapshot.id


@pytest.mark.parametrize("if_not_exists", ["fail", "skip"])
def test_delete_table_does_not_delete_view(
    ducklake: dl.Ducklake,
    delete_table: Callable[..., None],
    if_not_exists: Literal["fail", "skip"],
) -> None:
    # Arrange
    ducklake.create_view("test", "SELECT 1 AS x")
    snapshot = ducklake.get_latest_snapshot()
    expected = pytest.raises(dlexc.NotFoundError) if if_not_exists == "fail" else nullcontext()

    # Act
    with expected:
        delete_table("test", if_not_exists=if_not_exists)

    # Assert
    assert ducklake.get_view("test").name == ("main", "test")
    assert ducklake.get_latest_snapshot().id == snapshot.id
