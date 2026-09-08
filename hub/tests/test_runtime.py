"""An installed App starts, answers, and stops."""

import asyncio
from pathlib import Path

import pytest

from tests_support import SAMPLES, hide_the_pytest_marker, http_status, hub
from vibepy_hub.models import AppListing, Installation, RunningApp


async def test_an_installed_app_starts_answers_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hide_the_pytest_marker(monkeypatch)
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
        await tools.invoke("install_app", {"app_name": "todo"})
        await tools.invoke(
            "configure_app",
            {"app_name": "todo", "values": {"db_path": str(tmp_path / "todo.db")}},
        )
        started = await tools.invoke("start_app", {"app_name": "todo", "secrets": {}})
        assert isinstance(started, RunningApp)
        assert started.diagnostic is None
        assert started.url is not None

        listed = await tools.invoke("list_apps", {})
        assert isinstance(listed, AppListing)
        assert [row.url for row in listed.apps if row.app_name == "todo"] == [started.url]
        assert [row.state for row in listed.apps if row.app_name == "todo"] == ["running"]

        assert await http_status(f"{started.url}/todos") == 200

        stopped = await tools.invoke("stop_app", {"app_name": "todo"})
        assert isinstance(stopped, RunningApp)
        assert stopped.state == "installed"


async def test_starting_an_app_that_is_not_installed_is_a_diagnostic(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("start_app", {"app_name": "todo", "secrets": {}})

    assert isinstance(answered, RunningApp)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_installed"


async def test_an_app_without_pages_reports_that_there_is_nothing_to_start(
    tmp_path: Path,
) -> None:
    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
        installed = await tools.invoke("install_app", {"app_name": "notes"})
        answered = await tools.invoke("start_app", {"app_name": "notes", "secrets": {}})

    assert isinstance(installed, Installation)
    assert installed.app.has_pages is False
    assert isinstance(answered, RunningApp)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.no_web_channel"


async def test_stopping_an_app_that_is_not_running_is_a_diagnostic(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("stop_app", {"app_name": "todo"})

    assert isinstance(answered, RunningApp)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_running"


async def test_closing_the_window_leaves_no_child_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hide_the_pytest_marker(monkeypatch)
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
        await tools.invoke("install_app", {"app_name": "todo"})
        await tools.invoke(
            "configure_app",
            {"app_name": "todo", "values": {"db_path": str(tmp_path / "todo.db")}},
        )
        started = await tools.invoke("start_app", {"app_name": "todo", "secrets": {}})
        assert isinstance(started, RunningApp)
        url = started.url
    assert url is not None

    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", int(url.rsplit(":", 1)[1]))
