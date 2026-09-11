"""Invoking one Tool of a project's App, in the project's own environment."""

import asyncio
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from vibepy_core import ErrorCategory
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.authoring.internals import locate, python
from vibepy_studio.authoring.models import Invocation, InvokeRequest, diagnostic_of
from vibepy_studio.authoring.tools.inspection import uv_unavailable
from vibepy_studio.internals import NotRunnable, StudioDeps, reported, run
from vibepy_studio.models import Diagnostic

logger = logging.getLogger(__name__)

_OUTPUT = TypeAdapter(dict[str, object])
"""The command writes one JSON object: the Tool's output model, dumped."""


def _environment_failed(project: Path, output: str, /) -> Diagnostic:
    return Diagnostic(
        code="authoring.environment_failed",
        category=ErrorCategory.EXECUTION,
        message=output,
        details={"project": str(project)},
    )


async def invoke_tool(_ctx: ToolContext[StudioDeps], payload: InvokeRequest) -> Invocation:
    """Invoke one Tool once through the framework's own window, and return what it said."""
    project = await asyncio.to_thread(locate, payload.project)
    if project is None:
        return Invocation(
            diagnostic=Diagnostic(
                code="authoring.project_not_found",
                category=ErrorCategory.CALLER,
                message=f"{payload.project} holds no pyproject.toml",
                details={"project": str(payload.project)},
            )
        )
    request = json.dumps({"config": payload.config, "input": payload.input})
    try:
        completed = await run(
            [*python(project), "-m", "vibepy_core.invoke", payload.app, payload.tool], stdin=request
        )
    except NotRunnable:
        return Invocation(diagnostic=uv_unavailable(project))
    if completed.returncode != 0:
        report = reported(completed.stderr)
        if report is not None:
            return Invocation(
                diagnostic=diagnostic_of(
                    report, project=str(project), app=payload.app, tool=payload.tool
                )
            )
        return Invocation(
            diagnostic=_environment_failed(project, (completed.stdout + completed.stderr).strip())
        )
    try:
        return Invocation(output=_OUTPUT.validate_json(completed.stdout))
    except ValidationError as invalid:
        logger.debug("the child wrote something other than one object", exc_info=invalid)
        return Invocation(diagnostic=_environment_failed(project, completed.stdout.strip()))


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
