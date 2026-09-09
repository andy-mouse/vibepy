"""An installed App starts, answers, and stops.

These run inside pytest and start Apps without hiding anything from them. That
is itself the contract: the Hub composes a child's environment rather than
passing on its own, so a served App is never told it is running the Hub's
current test or living in the Hub's virtual environment.
"""

import asyncio
from pathlib import Path

import pytest

from tests_support import EXAMPLES, http_status, hub
from vibepy_core.errors import ErrorCategory
from vibepy_hub.models import AppListing, Installation, RunningApp


async def test_an_installed_app_starts_answers_and_stops(tmp_path: Path) -> None:
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
        assert isinstance(started, RunningApp)
        assert started.diagnostic is None
        assert started.url is not None

        listed = await tools.invoke("list_apps", {})
        assert isinstance(listed, AppListing)
        assert [row.url for row in listed.apps if row.app_name == "vibepy-todo"] == [started.url]
        assert [row.state for row in listed.apps if row.app_name == "vibepy-todo"] == ["running"]

        assert await http_status(f"{started.url}/todos") == 200

        stopped = await tools.invoke("stop_app", {"app_name": "vibepy-todo"})
        assert isinstance(stopped, RunningApp)
        assert stopped.state == "installed"


async def test_starting_an_app_that_is_not_installed_is_a_diagnostic(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})

    assert isinstance(answered, RunningApp)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_installed"


async def test_an_app_without_pages_reports_that_there_is_nothing_to_start(
    tmp_path: Path,
) -> None:
    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        installed = await tools.invoke("install_app", {"app_name": "vibepy-notes"})
        answered = await tools.invoke("start_app", {"app_name": "vibepy-notes", "secrets": {}})

    assert isinstance(installed, Installation)
    assert installed.app.has_pages is False
    assert isinstance(answered, RunningApp)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.no_web_channel"


async def test_stopping_an_app_that_is_not_running_is_a_diagnostic(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("stop_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, RunningApp)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_running"


async def test_closing_the_window_leaves_no_child_behind(tmp_path: Path) -> None:
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
        assert isinstance(started, RunningApp)
        url = started.url
    assert url is not None

    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", int(url.rsplit(":", 1)[1]))


async def test_an_app_whose_window_rejects_its_configuration_does_not_start(
    tmp_path: Path,
) -> None:
    """Starting means answering, and a window that will not open never answers.

    Todo declares `db_path`, so an empty configuration is refused as the window
    opens. The Hub must report that rather than hand over a url.
    """
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        started = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})

    assert isinstance(started, RunningApp)
    assert started.url is None
    assert started.diagnostic is not None
    assert started.diagnostic.code == "config.invalid"
    assert started.diagnostic.category == ErrorCategory.CALLER
    assert "db_path" in started.diagnostic.details["fields"]
