"""Holding a source project to what the framework requires of an App."""

import logging
from collections.abc import Sequence

from vibepy_core.channel import Channel
from vibepy_core.errors import ErrorInfo
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.authoring.internals import (
    TypecheckFailed,
    declared_name,
    locate,
    python,
    typecheck,
)
from vibepy_studio.authoring.models import (
    AppValidation,
    Diagnostic,
    Severity,
    ValidateRequest,
    environment_failed,
    project_not_found,
    type_error,
    uv_unavailable,
    validation,
)
from vibepy_studio.internals import DescribeFailed, NotRunnable, describe
from vibepy_studio.models import diagnostic_of

logger = logging.getLogger(__name__)


def _error(info: ErrorInfo, /) -> Diagnostic:
    return Diagnostic(severity=Severity.ERROR, error=info)


async def validate_app(_ctx: ToolContext[object], payload: ValidateRequest) -> AppValidation:
    """Report every declaration violation and every type diagnostic of a source project.

    Two authorities, run independently in the project's environment: the
    framework's own `describe`, whose failure path is the declaration rules, and
    pyright, whose diagnostics are the typed contracts. Each finding is one
    `Diagnostic`; the project conforms when none is an error.
    """
    project = await locate(payload.project)
    if project is None:
        return validation([_error(project_not_found(payload.project, "holds no pyproject.toml"))])
    if await declared_name(project) is None:
        return validation([_error(project_not_found(project, "declares no [project] name"))])

    found: list[Diagnostic] = []
    try:
        await describe(python(project))
    except NotRunnable:
        return validation([_error(uv_unavailable(project))])
    except DescribeFailed as failed:
        members = [info for info in failed.reports if info.code != "app.declaration_invalid"]
        if members:
            found.extend(_error(diagnostic_of(info, project=str(project))) for info in members)
        else:
            found.append(_error(environment_failed(project, failed.output)))

    try:
        for entry in await typecheck(project):
            found.append(
                Diagnostic(
                    severity=entry.severity,
                    error=type_error(
                        project,
                        file=entry.file,
                        line=entry.range.start.line + 1,
                        rule=entry.rule,
                        message=entry.message,
                    ),
                )
            )
    except NotRunnable:
        found.append(_error(uv_unavailable(project)))
    except TypecheckFailed as failed:
        found.append(_error(environment_failed(project, failed.output)))
    return validation(found)


VALIDATION_TOOLS: Sequence[Tool[object]] = [
    Tool(
        definition=ToolDefinition(
            name="validate_app",
            description=(
                "Hold a source project to the framework's declaration rules and its typed "
                "contracts, in the project's own environment"
            ),
            input_model=ValidateRequest,
            output_model=AppValidation,
            read_only=True,
            channels=frozenset({Channel.AGENT}),
        ),
        handler=validate_app,
    ),
]
