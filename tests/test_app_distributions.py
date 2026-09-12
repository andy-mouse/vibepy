"""What every App in this repository guarantees, asked of every App there is.

These Apps are what the Hub's tests install, and the same hands write both.
That is a trap: a gate assembled from fixtures shaped to pass it proves only
that they were shaped that way. So each App is also held here to what the
framework asks of any App, with no Hub in the picture. One that an author
could not copy is not worth installing.

Nothing below names an App. The subjects come from `discover_apps()` and the
answers from `describe_app()`, which are the framework's own reader -- so an
App added to this repository joins these tests by existing, and a contract
that changes changes here once rather than once per App. What is stated per
App is only what is that App's own domain, and it is stated by exercising the
App rather than by restating its declaration.
"""

from pathlib import Path

import pytest
from pydantic import SecretStr

from timer_app.entry import TIMER_APP, Elapsed, timer_lifespan
from todo_app.entry import (
    TODO_APP,
    Completion,
    Todo,
    TodoConfig,
    TodoList,
    TodoStore,
    TodoStoreUnreadable,
    todo_lifespan,
)
from vibepy_core import Channel, ErrorCategory, Principal
from vibepy_core.app.composition import tool_runtime_for
from vibepy_core.app.package import AppRef, describe_app, discover_apps

DECLARED = sorted(discover_apps(), key=lambda ref: ref.app_name)
"""Every App this environment offers. Empty would pass every test below."""


def test_this_environment_offers_the_apps_the_tests_install() -> None:
    """The guard on the parametrization: an empty list makes it vacuous.

    The count is not asserted -- adding an App must not fail a test that has
    nothing to do with it -- but its absence is, because `discover_apps()`
    answering nothing would silently retire everything parametrized on it.
    """
    assert DECLARED


@pytest.mark.parametrize("ref", DECLARED, ids=lambda ref: ref.app_name)
def test_a_declared_app_is_one_the_framework_can_read(ref: AppRef) -> None:
    """Declaring is a promise that `describe_app` can be kept.

    It raises when the entry point does not resolve or does not name an
    `AppEntrypoint`, so this is the framework's own check rather than a second
    one written beside it.
    """
    described = describe_app(ref)

    assert described.app_id
    assert described.name
    assert described.version


@pytest.mark.parametrize("ref", DECLARED, ids=lambda ref: ref.app_name)
def test_an_app_with_pages_has_tools_for_them_to_reach(ref: AppRef) -> None:
    """`AGENTS.md`: a Page must not bypass Tools for business state.

    A Page cannot be followed from here into what it calls, but an App that
    declares Pages and no Tools has nothing for one to reach, and that is the
    shape the rule forbids.
    """
    described = describe_app(ref)

    if described.pages:
        assert described.tools


async def test_the_timer_app_answers_from_what_its_window_acquired() -> None:
    """Timer's own domain: the Tool reads the window's resource, not a clock.

    It is the only App here whose lifespan yields a value, so it is the only
    place that shows a handler receiving what the window acquired.
    """
    async with tool_runtime_for(
        TIMER_APP, timer_lifespan, config={}, channel=Channel.AGENT
    ) as tools:
        answered = Elapsed.model_validate(
            await tools.invoke("elapsed", {}, principal=Principal(id="test"))
        )

    assert answered.seconds >= 0.0


def test_a_todo_survives_a_new_store_over_the_same_path(tmp_path: Path) -> None:
    """Todo keeps what it is given, where it was told to keep it.

    An App whose store lived in memory would let a Page and an agent disagree
    the moment either restarts, which is the opposite of what
    `docs/architecture/app-model.md` asks of an App with two channels.
    """
    config = TodoConfig(db_path=tmp_path / "todo.json", db_key=SecretStr("k"))

    TodoStore(config.db_path, config.db_key).create("buy milk")

    assert [todo.title for todo in TodoStore(config.db_path, config.db_key).list_all()] == [
        "buy milk"
    ]


def test_a_file_stamped_under_another_key_is_refused(tmp_path: Path) -> None:
    """The secret Todo declares is one it uses, not one it merely names."""
    path = tmp_path / "todo.json"
    TodoStore(path, SecretStr("one")).create("buy milk")

    with pytest.raises(TodoStoreUnreadable):
        TodoStore(path, SecretStr("two")).list_all()


async def test_a_completed_todo_is_done_in_a_later_window(tmp_path: Path) -> None:
    """`complete_todo` persists, so a second window over the same store sees it.

    Two separate windows prove the change reached the store rather than only
    an in-memory value the first window happened to hold.
    """
    config = {"db_path": tmp_path / "todo.json", "db_key": "k"}

    async with tool_runtime_for(
        TODO_APP, todo_lifespan, config=config, channel=Channel.AGENT
    ) as tools:
        created = Todo.model_validate(
            await tools.invoke("create_todo", {"title": "buy milk"}, principal=Principal(id="test"))
        )
        assert created.done is False
        completed = Completion.model_validate(
            await tools.invoke("complete_todo", {"id": created.id}, principal=Principal(id="test"))
        )

    assert completed.diagnostic is None
    assert completed.todo is not None
    assert completed.todo.done is True

    async with tool_runtime_for(
        TODO_APP, todo_lifespan, config=config, channel=Channel.AGENT
    ) as tools:
        listed = TodoList.model_validate(
            await tools.invoke("list_todos", {}, principal=Principal(id="test"))
        )

    assert [todo.done for todo in listed.todos if todo.id == created.id] == [True]


async def test_completing_an_unknown_id_answers_a_diagnostic(tmp_path: Path) -> None:
    """An unknown id is the App's expected failure, and travels as data (ADR-029)."""
    config = {"db_path": tmp_path / "todo.json", "db_key": "k"}

    async with tool_runtime_for(
        TODO_APP, todo_lifespan, config=config, channel=Channel.AGENT
    ) as tools:
        completed = Completion.model_validate(
            await tools.invoke("complete_todo", {"id": 1}, principal=Principal(id="test"))
        )

    assert completed.todo is None
    assert completed.diagnostic is not None
    assert completed.diagnostic.code == "todo.not_found"
    assert completed.diagnostic.category == ErrorCategory.CALLER
    assert completed.diagnostic.details == {"id": "1"}
