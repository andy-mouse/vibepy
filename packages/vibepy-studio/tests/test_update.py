"""Updating an installed App keeps what the Hub holds for it."""

import shutil
from pathlib import Path

import pytest

from tests_support import FIXTURES, bumped_fixture_wheel, studio
from vibepy_studio.operating.internals import read_state
from vibepy_studio.operating.internals.routing import ROUTES
from vibepy_studio.operating.models import AppListing, Installation


@pytest.fixture(scope="session")
def newer_wheelhouse(tmp_path_factory: pytest.TempPathFactory, wheelhouse: Path) -> Path:
    """The session wheelhouse plus a Todo one version up, built once."""
    out = tmp_path_factory.mktemp("newer")
    for wheel in wheelhouse.glob("*.whl"):
        shutil.copy(wheel, out / wheel.name)
    bumped_fixture_wheel(FIXTURES / "todo-app", out, version="0.2.0")
    return out


@pytest.fixture(scope="session")
def older_wheelhouse(tmp_path_factory: pytest.TempPathFactory, wheelhouse: Path) -> Path:
    """The session wheelhouse plus a Todo one version down, built once."""
    out = tmp_path_factory.mktemp("older")
    for wheel in wheelhouse.glob("*.whl"):
        shutil.copy(wheel, out / wheel.name)
    bumped_fixture_wheel(FIXTURES / "todo-app", out, version="0.0.1")
    return out


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_an_older_wheel_is_not_offered_as_an_update(
    installed: Path, older_wheelhouse: Path
) -> None:
    async with studio(installed) as tools:
        await tools.invoke("register_package_source", {"path": str(older_wheelhouse)})
        listed = await tools.invoke("list_apps", {})
        answered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})

    assert isinstance(listed, AppListing)
    row = next(row for row in listed.apps if row.app_name == "vibepy-todo")
    assert row.distribution_version == "0.1.0"
    assert row.available_version is None
    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.up_to_date"


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_a_newer_wheel_is_offered_and_updating_keeps_configuration_port_and_route(
    tmp_path: Path, installed: Path, newer_wheelhouse: Path
) -> None:
    async with studio(installed) as tools:
        await tools.invoke("register_package_source", {"path": str(newer_wheelhouse)})
        offered = await tools.invoke("list_apps", {})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.db"), "db_key": "k"},
            },
        )
        port_before = (await read_state(installed)).ports["vibepy-todo"]
        route_before = (installed / ROUTES / "vibepy-todo.yml").read_text(encoding="utf-8")

        updated = await tools.invoke("update_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(offered, AppListing)
    before = next(row for row in offered.apps if row.app_name == "vibepy-todo")
    assert before.state == "installed"
    assert before.version == "0.0.0"
    assert before.distribution_version == "0.1.0"
    assert before.available_version == "0.2.0"
    notes = next(row for row in offered.apps if row.app_name == "vibepy-notes")
    assert notes.available_version is None

    assert isinstance(updated, Installation)
    assert updated.diagnostic is None
    assert updated.app.distribution_version == "0.2.0"
    assert isinstance(listed, AppListing)
    row = next(row for row in listed.apps if row.app_name == "vibepy-todo")
    assert row.distribution_version == "0.2.0"
    assert row.available_version is None
    # Configuration, port and route are what survive an update. Whether the new
    # version then runs is `test_runtime.py`'s subject, and starting it here
    # would pay for a child process to learn nothing this test is about.
    assert row.configured is True
    assert (await read_state(installed)).ports["vibepy-todo"] == port_before
    assert (installed / ROUTES / "vibepy-todo.yml").read_text(encoding="utf-8") == route_before


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_updating_a_running_app_is_refused(
    tmp_path: Path, installed: Path, newer_wheelhouse: Path
) -> None:
    async with studio(installed) as tools:
        await tools.invoke("register_package_source", {"path": str(newer_wheelhouse)})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.db"), "db_key": "k"},
            },
        )
        await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        answered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})
        await tools.invoke("stop_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.already_running"
    assert isinstance(listed, AppListing)
    assert [row.distribution_version for row in listed.apps if row.app_name == "vibepy-todo"] == [
        "0.1.0"
    ]


async def test_updating_an_app_that_is_not_installed_is_a_diagnostic(tmp_path: Path) -> None:
    async with studio(tmp_path / "hub") as tools:
        answered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_installed"


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_updating_to_nothing_better_is_a_diagnostic(tmp_path: Path, installed: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    async with studio(installed) as tools:
        at_the_offered_version = await tools.invoke("update_app", {"app_name": "vibepy-todo"})
        await tools.invoke("register_package_source", {"path": str(empty)})
        no_longer_offered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})

    assert isinstance(at_the_offered_version, Installation)
    assert at_the_offered_version.diagnostic is not None
    assert at_the_offered_version.diagnostic.code == "hub.up_to_date"
    assert at_the_offered_version.app.state == "installed"
    assert isinstance(no_longer_offered, Installation)
    assert no_longer_offered.diagnostic is not None
    assert no_longer_offered.diagnostic.code == "hub.candidate_absent"
