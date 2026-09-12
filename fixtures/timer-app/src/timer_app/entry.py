"""How long this App's window has been open, on a Page and through a Tool.

Todo and Notes are the two Apps the framework's own tests are written
against. This is the third, and it exists for one reason: an App is reached at
an address of its own, and proving that two Apps get two addresses needs two
Apps with a Web channel. Notes declares no Pages on purpose, so it cannot be
the second one.

It requires nothing of its host, which is the other half of its job: a test
that installs it is asserting about Studio, not about what this App happens
to need. Its lifespan holds the one thing it knows -- when it opened -- so the
resource an App may hold is exercised here rather than only described.

Its `probe` Tool is the witness M17's isolation tests read: what Studio let
this process see, reported from inside it.
"""

import asyncio
import importlib.util
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from nicegui import ui
from pydantic import BaseModel

from vibepy_core import (
    AppConfig,
    AppDefinition,
    AppEntrypoint,
    Page,
    PageContext,
    PageDefinition,
    Tool,
    ToolContext,
    ToolDefinition,
)


class TimerConfig(AppConfig):
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


class Probe(BaseModel):
    module: str


class Probed(BaseModel):
    """What this process can see of its host: where it stands, what it imports."""

    cwd: str
    sys_path: list[str]
    importable: bool
    wrote: str


async def probe(_ctx: ToolContext[datetime], payload: Probe) -> Probed:
    """Report the process's working directory and import path, and write one relative file.

    Exists so that a test of Studio can read, from inside the running App, what
    Studio let it see. The file is what an App writes when it names a file and
    no folder.
    """
    wrote = Path("probe.txt")

    def _write() -> str:
        wrote.write_text("probed", encoding="utf-8")
        return str(wrote.resolve())

    resolved = await asyncio.to_thread(_write)
    return Probed(
        cwd=str(Path.cwd()),
        sys_path=list(sys.path),
        importable=importlib.util.find_spec(payload.module) is not None,
        wrote=resolved,
    )


async def home(ctx: PageContext) -> None:
    """The Page reaches its domain through a Tool, like any other."""
    since = Elapsed.model_validate(await ctx.tools.invoke("elapsed", {}))
    ui.label(f"open for {since.seconds:.0f}s")
    probed = Probed.model_validate(await ctx.tools.invoke("probe", {"module": "planted_module"}))
    ui.label(f"cwd={probed.cwd}")
    ui.label(f"importable={probed.importable}")
    ui.label(f"wrote={probed.wrote}")
    for entry in probed.sys_path:
        ui.label(f"path={entry}")


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
                read_only=True,
            ),
            handler=elapsed,
        ),
        Tool(
            definition=ToolDefinition(
                name="probe",
                description="Where this process stands and what it can import",
                input_model=Probe,
                output_model=Probed,
                read_only=True,
            ),
            handler=probe,
        ),
    ],
    pages=[
        Page(
            definition=PageDefinition(
                name="home", route="/home", title="Timer", tools=frozenset({"elapsed", "probe"})
            ),
            handler=home,
        )
    ],
)

APP: AppEntrypoint[datetime, TimerConfig] = AppEntrypoint(
    definition=TIMER_APP, lifespan=timer_lifespan
)
