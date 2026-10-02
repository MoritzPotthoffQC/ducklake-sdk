import pytest

import ducklake as dl
import ducklake.exceptions as dlexc


def _table_names(ducklake: dl.Ducklake) -> set[dl.TableName]:
    return {table.name for table in ducklake.list_tables()}


def test_delete_table_created_in_transaction(
    shared_ducklake: dl.Ducklake, random_table_name: str
) -> None:
    # Arrange
    snapshot = shared_ducklake.get_latest_snapshot()

    # Act
    with shared_ducklake.transaction() as tx:
        tx.create_table(random_table_name, {"x": dl.Int64()})
        tx.delete_table(random_table_name)

    # Assert
    assert shared_ducklake.get_latest_snapshot().id == snapshot.id
    assert ("main", random_table_name) not in _table_names(shared_ducklake)


def test_delete_table_twice_skip(shared_ducklake: dl.Ducklake, random_table_name: str) -> None:
    # Arrange
    shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})

    # Act
    with shared_ducklake.transaction() as tx:
        tx.delete_table(random_table_name)
        tx.delete_table(random_table_name, if_not_exists="skip")

    # Assert
    assert ("main", random_table_name) not in _table_names(shared_ducklake)


def test_delete_table_twice_fail_raises(
    shared_ducklake: dl.Ducklake, random_table_name: str
) -> None:
    # Arrange
    shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})

    # Act & Assert
    with shared_ducklake.transaction() as tx:
        tx.delete_table(random_table_name)
        with pytest.raises(dlexc.NotFoundError):
            tx.delete_table(random_table_name)
    assert ("main", random_table_name) not in _table_names(shared_ducklake)


def test_delete_table_not_visible_before_commit(
    shared_ducklake: dl.Ducklake, random_table_name: str
) -> None:
    # Arrange
    shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})

    # Act
    tx = shared_ducklake.transaction()
    tx.delete_table(random_table_name)

    # Assert
    assert ("main", random_table_name) in _table_names(shared_ducklake)
    tx.commit()
    assert ("main", random_table_name) not in _table_names(shared_ducklake)


def test_operations_after_skipped_delete_table(
    shared_ducklake: dl.Ducklake, random_table_name: str
) -> None:
    # Arrange
    shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})
    created_name = random_table_name + "_created"

    # Act
    with shared_ducklake.transaction() as tx:
        tx.delete_table(random_table_name + "_missing", if_not_exists="skip")
        tx.delete_table(f"missing_schema.{random_table_name}", if_not_exists="skip")
        tx.create_table(created_name, {"x": dl.Int64()})
        tx.delete_table(random_table_name, if_not_exists="skip")

    # Assert
    names = _table_names(shared_ducklake)
    assert ("main", created_name) in names
    assert ("main", random_table_name) not in names


def test_delete_table_rolled_back_on_exception(
    shared_ducklake: dl.Ducklake, random_table_name: str
) -> None:
    # Arrange
    shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})

    # Act
    with pytest.raises(RuntimeError), shared_ducklake.transaction() as tx:
        tx.delete_table(random_table_name)
        raise RuntimeError

    # Assert
    assert ("main", random_table_name) in _table_names(shared_ducklake)


def test_delete_table_then_recreate(shared_ducklake: dl.Ducklake, random_table_name: str) -> None:
    # Arrange
    shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})

    # Act
    with shared_ducklake.transaction() as tx:
        tx.delete_table(random_table_name)
        tx.create_table(random_table_name, {"y": dl.Varchar()})

    # Assert
    table = shared_ducklake.table(random_table_name)
    assert table.schema.columns == [dl.Column("y", dl.Varchar(), field_id=1)]
