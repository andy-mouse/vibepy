"""Installing an App gives it an environment of its own."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests_support import EXAMPLES, hub, write_project
from vibepy_core.errors import ToolInputValidationError
from vibepy_hub.internals import AppNameInvalid
from vibepy_hub.internals import environment as hub_environment
from vibepy_hub.models import AppListing, AppName, Installation, RunningApp


def environment(root: Path, app_name: str, /) -> Path:
    """Where the Hub's declared root holds one App, as the spec describes it."""
    return root / "envs" / app_name


def a_python_lives_in(env: Path, /) -> bool:
    """Whether that environment has an interpreter of its own."""
    return (env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")).is_file()


async def test_installing_an_app_creates_an_environment_of_its_own(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        installed = await tools.invoke("install_app", {"app_name": "todo"})

    assert isinstance(installed, Installation)
    assert installed.diagnostic is None
    assert installed.app.name == "Todo"
    assert installed.app.version == "0.0.0"
    assert installed.app.has_pages is True
    assert a_python_lives_in(environment(root, "todo"))


async def test_an_installed_app_is_listed_apart_from_an_offered_one(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["todo"].state == "installed"
    assert rows["notes"].state == "available"


async def test_an_app_is_started_by_the_name_it_declares(tmp_path: Path) -> None:
    """A folder's name is not a declaration.

    `examples/todo` declares itself as `todo-app`, so the Hub files it under the
    name it was asked for and runs it under the name its environment answers to.
    """
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "todo"})
        await tools.invoke(
            "configure_app",
            {"app_name": "todo", "values": {"db_path": str(tmp_path / "todo.db")}},
        )
        started = await tools.invoke("start_app", {"app_name": "todo", "secrets": {}})

    assert isinstance(started, RunningApp)
    assert started.diagnostic is None


async def test_removing_an_app_deletes_its_environment_and_leaves_its_data(
    tmp_path: Path,
) -> None:
    root = tmp_path / "hub"
    data = tmp_path / "todo.db"
    data.write_text("a todo", encoding="utf-8")

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "todo"})
        await tools.invoke("remove_app", {"app_name": "todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    assert [row.state for row in listed.apps if row.app_name == "todo"] == ["available"]
    assert not environment(root, "todo").exists()
    assert data.is_file()


async def test_an_app_no_source_offers_is_a_diagnostic(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("install_app", {"app_name": "absent"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.candidate_absent"


async def test_a_folder_that_installs_no_app_is_a_diagnostic(tmp_path: Path) -> None:
    source = tmp_path / "packages"
    write_project(source / "plain", name="plain-package", declares=False)
    (source / "plain" / "plain_package.py").write_text("", encoding="utf-8")

    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(source)})
        answered = await tools.invoke("install_app", {"app_name": "plain"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code in {"hub.no_app_declared", "hub.install_failed"}


async def test_an_uninstallable_folder_is_a_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`uv` is how an App gets an environment; without it, installing says so."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        answered = await tools.invoke("install_app", {"app_name": "todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.install_failed"
    assert "uv" in answered.diagnostic.message


async def test_a_traversing_app_name_deletes_nothing(tmp_path: Path) -> None:
    """ADR-024 exposes every Hub Tool on the Agent channel, so this is a
    model-controlled string reaching shutil.rmtree."""
    root = tmp_path / "hub" / "deep"
    (root / "envs" / "todo").mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")

    async with hub(root) as tools:
        with pytest.raises(ToolInputValidationError):
            await tools.invoke("remove_app", {"app_name": "../../../victim"})

    assert (victim / "keep.txt").is_file()


async def test_an_absolute_app_name_is_refused(tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.mkdir()

    async with hub(tmp_path / "hub") as tools:
        with pytest.raises(ToolInputValidationError):
            await tools.invoke("remove_app", {"app_name": str(victim)})

    assert victim.is_dir()


@pytest.mark.parametrize("name", ["../../victim", "..", ".", "", "a/b", "x/../y"])
def test_environment_refuses_a_name_that_does_not_resolve_inside(tmp_path: Path, name: str) -> None:
    """The sink's guarantee: whatever this platform reads as leaving the root."""
    with pytest.raises(AppNameInvalid):
        hub_environment(tmp_path, name)


@pytest.mark.parametrize("name", ["../../victim", "..", ".", "", "a/b", "a\\b", "C:x"])
def test_a_tool_input_refuses_a_name_that_is_not_one_segment(name: str) -> None:
    """The boundary's constraint, which is platform-independent.

    A backslash and a colon are legal in a POSIX filename and are separators on
    Windows, so the field refuses them on both rather than only where the Hub
    happens to run.
    """
    with pytest.raises(ValidationError):
        AppName(app_name=name)


def test_environment_answers_for_a_plain_name(tmp_path: Path) -> None:
    assert hub_environment(tmp_path, "todo") == tmp_path / "envs" / "todo"
