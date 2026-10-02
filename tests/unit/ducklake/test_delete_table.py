from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal

import polars as pl
import pytest
from _testutils import assert_ducklake_catalogs_equal, make_catalog_url, make_storage_path

import ducklake as dl
import ducklake.exceptions as dlexc

DeleteTable = Callable[..., None]


@pytest.fixture(params=["ducklake", "transaction"])
def delete_table(request: pytest.FixtureRequest, shared_ducklake: dl.Ducklake) -> DeleteTable:
    def delete_table_in_transaction(
        name: str | tuple[str, str] | dl.TableName,
        *,
        if_not_exists: Literal["fail", "skip"] = "fail",
    ) -> None:
        with shared_ducklake.transaction() as tx:
            tx.delete_table(name, if_not_exists=if_not_exists)

    if request.param == "ducklake":
        return shared_ducklake.delete_table
    return delete_table_in_transaction


@pytest.fixture()
def tables(
    shared_ducklake: dl.Ducklake, random_schema_name: str, random_table_name: str
) -> set[dl.TableName]:
    shared_ducklake.create_schema(random_schema_name)
    names = {
        dl.TableName(schema, name)
        for schema in ("main", random_schema_name)
        for name in (random_table_name, random_table_name + "_sibling")
    }
    for name in names:
        shared_ducklake.create_table(name, {"x": dl.Int64()})
    return names


def _table_names(ducklake: dl.Ducklake) -> set[dl.TableName]:
    return {table.name for table in ducklake.list_tables()}


# -------------------------------------------- TESTS -------------------------------------------- #


@pytest.mark.parametrize(
    ("make_name", "deleted_schema"),
    [
        pytest.param(lambda schema, table: table, "main", id="unqualified"),
        pytest.param(lambda schema, table: f"{schema}.{table}", None, id="qualified"),
        pytest.param(lambda schema, table: f'"{schema}"."{table}"', None, id="quoted"),
        pytest.param(lambda schema, table: dl.TableName(schema, table), None, id="table_name"),
        pytest.param(lambda schema, table: (schema, table), None, id="tuple"),
    ],
)
def test_delete_table(
    shared_ducklake: dl.Ducklake,
    delete_table: DeleteTable,
    tables: set[dl.TableName],
    random_schema_name: str,
    random_table_name: str,
    make_name: Callable[[str, str], Any],
    deleted_schema: str | None,
) -> None:
    # Arrange
    deleted = dl.TableName(deleted_schema or random_schema_name, random_table_name)
    before = _table_names(shared_ducklake)

    # Act
    delete_table(make_name(random_schema_name, random_table_name))

    # Assert
    assert _table_names(shared_ducklake) == before - {deleted}
    with pytest.raises(dlexc.NotFoundError):
        shared_ducklake.table(deleted)


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param(lambda schema, table: f"main.{table}_missing", id="missing_table"),
        pytest.param(lambda schema, table: f"{schema}_missing.{table}", id="missing_schema"),
    ],
)
@pytest.mark.parametrize("kwargs", [{}, {"if_not_exists": "fail"}], ids=["default", "fail"])
def test_delete_missing_table_raises(
    shared_ducklake: dl.Ducklake,
    delete_table: DeleteTable,
    tables: set[dl.TableName],
    random_schema_name: str,
    random_table_name: str,
    missing: Callable[[str, str], str],
    kwargs: dict[str, Any],
) -> None:
    # Arrange
    name = missing(random_schema_name, random_table_name)
    with pytest.raises(dlexc.NotFoundError) as expected:
        shared_ducklake.table(name)
    snapshot = shared_ducklake.get_latest_snapshot()

    # Act
    with pytest.raises(dlexc.NotFoundError) as actual:
        delete_table(name, **kwargs)

    # Assert
    assert str(actual.value) == str(expected.value)
    assert shared_ducklake.get_latest_snapshot().id == snapshot.id


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param(lambda schema, table: f"main.{table}_missing", id="missing_table"),
        pytest.param(lambda schema, table: f"{schema}_missing.{table}", id="missing_schema"),
    ],
)
def test_delete_missing_table_skip(
    shared_ducklake: dl.Ducklake,
    delete_table: DeleteTable,
    tables: set[dl.TableName],
    random_schema_name: str,
    random_table_name: str,
    missing: Callable[[str, str], str],
) -> None:
    # Arrange
    before = _table_names(shared_ducklake)
    snapshot = shared_ducklake.get_latest_snapshot()

    # Act
    delete_table(missing(random_schema_name, random_table_name), if_not_exists="skip")

    # Assert
    assert _table_names(shared_ducklake) == before
    assert shared_ducklake.get_latest_snapshot().id == snapshot.id


def test_delete_table_invalid_strategy_raises(
    shared_ducklake: dl.Ducklake, delete_table: DeleteTable, random_table_name: str
) -> None:
    # Arrange
    shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})

    # Act & Assert
    with pytest.raises(ValueError, match="Invalid IfExistsStrategy"):
        delete_table(random_table_name, if_not_exists="invalid")
    assert ("main", random_table_name) in _table_names(shared_ducklake)


@pytest.mark.parametrize("kwargs", [{}, {"if_not_exists": "skip"}], ids=["fail", "skip"])
def test_delete_table_does_not_delete_view(
    shared_ducklake: dl.Ducklake,
    delete_table: DeleteTable,
    random_table_name: str,
    random_view_name: str,
    kwargs: dict[str, Any],
) -> None:
    # Arrange
    shared_ducklake.create_table(random_table_name, {"x": dl.Int64()})
    shared_ducklake.create_view(random_view_name, f"SELECT x FROM {random_table_name}")

    # Act
    if kwargs:
        delete_table(random_view_name, **kwargs)
    else:
        with pytest.raises(dlexc.NotFoundError):
            delete_table(random_view_name, **kwargs)

    # Assert
    assert ("main", random_view_name) in {view.name for view in shared_ducklake.list_views()}


# ------------------------------------------- PARITY -------------------------------------------- #


def _delete_via_handle(ducklake: dl.Ducklake, name: str) -> None:
    ducklake.table(name).delete()


def _delete_via_name(ducklake: dl.Ducklake, name: str) -> None:
    ducklake.delete_table(name)


def _delete_via_transaction_handle(ducklake: dl.Ducklake, name: str) -> None:
    with ducklake.transaction() as tx:
        tx.table(name).delete()


def _delete_via_transaction_name(ducklake: dl.Ducklake, name: str) -> None:
    with ducklake.transaction() as tx:
        tx.delete_table(name)


def _expire_and_cleanup(ducklake: dl.Ducklake) -> list[str]:
    ducklake.expire_snapshots(versions=[snapshot.id for snapshot in ducklake.list_snapshots()])
    return ducklake.cleanup_old_files(cleanup_all=True)


@pytest.fixture()
def reference(catalog: str, storage: str, tmp_path: Path) -> Iterator[tuple[dl.Ducklake, str]]:
    with (
        make_catalog_url(catalog, tmp_path) as catalog_url,
        make_storage_path(storage, tmp_path) as storage_path,
        dl.create(catalog_url, data_path=storage_path) as ducklake,
    ):
        yield ducklake, catalog_url


@pytest.mark.parametrize("maintenance", [False, True], ids=["delete", "delete_and_cleanup"])
@pytest.mark.parametrize(
    ("delete_reference", "delete_actual"),
    [
        pytest.param(_delete_via_handle, _delete_via_name, id="ducklake"),
        pytest.param(
            _delete_via_transaction_handle, _delete_via_transaction_name, id="transaction"
        ),
    ],
)
def test_delete_table_matches_table_delete(
    ducklake: dl.Ducklake,
    catalog_url: str,
    reference: tuple[dl.Ducklake, str],
    delete_reference: Callable[[dl.Ducklake, str], None],
    delete_actual: Callable[[dl.Ducklake, str], None],
    maintenance: bool,
) -> None:
    # Arrange
    reference_ducklake, reference_catalog_url = reference
    for lake in (reference_ducklake, ducklake):
        for name in ("target", "sibling"):
            table = lake.create_table(name, {"x": dl.Int64()})
            table.set_metadata(data_inlining_row_limit=0)
            table.write_polars(pl.DataFrame({"x": [1, 2, 3]}))

    # Act
    delete_reference(reference_ducklake, "target")
    delete_actual(ducklake, "target")
    if maintenance:
        reference_cleaned = _expire_and_cleanup(reference_ducklake)
        actual_cleaned = _expire_and_cleanup(ducklake)

    # Assert
    assert_ducklake_catalogs_equal(reference_catalog_url, catalog_url)
    if maintenance:
        assert len(actual_cleaned) == len(reference_cleaned) == 1
    with pytest.raises(dlexc.NotFoundError):
        ducklake.table("target")
    recreated = ducklake.create_table("target", {"y": dl.Varchar()})
    assert recreated.schema.columns == [dl.Column("y", dl.Varchar(), field_id=1)]
