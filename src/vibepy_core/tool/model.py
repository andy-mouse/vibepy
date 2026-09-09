"""Declarations of the Tool model. These types carry no invocation behaviour."""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, JsonValue


@dataclass(frozen=True)
class ToolContext[DepsT]:
    """Invocation-scoped context. Created by ToolRuntime, never by a channel.

    ``dependencies`` is the App's own application-scoped resource. The
    channel's running window acquires it once and every invocation inside that
    window receives that same value, typed by the app itself.
    """

    app_id: str
    invocation_id: str
    dependencies: DepsT


@dataclass(frozen=True)
class ToolDefinition[InputT: BaseModel, OutputT: BaseModel]:
    """Static declaration of a Tool. Both models are required.

    The declaration answers with its own JSON Schemas, so every surface that
    publishes them publishes the same ones. Two surfaces do — the Agent
    channel's projection and a package's self-description — and ADR-007
    requires that a published schema and the value it describes cannot diverge.
    Held here rather than at each surface because a rule written twice is a rule
    that can be changed once.
    """

    name: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]

    def input_schema(self) -> dict[str, JsonValue]:
        """What an argument mapping is validated against.

        The validation schema: an input model is accepted, so a member it only
        produces is not part of what a caller may send.
        """
        return self.input_model.model_json_schema()

    def output_schema(self) -> dict[str, JsonValue]:
        """What a result is serialized to.

        The serialization schema, because a channel sends
        ``model_dump(by_alias=True, mode="json")``. A computed member and a
        serialization alias both appear here and in that payload, and in
        neither the validation schema nor the arguments a caller sends.

        A fresh mutable mapping each call, which is what an SDK that types this
        field as a plain dict expects; `JsonValue` rather than `Any`, which is
        what this framework's own description surface expects.
        """
        return self.output_model.model_json_schema(mode="serialization")


class ToolHandler[DepsT, InputT: BaseModel, OutputT: BaseModel](Protocol):
    """The async operation behind a Tool.

    Parameters are positional-only so that an app author may name them freely.
    """

    def __call__(self, ctx: ToolContext[DepsT], payload: InputT, /) -> Awaitable[OutputT]: ...
