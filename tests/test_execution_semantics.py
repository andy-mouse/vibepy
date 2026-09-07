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

``create_dependencies`` is the real factory, and the log is read back through a
Tool rather than by holding the resource, so the test observes app-scoped state
only through the App's public surface. ``tests/test_app_runtime.py`` observes
``id(ctx.dependencies)`` the same way.
"""

import asyncio

from pydantic import BaseModel

from vibepy.app import AppDefinition, AppRuntime
from vibepy.page import Page, PageContext, PageDefinition
from vibepy.tool import Tool, ToolContext, ToolDefinition

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


def build_app() -> AppRuntime[Rendezvous]:
    return AppRuntime(
        AppDefinition(
            app_id="rendezvous-app",
            name="Rendezvous",
            version="0.0.0",
            create_dependencies=Rendezvous,
            tools=[MEET, READ_LOG],
            pages=[
                Page(
                    definition=PageDefinition(name="meeting", route="/meeting", title="Meeting"),
                    handler=meeting_page,
                ),
            ],
        )
    )


async def logged(app: AppRuntime[Rendezvous]) -> list[str]:
    snapshot = await app.tool_runtime.invoke("read_log", {})
    assert isinstance(snapshot, LogSnapshot)
    return snapshot.entries


async def overlap() -> tuple[AppRuntime[Rendezvous], Meeting, Meeting]:
    """Invoke one App's Tool twice concurrently and return the App and both reports."""
    app = build_app()

    async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
        first, second = await asyncio.gather(
            app.tool_runtime.invoke("meet", {}),
            app.tool_runtime.invoke("meet", {}),
        )

    assert isinstance(first, Meeting)
    assert isinstance(second, Meeting)
    return app, first, second


async def test_two_invocations_are_in_flight_at_once() -> None:
    app, _first, _second = await overlap()

    assert await logged(app) == ARRIVALS_THEN_DEPARTURES


async def test_concurrent_invocations_receive_independent_contexts() -> None:
    _app, first, second = await overlap()

    assert first.invocation_id != second.invocation_id


async def test_concurrent_invocations_share_app_scoped_dependencies() -> None:
    _app, first, second = await overlap()

    assert first.dependency_id == second.dependency_id


async def test_two_page_renders_are_in_flight_at_once() -> None:
    """PageRuntime's docstring claims it does not serialize renders; this holds it to that."""
    app = build_app()

    async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
        await asyncio.gather(
            app.page_runtime.render("meeting"),
            app.page_runtime.render("meeting"),
        )

    assert await logged(app) == ARRIVALS_THEN_DEPARTURES
