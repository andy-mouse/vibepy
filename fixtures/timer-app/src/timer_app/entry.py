"""How long this App's window has been open, on a Page and through a Tool.

Todo and Notes are the two Apps the framework's own tests are written
against. This is the third, and it exists for one reason: an App is reached at
an address of its own, and proving that two Apps get two addresses needs two
Apps with a Web channel. Notes declares no Pages on purpose, so it cannot be
the second one.

It requires nothing of its host, which is the other half of its job: a test
that installs it is asserting about the Hub, not about what this App happens
to need. Its lifespan holds the one thing it knows -- when it opened -- so the
resource an App may hold is exercised here rather than only described.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from nicegui import ui
from pydantic import BaseModel

from vibepy_core import (
    AppDefinition,
    AppEntrypoint,
    Page,
    PageContext,
    PageDefinition,
    Tool,
    ToolContext,
    ToolDefinition,
)


class TimerConfig(BaseModel):
    """This App requires nothing of its host."""


class Opened(BaseModel):
    """Nothing is asked to read the clock."""


class Elapsed(BaseModel):
    seconds: float


@asynccontextmanager
async def timer_lifespan(_config: TimerConfig) -> AsyncGenerator[datetime]:
    """The window's own start, held for as long as the window is open."""
    yield datetime.now(UTC)


async def elapsed(ctx: ToolContext[datetime], _payload: Opened) -> Elapsed:
    """How long ago this window opened, in seconds."""
    return Elapsed(seconds=(datetime.now(UTC) - ctx.dependencies).total_seconds())


async def home(ctx: PageContext) -> None:
    """The Page reaches its domain through a Tool, like any other."""
    since = Elapsed.model_validate(await ctx.tools.invoke("elapsed", {}))
    ui.label(f"open for {since.seconds:.0f}s")


TIMER_APP: AppDefinition[datetime, TimerConfig] = AppDefinition(
    app_id="timer-app",
    name="Timer",
    version="0.0.0",
    config=TimerConfig,
    tools=[
        Tool(
            definition=ToolDefinition(
                name="elapsed",
                description="How long this window has been open",
                input_model=Opened,
                output_model=Elapsed,
            ),
            handler=elapsed,
        )
    ],
    pages=[
        Page(
            definition=PageDefinition(name="home", route="/home", title="Timer"),
            handler=home,
        )
    ],
)

APP: AppEntrypoint[datetime, TimerConfig] = AppEntrypoint(
    definition=TIMER_APP, lifespan=timer_lifespan
)
