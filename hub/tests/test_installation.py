"""Installing an App gives it an environment of its own."""

from pathlib import Path

import pytest

from tests_support import SAMPLES, hub, write_project
from vibepy_hub.installer import environment, interpreter
from vibepy_hub.models import AppListing, Installation, RunningApp


async def test_installing_the_todo_app_creates_its_own_environment(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
        installed = await tools.invoke("install_app", {"app_name": "todo"})

    assert isinstance(installed, Installation)
    assert installed.diagnostic is None
    assert installed.app.name == "Todo"
    assert installed.app.has_pages is True
    assert interpreter(environment(root, "todo")).is_file()


async def test_an_installed_app_is_listed_from_its_environment(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
        await tools.invoke("install_app", {"app_name": "todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["todo"].state == "installed"
    assert rows["notes"].state == "available"


async def test_removing_an_app_deletes_its_environment_and_leaves_its_data(
    tmp_path: Path,
) -> None:
    root = tmp_path / "hub"
    data = tmp_path / "todo.db"
    data.write_text("a todo", encoding="utf-8")

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
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


async def test_a_missing_uv_is_a_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
        answered = await tools.invoke("install_app", {"app_name": "todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.install_failed"
    assert "uv" in answered.diagnostic.message


async def test_an_app_is_started_by_the_name_it_declares(tmp_path: Path) -> None:
    """A folder's name is not a declaration.

    `samples/todo` declares itself as `todo-app`, so the Hub files it under the
    name it was asked for and runs it under the name its environment answers to.
    """
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
        await tools.invoke("install_app", {"app_name": "todo"})
        await tools.invoke(
            "configure_app",
            {"app_name": "todo", "values": {"db_path": str(tmp_path / "todo.db")}},
        )
        started = await tools.invoke("start_app", {"app_name": "todo", "secrets": {}})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(started, RunningApp)
    assert started.diagnostic is None
    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["todo"].state == "running"
    assert rows["todo"].version == "0.0.0"


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
