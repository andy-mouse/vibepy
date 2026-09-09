"""Installing an App gives it an environment of its own."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests_support import EXAMPLES, hub, write_project
from vibepy_core.errors import ToolInputValidationError
from vibepy_hub.internals import AppNameInvalid, InstallFailed, read_facts
from vibepy_hub.internals import environment as hub_environment
from vibepy_hub.models import AppFacts, AppListing, AppName, Installation, RunningApp


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
        installed = await tools.invoke("install_app", {"app_name": "vibepy-todo"})

    assert isinstance(installed, Installation)
    assert installed.diagnostic is None
    assert installed.app.name == "Todo"
    assert installed.app.version == "0.0.0"
    assert installed.app.has_pages is True
    assert a_python_lives_in(environment(root, "vibepy-todo"))


async def test_an_installed_app_is_listed_apart_from_an_offered_one(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["vibepy-todo"].state == "installed"
    assert rows["vibepy-notes"].state == "available"


async def test_an_app_is_started_by_the_name_it_declares(tmp_path: Path) -> None:
    """A folder's name is not a declaration.

    `examples/todo` is the distribution `vibepy-todo` and declares itself as
    `todo-app`, so the Hub files it under the distribution name it was asked for
    and runs it under the name its environment answers to.
    """
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.db"), "db_key": "k"},
            },
        )
        started = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        facts = await read_facts(environment(root, "vibepy-todo"))

    assert isinstance(started, RunningApp)
    assert started.diagnostic is None
    assert facts is not None
    assert facts.declared_name == "todo-app"


async def test_removing_an_app_deletes_its_environment_and_leaves_its_data(
    tmp_path: Path,
) -> None:
    root = tmp_path / "hub"
    data = tmp_path / "todo.db"
    data.write_text("a todo", encoding="utf-8")

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke("remove_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    assert [row.state for row in listed.apps if row.app_name == "vibepy-todo"] == ["available"]
    assert not environment(root, "vibepy-todo").exists()
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
        answered = await tools.invoke("install_app", {"app_name": "plain-package"})

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
        answered = await tools.invoke("install_app", {"app_name": "vibepy-todo"})

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


async def test_one_app_is_one_row_however_it_was_installed(tmp_path: Path) -> None:
    """Installing by the distribution name lists that App once, not twice."""
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    rows = [row for row in listed.apps if row.app_name == "vibepy-todo"]
    assert [row.state for row in rows] == ["installed"]
    assert [row.app_name for row in listed.apps].count("todo") == 0


async def test_a_folder_name_is_not_an_app_name(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        answered = await tools.invoke("install_app", {"app_name": "todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.candidate_absent"


async def test_two_spellings_of_one_name_address_one_app(tmp_path: Path) -> None:
    """The specification compares names by normalizing them, and so does the Hub."""
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "Vibepy_Todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    assert [row.state for row in listed.apps if row.app_name == "vibepy-todo"] == ["installed"]
    assert a_python_lives_in(environment(root, "vibepy-todo"))


async def test_a_distribution_declaring_two_apps_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One environment holds one App, so two declarations are reported rather
    than one of them silently dropped."""
    root = tmp_path / "hub"

    async def describes_two(env: Path, /) -> tuple[AppFacts, ...]:
        return (
            AppFacts(
                app_id="todo-app",
                name="Todo",
                version="0.0.0",
                declared_name="todo-app",
                distribution="vibepy-todo",
            ),
            AppFacts(
                app_id="second-app",
                name="Second",
                version="0.0.0",
                declared_name="second",
                distribution="vibepy-todo",
            ),
        )

    monkeypatch.setattr("vibepy_hub.tools.installation.describe", describes_two)

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        answered = await tools.invoke("install_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.multiple_apps_declared"
    assert "second" in answered.diagnostic.details["declared"]
    assert not environment(root, "vibepy-todo").exists()


async def test_a_failed_description_leaves_no_environment_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`purelib` and `describe` run in the App's interpreter, and a failure
    there is a diagnostic like every other failure here."""
    root = tmp_path / "hub"

    async def refuse(env: Path, /) -> Path:
        raise InstallFailed("purelib", "the interpreter did not answer")

    monkeypatch.setattr("vibepy_hub.tools.installation.purelib", refuse)

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        answered = await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.install_failed"
    assert not environment(root, "vibepy-todo").exists()
    assert isinstance(listed, AppListing)
    assert [row.state for row in listed.apps if row.app_name == "vibepy-todo"] == ["available"]


async def test_an_environment_that_cannot_be_interrogated_is_a_row(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    (root / "envs" / "vibepy-todo").mkdir(parents=True)

    async with hub(root) as tools:
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["vibepy-todo"].diagnostic is not None
    assert rows["vibepy-todo"].diagnostic.code == "hub.facts_unreadable"
