"""Declarations of the Tool model. These types carry no invocation behaviour."""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolContext[DepsT]:
    """Invocation-scoped context. Created by ToolRuntime, never by a channel.

    ``dependencies`` is the Plugin's own application-scoped resource. The
    channel's running window acquires it once and every invocation inside that
    window receives that same value, typed by the plugin itself.
    """

    plugin_id: str
    invocation_id: str
    dependencies: DepsT


@dataclass(frozen=True)
class ToolDefinition[InputT: BaseModel, OutputT: BaseModel]:
    """Static declaration of a Tool. Both models are required."""

    name: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]


class ToolHandler[DepsT, InputT: BaseModel, OutputT: BaseModel](Protocol):
    """The async operation behind a Tool.

    Parameters are positional-only so that an app author may name them freely.
    """

    def __call__(self, ctx: ToolContext[DepsT], payload: InputT, /) -> Awaitable[OutputT]: ...
