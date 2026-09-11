"""Updating an installed App keeps what the Hub holds for it."""

import shutil
from pathlib import Path

import pytest

from tests_support import FIXTURES, bumped_fixture_wheel, hub
from vibepy_hub.internals import read_state
from vibepy_hub.internals.routing import ROUTES
from vibepy_hub.models import AppListing, Installation, RunningApp


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
    async with hub(installed) as tools:
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
async def test_a_newer_wheel_shows_as_an_available_version(
    installed: Path, newer_wheelhouse: Path
) -> None:
    async with hub(installed) as tools:
        await tools.invoke("register_package_source", {"path": str(newer_wheelhouse)})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    row = next(row for row in listed.apps if row.app_name == "vibepy-todo")
    assert row.state == "installed"
    assert row.version == "0.0.0"
    assert row.distribution_version == "0.1.0"
    assert row.available_version == "0.2.0"
    notes = next(row for row in listed.apps if row.app_name == "vibepy-notes")
    assert notes.available_version is None


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_updating_keeps_configuration_port_and_route(
    tmp_path: Path, installed: Path, newer_wheelhouse: Path
) -> None:
    async with hub(installed) as tools:
        await tools.invoke("register_package_source", {"path": str(newer_wheelhouse)})
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
        started = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        await tools.invoke("stop_app", {"app_name": "vibepy-todo"})

    assert isinstance(updated, Installation)
    assert updated.diagnostic is None
    assert updated.app.distribution_version == "0.2.0"
    assert isinstance(listed, AppListing)
    row = next(row for row in listed.apps if row.app_name == "vibepy-todo")
    assert row.distribution_version == "0.2.0"
    assert row.available_version is None
    assert row.configured is True
    assert (await read_state(installed)).ports["vibepy-todo"] == port_before
    assert (installed / ROUTES / "vibepy-todo.yml").read_text(encoding="utf-8") == route_before
    assert isinstance(started, RunningApp)
    assert started.diagnostic is None


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_updating_an_app_at_the_offered_version_is_a_diagnostic(installed: Path) -> None:
    async with hub(installed) as tools:
        answered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.up_to_date"
    assert answered.app.state == "installed"


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_updating_a_running_app_is_refused(
    tmp_path: Path, installed: Path, newer_wheelhouse: Path
) -> None:
    async with hub(installed) as tools:
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
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_installed"


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_updating_an_app_the_source_no_longer_offers_is_a_diagnostic(
    tmp_path: Path, installed: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    async with hub(installed) as tools:
        await tools.invoke("register_package_source", {"path": str(empty)})
        answered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.candidate_absent"
