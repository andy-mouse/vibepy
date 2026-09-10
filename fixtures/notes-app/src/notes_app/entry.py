"""An App with Tools and no Pages, which is a whole App.

ADR-017 states that an App declaring no Pages has no Web channel and therefore no
runtime for the Hub to start, and is complete for an agent. This is that App, and
ADR-025 cites it as the evidence that such an App installs no Web technology --
which is also what makes it the lightest thing the suite can install.

It declares a secret, which is what an agent-facing App usually needs of its
host, and what lets a Host show that a secret is declared by type rather than by
storage. Most tests that need an App installed are handed this one.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import BaseModel, SecretStr

from vibepy_core import AppDefinition, AppEntrypoint, Tool, ToolContext, ToolDefinition


class NotesConfig(BaseModel):
    """What the Notes App requires of its host."""

    api_base_url: str
    api_token: SecretStr


class NoteInput(BaseModel):
    body: str


class Note(BaseModel):
    body: str
    length: int


@asynccontextmanager
async def notes_lifespan(_config: NotesConfig) -> AsyncGenerator[None]:
    """The Notes App needs no resource, and says so by yielding None."""
    yield None


async def measure_note(_ctx: ToolContext[None], payload: NoteInput) -> Note:
    return Note(body=payload.body, length=len(payload.body))


NOTES_APP: AppDefinition[None, NotesConfig] = AppDefinition(
    app_id="notes-app",
    name="Notes",
    version="0.1.0",
    config=NotesConfig,
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

APP: AppEntrypoint[None, NotesConfig] = AppEntrypoint(definition=NOTES_APP, lifespan=notes_lifespan)
