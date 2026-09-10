"""A servable App with nothing in it but a Page and the Tool it reaches.

A fixture, not a sample. `examples/` holds one App with a Web channel on
purpose -- `examples/notes` is Agent-only so that the extras split stays
provable -- and a test that needs a second one needs it to be uninteresting:
this declares no configuration, so a test that installs it asserts about the
Hub rather than about what this App happens to require.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from nicegui import ui
from pydantic import BaseModel

from vibepy_core.app import AppDefinition, AppEntrypoint
from vibepy_core.page import Page, PageContext, PageDefinition
from vibepy_core.tool import Tool, ToolContext, ToolDefinition


class NoConfig(BaseModel):
    """This App requires nothing of its host."""


class Greeting(BaseModel):
    said: str


@asynccontextmanager
async def second_lifespan(_config: NoConfig) -> AsyncGenerator[None]:
    """It holds no resource, and says so by yielding None."""
    yield None


async def greet(_ctx: ToolContext[None], _payload: NoConfig) -> Greeting:
    return Greeting(said="second-app")


async def home(ctx: PageContext) -> None:
    """The Page reaches its domain through a Tool, like any other."""
    said = Greeting.model_validate(await ctx.tools.invoke("greet", {}))
    ui.label(said.said)


SECOND_APP: AppDefinition[None, NoConfig] = AppDefinition(
    app_id="second-app",
    name="Second",
    version="0.0.0",
    config=NoConfig,
    tools=[
        Tool(
            definition=ToolDefinition(
                name="greet",
                description="Say this App's name",
                input_model=NoConfig,
                output_model=Greeting,
            ),
            handler=greet,
        )
    ],
    pages=[
        Page(
            definition=PageDefinition(name="home", route="/home", title="Home"),
            handler=home,
        )
    ],
)

APP: AppEntrypoint[None, NoConfig] = AppEntrypoint(definition=SECOND_APP, lifespan=second_lifespan)
