"""Registering a folder is what makes its Apps installable."""

from pathlib import Path

from tests_support import write_project
from vibepy.app.composition import tool_runtime_for
from vibepy_hub.entry import APP, HUB_APP
from vibepy_hub.models import SourceListing


async def test_registering_a_folder_lists_its_candidates(tmp_path: Path) -> None:
    source = tmp_path / "packages"
    write_project(source / "demo", name="demo", declares=True)
    config = {"root": str(tmp_path / "hub")}

    async with tool_runtime_for(HUB_APP, APP.lifespan, config=config) as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})
        assert isinstance(listed, SourceListing)
        assert [row.name for row in listed.candidates] == ["demo"]

        remaining = await tools.invoke("remove_package_source", {"path": str(source)})
        assert isinstance(remaining, SourceListing)
        assert remaining.sources == []


async def test_an_absent_folder_is_a_diagnostic(tmp_path: Path) -> None:
    config = {"root": str(tmp_path / "hub")}

    async with tool_runtime_for(HUB_APP, APP.lifespan, config=config) as tools:
        answered = await tools.invoke("register_package_source", {"path": str(tmp_path / "no")})

    assert isinstance(answered, SourceListing)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.source_unreadable"


async def test_a_registered_folder_outlives_the_window(tmp_path: Path) -> None:
    source = tmp_path / "packages"
    write_project(source / "demo", name="demo", declares=True)
    config = {"root": str(tmp_path / "hub")}

    async with tool_runtime_for(HUB_APP, APP.lifespan, config=config) as tools:
        await tools.invoke("register_package_source", {"path": str(source)})

    async with tool_runtime_for(HUB_APP, APP.lifespan, config=config) as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})

    assert isinstance(listed, SourceListing)
    assert listed.sources == [source]
