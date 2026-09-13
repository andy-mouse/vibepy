"""Installing an App gives it an environment of its own."""

import asyncio
import shutil
import sys
from pathlib import Path, PurePath

import pytest
from pydantic import SecretStr, ValidationError

from tests_support import AGENT, described_app, studio, write_wheel
from todo_app.entry import TodoStore
from vibepy_core.errors import ToolInputValidationError
from vibepy_studio.operating.internals import (
    AppNameInvalid,
    InstallFailed,
    read_facts,
    read_state,
    remove_environment,
)
from vibepy_studio.operating.internals import app_folder as root_app_folder
from vibepy_studio.operating.internals import environment as root_environment
from vibepy_studio.operating.models import (
    AppFacts,
    AppListing,
    AppName,
    Installation,
    RunningApp,
    SourceListing,
)


def environment(root: Path, app_name: str, /) -> Path:
    """Where Studio's declared root holds one App's environment, as the spec describes it."""
    return root / app_name / "env"


def forget_the_declaration(purelib: PurePath, /) -> None:
    """Delete an App's distribution metadata, leaving the environment that held it."""
    for info in Path(purelib).glob("vibepy_notes-*.dist-info"):
        shutil.rmtree(info)


def a_python_lives_in(env: Path, /) -> bool:
    """Whether that environment has an interpreter of its own."""
    return (env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")).is_file()


@pytest.mark.integration
async def test_installing_an_app_creates_an_environment_of_its_own(
    tmp_path: Path, wheelhouse: Path
) -> None:
    root = tmp_path / "root"

    async with studio(root) as tools:
        await tools.invoke("register_package_source", {"path": str(wheelhouse)}, principal=AGENT)
        installed = await tools.invoke("install_app", {"app_name": "vibepy-notes"}, principal=AGENT)

    assert isinstance(installed, Installation)
    assert installed.diagnostic is None
    assert installed.app.name == "Notes"
    assert installed.app.version == "0.1.0"
    assert a_python_lives_in(environment(root, "vibepy-notes"))


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_an_installed_app_is_listed_apart_from_an_offered_one(installed: Path) -> None:
    async with studio(installed) as tools:
        listed = await tools.invoke("list_apps", {}, principal=AGENT)

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["vibepy-notes"].state == "installed"
    assert rows["vibepy-timer"].state == "available"


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_the_facts_kept_carry_the_whole_description_the_app_wrote(installed: Path) -> None:
    """The record is what `describe` wrote, so what an App declares is not
    narrowed on its way into the operating role's own file."""
    facts = await read_facts(environment(installed, "vibepy-todo"))

    assert facts is not None
    assert facts.purelib is not None
    # The record is read back from JSON, and a path out of it reaches no file system.
    assert not hasattr(facts.purelib, "is_dir")
    assert facts.described.description.tools[0].name == "create_todo"
    assert [field.name for field in facts.described.description.config_fields] == [
        "db_path",
        "db_key",
    ]


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_an_app_is_started_by_the_name_it_declares(tmp_path: Path, installed: Path) -> None:
    """A folder's name is not a declaration.

    `fixtures/todo` is the distribution `vibepy-todo` and declares itself as
    `todo-app`, so the operating role files it under the distribution name it was asked for
    and runs it under the name its environment answers to.
    """
    async with studio(installed) as tools:
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.db"), "db_key": "k"},
            },
            principal=AGENT,
        )
        started = await tools.invoke(
            "start_app", {"app_name": "vibepy-todo", "secrets": {}}, principal=AGENT
        )

    # Starting is the assertion: `vibepy_core.serve` is addressed by the name
    # the App declares, so an App filed under `vibepy-todo` and run under
    # anything but `todo-app` does not answer at all.
    assert isinstance(started, RunningApp)
    assert started.diagnostic is None


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_removing_an_app_deletes_its_environment_and_leaves_its_data(
    tmp_path: Path, installed: Path
) -> None:
    """The data is written by the App's own store, at the path it was configured
    with, so the assertion means something: it is real, and it lies outside the
    environment `remove_app` deletes."""
    data = tmp_path / "todo.json"

    async with studio(installed) as tools:
        await tools.invoke(
            "configure_app",
            {"app_name": "vibepy-todo", "values": {"db_path": str(data), "db_key": "k"}},
            principal=AGENT,
        )
        await asyncio.to_thread(TodoStore(data, SecretStr("k")).create, "keep me")
        assert data.is_file()

        await tools.invoke("remove_app", {"app_name": "vibepy-todo"}, principal=AGENT)
        listed = await tools.invoke("list_apps", {}, principal=AGENT)

    assert isinstance(listed, AppListing)
    assert [row.state for row in listed.apps if row.app_name == "vibepy-todo"] == ["available"]
    assert not environment(installed, "vibepy-todo").exists()
    assert data.is_file()
    assert [todo.title for todo in TodoStore(data, SecretStr("k")).list_all()] == ["keep me"]


async def test_an_app_no_source_offers_is_a_diagnostic(tmp_path: Path) -> None:
    async with studio(tmp_path / "root") as tools:
        answered = await tools.invoke("install_app", {"app_name": "absent"}, principal=AGENT)

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "operating.candidate_absent"


async def test_a_wheel_that_declares_no_app_is_refused_before_an_environment_exists(
    tmp_path: Path,
) -> None:
    """A wheel's entry points are a fact, so the answer needs no install to find out."""
    source = tmp_path / "wheels"
    write_wheel(source, name="plain-package", version="1.0.0", declares=False)
    root = tmp_path / "root"

    async with studio(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)}, principal=AGENT)
        answered = await tools.invoke("install_app", {"app_name": "plain-package"}, principal=AGENT)

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "operating.no_app_declared"
    assert not environment(root, "plain-package").exists()


async def test_list_apps_offers_only_wheels_that_declare_an_app(tmp_path: Path) -> None:
    """The wheelhouse also carries the framework and its dependencies, resolved
    via `--find-links`; `list_apps` must not offer those as Apps."""
    source = tmp_path / "wheels"
    write_wheel(source, name="demo-app", version="1.0.0", declares=True)
    write_wheel(source, name="some-library", version="1.0.0", declares=False)

    async with studio(tmp_path / "root") as tools:
        registered = await tools.invoke(
            "register_package_source", {"path": str(source)}, principal=AGENT
        )
        listed = await tools.invoke("list_apps", {}, principal=AGENT)

    assert isinstance(registered, SourceListing)
    assert sorted((row.name, row.declares_app) for row in registered.candidates) == [
        ("demo-app", True),
        ("some-library", False),
    ]
    assert isinstance(listed, AppListing)
    assert [row.app_name for row in listed.apps] == ["demo-app"]


@pytest.mark.integration
async def test_an_uninstallable_folder_is_a_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wheelhouse: Path
) -> None:
    """`uv` is how an App gets an environment; without it, installing says so."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    async with studio(tmp_path / "root") as tools:
        await tools.invoke("register_package_source", {"path": str(wheelhouse)}, principal=AGENT)
        answered = await tools.invoke("install_app", {"app_name": "vibepy-todo"}, principal=AGENT)

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "operating.install_failed"
    assert "uv" in answered.diagnostic.message


async def test_a_traversing_app_name_deletes_nothing(tmp_path: Path) -> None:
    """ADR-024 exposes every operating Tool on the Agent channel, so this is a
    model-controlled string reaching shutil.rmtree."""
    root = tmp_path / "root" / "deep"
    (root / "todo" / "env").mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")

    async with studio(root) as tools:
        with pytest.raises(ToolInputValidationError):
            await tools.invoke("remove_app", {"app_name": "../../../victim"}, principal=AGENT)

    assert (victim / "keep.txt").is_file()


async def test_an_absolute_app_name_is_refused(tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.mkdir()

    async with studio(tmp_path / "root") as tools:
        with pytest.raises(ToolInputValidationError):
            await tools.invoke("remove_app", {"app_name": str(victim)}, principal=AGENT)

    assert victim.is_dir()


@pytest.mark.parametrize("name", ["../../victim", "..", ".", "", "a/b", "x/../y"])
def test_environment_refuses_a_name_that_does_not_resolve_inside(tmp_path: Path, name: str) -> None:
    """The sink's guarantee: whatever this platform reads as leaving the root."""
    with pytest.raises(AppNameInvalid):
        root_environment(tmp_path, name)


@pytest.mark.parametrize("name", ["../../victim", "..", ".", "", "a/b", "a\\b", "C:x"])
def test_a_tool_input_refuses_a_name_that_is_not_one_segment(name: str) -> None:
    """The boundary's constraint, which is platform-independent.

    A backslash and a colon are legal in a POSIX filename and are separators on
    Windows, so the field refuses them on both rather than only where Studio
    happens to run.
    """
    with pytest.raises(ValidationError):
        AppName(app_name=name)


def test_environment_answers_for_a_plain_name(tmp_path: Path) -> None:
    assert root_environment(tmp_path, "todo") == tmp_path / "todo" / "env"


@pytest.mark.integration
async def test_one_app_is_one_row_however_it_was_installed(
    tmp_path: Path, wheelhouse: Path
) -> None:
    """Installing by the distribution name lists that App once, not twice."""
    root = tmp_path / "root"

    async with studio(root) as tools:
        await tools.invoke("register_package_source", {"path": str(wheelhouse)}, principal=AGENT)
        await tools.invoke("install_app", {"app_name": "vibepy-notes"}, principal=AGENT)
        listed = await tools.invoke("list_apps", {}, principal=AGENT)

    assert isinstance(listed, AppListing)
    rows = [row for row in listed.apps if row.app_name == "vibepy-notes"]
    assert [row.state for row in rows] == ["installed"]
    assert [row.app_name for row in listed.apps].count("notes") == 0


async def test_a_folder_name_is_not_an_app_name(tmp_path: Path, wheelhouse: Path) -> None:
    async with studio(tmp_path / "root") as tools:
        await tools.invoke("register_package_source", {"path": str(wheelhouse)}, principal=AGENT)
        answered = await tools.invoke("install_app", {"app_name": "todo"}, principal=AGENT)

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "operating.candidate_absent"


@pytest.mark.integration
async def test_two_spellings_of_one_name_address_one_app(tmp_path: Path, wheelhouse: Path) -> None:
    """The specification compares names by normalizing them, and so does the operating role."""
    root = tmp_path / "root"

    async with studio(root) as tools:
        await tools.invoke("register_package_source", {"path": str(wheelhouse)}, principal=AGENT)
        await tools.invoke("install_app", {"app_name": "Vibepy_Notes"}, principal=AGENT)
        listed = await tools.invoke("list_apps", {}, principal=AGENT)

    assert isinstance(listed, AppListing)
    assert [row.state for row in listed.apps if row.app_name == "vibepy-notes"] == ["installed"]
    assert a_python_lives_in(environment(root, "vibepy-notes"))


@pytest.mark.integration
async def test_a_distribution_declaring_two_apps_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wheelhouse: Path
) -> None:
    """One environment holds one App, so two declarations are reported rather
    than one of them silently dropped."""
    root = tmp_path / "root"

    async def describes_two(env: Path, /, *, cwd: PurePath | None = None) -> tuple[AppFacts, ...]:
        return (
            AppFacts(
                described=described_app(
                    app_id="todo-app",
                    name="Todo",
                    app_name="todo-app",
                    distribution="vibepy-todo",
                )
            ),
            AppFacts(
                described=described_app(
                    app_id="timer-app",
                    name="Timer",
                    app_name="timer-app",
                    distribution="vibepy-todo",
                )
            ),
        )

    monkeypatch.setattr(
        "vibepy_studio.operating.internals.root.describe_environment", describes_two
    )

    async with studio(root) as tools:
        await tools.invoke("register_package_source", {"path": str(wheelhouse)}, principal=AGENT)
        answered = await tools.invoke("install_app", {"app_name": "vibepy-todo"}, principal=AGENT)

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "operating.multiple_apps_declared"
    assert "timer-app" in answered.diagnostic.details["declared"]
    assert not environment(root, "vibepy-todo").exists()


@pytest.mark.integration
async def test_a_failed_description_leaves_no_environment_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wheelhouse: Path
) -> None:
    """`purelib` and `describe` run in the App's interpreter, and a failure
    there is a diagnostic like every other failure here."""
    root = tmp_path / "root"

    async def refuse(env: Path, /) -> Path:
        raise InstallFailed("purelib", "the interpreter did not answer")

    monkeypatch.setattr("vibepy_studio.operating.internals.root.purelib", refuse)

    async with studio(root) as tools:
        await tools.invoke("register_package_source", {"path": str(wheelhouse)}, principal=AGENT)
        answered = await tools.invoke("install_app", {"app_name": "vibepy-notes"}, principal=AGENT)
        listed = await tools.invoke("list_apps", {}, principal=AGENT)

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "operating.install_failed"
    assert not environment(root, "vibepy-notes").exists()
    assert isinstance(listed, AppListing)
    assert [row.state for row in listed.apps if row.app_name == "vibepy-notes"] == ["available"]


async def test_an_environment_that_cannot_be_interrogated_is_a_row(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "vibepy-todo" / "env").mkdir(parents=True)

    async with studio(root) as tools:
        listed = await tools.invoke("list_apps", {}, principal=AGENT)

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["vibepy-todo"].diagnostic is not None
    assert rows["vibepy-todo"].diagnostic.code == "operating.facts_unreadable"


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_an_environment_that_no_longer_declares_its_app_says_so(
    installed: Path,
) -> None:
    async with studio(installed) as tools:
        facts = await read_facts(environment(installed, "vibepy-notes"))
        assert facts is not None and facts.purelib is not None
        await asyncio.to_thread(forget_the_declaration, facts.purelib)

        listed = await tools.invoke("list_apps", {}, principal=AGENT)

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["vibepy-notes"].diagnostic is not None
    assert rows["vibepy-notes"].diagnostic.code == "operating.declaration_missing"


@pytest.mark.integration
async def test_the_facts_kept_are_the_installed_apps_and_not_the_first_described(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wheelhouse: Path
) -> None:
    """The join is on identity, so position cannot decide it.

    An environment holds the App's own distribution and whatever that
    distribution depends on, and a dependency may declare an App of its own.
    Here one sorts first and is not the one installed.
    """
    root = tmp_path / "root"

    async def describes_two(env: Path, /, *, cwd: PurePath | None = None) -> tuple[AppFacts, ...]:
        return (
            AppFacts(
                described=described_app(
                    app_id="aardvark-app",
                    name="Aardvark",
                    version="9.9.9",
                    app_name="aardvark",
                    distribution="vibepy-aardvark",
                )
            ),
            AppFacts(
                described=described_app(
                    app_id="todo-app",
                    name="Todo",
                    app_name="todo-app",
                    distribution="vibepy-todo",
                )
            ),
        )

    monkeypatch.setattr(
        "vibepy_studio.operating.internals.root.describe_environment", describes_two
    )

    async with studio(root) as tools:
        await tools.invoke("register_package_source", {"path": str(wheelhouse)}, principal=AGENT)
        installed = await tools.invoke("install_app", {"app_name": "vibepy-todo"}, principal=AGENT)

    # The row carries the facts that were kept, so the name it reports is which
    # of the two descriptions was joined: taking the first would say Aardvark.
    assert isinstance(installed, Installation)
    assert installed.diagnostic is None
    assert installed.app.name == "Todo"
    assert installed.app.version == "0.0.0"


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_installing_again_after_a_removal_that_kept_the_port_reuses_it(
    installed: Path, wheelhouse: Path
) -> None:
    """A held port is the App's until `remove_app` forgets it; an install finding one reuses it.

    Reached by `update_app`, whose remove step keeps the port. Driven here through
    the state directly because no Tool removes an environment without its port.
    """
    before = (await read_state(installed / "vibepy-studio")).ports["vibepy-todo"]
    await remove_environment(environment(installed, "vibepy-todo"))

    async with studio(installed) as tools:
        again = await tools.invoke("install_app", {"app_name": "vibepy-todo"}, principal=AGENT)

    assert isinstance(again, Installation)
    assert again.diagnostic is None
    assert (await read_state(installed / "vibepy-studio")).ports["vibepy-todo"] == before


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_removing_an_app_deletes_its_whole_folder(installed: Path) -> None:
    """The folder is Studio's unit: what the App wrote beside its environment goes with it."""
    folder = installed / "vibepy-todo"
    (folder / "scratch.txt").write_text("mine", encoding="utf-8")

    async with studio(installed) as tools:
        await tools.invoke("remove_app", {"app_name": "vibepy-todo"}, principal=AGENT)

    assert not folder.exists()


def test_app_folder_is_the_environments_parent(tmp_path: Path) -> None:
    assert root_app_folder(tmp_path, "todo") == tmp_path / "todo"
    assert root_environment(tmp_path, "todo").parent == root_app_folder(tmp_path, "todo")


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_studios_own_folder_is_not_an_installed_app(installed: Path) -> None:
    """One rule for the root, and Studio is not an exception to it: its folder has no
    `env/`, so it is not one of the Apps the board lists."""
    assert (installed / "vibepy-studio" / "state.json").is_file()
    async with studio(installed) as tools:
        listed = await tools.invoke("list_apps", {}, principal=AGENT)
        assert isinstance(listed, AppListing)
        assert "vibepy-studio" not in {row.app_name for row in listed.apps}
