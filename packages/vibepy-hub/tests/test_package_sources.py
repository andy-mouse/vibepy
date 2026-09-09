"""Registering a folder is what makes its Apps installable."""

import shutil
from pathlib import Path

from tests_support import hub, write_project
from vibepy_hub.models import AppListing, Installation, SourceListing


async def test_registering_a_folder_lists_what_it_offers(tmp_path: Path) -> None:
    source = tmp_path / "packages"
    write_project(source / "zulu", name="zulu-app", declares=True)
    write_project(source / "alpha", name="alpha-app", declares=True)

    async with hub(tmp_path / "hub") as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})

    assert isinstance(listed, SourceListing)
    assert [(row.name, row.version, row.declares_app) for row in listed.candidates] == [
        ("alpha-app", "1.2.3", True),
        ("zulu-app", "1.2.3", True),
    ]


async def test_a_folder_without_a_visible_declaration_is_still_offered(tmp_path: Path) -> None:
    """A backend may add entry points, so a static reading is a hint."""
    source = tmp_path / "packages"
    write_project(source / "plain", name="plain", declares=False)

    async with hub(tmp_path / "hub") as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})

    assert isinstance(listed, SourceListing)
    assert [(row.name, row.declares_app) for row in listed.candidates] == [("plain", False)]


async def test_a_folder_carrying_no_project_file_offers_nothing(tmp_path: Path) -> None:
    source = tmp_path / "packages"
    (source / "notes").mkdir(parents=True)

    async with hub(tmp_path / "hub") as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})

    assert isinstance(listed, SourceListing)
    assert listed.candidates == []


async def test_an_absent_folder_is_a_diagnostic(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("register_package_source", {"path": str(tmp_path / "no")})

    assert isinstance(answered, SourceListing)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.source_unreadable"


async def test_a_removed_folder_offers_nothing_and_a_kept_one_outlives_the_window(
    tmp_path: Path,
) -> None:
    source = tmp_path / "packages"
    write_project(source / "demo", name="demo", declares=True)
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)})

    async with hub(root) as tools:
        kept = await tools.invoke("register_package_source", {"path": str(source)})
        removed = await tools.invoke("remove_package_source", {"path": str(source)})

    assert isinstance(kept, SourceListing)
    assert kept.sources == [source]
    assert isinstance(removed, SourceListing)
    assert removed.sources == []
    assert removed.candidates == []


async def test_a_folder_whose_project_declares_no_name_offers_nothing(tmp_path: Path) -> None:
    """`name` is required and static, so a project file without one is not a project."""
    source = tmp_path / "packages"
    (source / "nameless").mkdir(parents=True)
    (source / "nameless" / "pyproject.toml").write_text(
        '[project]\nversion = "1.0.0"\n', encoding="utf-8"
    )

    async with hub(tmp_path / "hub") as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})

    assert isinstance(listed, SourceListing)
    assert listed.candidates == []


async def test_a_source_that_has_disappeared_is_a_diagnostic_not_an_exception(
    tmp_path: Path,
) -> None:
    source = tmp_path / "packages"
    write_project(source / "demo", name="demo", declares=True)
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)})

    shutil.rmtree(source)

    async with hub(root) as tools:
        listed = await tools.invoke("list_apps", {})
        withdrawn = await tools.invoke("remove_package_source", {"path": str(source)})

    assert isinstance(listed, AppListing)
    assert listed.diagnostic is not None
    assert listed.diagnostic.code == "hub.source_unreadable"
    assert isinstance(withdrawn, SourceListing)
    assert withdrawn.sources == []


async def test_two_sources_offering_one_name_is_refused_rather_than_ordered(
    tmp_path: Path,
) -> None:
    """One name addresses one App, so two folders claiming it addresses none.

    Installing the first-registered source's copy would make registration order
    decide which App a name means, which is the shape this stage exists to
    remove. `docs/decisions/ADR-027` already refuses a duplicate name at the
    point it is read rather than letting one of the two disappear.
    """
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_project(first / "demo", name="demo-app", declares=True)
    write_project(second / "demo-copy", name="Demo_App", declares=True)

    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(first)})
        await tools.invoke("register_package_source", {"path": str(second)})
        answered = await tools.invoke("install_app", {"app_name": "demo-app"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.candidate_ambiguous"
    assert str(first / "demo") in answered.diagnostic.details["folders"]
    assert str(second / "demo-copy") in answered.diagnostic.details["folders"]

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["demo-app"].diagnostic is not None
    assert rows["demo-app"].diagnostic.code == "hub.candidate_ambiguous"


async def test_registering_reports_a_source_that_can_no_longer_be_read(
    tmp_path: Path,
) -> None:
    """Every Tool answering with a source listing says the same thing about it.

    `list_apps` reports a registered source it could not read; so must this, or
    one Tool's silence contradicts the other's diagnostic about one fact.
    """
    gone = tmp_path / "gone"
    kept = tmp_path / "kept"
    write_project(gone / "demo", name="demo-app", declares=True)
    kept.mkdir()
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(gone)})

    shutil.rmtree(gone)

    async with hub(root) as tools:
        listed = await tools.invoke("register_package_source", {"path": str(kept)})

    assert isinstance(listed, SourceListing)
    assert listed.diagnostic is not None
    assert listed.diagnostic.code == "hub.source_unreadable"
    assert str(gone) in listed.diagnostic.details["paths"]
