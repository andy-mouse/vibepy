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
    """And it says a different call could succeed, which is what a category is for."""
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})

    assert isinstance(answered, RunningApp)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_installed"
    assert answered.diagnostic.category == ErrorCategory.CALLER


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


async def test_a_secret_supplied_at_start_reaches_the_app(tmp_path: Path) -> None:
    """`start_app`'s `secrets` is merged over what the Hub holds, and the App's
    window validates the result: without the secret it refuses to open."""
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke(
            "configure_app",
            {"app_name": "vibepy-todo", "values": {"db_path": str(tmp_path / "todo.json")}},
        )
        refused = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        started = await tools.invoke(
            "start_app", {"app_name": "vibepy-todo", "secrets": {"db_key": "supplied"}}
        )

    assert isinstance(refused, RunningApp)
    assert refused.diagnostic is not None
    assert refused.diagnostic.code == "config.invalid"
    assert "db_key" in refused.diagnostic.details["fields"]
    assert isinstance(started, RunningApp)
    assert started.diagnostic is None
    assert started.url is not None


async def test_starting_a_running_app_says_it_is_already_running(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            },
        )
        await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        again = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})

    assert isinstance(again, RunningApp)
    assert again.diagnostic is not None
    assert again.diagnostic.code == "hub.already_running"


async def test_two_overlapping_starts_answer_once(tmp_path: Path) -> None:
    """`hub.already_running` covers a child that is still starting.

    Two callers reaching `start_app` at once is what the Hub is built for:
    ToolRuntime permits concurrent invocations and does not serialize them. The
    claim is observable here, through Tools, so it needs no reach into
    `Processes`: one App runs, the other is told so, and the window closes over
    both.
    """
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            },
        )
        payload: dict[str, object] = {"app_name": "vibepy-todo", "secrets": {}}
        first, second = await asyncio.gather(
            tools.invoke("start_app", payload), tools.invoke("start_app", payload)
        )

    assert isinstance(first, RunningApp)
    assert isinstance(second, RunningApp)
    answered = [first, second]
    assert [one.url is not None for one in answered].count(True) == 1
    refused = next(one for one in answered if one.url is None)
    assert refused.diagnostic is not None
    assert refused.diagnostic.code == "hub.already_running"

    # And the second start left nothing running behind the first: a child this
    # window did not file is one it could not close.
    started = next(one for one in answered if one.url is not None)
    assert started.url is not None
    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", int(started.url.rsplit(":", 1)[1]))
