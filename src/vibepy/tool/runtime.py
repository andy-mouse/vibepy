"""The single invocation path shared by every channel.

Input validation, the handler call and output validation belong together: input
validation is what proves a raw mapping has the handler's input type. They live
in the closure a Tool builds over its handler, so a Tool is addressable by one
uniform callable type regardless of the models it declares.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from vibepy.errors import ToolInputValidationError, ToolOutputValidationError
from vibepy.tool.model import ToolContext, ToolDefinition, ToolHandler

if TYPE_CHECKING:
    from vibepy.tool.registry import ToolRegistry

type BoundTool[DepsT] = Callable[[ToolContext[DepsT], Mapping[str, object]], Awaitable[BaseModel]]


class Tool[DepsT]:
    """A ToolDefinition paired with the handler that implements it, already bound.

    The class is generic in ``DepsT`` only, while ``__init__`` is generic in the
    declared models. A Tool therefore has one static type per App, which is what
    lets an AppDefinition hold a sequence of them: ``InputT`` appears covariantly
    in the declaration and contravariantly in the handler, so a Tool generic in it
    would be invariant and no common element type would exist.

    Binding happens here rather than in a registry because a declaration is not
    useful before it is callable, and the erasure has exactly one cause.

    The output is revalidated from its dump rather than accepted as-is, so a
    result built by ``model_construct`` or mutated after construction cannot pass
    unchecked. Output models must round-trip through ``model_dump(by_alias=True)``.
    """

    def __init__[InputT: BaseModel, OutputT: BaseModel](
        self,
        *,
        definition: ToolDefinition[InputT, OutputT],
        handler: ToolHandler[DepsT, InputT, OutputT],
    ) -> None:
        async def bound(ctx: ToolContext[DepsT], raw_input: Mapping[str, object]) -> BaseModel:
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

        self.definition: ToolDefinition[BaseModel, BaseModel] = definition
        self.bound: BoundTool[DepsT] = bound


class ToolRuntime[DepsT]:
    """Resolves a Tool by name, creates its ToolContext, and invokes it.

    ``dependencies`` is the application-scoped resource AppRuntime owns. The
    runtime holds it and puts it into every ToolContext it creates, so a channel
    never constructs a context and never sees AppRuntime.

    Concurrent invocations are permitted. Nothing here serializes them.
    """

    def __init__(
        self, *, app_id: str, registry: "ToolRegistry[DepsT]", dependencies: DepsT
    ) -> None:
        self._app_id = app_id
        self._registry = registry
        self._dependencies = dependencies

    async def invoke(self, name: str, raw_input: Mapping[str, object]) -> BaseModel:
        tool = self._registry.resolve(name)
        ctx = ToolContext(
            app_id=self._app_id,
            invocation_id=str(uuid4()),
            dependencies=self._dependencies,
        )
        return await tool.bound(ctx, raw_input)
