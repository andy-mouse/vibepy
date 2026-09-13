"""Declarations of the Tool model. These types carry no invocation behaviour."""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, JsonValue

from vibepy_core.channel import Channel
from vibepy_core.errors import ToolChannelsEmptyError
from vibepy_core.principal import Principal


class InvocationRequest(BaseModel):
    """What one invocation carries across a process boundary: the Tool's `input`.

    It lives with the Tool vocabulary it is made of rather than with the command
    that transports it, per `docs/architecture/app-model.md` "The import surface".
    Any other key is refused rather than ignored, so a request written for a
    channel the reader does not have fails and says so.
    """

    model_config = ConfigDict(extra="forbid")

    input: dict[str, JsonValue] = {}


@dataclass(frozen=True, kw_only=True)
class ToolContext[DepsT]:
    """Invocation-scoped context. Created by ToolRuntime, never by a channel.

    ``dependencies`` is the App's own application-scoped resource. The
    channel's running window acquires it once and every invocation inside that
    window receives that same value, typed by the app itself.

    ``principal`` and ``channel`` are who this invocation is for and where it
    came through, as the runtime authorized it. A handler reads them; it does
    not decide with them, because the decision was already taken.
    """

    app_id: str
    invocation_id: str
    dependencies: DepsT
    principal: Principal
    channel: Channel


@dataclass(frozen=True, kw_only=True)
class ToolDefinition[InputT: BaseModel, OutputT: BaseModel]:
    """Static declaration of a Tool. Both models are required, and so is `read_only`."""

    name: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]
    read_only: bool
    channels: frozenset[Channel] = frozenset(Channel)
    required_roles: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """Refuse a declaration exposed through no channel.

        Raises:
            ToolChannelsEmptyError: `channels` is empty.
        """
        if not self.channels:
            raise ToolChannelsEmptyError(self.name)

    def input_schema(self) -> dict[str, JsonValue]:
        """Return what an argument mapping is validated against.

        The validation schema: an input model is accepted, so a member it only
        produces is not part of what a caller may send.
        """
        return self.input_model.model_json_schema()

    def output_schema(self) -> dict[str, JsonValue]:
        """Return what a result is serialized to.

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

    def __call__(self, ctx: ToolContext[DepsT], payload: InputT, /) -> Awaitable[OutputT]:
        """Handle one invocation and return its result."""
        ...
