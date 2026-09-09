"""The execution-semantics contract from docs/architecture/runtime.md.

Two invocations of one App overlap, each with its own ToolContext, over one
application-scoped resource. This test is constitutional: it stays for the life
of the project.

The proof is a barrier rather than a duration. An ``asyncio.Barrier(2)`` opens
only once two waiters are inside it, and it is reached through
``ctx.dependencies``, so it opens only if the two invocations overlap and also
received the same resource. The handler logs on both sides of the barrier, so
overlap is asserted as an order of events rather than as the absence of a
failure. A passing run asserts nothing about elapsed time; ``asyncio.timeout``
exists only to turn the deadlock of a serialized runtime into a failure.

The log is read back through a Tool rather than by holding the resource, so the
test observes application-scoped state only through the App's public surface.

Where a test needs two windows of one App at once - a Web window to render
through and an Agent-shaped window to read the log from - it composes both over
one lifespan of its own. That is an arrangement the test makes, not a guarantee
the framework offers: ADR-017 puts each channel in its own process.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from mcp.client import Client
from nicegui import ui
from nicegui.testing import User
from pydantic import BaseModel

from vibepy_core.adapters.mcp import build_mcp_server
from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import AppDefinition, Lifespan, NoConfig, page_runtime_for, tool_runtime_for
from vibepy_core.page import Page, PageContext, PageDefinition
from vibepy_core.tool import Tool, ToolContext, ToolDefinition, ToolRuntime

PARTIES = 2
DEADLOCK_TIMEOUT_SECONDS = 5
ARRIVALS_THEN_DEPARTURES = ["arrived", "arrived", "departed", "departed"]


class EmptyInput(BaseModel):
    pass


class Meeting(BaseModel):
    """What one invocation reports about itself once the barrier opens."""

    invocation_id: str
    dependency_id: int


class LogSnapshot(BaseModel):
    entries: list[str]


class Rendezvous:
    """The app's application-scoped resource: one barrier and one arrival log."""

    def __init__(self) -> None:
        self.barrier = asyncio.Barrier(PARTIES)
        self.log: list[str] = []


def rendezvous_lifespan() -> Lifespan[Rendezvous, NoConfig]:
    """One Rendezvous, however many windows are opened over it."""
    rendezvous = Rendezvous()

    @asynccontextmanager
    async def lifespan(_config: NoConfig) -> AsyncGenerator[Rendezvous]:
        yield rendezvous

    return lifespan


async def meet(ctx: ToolContext[Rendezvous], _payload: EmptyInput) -> Meeting:
    """Return only once a second invocation is inside the same barrier."""
    ctx.dependencies.log.append("arrived")
    await ctx.dependencies.barrier.wait()
    ctx.dependencies.log.append("departed")
    return Meeting(invocation_id=ctx.invocation_id, dependency_id=id(ctx.dependencies))


async def read_log(ctx: ToolContext[Rendezvous], _payload: EmptyInput) -> LogSnapshot:
    return LogSnapshot(entries=list(ctx.dependencies.log))


MEET = Tool(
    definition=ToolDefinition(
        name="meet",
        description="Wait for a concurrent invocation, then report this one's identity",
        input_model=EmptyInput,
        output_model=Meeting,
    ),
    handler=meet,
)

READ_LOG = Tool(
    definition=ToolDefinition(
        name="read_log",
        description="Report the arrival and departure log",
        input_model=EmptyInput,
        output_model=LogSnapshot,
    ),
    handler=read_log,
)


async def meeting_page(ctx: PageContext) -> None:
    """The render path: a Page reaches the Tool through ToolInvoker."""
    await ctx.tools.invoke("meet", {})


async def meeting_button_page(ctx: PageContext) -> None:
    """The interaction path: a click invokes the Tool, then the label reflects it.

    The label is what ``should_see`` waits on. NiceGUI dispatches an async event
    handler as a background task, so the click returns before the invocation
    finishes, and the UI is the documented place to observe that it did.
    """
    status = ui.label("waiting")

    async def meet_now() -> None:
        await ctx.tools.invoke("meet", {})
        status.set_text("met")

    ui.button("Meet", on_click=meet_now)


RENDEZVOUS = AppDefinition(
    app_id="rendezvous-app",
    name="Rendezvous",
    version="0.0.0",
    config=NoConfig,
    tools=[MEET, READ_LOG],
    pages=[
        Page(
            definition=PageDefinition(name="meeting", route="/meeting", title="Meeting"),
            handler=meeting_page,
        ),
        Page(
            definition=PageDefinition(
                name="meeting_button", route="/meeting-button", title="Meeting"
            ),
            handler=meeting_button_page,
        ),
    ],
)


async def logged(tools: ToolRuntime[Rendezvous]) -> list[str]:
    snapshot = await tools.invoke("read_log", {})
    assert isinstance(snapshot, LogSnapshot)
    return snapshot.entries


async def overlap(tools: ToolRuntime[Rendezvous]) -> tuple[Meeting, Meeting]:
    """Invoke one window's Tool twice concurrently and return both reports."""
    async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
        first, second = await asyncio.gather(
            tools.invoke("meet", {}),
            tools.invoke("meet", {}),
        )

    assert isinstance(first, Meeting)
    assert isinstance(second, Meeting)
    return first, second


async def test_two_invocations_are_in_flight_at_once() -> None:
    async with tool_runtime_for(RENDEZVOUS, rendezvous_lifespan(), config={}) as tools:
        await overlap(tools)

        assert await logged(tools) == ARRIVALS_THEN_DEPARTURES


async def test_concurrent_invocations_receive_independent_contexts() -> None:
    async with tool_runtime_for(RENDEZVOUS, rendezvous_lifespan(), config={}) as tools:
        first, second = await overlap(tools)

    assert first.invocation_id != second.invocation_id


async def test_concurrent_invocations_share_app_scoped_dependencies() -> None:
    async with tool_runtime_for(RENDEZVOUS, rendezvous_lifespan(), config={}) as tools:
        first, second = await overlap(tools)

    assert first.dependency_id == second.dependency_id


async def test_two_page_renders_are_in_flight_at_once() -> None:
    """PageRuntime's docstring claims it does not serialize renders; this holds it to that."""
    lifespan = rendezvous_lifespan()

    async with page_runtime_for(RENDEZVOUS, lifespan, config={}) as pages:
        async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
            await asyncio.gather(
                pages.render("meeting"),
                pages.render("meeting"),
            )

        async with tool_runtime_for(RENDEZVOUS, lifespan, config={}) as tools:
            assert await logged(tools) == ARRIVALS_THEN_DEPARTURES


async def test_two_agent_channel_calls_are_in_flight_at_once() -> None:
    """The Agent channel's request concurrency is the SDK's, and this pins it.

    The protocol permits concurrent in-flight requests without requiring a
    server to process them concurrently, and the SDK documents no concurrency
    guarantee for request handling - only the serialized exception, its
    ``inline_methods``, which the runner sets to ``{"initialize"}``. The SDK
    does spawn everything else, so two ``tools/call`` requests overlap, but
    that is implementation behaviour rather than a promise, and
    ``pyproject.toml`` pins only ``mcp>=2.1``. If it ever changed, this
    framework's concurrency guarantee would deliver nothing to an agent, and
    this test is what would say so.

    Passing a Server straight to Client is the SDK's documented in-memory
    transport, which it names as the testing path.
    """
    server = build_mcp_server(RENDEZVOUS, rendezvous_lifespan(), config={})

    async with Client(server) as agent:
        async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
            first, second = await asyncio.gather(
                agent.call_tool("meet", {}),
                agent.call_tool("meet", {}),
            )
        listed = await agent.call_tool("read_log", {})

    assert not first.is_error
    assert not second.is_error
    assert LogSnapshot.model_validate(listed.structured_content).entries == ARRIVALS_THEN_DEPARTURES


async def test_two_web_channel_interactions_are_in_flight_at_once(
    create_user: Callable[[], User],
) -> None:
    """The Web channel's request concurrency is NiceGUI's, and this pins it.

    ``pyproject.toml`` pins only ``nicegui>=3.16``. NiceGUI dispatches an async
    event handler as a background task, so a click does not hold the
    interaction and two of them overlap. The shape here is NiceGUI's documented
    one for simultaneous users: ``create_user()``, ``open``, ``find`` with an
    interaction, then ``should_see``.

    ``should_see`` is also the wait. It retries until the label changes and
    fails if it never does, so nothing in the fixture waits on the invocation.
    """
    lifespan = rendezvous_lifespan()

    async with page_runtime_for(RENDEZVOUS, lifespan, config={}) as pages:
        register_pages(RENDEZVOUS, pages)

        first = create_user()
        second = create_user()
        await first.open("/meeting-button")
        await second.open("/meeting-button")

        first.find("Meet").click()
        second.find("Meet").click()

        await first.should_see("met")
        await second.should_see("met")

        async with tool_runtime_for(RENDEZVOUS, lifespan, config={}) as tools:
            assert await logged(tools) == ARRIVALS_THEN_DEPARTURES
