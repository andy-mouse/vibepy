"""What a channel's running window is, and what it is not.

There is no object for a app that is not running. These tests address the
window itself, which is why every one of them is an ``async with``.
"""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from pydantic import BaseModel

from tests.lifecycle import no_dependencies
from vibepy_core.app import (
    AppDefinition,
    Lifespan,
    NoConfig,
    page_runtime_for,
    tool_runtime_for,
)
from vibepy_core.errors import PageNameConflictError, ToolNameConflictError
from vibepy_core.page import Page, PageContext, PageDefinition
from vibepy_core.tool import Tool, ToolContext, ToolDefinition


class Journal:
    """The app's resource. Records what the lifespan did to it."""

    def __init__(self, log: list[str]) -> None:
        self.log = log


class EmptyInput(BaseModel):
    pass


class Entry(BaseModel):
    seen: str


def journal_definition(log: list[str]) -> AppDefinition[Journal, NoConfig]:
    async def read(ctx: ToolContext[Journal], _payload: EmptyInput) -> Entry:
        ctx.dependencies.log.append("invoked")
        return Entry(seen=ctx.app_id)

    async def render(ctx: PageContext) -> None:
        await ctx.tools.invoke("read", {})

    return AppDefinition(
        app_id="journal",
        name="Journal",
        version="0.0.0",
        config=NoConfig,
        tools=[
            Tool(
                definition=ToolDefinition(
                    name="read",
                    description="Read the journal",
                    input_model=EmptyInput,
                    output_model=Entry,
                ),
                handler=read,
            )
        ],
        pages=[
            Page(
                definition=PageDefinition(name="journal", route="/journal", title="Journal"),
                handler=render,
            )
        ],
    )


def journal_lifespan(log: list[str]) -> Lifespan[Journal, NoConfig]:
    @asynccontextmanager
    async def lifespan(_config: NoConfig) -> AsyncGenerator[Journal]:
        log.append("acquired")
        try:
            yield Journal(log)
        finally:
            log.append("released")

    return lifespan


async def test_the_lifespan_runs_on_both_sides_of_the_window() -> None:
    log: list[str] = []

    async with tool_runtime_for(journal_definition(log), journal_lifespan(log), config={}):
        assert log == ["acquired"]

    assert log == ["acquired", "released"]


async def test_a_tool_receives_what_the_lifespan_yielded() -> None:
    log: list[str] = []

    async with tool_runtime_for(journal_definition(log), journal_lifespan(log), config={}) as tools:
        result = await tools.invoke("read", {})

    assert isinstance(result, Entry)
    assert result.seen == "journal"
    assert log == ["acquired", "invoked", "released"]


async def test_two_windows_enter_two_lifespans() -> None:
    log: list[str] = []
    definition = journal_definition(log)

    async with tool_runtime_for(definition, journal_lifespan(log), config={}) as first:
        async with tool_runtime_for(definition, journal_lifespan(log), config={}) as second:
            first_seen = await first.invoke("read", {})
            second_seen = await second.invoke("read", {})

    assert first is not second
    assert isinstance(first_seen, Entry)
    assert isinstance(second_seen, Entry)
    assert log.count("acquired") == 2
    assert log.count("released") == 2


async def test_a_page_reaches_a_tool_through_the_window() -> None:
    log: list[str] = []

    async with page_runtime_for(journal_definition(log), journal_lifespan(log), config={}) as pages:
        await pages.render("journal")

    assert log == ["acquired", "invoked", "released"]


class Boom(Exception):
    """A failure inside the app's own lifespan."""


class FailingAcquire(AbstractAsyncContextManager[Journal]):
    """A lifespan that raises on the way in.

    Written as a class rather than a generator because a generator whose body
    raises before its ``yield`` has an unreachable ``yield``.
    """

    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def __aenter__(self) -> Journal:
        self._log.append("attempted")
        raise Boom("acquisition failed")

    async def __aexit__(self, *exc_info: object) -> None:
        self._log.append("released")


async def test_a_failing_acquisition_reaches_the_caller() -> None:
    log: list[str] = []

    with pytest.raises(Boom):
        async with tool_runtime_for(
            journal_definition(log), lambda _config: FailingAcquire(log), config={}
        ):
            pass  # pragma: no cover - the block is never entered

    assert log == ["attempted"]


async def test_an_earlier_resource_is_released_when_a_later_one_fails() -> None:
    """The resource that was acquired is released; the one that failed is not.

    ``__aexit__`` is registered only after ``__aenter__`` returns.
    """
    log: list[str] = []

    @asynccontextmanager
    async def earlier() -> AsyncGenerator[None]:
        log.append("earlier acquired")
        try:
            yield None
        finally:
            log.append("earlier released")

    @asynccontextmanager
    async def both(_config: NoConfig) -> AsyncGenerator[Journal]:
        async with earlier(), FailingAcquire(log) as journal:
            yield journal

    with pytest.raises(Boom):
        async with tool_runtime_for(journal_definition(log), both, config={}):
            pass  # pragma: no cover - the block is never entered

    assert log == ["earlier acquired", "attempted", "earlier released"]


async def test_two_pages_declaring_one_name_do_not_open_a_window() -> None:
    """A name is what the framework addresses a Page by, so it refuses the pair.

    Refused where a declaration becomes a registry, which is before the window
    opens and therefore before any route can exist.
    """

    async def render(_ctx: PageContext) -> None:
        return None

    definition: AppDefinition[None, NoConfig] = AppDefinition(
        app_id="collides",
        name="Collides",
        version="0.0.0",
        config=NoConfig,
        tools=[],
        pages=[
            Page(
                definition=PageDefinition(name="todos", route="/todos", title="Todos"),
                handler=render,
            ),
            Page(
                definition=PageDefinition(name="todos", route="/todo-list", title="List"),
                handler=render,
            ),
        ],
    )

    with pytest.raises(PageNameConflictError) as error:
        async with page_runtime_for(definition, no_dependencies, config={}):
            raise AssertionError("the window must not open")

    assert error.value.page_name == "todos"
    assert {error.value.route, error.value.conflicting_route} == {"/todos", "/todo-list"}


async def test_two_tools_declaring_one_name_do_not_open_a_window() -> None:
    """A channel enumerates the declaration, so a duplicate name would publish
    two Tools and answer both with one. ADR-027."""

    async def read(_ctx: ToolContext[None], _payload: EmptyInput) -> Entry:
        return Entry(seen="either")

    def declared(description: str) -> Tool[None]:
        return Tool(
            definition=ToolDefinition(
                name="read",
                description=description,
                input_model=EmptyInput,
                output_model=Entry,
            ),
            handler=read,
        )

    definition: AppDefinition[None, NoConfig] = AppDefinition(
        app_id="collides",
        name="Collides",
        version="0.0.0",
        config=NoConfig,
        tools=[declared("first"), declared("second")],
        pages=[],
    )

    with pytest.raises(ToolNameConflictError) as error:
        async with tool_runtime_for(definition, no_dependencies, config={}):
            raise AssertionError("the window must not open")

    assert error.value.tool_name == "read"
