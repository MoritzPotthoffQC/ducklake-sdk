from contextlib import nullcontext
from typing import Literal

import pytest

import ducklake as dl
import ducklake.exceptions as dlexc


@pytest.fixture()
def view(shared_ducklake: dl.Ducklake, random_view_name: str) -> dl.View:
    return shared_ducklake.create_view(random_view_name, "SELECT 1 AS x")


@pytest.mark.parametrize("if_not_exists", ["fail", "skip"])
def test_delete_view_twice(
    shared_ducklake: dl.Ducklake,
    view: dl.View,
    random_view_name: str,
    if_not_exists: Literal["fail", "skip"],
) -> None:
    # Arrange
    expected = pytest.raises(dlexc.NotFoundError) if if_not_exists == "fail" else nullcontext()

    # Act
    with shared_ducklake.transaction() as tx:
        tx.delete_view(view.name)
        with expected:
            tx.delete_view(view.name, if_not_exists=if_not_exists)

    # Assert
    assert ("main", random_view_name) not in {item.name for item in shared_ducklake.list_views()}


def test_delete_view_not_visible_before_commit(
    shared_ducklake: dl.Ducklake, view: dl.View, random_view_name: str
) -> None:
    # Arrange
    tx = shared_ducklake.transaction()

    # Act
    tx.delete_view(view.name)

    # Assert
    assert view.name in {item.name for item in shared_ducklake.list_views()}
    tx.commit()
    assert ("main", random_view_name) not in {item.name for item in shared_ducklake.list_views()}


@pytest.mark.parametrize("missing_name", ["missing", "missing_schema.test"])
def test_operations_after_skipped_delete_view(
    shared_ducklake: dl.Ducklake,
    view: dl.View,
    random_view_name: str,
    missing_name: str,
) -> None:
    # Arrange
    created_name = random_view_name + "_created"

    # Act
    with shared_ducklake.transaction() as tx:
        tx.delete_view(missing_name, if_not_exists="skip")
        tx.create_table(created_name, {"x": dl.Int64()})
        tx.delete_view(view.name, if_not_exists="skip")

    # Assert
    assert shared_ducklake.has_table(created_name)
    assert ("main", random_view_name) not in {item.name for item in shared_ducklake.list_views()}


def test_delete_view_rolled_back_on_exception(shared_ducklake: dl.Ducklake, view: dl.View) -> None:
    # Arrange
    snapshot = shared_ducklake.get_latest_snapshot()

    # Act
    with pytest.raises(RuntimeError), shared_ducklake.transaction() as tx:
        tx.delete_view(view.name)
        raise RuntimeError

    # Assert
    assert view.name in {item.name for item in shared_ducklake.list_views()}
    assert shared_ducklake.get_latest_snapshot().id == snapshot.id
