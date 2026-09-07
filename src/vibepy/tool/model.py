"""Declarations of the Tool model. These types carry no invocation behaviour."""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolContext:
    """Invocation-scoped context. Created by ToolRuntime, never by a channel."""

    app_id: str
    invocation_id: str


@dataclass(frozen=True)
class ToolDefinition[InputT: BaseModel, OutputT: BaseModel]:
    """Static declaration of a Tool. Both models are required."""

    name: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]


class ToolHandler[InputT: BaseModel, OutputT: BaseModel](Protocol):
    """The async operation behind a Tool.

    Parameters are positional-only so that an app author may name them freely.
    """

    def __call__(self, ctx: ToolContext, payload: InputT, /) -> Awaitable[OutputT]: ...


@dataclass(frozen=True)
class Tool[InputT: BaseModel, OutputT: BaseModel]:
    """A ToolDefinition paired with the handler that implements it."""

    definition: ToolDefinition[InputT, OutputT]
    handler: ToolHandler[InputT, OutputT]
