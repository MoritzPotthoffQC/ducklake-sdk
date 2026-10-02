from contextlib import nullcontext
from typing import Literal

import pytest

import ducklake as dl
import ducklake.exceptions as dlexc


@pytest.fixture(params=["table", "view"])
def relation_kind(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture()
def relation_name(
    shared_ducklake: dl.Ducklake, random_table_name: str, relation_kind: str
) -> dl.TableName:
    if relation_kind == "table":
        return shared_ducklake.create_table(random_table_name, {"x": dl.Int64()}).name
    return shared_ducklake.create_view(random_table_name, "SELECT 1 AS x").name


def _names(ducklake: dl.Ducklake, relation_kind: str) -> set[dl.TableName]:
    relations = ducklake.list_tables() if relation_kind == "table" else ducklake.list_views()
    return {relation.name for relation in relations}


# -------------------------------------------- TESTS -------------------------------------------- #


@pytest.mark.parametrize("if_not_exists", ["fail", "skip"])
def test_delete_relation_twice(
    shared_ducklake: dl.Ducklake,
    relation_name: dl.TableName,
    relation_kind: str,
    if_not_exists: Literal["fail", "skip"],
) -> None:
    # Arrange
    expected = pytest.raises(dlexc.NotFoundError) if if_not_exists == "fail" else nullcontext()

    # Act
    with shared_ducklake.transaction() as tx:
        delete = tx.delete_table if relation_kind == "table" else tx.delete_view
        delete(relation_name)
        with expected:
            delete(relation_name, if_not_exists=if_not_exists)

    # Assert
    assert relation_name not in _names(shared_ducklake, relation_kind)


def test_delete_relation_not_visible_before_commit(
    shared_ducklake: dl.Ducklake, relation_name: dl.TableName, relation_kind: str
) -> None:
    # Arrange
    tx = shared_ducklake.transaction()
    delete = tx.delete_table if relation_kind == "table" else tx.delete_view

    # Act
    delete(relation_name)

    # Assert
    assert relation_name in _names(shared_ducklake, relation_kind)
    tx.commit()
    assert relation_name not in _names(shared_ducklake, relation_kind)


def test_operations_after_skipped_delete_relation(
    shared_ducklake: dl.Ducklake,
    relation_name: dl.TableName,
    relation_kind: str,
    random_table_name: str,
) -> None:
    # Arrange
    created_name = random_table_name + "_created"

    # Act
    with shared_ducklake.transaction() as tx:
        delete = tx.delete_table if relation_kind == "table" else tx.delete_view
        delete(random_table_name + "_missing", if_not_exists="skip")
        delete(f"missing_schema.{random_table_name}", if_not_exists="skip")
        tx.create_table(created_name, {"x": dl.Int64()})
        delete(relation_name, if_not_exists="skip")

    # Assert
    assert shared_ducklake.has_table(created_name)
    assert relation_name not in _names(shared_ducklake, relation_kind)


def test_delete_relation_rolled_back_on_exception(
    shared_ducklake: dl.Ducklake, relation_name: dl.TableName, relation_kind: str
) -> None:
    # Arrange
    snapshot = shared_ducklake.get_latest_snapshot()

    # Act
    with pytest.raises(RuntimeError), shared_ducklake.transaction() as tx:
        delete = tx.delete_table if relation_kind == "table" else tx.delete_view
        delete(relation_name)
        raise RuntimeError

    # Assert
    assert relation_name in _names(shared_ducklake, relation_kind)
    assert shared_ducklake.get_latest_snapshot().id == snapshot.id
