"""What a channel's running window is, and what it is not.

There is no object for a app that is not running. These tests address the
window itself, which is why every one of them is an ``async with``.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from pydantic import BaseModel

from vibepy_core import Channel, Principal
from vibepy_core.app import (
    AppDefinition,
    Lifespan,
    NoConfig,
    page_runtime_for,
    read_window_record,
    tool_runtime_for,
)
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
                    read_only=True,
                ),
                handler=read,
            )
        ],
        pages=[
            Page(
                definition=PageDefinition(
                    name="journal", route="/journal", title="Journal", tools=frozenset({"read"})
                ),
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

    async with tool_runtime_for(
        journal_definition(log), journal_lifespan(log), config={}, channel=Channel.AGENT
    ):
        assert log == ["acquired"]

    assert log == ["acquired", "released"]


async def test_a_tool_receives_what_the_lifespan_yielded() -> None:
    log: list[str] = []

    async with tool_runtime_for(
        journal_definition(log), journal_lifespan(log), config={}, channel=Channel.AGENT
    ) as tools:
        result = await tools.invoke("read", {}, principal=Principal(id="test"))

    assert isinstance(result, Entry)
    assert result.seen == "journal"
    assert log == ["acquired", "invoked", "released"]


async def test_two_windows_enter_two_lifespans() -> None:
    log: list[str] = []
    definition = journal_definition(log)

    async with tool_runtime_for(
        definition, journal_lifespan(log), config={}, channel=Channel.AGENT
    ) as first:
        async with tool_runtime_for(
            definition, journal_lifespan(log), config={}, channel=Channel.AGENT
        ) as second:
            first_seen = await first.invoke("read", {}, principal=Principal(id="test"))
            second_seen = await second.invoke("read", {}, principal=Principal(id="test"))

    assert first is not second
    assert isinstance(first_seen, Entry)
    assert isinstance(second_seen, Entry)
    assert log.count("acquired") == 2
    assert log.count("released") == 2


async def test_a_page_reaches_a_tool_through_the_window() -> None:
    log: list[str] = []

    async with page_runtime_for(journal_definition(log), journal_lifespan(log), config={}) as pages:
        await pages.render("journal", principal=Principal(id="operator"))

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
            journal_definition(log),
            lambda _config: FailingAcquire(log),
            config={},
            channel=Channel.AGENT,
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
        async with tool_runtime_for(
            journal_definition(log), both, config={}, channel=Channel.AGENT
        ):
            pass  # pragma: no cover - the block is never entered

    assert log == ["earlier acquired", "attempted", "earlier released"]


async def test_a_closing_window_records_that_it_closed(caplog: pytest.LogCaptureFixture) -> None:
    """The lifespan's exit crosses the process boundary as one `WindowRecord`.

    The record is written after the resource is released, so a reader of a
    framework process's standard error learns the window is gone and not merely
    that the runtime was handed back.
    """
    log: list[str] = []
    with caplog.at_level(logging.INFO, logger="vibepy_core"):
        async with tool_runtime_for(
            journal_definition(log), journal_lifespan(log), config={}, channel=Channel.AGENT
        ):
            assert [line for line in caplog.messages if read_window_record(line)] == []

    closed = [read_window_record(line) for line in caplog.messages]
    written = [record for record in closed if record is not None]
    assert len(written) == 1
    assert written[0].app_id == "journal"
    assert written[0].channel is Channel.AGENT
    assert log == ["acquired", "released"]


async def test_a_window_that_fails_to_close_records_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A window that ends by raising is one report, not a report and a record."""
    log: list[str] = []
    with caplog.at_level(logging.INFO, logger="vibepy_core"), pytest.raises(Boom):
        async with tool_runtime_for(
            journal_definition(log),
            lambda _config: FailingAcquire(log),
            config={},
            channel=Channel.AGENT,
        ):
            pass  # pragma: no cover - the block is never entered

    assert [record for line in caplog.messages if (record := read_window_record(line))] == []
