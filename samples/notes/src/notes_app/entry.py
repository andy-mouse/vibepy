"""A sample App with Tools and no Pages.

ADR-017 states that an App declaring no Pages has no Web channel and therefore no
runtime for the Hub to start, and is complete for an agent. This is that App.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import BaseModel

from vibepy.app import AppDefinition, AppEntrypoint, NoConfig
from vibepy.tool import Tool, ToolContext, ToolDefinition


class NoteInput(BaseModel):
    body: str


class Note(BaseModel):
    body: str
    length: int


@asynccontextmanager
async def notes_lifespan(_config: NoConfig) -> AsyncGenerator[None]:
    """The Notes App needs no resource, and says so by yielding None."""
    yield None


async def measure_note(_ctx: ToolContext[None], payload: NoteInput) -> Note:
    return Note(body=payload.body, length=len(payload.body))


NOTES_APP: AppDefinition[None, NoConfig] = AppDefinition(
    app_id="notes-app",
    name="Notes",
    version="0.1.0",
    config=NoConfig,
    tools=[
        Tool(
            definition=ToolDefinition(
                name="measure_note",
                description="Measure a note",
                input_model=NoteInput,
                output_model=Note,
            ),
            handler=measure_note,
        )
    ],
    pages=[],
)

APP: AppEntrypoint[None, NoConfig] = AppEntrypoint(definition=NOTES_APP, lifespan=notes_lifespan)
