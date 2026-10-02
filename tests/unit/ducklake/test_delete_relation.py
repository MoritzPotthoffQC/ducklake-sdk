from collections.abc import Callable
from contextlib import nullcontext
from typing import Literal

import pytest

import ducklake as dl
import ducklake.exceptions as dlexc


@pytest.fixture(params=["table", "view"])
def relation_kind(request: pytest.FixtureRequest) -> str:
    return request.param


def _names(ducklake: dl.Ducklake, relation_kind: str) -> set[dl.TableName]:
    relations = ducklake.list_tables() if relation_kind == "table" else ducklake.list_views()
    return {relation.name for relation in relations}


@pytest.fixture(params=["ducklake", "transaction"])
def delete_relation(
    request: pytest.FixtureRequest, ducklake: dl.Ducklake, relation_kind: str
) -> Callable[..., None]:
    def delete_in_transaction(
        name: str | tuple[str, str] | dl.TableName,
        *,
        if_not_exists: Literal["fail", "skip"] = "fail",
    ) -> None:
        with ducklake.transaction() as tx:
            delete = tx.delete_table if relation_kind == "table" else tx.delete_view
            delete(name, if_not_exists=if_not_exists)

    delete = ducklake.delete_table if relation_kind == "table" else ducklake.delete_view
    return delete if request.param == "ducklake" else delete_in_transaction


@pytest.fixture()
def relations(ducklake: dl.Ducklake, relation_kind: str) -> set[dl.TableName]:
    ducklake.create_schema("custom")
    names = {
        dl.TableName(schema, name) for schema in ("main", "custom") for name in ("test", "sibling")
    }
    for name in names:
        if relation_kind == "table":
            ducklake.create_table(name, {"x": dl.Int64()})
        else:
            ducklake.create_view(name, "SELECT 1 AS x")
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
def test_delete_relation(
    ducklake: dl.Ducklake,
    delete_relation: Callable[..., None],
    relations: set[dl.TableName],
    relation_kind: str,
    name: str | tuple[str, str],
    schema: str,
    if_not_exists: Literal["fail", "skip"],
) -> None:
    # Arrange
    deleted = dl.TableName(schema, "test")

    # Act
    delete_relation(name, if_not_exists=if_not_exists)

    # Assert
    assert _names(ducklake, relation_kind) == relations - {deleted}


@pytest.mark.parametrize("name", ["missing", "missing_schema.test"])
@pytest.mark.parametrize("if_not_exists", ["fail", "skip"])
def test_delete_missing_relation(
    ducklake: dl.Ducklake,
    delete_relation: Callable[..., None],
    relations: set[dl.TableName],
    relation_kind: str,
    name: str,
    if_not_exists: Literal["fail", "skip"],
) -> None:
    # Arrange
    snapshot = ducklake.get_latest_snapshot()
    expected = pytest.raises(dlexc.NotFoundError) if if_not_exists == "fail" else nullcontext()

    # Act
    with expected:
        delete_relation(name, if_not_exists=if_not_exists)

    # Assert
    assert _names(ducklake, relation_kind) == relations
    assert ducklake.get_latest_snapshot().id == snapshot.id


def test_delete_missing_relation_fails_by_default(
    ducklake: dl.Ducklake, delete_relation: Callable[..., None]
) -> None:
    # Arrange
    snapshot = ducklake.get_latest_snapshot()

    # Act
    with pytest.raises(dlexc.NotFoundError):
        delete_relation("missing")

    # Assert
    assert ducklake.get_latest_snapshot().id == snapshot.id


def test_delete_relation_invalid_strategy_raises(
    ducklake: dl.Ducklake,
    delete_relation: Callable[..., None],
    relations: set[dl.TableName],
    relation_kind: str,
) -> None:
    # Arrange
    snapshot = ducklake.get_latest_snapshot()

    # Act
    with pytest.raises(ValueError, match="Invalid IfExistsStrategy"):
        delete_relation("test", if_not_exists="invalid")

    # Assert
    assert _names(ducklake, relation_kind) == relations
    assert ducklake.get_latest_snapshot().id == snapshot.id


@pytest.mark.parametrize("if_not_exists", ["fail", "skip"])
def test_delete_relation_does_not_delete_other_kind(
    ducklake: dl.Ducklake,
    delete_relation: Callable[..., None],
    relation_kind: str,
    if_not_exists: Literal["fail", "skip"],
) -> None:
    # Arrange
    if relation_kind == "table":
        ducklake.create_view("test", "SELECT 1 AS x")
    else:
        ducklake.create_table("test", {"x": dl.Int64()})
    snapshot = ducklake.get_latest_snapshot()
    expected = pytest.raises(dlexc.NotFoundError) if if_not_exists == "fail" else nullcontext()

    # Act
    with expected:
        delete_relation("test", if_not_exists=if_not_exists)

    # Assert
    other_kind = "view" if relation_kind == "table" else "table"
    assert _names(ducklake, other_kind) == {dl.TableName("main", "test")}
    assert ducklake.get_latest_snapshot().id == snapshot.id
