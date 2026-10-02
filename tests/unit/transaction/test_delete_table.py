from contextlib import nullcontext
from typing import Literal

import pytest

import ducklake as dl
import ducklake.exceptions as dlexc


@pytest.fixture()
def table_name(shared_ducklake: dl.Ducklake, random_table_name: str) -> dl.TableName:
    return shared_ducklake.create_table(random_table_name, {"x": dl.Int64()}).name


# -------------------------------------------- TESTS -------------------------------------------- #


@pytest.mark.parametrize("if_not_exists", ["fail", "skip"])
def test_delete_table_twice(
    shared_ducklake: dl.Ducklake, table_name: dl.TableName, if_not_exists: Literal["fail", "skip"]
) -> None:
    # Arrange
    expected = pytest.raises(dlexc.NotFoundError) if if_not_exists == "fail" else nullcontext()

    # Act
    with shared_ducklake.transaction() as tx:
        tx.delete_table(table_name)
        with expected:
            tx.delete_table(table_name, if_not_exists=if_not_exists)
        tables = tx.list_tables()

    # Assert
    assert table_name not in {t.name for t in tables}
    assert not shared_ducklake.has_table(table_name)


def test_delete_table_not_visible_before_commit(
    shared_ducklake: dl.Ducklake, table_name: dl.TableName
) -> None:
    # Arrange
    tx = shared_ducklake.transaction()

    # Act
    tx.delete_table(table_name)

    # Assert
    assert shared_ducklake.has_table(table_name)
    tx.commit()
    assert not shared_ducklake.has_table(table_name)


def test_operations_after_skipped_delete_table(
    shared_ducklake: dl.Ducklake, table_name: dl.TableName, random_table_name: str
) -> None:
    # Arrange
    created_name = random_table_name + "_created"

    # Act
    with shared_ducklake.transaction() as tx:
        tx.delete_table(random_table_name + "_missing", if_not_exists="skip")
        tx.delete_table(f"missing_schema.{random_table_name}", if_not_exists="skip")
        tx.create_table(created_name, {"x": dl.Int64()})
        tx.delete_table(table_name, if_not_exists="skip")

    # Assert
    assert shared_ducklake.has_table(created_name)
    assert not shared_ducklake.has_table(table_name)


def test_delete_table_rolled_back_on_exception(
    shared_ducklake: dl.Ducklake, table_name: dl.TableName
) -> None:
    # Arrange
    snapshot = shared_ducklake.get_latest_snapshot()

    # Act
    with pytest.raises(RuntimeError), shared_ducklake.transaction() as tx:
        tx.delete_table(table_name)
        raise RuntimeError

    # Assert
    assert shared_ducklake.has_table(table_name)
    assert shared_ducklake.get_latest_snapshot().id == snapshot.id
