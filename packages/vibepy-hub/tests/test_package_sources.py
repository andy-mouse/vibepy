"""Registering a folder of wheels is what makes its Apps installable."""

import shutil
from pathlib import Path

import pytest

from tests_support import hub, write_wheel
from vibepy_core.errors import ToolInputValidationError
from vibepy_hub.models import AppListing, SourceListing


async def test_registering_a_folder_lists_what_it_offers(tmp_path: Path) -> None:
    source = tmp_path / "wheels"
    write_wheel(source, name="zulu-app", version="1.2.3", declares=True)
    write_wheel(source, name="alpha-app", version="0.4.0", declares=False)

    async with hub(tmp_path / "hub") as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})

    assert isinstance(listed, SourceListing)
    assert listed.source == source
    assert [(row.name, row.version, row.declares_app) for row in listed.candidates] == [
        ("alpha-app", "0.4.0", False),
        ("zulu-app", "1.2.3", True),
    ]


async def test_registering_a_second_folder_replaces_the_first(tmp_path: Path) -> None:
    """One folder is registered at a time: the Hub has one wheelhouse, not a search path."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_wheel(first, name="one", version="1.0.0", declares=True)
    write_wheel(second, name="two", version="1.0.0", declares=True)

    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(first)})
        listed = await tools.invoke("register_package_source", {"path": str(second)})
        apps = await tools.invoke("list_apps", {})

    assert isinstance(listed, SourceListing)
    assert listed.source == second
    assert [row.name for row in listed.candidates] == ["two"]
    assert isinstance(apps, AppListing)
    assert [row.app_name for row in apps.apps] == ["two"]
    assert apps.source == second


async def test_an_empty_folder_offers_nothing(tmp_path: Path) -> None:
    source = tmp_path / "wheels"
    source.mkdir()

    async with hub(tmp_path / "hub") as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})

    assert isinstance(listed, SourceListing)
    assert listed.source == source
    assert listed.candidates == []


async def test_an_absent_folder_is_a_diagnostic_and_registers_nothing(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("register_package_source", {"path": str(tmp_path / "no")})

    assert isinstance(answered, SourceListing)
    assert answered.source is None
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.source_unreadable"


async def test_a_registered_folder_outlives_the_window_and_removing_clears_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "wheels"
    write_wheel(source, name="demo", version="1.0.0", declares=True)
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)})

    async with hub(root) as tools:
        kept = await tools.invoke("list_apps", {})
        removed = await tools.invoke("remove_package_source", {})

    assert isinstance(kept, AppListing)
    assert [row.app_name for row in kept.apps] == ["demo"]
    assert isinstance(removed, SourceListing)
    assert removed.source is None
    assert removed.candidates == []

    async with hub(root) as tools:
        after = await tools.invoke("list_apps", {})

    assert isinstance(after, AppListing)
    assert after.source is None


async def test_a_source_that_has_disappeared_is_a_diagnostic_not_an_exception(
    tmp_path: Path,
) -> None:
    source = tmp_path / "wheels"
    write_wheel(source, name="demo", version="1.0.0", declares=True)
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)})

    shutil.rmtree(source)

    async with hub(root) as tools:
        listed = await tools.invoke("list_apps", {})
        withdrawn = await tools.invoke("remove_package_source", {})

    assert isinstance(listed, AppListing)
    assert listed.diagnostic is not None
    assert listed.diagnostic.code == "hub.source_unreadable"
    assert isinstance(withdrawn, SourceListing)
    assert withdrawn.source is None


async def test_an_empty_path_is_refused_rather_than_the_working_directory(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        with pytest.raises(ToolInputValidationError):
            await tools.invoke("register_package_source", {"path": ""})
