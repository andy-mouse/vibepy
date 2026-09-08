"""The runtime lifecycle contract from docs/architecture/lifecycle.md.

The resource is acquired by a lifespan, so the tests observe the boundaries the
way an app does: what the lifespan recorded, read back through a Tool or through
the list the lifespan wrote into.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from types import TracebackType

import pytest
from pydantic import BaseModel

from vibepy.app import AppDefinition, AppRuntime
from vibepy.errors import AppRuntimeNotRunningError, AppRuntimeTransitionError
from vibepy.lifecycle import AppRuntimeState
from vibepy.tool import Tool, ToolContext, ToolDefinition


class Journal:
    """The app's application-scoped resource: what its lifespan recorded."""

    def __init__(self, entries: list[str]) -> None:
        self.entries = entries


class EmptyInput(BaseModel):
    pass


class Entries(BaseModel):
    entries: list[str]


async def read_entries(ctx: ToolContext[Journal], _payload: EmptyInput) -> Entries:
    return Entries(entries=list(ctx.dependencies.entries))


READ_ENTRIES = Tool(
    definition=ToolDefinition(
        name="read_entries",
        description="Report what the lifespan recorded",
        input_model=EmptyInput,
        output_model=Entries,
    ),
    handler=read_entries,
)


def journal_app(entries: list[str]) -> AppRuntime[Journal]:
    """An App whose lifespan writes into a list the caller keeps."""

    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[Journal]:
        entries.append("acquired")
        yield Journal(entries)
        entries.append("released")

    return AppRuntime(
        AppDefinition(
            plugin_id="journal-app",
            name="Journal",
            version="0.0.0",
            lifespan=lifespan,
            tools=[READ_ENTRIES],
            pages=[],
        )
    )


def test_a_constructed_runtime_is_created() -> None:
    assert journal_app([]).state is AppRuntimeState.CREATED


def test_construction_acquires_nothing() -> None:
    entries: list[str] = []

    journal_app(entries)

    assert entries == []


async def test_start_reaches_running() -> None:
    app = journal_app([])

    await app.start()

    assert app.state is AppRuntimeState.RUNNING


async def test_stop_reaches_stopped() -> None:
    app = journal_app([])
    await app.start()

    await app.stop()

    assert app.state is AppRuntimeState.STOPPED


async def test_the_lifespan_runs_on_both_sides_of_the_running_window() -> None:
    entries: list[str] = []
    app = journal_app(entries)

    await app.start()
    acquired = list(entries)
    await app.stop()

    assert acquired == ["acquired"]
    assert entries == ["acquired", "released"]


async def test_a_tool_receives_what_the_lifespan_yielded() -> None:
    app = journal_app([])
    await app.start()

    result = await app.tool_runtime.invoke("read_entries", {})

    await app.stop()
    assert result == Entries(entries=["acquired"])


async def test_two_runtimes_enter_two_lifespans() -> None:
    first_entries: list[str] = []
    second_entries: list[str] = []
    first = journal_app(first_entries)
    journal_app(second_entries)

    await first.start()

    assert first_entries == ["acquired"]
    assert second_entries == []
    await first.stop()


async def test_the_pre_yield_body_runs_while_starting() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[None]:
        entered.set()
        await release.wait()
        yield None

    app = AppRuntime(
        AppDefinition(
            plugin_id="slow-app",
            name="Slow",
            version="0.0.0",
            lifespan=lifespan,
            tools=[],
            pages=[],
        )
    )

    starting = asyncio.create_task(app.start())
    await entered.wait()
    assert app.state is AppRuntimeState.STARTING

    release.set()
    await starting
    assert app.state is AppRuntimeState.RUNNING
    await app.stop()


async def test_the_post_yield_body_runs_while_stopping() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[None]:
        yield None
        entered.set()
        await release.wait()

    app = AppRuntime(
        AppDefinition(
            plugin_id="slow-app",
            name="Slow",
            version="0.0.0",
            lifespan=lifespan,
            tools=[],
            pages=[],
        )
    )
    await app.start()

    stopping = asyncio.create_task(app.stop())
    await entered.wait()
    assert app.state is AppRuntimeState.STOPPING

    release.set()
    await stopping
    assert app.state is AppRuntimeState.STOPPED


async def test_starting_a_running_runtime_is_refused() -> None:
    app = journal_app([])
    await app.start()

    with pytest.raises(AppRuntimeTransitionError) as raised:
        await app.start()

    assert raised.value.plugin_id == "journal-app"
    assert raised.value.state is AppRuntimeState.RUNNING
    assert app.state is AppRuntimeState.RUNNING
    await app.stop()


async def test_stopped_is_terminal() -> None:
    app = journal_app([])
    await app.start()
    await app.stop()

    with pytest.raises(AppRuntimeTransitionError):
        await app.start()

    assert app.state is AppRuntimeState.STOPPED


async def test_stopping_before_starting_is_refused() -> None:
    app = journal_app([])

    with pytest.raises(AppRuntimeTransitionError) as raised:
        await app.stop()

    assert raised.value.state is AppRuntimeState.CREATED


async def test_concurrent_starts_admit_exactly_one() -> None:
    entries: list[str] = []
    app = journal_app(entries)

    outcomes = await asyncio.gather(app.start(), app.start(), return_exceptions=True)

    failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert len(failures) == 1
    assert isinstance(failures[0], AppRuntimeTransitionError)
    assert entries == ["acquired"]
    assert app.state is AppRuntimeState.RUNNING
    await app.stop()


def test_the_registries_are_readable_before_start() -> None:
    app = journal_app([])

    names = [definition.name for definition in app.tool_registry.definitions()]

    assert names == ["read_entries"]


def test_the_tool_runtime_is_unavailable_before_start() -> None:
    app = journal_app([])

    with pytest.raises(AppRuntimeNotRunningError) as raised:
        _ = app.tool_runtime

    assert raised.value.plugin_id == "journal-app"
    assert raised.value.state is AppRuntimeState.CREATED


def test_the_page_runtime_is_unavailable_before_start() -> None:
    app = journal_app([])

    with pytest.raises(AppRuntimeNotRunningError):
        _ = app.page_runtime


async def test_the_tool_runtime_is_unavailable_after_stop() -> None:
    app = journal_app([])
    await app.start()
    await app.stop()

    with pytest.raises(AppRuntimeNotRunningError) as raised:
        _ = app.tool_runtime

    assert raised.value.state is AppRuntimeState.STOPPED


async def test_one_running_window_has_one_tool_runtime() -> None:
    app = journal_app([])
    await app.start()

    assert app.tool_runtime is app.tool_runtime

    await app.stop()


class FailingAcquire(AbstractAsyncContextManager[None]):
    """A context manager whose acquisition raises.

    Written by hand rather than with ``@asynccontextmanager`` so that the release
    can assert it is never reached: the language reference places the acquisition
    outside the ``try`` of the ``async with`` expansion, so a failed ``__aenter__``
    never reaches ``__aexit__``. It subclasses the ABC rather than relying on a
    structural match, so the declaration type-checks regardless of how the stubs
    define it.
    """

    async def __aenter__(self) -> None:
        raise RuntimeError("the resource could not be acquired")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        raise AssertionError("release must not run when acquisition failed")


def app_with(lifespan: Callable[[], AbstractAsyncContextManager[None]]) -> AppRuntime[None]:
    return AppRuntime(
        AppDefinition(
            plugin_id="failing-app",
            name="Failing",
            version="0.0.0",
            lifespan=lifespan,
            tools=[],
            pages=[],
        )
    )


async def test_a_failed_acquisition_leaves_the_runtime_stopped() -> None:
    app = app_with(FailingAcquire)

    with pytest.raises(RuntimeError):
        await app.start()

    assert app.state is AppRuntimeState.STOPPED


async def test_a_failed_start_leaves_no_usable_runtime() -> None:
    app = app_with(FailingAcquire)

    with pytest.raises(RuntimeError):
        await app.start()

    with pytest.raises(AppRuntimeNotRunningError):
        _ = app.tool_runtime


async def test_an_earlier_resource_is_released_when_a_later_one_fails() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def first() -> AsyncGenerator[None]:
        events.append("first acquired")
        try:
            yield None
        finally:
            events.append("first released")

    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[None]:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(first())
            await stack.enter_async_context(FailingAcquire())
            yield None

    app = app_with(lifespan)

    with pytest.raises(RuntimeError):
        await app.start()

    assert events == ["first acquired", "first released"]
    assert app.state is AppRuntimeState.STOPPED


async def test_a_failed_release_still_reaches_stopped() -> None:
    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[None]:
        yield None
        raise RuntimeError("the resource could not be released")

    app = app_with(lifespan)
    await app.start()

    with pytest.raises(RuntimeError):
        await app.stop()

    assert app.state is AppRuntimeState.STOPPED
