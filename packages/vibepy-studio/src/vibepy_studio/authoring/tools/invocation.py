"""Invoking one Tool of a project's App, in the project's own environment."""

import asyncio
import logging
from collections.abc import Sequence

from pydantic import TypeAdapter, ValidationError

from vibepy_core.app.config import environment_for
from vibepy_core.invoke import InvocationRequest
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.authoring.internals import locate, python
from vibepy_studio.authoring.models import (
    Invocation,
    InvokeRequest,
    environment_failed,
    from_report,
    project_not_found,
    uv_unavailable,
)
from vibepy_studio.internals import NotRunnable, StudioDeps, reported, run

logger = logging.getLogger(__name__)

_OUTPUT = TypeAdapter(dict[str, object])
"""The command writes one JSON object: the Tool's output model, dumped."""


async def invoke_tool(_ctx: ToolContext[StudioDeps], payload: InvokeRequest) -> Invocation:
    """Invoke one Tool once through the framework's own window, and return what it said."""
    project = await asyncio.to_thread(locate, payload.project)
    if project is None:
        return Invocation(diagnostic=project_not_found(payload.project, "holds no pyproject.toml"))
    request = InvocationRequest(input=payload.input).model_dump_json()
    try:
        completed = await run(
            [*python(project), "-m", "vibepy_core.invoke", payload.app, payload.tool],
            stdin=request,
            env=environment_for(payload.config),
        )
    except NotRunnable:
        return Invocation(diagnostic=uv_unavailable(project))
    if completed.returncode != 0:
        return Invocation(
            diagnostic=from_report(
                project,
                reported(completed.stderr),
                (completed.stdout + completed.stderr).strip(),
                app=payload.app,
                tool=payload.tool,
            )
        )
    try:
        return Invocation(output=_OUTPUT.validate_json(completed.stdout))
    except ValidationError as invalid:
        logger.debug("the child wrote something other than one object", exc_info=invalid)
        return Invocation(diagnostic=environment_failed(project, completed.stdout.strip()))


INVOCATION_TOOLS: Sequence[Tool[StudioDeps]] = [
    Tool(
        definition=ToolDefinition(
            name="invoke_tool",
            description=(
                "Invoke one Tool of an App a source project declares, once, "
                "in the project's own environment"
            ),
            input_model=InvokeRequest,
            output_model=Invocation,
        ),
        handler=invoke_tool,
    ),
]
