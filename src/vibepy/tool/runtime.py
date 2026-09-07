"""The single invocation path shared by every channel.

``docs/architecture/tool-model.md`` assigns input validation, the handler call and
output validation to ToolRuntime, so binding lives here rather than in the
registry. See docs/decisions/ADR-008-tools-are-bound-at-registration.md.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from vibepy.errors import ToolInputValidationError, ToolOutputValidationError
from vibepy.tool.model import Tool, ToolContext

if TYPE_CHECKING:
    from vibepy.tool.registry import ToolRegistry

type BoundTool = Callable[[ToolContext, Mapping[str, object]], Awaitable[BaseModel]]


def bind[InputT: BaseModel, OutputT: BaseModel](tool: Tool[InputT, OutputT]) -> BoundTool:
    """Close over a typed Tool and return a callable addressable by name.

    A closure rather than a wrapper class: a method would have to prove again
    that the value it received is the handler's input type, which cannot be
    expressed. Input validation, the handler call and output validation happen
    together because input validation is what proves the raw mapping has the
    handler's input type.

    The output is revalidated from its dump rather than accepted as-is, so that
    a result built by ``model_construct`` or mutated after construction cannot
    pass unchecked. Output models must therefore round-trip through
    ``model_dump(by_alias=True)``. See
    docs/decisions/ADR-007-framework-guarantees-tool-output.md.
    """
    definition = tool.definition
    handler = tool.handler

    async def bound(ctx: ToolContext, raw_input: Mapping[str, object]) -> BaseModel:
        try:
            payload = definition.input_model.model_validate(raw_input)
        except ValidationError as error:
            raise ToolInputValidationError(definition.name) from error

        result = await handler(ctx, payload)
        dumped = result.model_dump(by_alias=True, warnings=False)

        try:
            return definition.output_model.model_validate(dumped)
        except ValidationError as error:
            raise ToolOutputValidationError(definition.name) from error

    return bound


class ToolRuntime:
    """Resolves a Tool by name, creates its ToolContext, and invokes it.

    Concurrent invocations are permitted. Nothing here serializes them.
    """

    def __init__(self, *, app_id: str, registry: "ToolRegistry") -> None:
        self._app_id = app_id
        self._registry = registry

    async def invoke(self, name: str, raw_input: Mapping[str, object]) -> BaseModel:
        bound = self._registry.resolve(name)
        ctx = ToolContext(app_id=self._app_id, invocation_id=str(uuid4()))
        return await bound(ctx, raw_input)
