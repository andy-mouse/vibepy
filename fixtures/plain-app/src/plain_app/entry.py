"""The smallest thing the Hub can install, and nothing more.

A fixture, not a sample. Most of what the Hub does -- give an App an
environment of its own, file it under its canonical name, hold what it was
configured with, say what it can no longer describe -- is the same whatever the
App is, and a test of that should not install a Web channel to see it. This
App depends on `vibepy-core` alone: no extra, and so no NiceGUI, which is what
makes installing it cost a second rather than three.

It declares one required value and one secret, because what the Hub holds and
what it hands back is told apart by exactly that. It declares no Pages, so a
test that needs a Web channel reaches for `fixtures/second-app` or an example
instead.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import BaseModel, SecretStr

from vibepy_core.app import AppDefinition, AppEntrypoint
from vibepy_core.tool import Tool, ToolContext, ToolDefinition


class PlainConfig(BaseModel):
    """One value it will hand back and one it will not."""

    data_path: str
    data_key: SecretStr


class Empty(BaseModel):
    """This Tool asks for nothing."""


class Named(BaseModel):
    called: str


@asynccontextmanager
async def plain_lifespan(_config: PlainConfig) -> AsyncGenerator[None]:
    """It holds no resource, and says so by yielding None."""
    yield None


async def name_itself(_ctx: ToolContext[None], _payload: Empty) -> Named:
    return Named(called="plain-app")


PLAIN_APP: AppDefinition[None, PlainConfig] = AppDefinition(
    app_id="plain-app",
    name="Plain",
    version="0.0.0",
    config=PlainConfig,
    tools=[
        Tool(
            definition=ToolDefinition(
                name="name_itself",
                description="Say this App's name",
                input_model=Empty,
                output_model=Named,
            ),
            handler=name_itself,
        )
    ],
    pages=[],
)

APP: AppEntrypoint[None, PlainConfig] = AppEntrypoint(definition=PLAIN_APP, lifespan=plain_lifespan)
