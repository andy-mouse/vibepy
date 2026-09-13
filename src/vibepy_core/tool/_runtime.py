"""The single invocation path shared by every channel.

Input validation, the handler call and output validation belong together: input
validation is what proves a raw mapping has the handler's input type. They live
in the closure a Tool builds over its handler, so a Tool is addressable by one
uniform callable type regardless of the models it declares.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from vibepy_core.channel import Channel
from vibepy_core.errors import (
    ErrorCategory,
    ErrorInfo,
    ToolInputValidationError,
    ToolOutputValidationError,
    to_error_info,
)
from vibepy_core.principal import Principal
from vibepy_core.tool._model import ToolContext, ToolDefinition, ToolHandler
from vibepy_core.tool._policy import AuthorizationRequest, ToolPolicy, default_policy
from vibepy_core.tool._record import InvocationRecord

if TYPE_CHECKING:
    from vibepy_core.tool._registry import ToolRegistry

logger = logging.getLogger(__name__)

type BoundTool[DepsT] = Callable[[ToolContext[DepsT], Mapping[str, object]], Awaitable[BaseModel]]


class Tool[DepsT]:
    """A ToolDefinition paired with the handler that implements it, already bound.

    The class is generic in ``DepsT`` only, while ``__init__`` is generic in the
    declared models. A Tool therefore has one static type per App, which is what
    lets an AppDefinition hold a sequence of them: ``InputT`` appears covariantly
    in the declaration and contravariantly in the handler, so a Tool generic in it
    would be invariant and no common element type would exist.

    Binding happens here rather than in a registry because a declaration is not
    useful before it is callable, and the erasure has exactly one cause. Both
    attributes are `Final`: a Tool is bound once and never rebound, which is what
    makes it contravariant in ``DepsT`` (`docs/architecture/tool-model.md`, Tool).

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
        """Bind `handler` to `definition` into one invocable callable."""

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

        self.definition: Final[ToolDefinition[BaseModel, BaseModel]] = definition
        self.bound: Final[BoundTool[DepsT]] = bound


class ToolRuntime[DepsT]:
    """Resolves a Tool by name, creates its ToolContext, invokes it, and writes it down.

    ``dependencies`` is the application-scoped resource the channel's window
    acquired. The runtime holds it and puts it into every ToolContext it creates,
    so a channel never constructs a context.

    ``channel`` is the window's, fixed when it opened; the principal is the
    call's, given per invocation. Authorization runs from the two and the
    declaration before input is validated, so what a caller may not invoke it
    also may not probe.

    Every invocation ends with one `InvocationRecord` on this module's logger,
    whatever way it ends. The id exists before anything can refuse, so a refusal
    is recorded with one. Nothing is translated: the record is written on the way
    out and the exception propagates as raised. This is the only writer.

    Concurrent invocations are permitted. Nothing here serializes them.
    """

    def __init__(
        self,
        *,
        app_id: str,
        registry: "ToolRegistry[DepsT]",
        dependencies: DepsT,
        channel: Channel,
        policy: ToolPolicy | None = None,
    ) -> None:
        """Hold what every invocation uses, this window's `channel` and `policy` included."""
        self._app_id = app_id
        self._registry = registry
        self._dependencies = dependencies
        self._channel = channel
        self._policy = policy

    async def invoke(
        self, name: str, raw_input: Mapping[str, object], /, *, principal: Principal
    ) -> BaseModel:
        """Authorize `principal` for `name`, invoke it with `raw_input`, record the ending.

        The framework's policy always runs, and the App's runs after it: an App
        may refuse further, never admit what the declaration refuses.

        A cancellation is recorded and re-raised, as asyncio requires of anything
        that catches it. The `except` arm below catches `Exception` and
        `asyncio.CancelledError` and nothing else: an exception group
        (`BaseExceptionGroup`) carrying a cancellation is not one exception and
        so is not caught, and `KeyboardInterrupt` and `SystemExit` are not caught
        either, because they end the process, and the process reports its own
        ending (ADR-030). None of these leave a record.

        Raises:
            ToolNotFoundError: no Tool is registered under `name`.
            ToolForbiddenError: `principal` may not invoke this Tool here.
            ToolInputValidationError: `raw_input` does not satisfy the Tool's
                input model.
            ToolOutputValidationError: the Tool returned what its own output
                model rejects.
        """
        invocation_id = str(uuid4())
        started_at = datetime.now(UTC)
        started = perf_counter()
        try:
            tool = self._registry.resolve(name)
            request = AuthorizationRequest(
                definition=tool.definition, principal=principal, channel=self._channel
            )
            default_policy.authorize(request)
            if self._policy is not None:
                self._policy.authorize(request)
            ctx = ToolContext(
                app_id=self._app_id,
                invocation_id=invocation_id,
                dependencies=self._dependencies,
                principal=principal,
                channel=self._channel,
            )
            result = await tool.bound(ctx, raw_input)
        except (asyncio.CancelledError, Exception) as error:
            self._record(
                invocation_id, name, principal, started_at, started, error=to_error_info(error)
            )
            raise
        self._record(invocation_id, name, principal, started_at, started, error=None)
        return result

    def _record(
        self,
        invocation_id: str,
        tool: str,
        principal: Principal,
        started_at: datetime,
        started: float,
        /,
        *,
        error: ErrorInfo | None,
    ) -> None:
        """Write the one record of an invocation that has just ended.

        Called after a successful return and, from the `except` arm, after a
        failure. `logging` tests `exc_info` for truthiness before deciding
        whether to attach a traceback, but stores whatever value it is given
        verbatim on the `LogRecord`: passing `False` leaves `log.exc_info` as
        `False`, not `None`, so `with_traceback` is narrowed to `None` when it
        is falsy. The traceback follows an `execution` failure only: that
        category alone is a defect in code a developer must find, and inside
        the `except` arm `exc_info=True` names the exception being handled.
        """
        record = InvocationRecord(
            invocation_id=invocation_id,
            app_id=self._app_id,
            tool=tool,
            channel=self._channel,
            principal=principal,
            started_at=started_at,
            duration_seconds=perf_counter() - started,
            error=error,
        )
        with_traceback = error is not None and error.category is ErrorCategory.EXECUTION
        logger.info(record.model_dump_json(), exc_info=with_traceback or None)
